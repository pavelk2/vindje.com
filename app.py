#!/usr/bin/env python3
"""
Marktplaats Smart Search — describe what you want in plain language,
get only the listings that actually match.

How it works (single file, zero dependencies, Python 3.8+):
  1. A free LLM (via OpenRouter) turns your wish into a structured
     Marktplaats search (Dutch keywords, price range, search radius).
  2. We query Marktplaats' own search API.
  3. The LLM reads every result and keeps only the ones that really
     match your requirements (size, features, condition, ...).

Run:
  OPENROUTER_API_KEY=sk-or-... python3 app.py
  open http://localhost:8000

Get a free key at https://openrouter.ai/keys (free models cost nothing).
Without a key the app still works as a plain Marktplaats search,
just without the smart parsing/filtering.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------- LLM (OpenRouter)

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Free models, tried in order (best quality first, ending with OpenRouter's
# own free-model router as a catch-all). Override with OPENROUTER_MODEL.
FREE_MODELS = [
    m.strip()
    for m in os.environ.get(
        "OPENROUTER_MODEL",
        "z-ai/glm-5.2:free,"
        "nvidia/nemotron-3-ultra-550b-a55b:free,"
        "google/gemma-4-31b-it:free,"
        "openrouter/free",
    ).split(",")
    if m.strip()
]


def llm(messages, max_tokens=2000):
    """Call the first free model that answers. Returns text or raises."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    last_err = None
    for model in FREE_MODELS:
        # Top free models are reasoning models; ask for low effort to keep
        # searches snappy. If a model rejects that parameter, retry without it.
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
                    "X-Title": "Marktplaats Smart Search",
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


def filter_listings(requirements, listings):
    if not requirements or not listings:
        return None
    lines = []
    for i, l in enumerate(listings):
        desc = l["description"][:300]
        attrs = "; ".join(l["attributes"][:8])
        lines.append(f"[{i}] {l['title']} | {desc} | {attrs}")
    result = llm_json(
        [
            {"role": "system", "content": FILTER_PROMPT % "\n".join("- " + r for r in requirements)},
            {"role": "user", "content": "\n".join(lines)},
        ],
        max_tokens=6000,
    )
    matches = {}
    for m in result.get("matches", []):
        try:
            n = int(m["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= n < len(listings):
            matches[n] = str(m.get("why", ""))
    return matches


# ---------------------------------------------------------------- pipeline

def smart_search(wish, postcode):
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

    if parsed:
        terms = parsed.get("search_terms") or wish
        distance = parsed.get("distance_meters")
        price_min = parsed.get("price_min_euro")
        price_max = parsed.get("price_max_euro")
        requirements = parsed.get("requirements") or []
    else:
        terms, distance, price_min, price_max, requirements = wish, None, None, None, []

    if distance and not postcode:
        notes.append("Your wish limits distance but no postcode was given — "
                     "add your postcode to enable the radius filter.")
        distance = None

    listings, total = search_marktplaats(
        terms, postcode=postcode, distance_meters=distance,
        price_min_euro=price_min, price_max_euro=price_max,
    )

    kept = listings
    if parsed and requirements and listings:
        try:
            matches = filter_listings(requirements, listings)
            if matches is not None:
                kept = []
                for i, l in enumerate(listings):
                    if i in matches:
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
<title>Marktplaats Smart Search</title>
<style>
  :root { --accent: #2d6a4f; --bg: #f6f5f2; --card: #fff; --ink: #1b1b1b; --muted: #6b7280; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--ink); }
  .wrap { max-width: 880px; margin: 0 auto; padding: 24px 16px 64px; }
  h1 { font-size: 26px; margin: 8px 0 2px; }
  .sub { color: var(--muted); margin: 0 0 20px; }
  form { display: grid; gap: 10px; }
  textarea { width: 100%; min-height: 84px; padding: 12px; font: inherit; border: 1px solid #d1d5db;
             border-radius: 10px; resize: vertical; background: var(--card); }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  input[type=text] { padding: 10px 12px; font: inherit; border: 1px solid #d1d5db; border-radius: 10px;
                     width: 170px; background: var(--card); }
  button { padding: 10px 22px; font: inherit; font-weight: 600; color: #fff; background: var(--accent);
           border: 0; border-radius: 10px; cursor: pointer; }
  button:disabled { opacity: .6; cursor: wait; }
  .interp { background: #e8f0ec; border-radius: 10px; padding: 12px 14px; margin: 18px 0 6px;
            font-size: 14px; display: none; }
  .interp b { color: var(--accent); }
  .note { color: #92400e; background: #fef3c7; border-radius: 8px; padding: 8px 12px;
          font-size: 13px; margin-top: 8px; }
  .count { color: var(--muted); font-size: 14px; margin: 14px 2px; }
  .card { display: flex; gap: 14px; background: var(--card); border-radius: 12px; padding: 12px;
          margin-bottom: 10px; text-decoration: none; color: inherit; border: 1px solid #e5e7eb; }
  .card:hover { border-color: var(--accent); }
  .card img { width: 110px; height: 110px; object-fit: cover; border-radius: 8px; background: #eee; flex: none; }
  .noimg { width: 110px; height: 110px; border-radius: 8px; background: #e5e7eb; flex: none;
           display: flex; align-items: center; justify-content: center; color: #9ca3af; font-size: 12px; }
  .card h3 { margin: 0 0 4px; font-size: 16px; }
  .meta { color: var(--muted); font-size: 13px; margin-bottom: 4px; }
  .price { font-weight: 700; color: var(--accent); }
  .why { font-size: 13px; color: #065f46; background: #d1fae5; border-radius: 6px;
         padding: 2px 8px; display: inline-block; margin-top: 6px; }
  .desc { font-size: 13px; color: #374151; margin: 2px 0 0;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .spinner { display: none; margin: 30px auto; border: 4px solid #e5e7eb; border-top-color: var(--accent);
             border-radius: 50%; width: 34px; height: 34px; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
  <h1>&#128269; Marktplaats Smart Search</h1>
  <p class="sub">Say what you want. AI searches Marktplaats and throws away the trash.</p>
  <form id="f">
    <textarea id="q" placeholder="e.g. wooden closet with drawers and hangers, about 1.5-2 meter height, within 15 minutes driving distance, max &euro;150"></textarea>
    <div class="row">
      <input type="text" id="pc" placeholder="Your postcode (1012AB)" autocomplete="postal-code">
      <button id="go" type="submit">Search</button>
    </div>
  </form>
  <div class="interp" id="interp"></div>
  <div id="notes"></div>
  <div class="spinner" id="spin"></div>
  <div class="count" id="count"></div>
  <div id="results"></div>
</div>
<script>
const f = document.getElementById('f');
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
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
  try {
    const r = await fetch('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({wish: q, postcode: pc})
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    render(d);
  } catch (err) {
    document.getElementById('notes').innerHTML = '<div class="note">Error: ' + esc(err.message) + '</div>';
  } finally {
    document.getElementById('go').disabled = false;
    document.getElementById('spin').style.display = 'none';
  }
});
document.getElementById('pc').value = localStorage.getItem('pc') || '';

function render(d) {
  const i = d.interpreted;
  if (d.ai) {
    let parts = ['Searching for <b>' + esc(i.search_terms) + '</b>'];
    if (i.price_min_euro != null || i.price_max_euro != null)
      parts.push('price <b>' + (i.price_min_euro ?? 0) + ' &ndash; ' + (i.price_max_euro ?? '&infin;') + ' &euro;</b>');
    if (i.distance_meters) parts.push('within <b>' + (i.distance_meters / 1000) + ' km</b>');
    if (i.requirements.length)
      parts.push('must match: <b>' + i.requirements.map(esc).join('</b>, <b>') + '</b>');
    const el = document.getElementById('interp');
    el.innerHTML = '&#129302; ' + parts.join(' &middot; ');
    el.style.display = 'block';
  }
  document.getElementById('notes').innerHTML =
    (d.notes || []).map(n => '<div class="note">' + esc(n) + '</div>').join('');
  document.getElementById('count').textContent = d.ai
    ? d.results.length + ' match(es) after AI-checking ' + d.scanned +
      ' listings (of ' + d.total_on_marktplaats + ' raw hits on Marktplaats)'
    : d.results.length + ' listings (of ' + d.total_on_marktplaats + ' hits)';
  document.getElementById('results').innerHTML = d.results.map(l => `
    <a class="card" href="${esc(l.url)}" target="_blank" rel="noopener">
      ${l.image ? `<img src="${esc(l.image)}" alt="" loading="lazy">` : '<div class="noimg">no photo</div>'}
      <div>
        <h3>${esc(l.title)}</h3>
        <div class="meta"><span class="price">${esc(l.price)}</span>
          &middot; ${esc(l.city)}${l.distance_km != null ? ' &middot; ' + l.distance_km + ' km' : ''}</div>
        <div class="desc">${esc(l.description)}</div>
        ${l.why ? `<div class="why">&#10003; ${esc(l.why)}</div>` : ''}
      </div>
    </a>`).join('');
}
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/search":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode())
            wish = (payload.get("wish") or "").strip()
            postcode = (payload.get("postcode") or "").strip()
            if not wish:
                raise ValueError("Empty search")
            result = smart_search(wish, postcode)
            body = json.dumps(result).encode()
            self.send_response(200)
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


if __name__ == "__main__":
    print(f"Marktplaats Smart Search → http://localhost:{PORT}")
    if not OPENROUTER_API_KEY:
        print("!! OPENROUTER_API_KEY not set: plain search only, no AI. "
              "Get a free key at https://openrouter.ai/keys")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
