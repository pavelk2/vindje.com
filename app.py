#!/usr/bin/env python3
"""
Robin-Bobin — smart search for Marktplaats: describe what you want in
plain language, get only the listings that actually match.

How it works (single file, zero dependencies, Python 3.8+):
  1. An LLM (via OpenRouter, Claude Haiku 4.5 by default) turns your wish
     into a structured Marktplaats search (Dutch keywords, price range,
     search radius).
  2. We query Marktplaats' own search API.
  3. The LLM reads every result and keeps only the ones that really
     match your requirements (size, features, condition, ...).

Run:
  OPENROUTER_API_KEY=sk-or-... python3 app.py
  open http://localhost:8000

Get a key at https://openrouter.ai/keys and add credits — the default
model (Claude Haiku 4.5) is paid, not one of OpenRouter's free models.
Without a key the app still works as a plain Marktplaats search,
just without the smart parsing/filtering.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------- LLM (OpenRouter)

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Models to try, in order (first is the primary paid model; the rest are
# fallbacks used only if it errors or rate-limits). Override with
# OPENROUTER_MODEL (comma-separated).
MODELS = [
    m.strip()
    for m in os.environ.get(
        "OPENROUTER_MODEL",
        "anthropic/claude-haiku-4.5,"
        "openrouter/free",
    ).split(",")
    if m.strip()
]


def llm(messages, max_tokens=2000):
    """Call the first model that answers. Returns text or raises."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    last_err = None
    for model in MODELS:
        # Ask for low reasoning effort to keep searches snappy. If a model
        # rejects that parameter, retry without it.
        for extra in ({"reasoning": {"effort": "low"}}, {}):
            payload = {"model": model, "messages": messages,
                       "max_tokens": max_tokens, "temperature": 0, **extra}
            req = urllib.request.Request(
                OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + OPENROUTER_API_KEY,
                    "HTTP-Referer": "https://github.com/pavelk2/marktplaats",
                    "X-Title": "Robin-Bobin",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode())
                text = data["choices"][0]["message"]["content"]
                if text and text.strip():
                    return text
                last_err = RuntimeError(f"{model}: empty response")
                break  # empty answer won't improve without the reasoning param
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code != 400:
                    break  # rate-limited/unavailable -> next model
            except Exception as e:
                last_err = e
                break
    raise RuntimeError(f"All models failed, last error: {last_err}")


def llm_json(messages, max_tokens=2000):
    """llm() + tolerant JSON extraction (models love code fences)."""
    text = llm(messages, max_tokens=max_tokens)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON in model response: " + text[:200])
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------- Step 1: parse the wish

PARSE_PROMPT = """You convert a buyer's wish into a Marktplaats (Dutch classifieds) search.
The wish may be in any language. Reply with ONLY a JSON object:

{
  "search_terms": "2-4 Dutch keywords a seller would use in a listing title",
  "price_min_euro": null or number,
  "price_max_euro": null or number,
  "distance_meters": null or number (if the buyer limits distance/travel time; assume driving = 50 km/h, cycling = 15 km/h, walking = 5 km/h),
  "requirements": ["each concrete requirement the buyer stated, in English, one per item"]
}

Rules:
- search_terms must be generic enough to find candidates (e.g. "kledingkast hout", not a full sentence). No commas.
- requirements capture everything checkable from a listing's text: dimensions, materials, features, condition, colors...
- Do NOT put price or distance into requirements; they go in their own fields."""


def parse_wish(wish):
    return llm_json(
        [
            {"role": "system", "content": PARSE_PROMPT},
            {"role": "user", "content": wish},
        ],
        max_tokens=2000,
    )


# ---------------------------------------------------------------- Step 2: search Marktplaats

# Radii the Marktplaats UI actually supports.
ALLOWED_RADII = [1000, 2000, 3000, 5000, 10000, 15000, 25000, 50000, 75000, 100000]


def snap_radius(meters):
    return min(ALLOWED_RADII, key=lambda r: abs(r - meters))


def search_marktplaats(terms, postcode=None, distance_meters=None,
                       price_min_euro=None, price_max_euro=None, limit=60):
    params = [
        ("query", terms),
        ("limit", str(limit)),
        ("offset", "0"),
        ("searchInTitleAndDescription", "true"),
    ]
    if postcode and distance_meters:
        params.append(("postcode", postcode.replace(" ", "").upper()))
        params.append(("distanceMeters", str(snap_radius(int(distance_meters)))))
    if price_min_euro is not None or price_max_euro is not None:
        lo = int((price_min_euro or 0) * 100)
        hi = int(price_max_euro * 100) if price_max_euro is not None else ""
        params.append(("attributeRanges[]", f"PriceCents:{lo}:{hi}"))
    url = "https://www.marktplaats.nl/lrp/api/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    listings = []
    for raw in data.get("listings", []):
        price = format_price(raw.get("priceInfo") or {})
        loc = raw.get("location") or {}
        attrs = []
        for a in (raw.get("extendedAttributes") or raw.get("attributes") or []):
            if a.get("value"):
                attrs.append(f"{a['key']}: {a['value']}")
        image = ""
        pics = raw.get("pictures") or []
        if pics:
            image = pics[0].get("mediumUrl") or pics[0].get("largeUrl") or ""
        elif raw.get("imageUrls"):
            image = "https:" + raw["imageUrls"][0]
        dist = loc.get("distanceMeters", -1000)
        listings.append(
            {
                "id": raw.get("itemId"),
                "title": raw.get("title", ""),
                "description": (raw.get("categorySpecificDescription")
                                or raw.get("description") or ""),
                "price": price,
                "city": loc.get("cityName", ""),
                "distance_km": round(dist / 1000, 1) if dist and dist > 0 else None,
                "attributes": attrs,
                "image": image,
                "url": "https://www.marktplaats.nl" + raw.get("vipUrl", ""),
            }
        )
    return listings, data.get("totalResultCount", len(listings))


def format_price(price_info):
    cents = price_info.get("priceCents", 0)
    ptype = price_info.get("priceType", "")
    if cents:
        euros = f"€{cents / 100:,.0f}".replace(",", ".")
        return euros + (" (bid from)" if "BID" in ptype else "")
    return {
        "FREE": "Free", "FAST_BID": "Bidding", "MIN_BID": "Bidding",
        "NOTK": "Negotiable", "ON_REQUEST": "On request", "RESERVED": "Reserved",
        "SEE_DESCRIPTION": "See description", "EXCHANGE": "Exchange",
    }.get(ptype, ptype or "?")


# ---------------------------------------------------------------- Step 3: AI-filter results

FILTER_PROMPT = """You are filtering Dutch classifieds listings for a buyer.
Buyer's requirements:
%s

Below are numbered listings (title / description / attributes, in Dutch).
Keep a listing only if it plausibly satisfies ALL requirements, or if the text
doesn't contradict them and the item is clearly the right kind of thing.
Reject anything that is the wrong kind of item, a service/ad, or contradicts a requirement.

Reply with ONLY JSON: {"matches": [{"n": <listing number>, "why": "<max 12 words, English>"}]}"""


FILTER_CHUNK = 15  # listings per LLM call; chunks are checked concurrently


def _filter_chunk(requirements, listings, base):
    lines = []
    for i, l in enumerate(listings):
        desc = str(l.get("description") or "")[:300]
        attrs = "; ".join(str(a) for a in (l.get("attributes") or [])[:8])
        lines.append(f"[{base + i}] {l.get('title', '')} | {desc} | {attrs}")
    result = llm_json(
        [
            {"role": "system", "content": FILTER_PROMPT % "\n".join("- " + r for r in requirements)},
            {"role": "user", "content": "\n".join(lines)},
        ],
        max_tokens=4000,
    )
    matches = {}
    for m in result.get("matches", []):
        try:
            n = int(m["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if base <= n < base + len(listings):
            matches[n] = str(m.get("why", ""))
    return matches


def filter_listings(requirements, listings):
    """Returns (matches dict, note or None). Raises only if every chunk fails."""
    if not requirements or not listings:
        return None, None
    chunks = [(i, listings[i : i + FILTER_CHUNK])
              for i in range(0, len(listings), FILTER_CHUNK)]
    matches, failed = {}, []
    with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as ex:
        futures = {ex.submit(_filter_chunk, requirements, chunk, base): (base, chunk)
                   for base, chunk in chunks}
        for fut in as_completed(futures):
            base, chunk = futures[fut]
            try:
                matches.update(fut.result())
            except Exception:
                failed.append((base, chunk))
    if failed and not matches and len(failed) == len(chunks):
        raise RuntimeError("all filter batches failed")
    note = None
    if failed:
        # keep un-checked listings rather than silently dropping them
        for base, chunk in failed:
            for i in range(len(chunk)):
                matches.setdefault(base + i, "")
        note = (f"AI check failed for {sum(len(c) for _, c in failed)} of "
                f"{len(listings)} listings; those are shown unfiltered.")
    return matches, note


# ---------------------------------------------------------------- pipeline

_UNSET = object()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def interpret(wish):
    """Phase 1: parse the wish with the LLM. Returns (parsed_or_None, notes)."""
    notes = []
    parsed = None
    if OPENROUTER_API_KEY:
        try:
            parsed = parse_wish(wish)
        except Exception as e:
            notes.append(f"AI query parsing failed ({e}); using your text as-is.")
    else:
        notes.append("OPENROUTER_API_KEY not set — running as a plain search "
                     "without AI parsing/filtering.")
    return parsed, notes


def search_params(parsed, wish, postcode):
    """Turn a parsed wish (or None) into Marktplaats search parameters."""
    notes = []
    if isinstance(parsed, dict):
        terms = parsed.get("search_terms") or wish
        distance = _num(parsed.get("distance_meters"))
        price_min = _num(parsed.get("price_min_euro"))
        price_max = _num(parsed.get("price_max_euro"))
        requirements = parsed.get("requirements") or []
    else:
        terms, distance, price_min, price_max, requirements = wish, None, None, None, []
    if distance and not postcode:
        notes.append("Your wish limits distance but no postcode was given — "
                     "add your postcode to enable the radius filter.")
        distance = None
    return terms, distance, price_min, price_max, requirements, notes


def smart_search(wish, postcode, parsed=_UNSET, notes=None):
    """Phase 2: search Marktplaats and AI-filter. Runs phase 1 first unless a
    pre-parsed result (possibly None) is handed in."""
    if parsed is _UNSET:
        parsed, notes = interpret(wish)
    notes = list(notes or [])
    if not isinstance(parsed, dict):
        parsed = None

    terms, distance, price_min, price_max, requirements, pnotes = \
        search_params(parsed, wish, postcode)
    notes.extend(pnotes)

    listings, total = search_marktplaats(
        terms, postcode=postcode, distance_meters=distance,
        price_min_euro=price_min, price_max_euro=price_max,
    )

    kept = listings
    if parsed and requirements and listings:
        try:
            matches, fnote = filter_listings(requirements, listings)
            if fnote:
                notes.append(fnote)
            if matches is not None:
                kept = []
                for i, l in enumerate(listings):
                    if i in matches:
                        if matches[i]:
                            l["why"] = matches[i]
                        kept.append(l)
        except Exception as e:
            notes.append(f"AI filtering failed ({e}); showing unfiltered results.")

    return {
        "wish": wish,
        "interpreted": {
            "search_terms": terms,
            "price_min_euro": price_min,
            "price_max_euro": price_max,
            "distance_meters": snap_radius(int(distance)) if distance and postcode else None,
            "requirements": requirements,
        },
        "scanned": len(listings),
        "total_on_marktplaats": total,
        "results": kept,
        "ai": bool(parsed),
        "notes": notes,
    }


# ---------------------------------------------------------------- web server

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robin-Bobin</title>
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128269;</text></svg>">
<style>
  :root {
    --ink: #1d1d1f; --body: #48484a; --muted: #86868b;
    --line: #e8e8ed; --line2: #d2d2d7; --field: #f5f5f7;
  }
  * { box-sizing: border-box; }
  ::selection { background: var(--ink); color: #fff; }
  body {
    margin: 0; background: #fff; color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI',
                 system-ui, Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
  }
  .wrap { max-width: 1040px; margin: 0 auto; padding: 0 20px 110px; }

  .top { padding: 30px 2px 0; font-size: 16px; font-weight: 700; letter-spacing: -.01em; }

  .hero { max-width: 660px; margin: 0 auto; }
  h1 {
    font-size: clamp(38px, 7.5vw, 62px); font-weight: 700; letter-spacing: -.035em;
    line-height: 1.04; text-align: center; margin: clamp(48px, 9vh, 88px) 0 30px;
  }

  .box {
    background: var(--field); border-radius: 26px; padding: 6px;
    transition: box-shadow .18s ease;
  }
  .box:focus-within { box-shadow: 0 0 0 1.5px var(--ink); }
  textarea {
    width: 100%; min-height: 86px; padding: 16px 16px 4px; font: inherit;
    font-size: 17px; letter-spacing: -.01em; line-height: 1.45; border: 0;
    resize: none; background: transparent; color: var(--ink); outline: none;
  }
  textarea::placeholder, input::placeholder { color: var(--muted); }
  .boxrow { display: flex; align-items: center; gap: 8px; padding: 6px; }
  input[type=text] {
    padding: 10px 16px; font: inherit; font-size: 15px; border: 0;
    border-radius: 980px; width: 132px; background: #fff; color: var(--ink);
    outline: none; transition: box-shadow .15s ease;
  }
  input[type=text]:focus { box-shadow: 0 0 0 1.5px var(--ink); }
  #go {
    margin-left: auto; padding: 11px 26px; font: inherit; font-size: 15px;
    font-weight: 600; color: #fff; background: var(--ink); border: 0;
    border-radius: 980px; cursor: pointer;
    transition: opacity .15s ease, transform .1s ease;
  }
  #go:hover { opacity: .85; }
  #go:active { transform: scale(.97); }
  #go:disabled { opacity: .35; cursor: wait; transform: none; }

  .examples { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center;
              margin-top: 16px; }
  .ex {
    background: transparent; border: 1px solid var(--line); border-radius: 980px;
    padding: 7px 15px; font: inherit; font-size: 13px; color: var(--muted);
    cursor: pointer; transition: color .15s ease, border-color .15s ease;
  }
  .ex:hover { color: var(--ink); border-color: var(--ink); }

  .interp { display: none; flex-wrap: wrap; gap: 7px; justify-content: center;
            margin: 26px 0 0; animation: rise .35s ease both; }
  .tok {
    font-size: 13px; padding: 6px 13px; border-radius: 980px;
    border: 1px solid var(--line2); color: var(--body); background: #fff;
  }
  .tok.dark { background: var(--ink); border-color: var(--ink); color: #fff;
              font-weight: 500; }

  .note { background: var(--field); color: var(--body); border-radius: 12px;
          padding: 11px 16px; font-size: 13px; margin: 14px auto 0;
          max-width: 560px; text-align: center; animation: rise .3s ease both; }
  #status { text-align: center; margin-top: 22px; }
  .count { color: var(--muted); font-size: 14px; letter-spacing: -.01em;
           min-height: 1em; }
  .count:empty { min-height: 0; margin: 0; }

  .spinner { display: none; margin: 36px auto 0; border: 2px solid var(--line);
             border-top-color: var(--ink); border-radius: 50%; width: 26px;
             height: 26px; animation: spin .7s linear infinite; }

  .results-sec { margin-top: 44px; }
  .bar { height: 2px; background: var(--line); border-radius: 2px; overflow: hidden;
         margin: 0 1px 16px; opacity: 0; transition: opacity .4s ease; }
  .bar i { display: block; height: 100%; width: 0; background: var(--ink);
           transition: width .45s ease; }
  #count { margin: 0 2px 16px; }

  #results { display: grid; grid-template-columns: 1fr; gap: 12px; }
  @media (min-width: 860px) { #results { grid-template-columns: 1fr 1fr; } }

  .card {
    display: flex; gap: 15px; background: #fff; border-radius: 20px; padding: 13px;
    text-decoration: none; color: inherit; border: 1px solid var(--line);
    animation: rise .3s ease backwards;
    transition: box-shadow .18s ease, border-color .18s ease, opacity .3s ease;
  }
  .card:hover { border-color: var(--line2); box-shadow: 0 10px 34px rgba(0,0,0,.08); }
  .card img, .noimg { width: 104px; height: 104px; object-fit: cover;
                      border-radius: 13px; background: var(--field); flex: none; }
  @media (min-width: 640px) { .card img, .noimg { width: 122px; height: 122px; } }
  .noimg { display: flex; align-items: center; justify-content: center;
           color: var(--line2); font-size: 11px; }
  .card > div:last-child { min-width: 0; align-self: center; }
  .card h3 { margin: 0 0 3px; font-size: 15.5px; font-weight: 600;
             letter-spacing: -.015em; line-height: 1.32;
             display: -webkit-box; -webkit-line-clamp: 2;
             -webkit-box-orient: vertical; overflow: hidden; }
  .meta { color: var(--muted); font-size: 13px; margin-bottom: 3px; }
  .price { font-weight: 600; color: var(--ink); }
  .desc { font-size: 13px; color: var(--muted); margin: 2px 0 0; line-height: 1.5;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
          overflow: hidden; }

  .why { font-size: 12.5px; margin-top: 8px; display: inline-flex; gap: 6px;
         align-items: baseline; color: var(--muted); line-height: 1.4; }
  .why b { color: var(--ink); font-weight: 700; }
  .why.pending { align-items: center; }
  .why.pending::before {
    content: ''; width: 11px; height: 11px; border-radius: 50%; flex: none;
    border: 2px solid var(--line2); border-top-color: var(--ink);
    animation: spin .7s linear infinite;
  }
  .why.warn { border: 1px dashed var(--line2); border-radius: 980px;
              padding: 3px 11px; }
  .card.pending { opacity: .5; }
  .card.matched { border-color: var(--ink); box-shadow: 0 0 0 1.5px var(--ink); }
  .card.matched:hover { box-shadow: 0 0 0 1.5px var(--ink), 0 10px 34px rgba(0,0,0,.08); }
  .card.rejected { opacity: .08; filter: grayscale(60%); }
  .card.rejected:hover { opacity: .55; filter: none; }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes rise { from { opacity: 0; transform: translateY(7px); }
                    to { opacity: 1; transform: none; } }
  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: .01s !important; transition-duration: .01s !important; }
  }

  .footer { margin-top: 70px; border-top: 1px solid var(--line); }
  .footer-inner { max-width: 1040px; margin: 0 auto; padding: 22px 20px 30px;
                  display: flex; align-items: center; justify-content: space-between;
                  flex-wrap: wrap; gap: 12px; }
  .footer-brand { font-size: 13px; color: var(--muted); }
  .footer-links { display: flex; gap: 22px; }
  .footer-links a { font-size: 13px; color: var(--muted); text-decoration: none; }
  .footer-links a:hover { color: var(--ink); }
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><a href="/" style="color:inherit;text-decoration:none">Robin-Bobin</a></div>
  <section class="hero">
    <h1>Say it. Find it.</h1>
    <form id="f">
      <div class="box">
        <textarea id="q" rows="3" placeholder="Wooden closet with drawers and hangers, about 1.5&ndash;2 m tall, within 15 minutes driving, max &euro;150"></textarea>
        <div class="boxrow">
          <input type="text" id="pc" placeholder="Postcode" autocomplete="postal-code">
          <button id="go" type="submit">Search</button>
        </div>
      </div>
      <div class="examples">
        <button type="button" class="ex" data-q="vintage bikes that are in a perfect condition under 30 minutes driving distance">Vintage bike, perfect condition</button>
        <button type="button" class="ex" data-q="Louis Poulsen lamps in perfect condition between 1950 and 2005 under 30 minutes driving">Louis Poulsen lamp, 1950&ndash;2005</button>
        <button type="button" class="ex" data-q="very cheap art (under 50 EUR), that could be worth 500 EUR at resale">Cheap art worth 10&times; at resale</button>
      </div>
    </form>
    <div class="interp" id="interp"></div>
    <div id="notes"></div>
    <div class="count" id="status"></div>
    <div class="spinner" id="spin"></div>
  </section>
  <section class="results-sec">
    <div class="bar" id="bar"><i></i></div>
    <div class="count" id="count"></div>
    <div id="results"></div>
  </section>
</div>
<footer class="footer">
  <div class="footer-inner">
    <span class="footer-brand">Robin-Bobin</span>
    <nav class="footer-links">
      <a href="/how-it-works">How it works</a>
      <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
    </nav>
  </div>
</footer>
<script>
const f = document.getElementById('f');
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function post(body) {
  return fetch('/api/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  }).then(r => r.json());
}

let baseNotes = [];
let state = {listings: [], total: 0, matched: 0, rejected: 0, failed: 0, checked: 0};

f.addEventListener('submit', async e => {
  e.preventDefault();
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const pc = document.getElementById('pc').value.trim();
  localStorage.setItem('pc', pc);
  document.getElementById('go').disabled = true;
  document.getElementById('spin').style.display = 'block';
  document.getElementById('results').innerHTML = '';
  document.getElementById('count').textContent = '';
  document.getElementById('notes').innerHTML = '';
  document.getElementById('interp').style.display = 'none';
  const bar0 = document.getElementById('bar');
  bar0.style.opacity = 0;
  bar0.firstElementChild.style.width = '0';
  baseNotes = [];
  const statusEl = document.getElementById('status');
  const t0 = Date.now();
  let stage = 'Understanding your wish&hellip;';
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    statusEl.innerHTML = stage + ' ' + s + 's' +
      (s > 30 ? ' &mdash; free AI can take a minute' : '');
  }, 1000);
  try {
    const p = await post({action: 'parse', wish: q});
    if (p.error) throw new Error(p.error);
    baseNotes = p.notes || [];
    showInterp(p.parsed, p.ai);
    showNotes([]);
    stage = 'Searching Marktplaats&hellip;';
    const d = await post({action: 'find', wish: q, postcode: pc, parsed: p.parsed});
    if (d.error) throw new Error(d.error);
    baseNotes = baseNotes.concat(d.notes || []);
    showNotes([]);
    const listings = d.listings || [];
    const reqs = d.requirements || [];
    state = {listings: listings, total: d.total_on_marktplaats,
             matched: 0, rejected: 0, failed: 0, checked: 0};
    const checking = p.ai && reqs.length > 0 && listings.length > 0;
    renderCards(listings, checking);
    document.getElementById('spin').style.display = 'none';
    updateCount(checking);
    if (checking) {
      stage = 'Checking ' + listings.length + ' listings&hellip;';
      await checkAll(listings, reqs);
      finishOrder(listings);
      updateCount(true);
    }
  } catch (err) {
    document.getElementById('notes').innerHTML += '<div class="note">Error: ' + esc(err.message) + '</div>';
  } finally {
    clearInterval(tick);
    statusEl.textContent = '';
    document.getElementById('go').disabled = false;
    document.getElementById('spin').style.display = 'none';
  }
});

async function checkAll(listings, reqs) {
  const B = 15, batches = [];
  for (let i = 0; i < listings.length; i += B) batches.push(listings.slice(i, i + B));
  let next = 0;
  async function worker() {
    while (next < batches.length) {
      const batch = batches[next++];
      try {
        const r = await post({action: 'check', requirements: reqs,
          listings: batch.map(l => ({id: l.id, title: l.title,
            description: l.description, attributes: l.attributes}))});
        if (r.error) throw new Error(r.error);
        for (const l of batch) applyVerdict(l, r.matches ? r.matches[l.id] : undefined, false);
      } catch (err) {
        for (const l of batch) applyVerdict(l, undefined, true);
      }
      updateCount(true);
    }
  }
  await Promise.all([worker(), worker()]);  // 2 at a time: free tiers rate-limit
}

function applyVerdict(l, why, failed) {
  const badge = document.getElementById('b-' + l.id);
  const card = document.getElementById('c-' + l.id);
  state.checked++;
  if (!badge || !card) return;
  card.classList.remove('pending');
  if (failed) {
    state.failed++; l._u = 1;
    badge.className = 'why warn';
    badge.innerHTML = 'Not checked';
  } else if (why !== undefined) {
    state.matched++; l._m = 1;
    card.classList.add('matched');
    badge.className = 'why';
    badge.innerHTML = '<b>&#10003;</b> ' + (why ? esc(why) : 'Matches');
  } else {
    state.rejected++; l._r = 1;
    card.classList.add('rejected');
    badge.remove();
  }
}

function finishOrder(listings) {
  // matched first, then unchecked, rejected last
  const res = document.getElementById('results');
  const order = listings.filter(l => l._m)
    .concat(listings.filter(l => l._u), listings.filter(l => l._r));
  for (const l of order) {
    const c = document.getElementById('c-' + l.id);
    if (c) res.appendChild(c);
  }
}

function updateCount(checking) {
  const s = state, el = document.getElementById('count');
  const bar = document.getElementById('bar');
  if (!checking) {
    el.textContent = s.listings.length + ' listings &middot; ' + s.total + ' hits on Marktplaats';
    el.innerHTML = el.textContent;
    return;
  }
  bar.style.opacity = 1;
  bar.firstElementChild.style.width =
    Math.round(s.checked / s.listings.length * 100) + '%';
  let parts = [s.matched + (s.matched === 1 ? ' match' : ' matches'),
               s.rejected + ' filtered out'];
  if (s.failed) parts.push(s.failed + ' unchecked');
  let txt = parts.join(' &middot; ');
  if (s.checked < s.listings.length) {
    txt += ' &middot; checking ' + (s.listings.length - s.checked) + ' more&hellip;';
  } else {
    setTimeout(() => { bar.style.opacity = 0; }, 700);
  }
  el.innerHTML = txt;
}

function renderCards(listings, checking) {
  document.getElementById('results').innerHTML = listings.map(l => `
    <a class="card${checking ? ' pending' : ''}" id="c-${esc(l.id)}" href="${esc(l.url)}" target="_blank" rel="noopener">
      ${l.image ? `<img src="${esc(l.image)}" alt="" loading="lazy">` : '<div class="noimg">no photo</div>'}
      <div>
        <h3>${esc(l.title)}</h3>
        <div class="meta"><span class="price">${esc(l.price)}</span>
          &middot; ${esc(l.city)}${l.distance_km != null ? ' &middot; ' + l.distance_km + ' km' : ''}</div>
        <div class="desc">${esc(l.description)}</div>
        ${checking ? `<span class="why pending" id="b-${esc(l.id)}">Checking&hellip;</span>` : ''}
      </div>
    </a>`).join('');
}
document.getElementById('pc').value = localStorage.getItem('pc') || '';

document.querySelectorAll('.ex').forEach(b => b.addEventListener('click', () => {
  const q = document.getElementById('q');
  q.value = b.dataset.q || b.textContent.trim();
  q.focus();
}));

document.getElementById('q').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    f.requestSubmit();
  }
});

function showInterp(i, ai) {
  if (!ai || !i) return;
  const t = ['<span class="tok dark">' + esc(i.search_terms) + '</span>'];
  const lo = i.price_min_euro, hi = i.price_max_euro;
  if (lo != null && hi != null) t.push('<span class="tok">&euro;' + lo + '&ndash;' + hi + '</span>');
  else if (hi != null) t.push('<span class="tok">under &euro;' + hi + '</span>');
  else if (lo != null) t.push('<span class="tok">from &euro;' + lo + '</span>');
  if (i.distance_meters) t.push('<span class="tok">within ' + (i.distance_meters / 1000) + ' km</span>');
  (i.requirements || []).forEach(r => t.push('<span class="tok">' + esc(r) + '</span>'));
  const el = document.getElementById('interp');
  el.innerHTML = t.join('');
  el.style.display = 'flex';
}

function showNotes(notes) {
  document.getElementById('notes').innerHTML =
    baseNotes.concat(notes || []).map(n => '<div class="note">' + esc(n) + '</div>').join('');
}

</script>
</body>
</html>"""


HOW_IT_WORKS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How it works &middot; Robin-Bobin</title>
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128269;</text></svg>">
<style>
  :root {
    --ink: #1d1d1f; --body: #48484a; --muted: #86868b;
    --line: #e8e8ed; --line2: #d2d2d7; --field: #f5f5f7;
  }
  * { box-sizing: border-box; }
  ::selection { background: var(--ink); color: #fff; }
  body {
    margin: 0; background: #fff; color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI',
                 system-ui, Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
  }
  .wrap { max-width: 720px; margin: 0 auto; padding: 0 20px 60px; }
  .top { padding: 30px 2px 0; font-size: 16px; font-weight: 700; letter-spacing: -.01em; }
  .top a { color: inherit; text-decoration: none; }

  .hero { max-width: 620px; margin: 0 auto; text-align: center; }
  h1 {
    font-size: clamp(34px, 6.5vw, 52px); font-weight: 700; letter-spacing: -.035em;
    line-height: 1.06; margin: clamp(40px, 8vh, 64px) 0 14px;
  }
  .sub { font-size: 18px; color: var(--body); line-height: 1.5; margin: 0 auto 8px; }

  .steps { list-style: none; margin: 56px 0 0; padding: 0; display: grid; gap: 16px; }
  .step {
    display: flex; gap: 18px; align-items: flex-start; background: var(--field);
    border-radius: 20px; padding: 22px 22px; text-align: left;
    animation: rise .35s ease backwards;
  }
  .step .n {
    flex: none; width: 40px; height: 40px; border-radius: 50%; background: var(--ink);
    color: #fff; font-weight: 700; font-size: 15px; display: flex; align-items: center;
    justify-content: center;
  }
  .step h3 { margin: 3px 0 4px; font-size: 17px; font-weight: 700; letter-spacing: -.015em; }
  .step p { margin: 0; font-size: 14.5px; color: var(--body); line-height: 1.55; }

  .cta { text-align: center; margin: 56px 0 0; }
  .cta a {
    display: inline-block; padding: 13px 30px; font-size: 15px; font-weight: 600;
    color: #fff; background: var(--ink); border-radius: 980px; text-decoration: none;
    transition: opacity .15s ease;
  }
  .cta a:hover { opacity: .85; }

  .aside { margin: 20px auto 0; font-size: 13px; color: var(--muted); max-width: 480px; }
  .aside a { color: inherit; }

  .footer { margin-top: 70px; border-top: 1px solid var(--line); }
  .footer-inner { max-width: 1040px; margin: 0 auto; padding: 22px 20px 30px;
                  display: flex; align-items: center; justify-content: space-between;
                  flex-wrap: wrap; gap: 12px; }
  .footer-brand { font-size: 13px; color: var(--muted); }
  .footer-links { display: flex; gap: 22px; }
  .footer-links a { font-size: 13px; color: var(--muted); text-decoration: none; }
  .footer-links a:hover { color: var(--ink); }

  @keyframes rise { from { opacity: 0; transform: translateY(7px); }
                    to { opacity: 1; transform: none; } }
  .step:nth-child(1) { animation-delay: .02s; }
  .step:nth-child(2) { animation-delay: .08s; }
  .step:nth-child(3) { animation-delay: .14s; }
  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: .01s !important; transition-duration: .01s !important; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><a href="/">Robin-Bobin</a></div>
  <section class="hero">
    <h1>How Robin-Bobin works</h1>
    <p class="sub">Marktplaats is full of listings that almost fit. Robin-Bobin reads
       every one of them for you, like a friend who actually knows what you're
       looking for &mdash; and only shows you the ones that do.</p>
  </section>

  <ol class="steps">
    <li class="step">
      <span class="n">1</span>
      <div>
        <h3>Tell it what you want, in plain words</h3>
        <p>Describe your wish however it comes to mind, in any language &mdash;
           "a wooden closet with drawers and hangers, about 1.5&ndash;2 m tall,
           within 15 minutes driving, max &euro;150." An AI reads that and turns
           it into a real Marktplaats search: Dutch keywords, a price range, and
           a search radius.</p>
      </div>
    </li>
    <li class="step">
      <span class="n">2</span>
      <div>
        <h3>It searches Marktplaats for you</h3>
        <p>Robin-Bobin queries Marktplaats' own search directly and pulls in
           every listing that could plausibly match &mdash; titles, descriptions,
           photos, prices, and distance, all at once.</p>
      </div>
    </li>
    <li class="step">
      <span class="n">3</span>
      <div>
        <h3>It reads each listing and keeps only the real matches</h3>
        <p>Instead of you scrolling through dozens of near-misses, the AI checks
           every result against what you actually asked for &mdash; size, condition,
           features, whatever you mentioned &mdash; and shows only the listings
           that hold up, each with a one-line reason why.</p>
      </div>
    </li>
  </ol>

  <div class="cta">
    <a href="/">Try a search</a>
  </div>
  <p class="aside">No account needed. Nothing is stored &mdash; every search
     talks to Marktplaats live.</p>
</div>
<footer class="footer">
  <div class="footer-inner">
    <span class="footer-brand">Robin-Bobin</span>
    <nav class="footer-links">
      <a href="/how-it-works">How it works</a>
      <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
    </nav>
  </div>
</footer>
</body>
</html>"""


# WSGI application: GET -> the page, POST -> a search. Vercel's Python
# runtime picks up the top-level `app` in a root app.py automatically;
# locally the __main__ block below serves the same app.
def app(environ, start_response):
    if environ.get("REQUEST_METHOD") == "POST":
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            payload = json.loads(environ["wsgi.input"].read(length).decode())
            wish = (payload.get("wish") or "").strip()
            postcode = (payload.get("postcode") or "").strip()
            action = (payload.get("action") or "").strip()
            if action == "check":
                # validate one batch of listings against the requirements
                requirements = [str(r) for r in (payload.get("requirements") or [])]
                items = [i for i in (payload.get("listings") or [])
                         if isinstance(i, dict)]
                if not items:
                    raise ValueError("No listings to check")
                matches = _filter_chunk(requirements, items, 0)
                result = {"matches": {str(items[n].get("id")): why
                                      for n, why in matches.items()}}
            elif not wish:
                raise ValueError("Empty search")
            elif action == "parse":
                parsed, notes = interpret(wish)
                result = {"ai": bool(parsed), "parsed": parsed, "notes": notes}
            elif action == "find":
                # search Marktplaats only — fast, no AI calls
                terms, distance, pmin, pmax, reqs, notes = search_params(
                    payload.get("parsed"), wish, postcode)
                listings, total = search_marktplaats(
                    terms, postcode=postcode, distance_meters=distance,
                    price_min_euro=pmin, price_max_euro=pmax)
                result = {"listings": listings, "total_on_marktplaats": total,
                          "requirements": reqs, "notes": notes}
            elif action == "results":
                result = smart_search(wish, postcode,
                                      parsed=payload.get("parsed"))
            else:  # single-call pipeline (curl-friendly)
                result = smart_search(wish, postcode)
            body = json.dumps(result).encode()
            status = "200 OK"
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            status = "500 Internal Server Error"
        headers = [("Content-Type", "application/json")]
    else:
        path = (environ.get("PATH_INFO") or "/").rstrip("/") or "/"
        body = (HOW_IT_WORKS_HTML if path == "/how-it-works" else HTML).encode()
        status = "200 OK"
        headers = [("Content-Type", "text/html; charset=utf-8")]
    headers.append(("Content-Length", str(len(body))))
    start_response(status, headers)
    return [body]


if __name__ == "__main__":
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, fmt, *args):
            pass

    print(f"Robin-Bobin → http://localhost:{PORT}")
    if not OPENROUTER_API_KEY:
        print("!! OPENROUTER_API_KEY not set: plain search only, no AI. "
              "Get a key (with credits) at https://openrouter.ai/keys")
    make_server("", PORT, app, server_class=ThreadingWSGIServer,
                handler_class=QuietHandler).serve_forever()
