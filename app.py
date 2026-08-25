#!/usr/bin/env python3
"""
vindje.com — smart search for Marktplaats: describe what you want in
plain language, get only the listings that actually match.

How it works (single file, zero dependencies, Python 3.8+):
  1. An LLM (via OpenRouter, GPT-5.6 Luna by default) turns your wish
     into a structured Marktplaats search (Dutch keywords, price range,
     search radius).
  2. We query Marktplaats' own search API.
  3. The LLM reads every result — text and its first photo — and keeps
     only the ones that really match your requirements (size, features,
     condition, resale value, ...).

Run:
  OPENROUTER_API_KEY=sk-or-... python3 app.py
  open http://localhost:8000

Get a key at https://openrouter.ai/keys and add credits — the default
model (GPT-5.6 Luna) is paid, not one of OpenRouter's free models.
Without a key the app still works as a plain Marktplaats search,
just without the smart parsing/filtering.
"""

import html
import json
import logging
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

PORT = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------- logging
#
# Plain stdlib logging to stdout. Vercel's Python runtime captures a
# function's stdout/stderr into its log viewer, so this shows up there with
# no extra setup. Set LOG_LEVEL=DEBUG for full request/response previews,
# or LOG_LEVEL=WARNING to quiet it down.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("vindje")


def _new_req_id():
    """Short id to correlate every log line from one HTTP request, including
    the parallel LLM calls made for its filter chunks."""
    return secrets.token_hex(4)


def _preview(value, n=200):
    s = str(value)
    return s if len(s) <= n else s[: n] + f"...(+{len(s) - n} more chars)"


def _summarize_messages(messages):
    """One-line shape of an outgoing LLM request (roles, text sizes, image
    counts) — logged instead of the full payload so a photo-heavy filter
    chunk doesn't flood the log with URLs, while still making it obvious
    whether images were actually included in the request."""
    parts = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            parts.append(f"{m.get('role')}=text({len(content)}c)")
        elif isinstance(content, list):
            n_text = sum(1 for b in content if b.get("type") == "text")
            n_img = sum(1 for b in content if b.get("type") == "image_url")
            parts.append(f"{m.get('role')}=text:{n_text}/image:{n_img}")
        else:
            parts.append(f"{m.get('role')}=?")
    return " ".join(parts)


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
        "openai/gpt-5.6-luna,"
        "openrouter/free",
    ).split(",")
    if m.strip()
]

log.info("vindje.com module loaded: models=%s api_key_set=%s", MODELS, bool(OPENROUTER_API_KEY))


def llm(messages, max_tokens=2000, req_id="-"):
    """Call the first model that answers. Returns text or raises."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    shape = _summarize_messages(messages)
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
                    "X-Title": "vindje.com",
                },
            )
            t0 = time.time()
            log.info("[%s] llm: -> model=%s reasoning=%s %s",
                     req_id, model, bool(extra), shape)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode())
                text = data["choices"][0]["message"]["content"]
                elapsed = time.time() - t0
                if text and text.strip():
                    log.info("[%s] llm: <- model=%s OK in %.2fs, %d chars: %s",
                             req_id, model, elapsed, len(text), _preview(text))
                    return text
                last_err = RuntimeError(f"{model}: empty response")
                log.warning("[%s] llm: <- model=%s EMPTY response in %.2fs",
                            req_id, model, elapsed)
                break  # empty answer won't improve without the reasoning param
            except urllib.error.HTTPError as e:
                elapsed = time.time() - t0
                last_err = e
                try:
                    err_body = e.read().decode(errors="replace")
                except Exception:
                    err_body = ""
                log.warning("[%s] llm: <- model=%s HTTP %s in %.2fs: %s",
                            req_id, model, e.code, elapsed, _preview(err_body, 500))
                if e.code != 400:
                    break  # rate-limited/unavailable -> next model
            except Exception as e:
                elapsed = time.time() - t0
                last_err = e
                log.warning("[%s] llm: <- model=%s ERROR in %.2fs: %s",
                            req_id, model, elapsed, e)
                break
    log.error("[%s] llm: ALL MODELS FAILED, last error: %s", req_id, last_err)
    raise RuntimeError(f"All models failed, last error: {last_err}")


def llm_json(messages, max_tokens=2000, req_id="-"):
    """llm() + tolerant JSON extraction (models love code fences)."""
    text = llm(messages, max_tokens=max_tokens, req_id=req_id)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        log.warning("[%s] llm_json: no JSON braces in response: %s", req_id, _preview(text))
        raise ValueError("No JSON in model response: " + text[:200])
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        log.warning("[%s] llm_json: JSON parse failed on: %s", req_id, _preview(text))
        raise


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
- Do NOT put price or distance into requirements; they go in their own fields.
- Unless the buyer explicitly asked for a spare part, component, or accessory, the FIRST requirement must
  state that the listing has to be the complete, whole item itself, and not a spare part, replacement part,
  component, or accessory for it (e.g. buyer wants "a bicycle" -> requirement "must be a complete, ridable
  bicycle, not a part or accessory such as a stem, derailleur, saddle, rack, or bike computer"). Marketplaces
  are full of listings for parts/accessories that mention the whole product only to say they fit it, and a
  plain keyword search cannot tell those apart, so this check matters."""


def parse_wish(wish, req_id="-"):
    log.info("[%s] parse_wish: wish=%r", req_id, _preview(wish, 150))
    parsed = llm_json(
        [
            {"role": "system", "content": PARSE_PROMPT},
            {"role": "user", "content": wish},
        ],
        max_tokens=2000,
        req_id=req_id,
    )
    log.info("[%s] parse_wish: terms=%r requirements=%d price=[%s,%s] distance_m=%s",
             req_id, parsed.get("search_terms"), len(parsed.get("requirements") or []),
             parsed.get("price_min_euro"), parsed.get("price_max_euro"),
             parsed.get("distance_meters"))
    return parsed


# ---------------------------------------------------------------- Step 2: search Marktplaats

# Radii the Marktplaats UI actually supports.
ALLOWED_RADII = [1000, 2000, 3000, 5000, 10000, 15000, 25000, 50000, 75000, 100000]


def snap_radius(meters):
    return min(ALLOWED_RADII, key=lambda r: abs(r - meters))


def search_marktplaats(terms, postcode=None, distance_meters=None,
                       price_min_euro=None, price_max_euro=None, limit=60,
                       req_id="-"):
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
    t0 = time.time()
    log.info("[%s] search_marktplaats: terms=%r postcode=%s distance_m=%s price=[%s,%s] limit=%d",
             req_id, terms, postcode, distance_meters, price_min_euro, price_max_euro, limit)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        log.warning("[%s] search_marktplaats: FAILED in %.2fs: %s", req_id, time.time() - t0, e)
        raise

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
            # biggest first: the result cards render photos ~700px wide,
            # so the ~500px mediumUrl comes out upscaled and soft
            image = (pics[0].get("extraExtraLargeUrl") or pics[0].get("largeUrl")
                     or pics[0].get("mediumUrl") or "")
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
    total = data.get("totalResultCount", len(listings))
    with_image = sum(1 for l in listings if l["image"])
    log.info("[%s] search_marktplaats: got %d listings (%d with image) of %d total, in %.2fs",
             req_id, len(listings), with_image, total, time.time() - t0)
    return listings, total


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

Below are numbered listings (title / description / attributes, in Dutch), each
immediately followed by that listing's own photo. Use the photo together with
the text — it's real evidence, not decoration: judge condition, materials,
and whether the item visibly is what the title/description claims (sellers'
words alone are not reliable, and a plain keyword search can't tell a genuine
item from a look-alike or a misleading listing).

Keep a listing only if it plausibly satisfies ALL requirements, or if the
text and photo don't contradict them and the item is clearly the right kind
of thing. Reject anything that is the wrong kind of item, a service/ad, or
contradicts a requirement. Watch especially for spare parts, replacement
parts, components, and accessories that only mention the whole product to
say they fit it (e.g. a stem, derailleur, saddle, rack, or bike computer is
NOT a bicycle; a lamp shade or cord is NOT a lamp) — reject these unless the
buyer actually asked for a part/accessory.

If a requirement asks about resale/market value (e.g. "worth at least
€X"), you have no live pricing data or ability to look up comparable sales —
give your best-informed judgment from brand/designer recognition, materials,
and build quality visible in the photo, and treat it as a plausibility
check, not an appraisal. Say so implicitly by keeping "why" honest (e.g.
"looks like a genuine Artemide ITIS, plausible resale value" rather than
asserting a precise price).

Reply with ONLY JSON: {"matches": [{"n": <listing number>, "why": "<max 12 words, English>"}]}"""


FILTER_CHUNK = 8  # listings per LLM call; smaller than before since each one
                  # now also carries an image, which costs far more tokens
                  # than its text. Chunks are checked concurrently.


def _filter_chunk(requirements, listings, base, req_id="-"):
    content = []
    n_images = 0
    for i, l in enumerate(listings):
        n = base + i
        desc = str(l.get("description") or "")[:300]
        attrs = "; ".join(str(a) for a in (l.get("attributes") or [])[:8])
        content.append({"type": "text", "text": f"[{n}] {l.get('title', '')} | {desc} | {attrs}"})
        image = l.get("image")
        if image:
            content.append({"type": "image_url", "image_url": {"url": image}})
            n_images += 1
    log.info("[%s] filter_chunk base=%d: %d listings, %d with image", req_id, base, len(listings), n_images)
    result = llm_json(
        [
            {"role": "system", "content": FILTER_PROMPT % "\n".join("- " + r for r in requirements)},
            {"role": "user", "content": content},
        ],
        max_tokens=4000,
        req_id=req_id,
    )
    matches = {}
    for m in result.get("matches", []):
        try:
            n = int(m["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if base <= n < base + len(listings):
            matches[n] = str(m.get("why", ""))
    log.info("[%s] filter_chunk base=%d: %d/%d matched: %s",
             req_id, base, len(matches), len(listings),
             {k: v for k, v in matches.items()})
    return matches


def filter_listings(requirements, listings, req_id="-"):
    """Returns (matches dict, note or None). Raises only if every chunk fails."""
    if not requirements or not listings:
        return None, None
    chunks = [(i, listings[i : i + FILTER_CHUNK])
              for i in range(0, len(listings), FILTER_CHUNK)]
    log.info("[%s] filter_listings: %d listings in %d chunk(s), %d requirements",
             req_id, len(listings), len(chunks), len(requirements))
    t0 = time.time()
    matches, failed = {}, []
    with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as ex:
        futures = {ex.submit(_filter_chunk, requirements, chunk, base, req_id): (base, chunk)
                   for base, chunk in chunks}
        for fut in as_completed(futures):
            base, chunk = futures[fut]
            try:
                matches.update(fut.result())
            except Exception as e:
                log.warning("[%s] filter_listings: chunk base=%d FAILED: %s", req_id, base, e)
                failed.append((base, chunk))
    if failed and not matches and len(failed) == len(chunks):
        log.error("[%s] filter_listings: all %d chunks failed", req_id, len(chunks))
        raise RuntimeError("all filter batches failed")
    note = None
    if failed:
        # keep un-checked listings rather than silently dropping them
        for base, chunk in failed:
            for i in range(len(chunk)):
                matches.setdefault(base + i, "")
        note = (f"AI check failed for {sum(len(c) for _, c in failed)} of "
                f"{len(listings)} listings; those are shown unfiltered.")
    log.info("[%s] filter_listings: done in %.2fs, %d matched of %d, %d chunk(s) failed",
             req_id, time.time() - t0, len(matches), len(listings), len(failed))
    return matches, note


# ---------------------------------------------------------------- sharing (Upstash Redis)

# Every completed search is saved (frozen snapshot) and given a short
# share id, so a link to /s/<id> shows the exact same results later, to
# anyone. Uses Upstash Redis' HTTP REST API directly via urllib — no
# extra dependency. Configure with UPSTASH_REDIS_REST_URL and
# UPSTASH_REDIS_REST_TOKEN (from the Upstash console; the token is
# secret and only ever used server-side).
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")


def upstash_command(*args):
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        raise RuntimeError(
            "Upstash Redis is not configured (UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN)"
        )
    req = urllib.request.Request(
        UPSTASH_REDIS_REST_URL,
        data=json.dumps(list(args)).encode(),
        headers={
            "Authorization": "Bearer " + UPSTASH_REDIS_REST_TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Upstash error {e.code}: {e.read().decode(errors='replace')[:300]}")
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Upstash error: {data['error']}")
    return data.get("result")


HISTORY_KEY = "history"
HISTORY_MAX = 500


def save_search(record):
    """Persist a completed search (frozen results) and return its share id."""
    if not record.get("wish"):
        raise ValueError("Nothing to share yet")
    share_id = secrets.token_urlsafe(9)
    wish = str(record["wish"])[:500]
    results = (record.get("results") or [])[:200]
    row = {
        "wish": wish,
        "postcode": str(record["postcode"])[:20] if record.get("postcode") else None,
        "interpreted": record.get("interpreted"),
        "results": results,
        "scanned": record.get("scanned"),
        "total_on_marktplaats": record.get("total_on_marktplaats"),
        "ai": bool(record.get("ai")),
        "notes": (record.get("notes") or [])[:20],
        "ts": time.time(),
    }
    upstash_command("SET", f"search:{share_id}", json.dumps(row))
    # Every saved search is also appended to a public history list so it
    # shows up on /history. Searches aren't tied to any user or account,
    # so there's nothing identifiable in it beyond the wish text itself.
    entry = json.dumps({"id": share_id, "wish": wish, "ts": row["ts"], "count": len(results)})
    upstash_command("LPUSH", HISTORY_KEY, entry)
    upstash_command("LTRIM", HISTORY_KEY, "0", str(HISTORY_MAX - 1))
    return share_id


def get_search(share_id):
    """Look up a previously saved search by its share id."""
    raw = upstash_command("GET", f"search:{share_id}")
    return json.loads(raw) if raw else None


DEALS_KEY = "deals:latest"


def get_deals():
    """The morning deal-hunt's finds (written by deals.py), for the
    homepage. None if absent or Redis isn't configured."""
    try:
        raw = upstash_command("GET", DEALS_KEY)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def get_history(limit=HISTORY_MAX):
    """Most recent saved searches, newest first, for the /history page."""
    raw = upstash_command("LRANGE", HISTORY_KEY, "0", str(limit - 1))
    entries = []
    for item in raw or []:
        try:
            entries.append(json.loads(item))
        except (TypeError, ValueError):
            continue
    return entries


# ---------------------------------------------------------------- pipeline

_UNSET = object()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def interpret(wish, req_id="-"):
    """Phase 1: parse the wish with the LLM. Returns (parsed_or_None, notes)."""
    notes = []
    parsed = None
    if OPENROUTER_API_KEY:
        try:
            parsed = parse_wish(wish, req_id=req_id)
        except Exception as e:
            log.warning("[%s] interpret: parse_wish failed: %s", req_id, e)
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


def smart_search(wish, postcode, parsed=_UNSET, notes=None, req_id="-"):
    """Phase 2: search Marktplaats and AI-filter. Runs phase 1 first unless a
    pre-parsed result (possibly None) is handed in."""
    t0 = time.time()
    log.info("[%s] smart_search: wish=%r postcode=%s", req_id, _preview(wish, 150), postcode)
    if parsed is _UNSET:
        parsed, notes = interpret(wish, req_id=req_id)
    notes = list(notes or [])
    if not isinstance(parsed, dict):
        parsed = None

    terms, distance, price_min, price_max, requirements, pnotes = \
        search_params(parsed, wish, postcode)
    notes.extend(pnotes)

    listings, total = search_marktplaats(
        terms, postcode=postcode, distance_meters=distance,
        price_min_euro=price_min, price_max_euro=price_max,
        req_id=req_id,
    )

    kept = listings
    if parsed and requirements and listings:
        try:
            matches, fnote = filter_listings(requirements, listings, req_id=req_id)
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
            log.warning("[%s] smart_search: filter_listings failed: %s", req_id, e)
            notes.append(f"AI filtering failed ({e}); showing unfiltered results.")

    log.info("[%s] smart_search: done in %.2fs, kept %d of %d scanned (%d on Marktplaats)",
             req_id, time.time() - t0, len(kept), len(listings), total)
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
<title>vindje.com &middot; Smart AI Search for Marktplaats</title>
<meta name="description" content="Describe what you want to buy in plain language. vindje.com turns it into a real Marktplaats search and uses AI to read every listing, keeping only the ones that actually match.">
<link rel="canonical" href="__ORIGIN__/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="vindje.com">
<meta property="og:title" content="vindje.com &middot; Smart AI Search for Marktplaats">
<meta property="og:description" content="Describe what you want to buy in plain language and get only the Marktplaats listings that actually match. No more scrolling through junk.">
<meta property="og:url" content="__ORIGIN__/">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="vindje.com &middot; Smart AI Search for Marktplaats">
<meta name="twitter:description" content="Describe what you want to buy in plain language and get only the Marktplaats listings that actually match.">
<meta name="theme-color" content="#ffffff">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebApplication","name":"vindje.com","url":"__ORIGIN__/","description":"Describe what you want to buy in plain language and get only the Marktplaats listings that actually match, filtered by AI.","applicationCategory":"ShoppingApplication","operatingSystem":"Any","offers":{"@type":"Offer","price":"0","priceCurrency":"EUR"}}
</script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect x='18' y='18' width='64' height='64' fill='%23d6001c'/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --ink: #0f0f10; --grey: #6d6d73; --faint: #a4a4ab;
    --hair: #e4e4e8; --panel: #f7f7f8;
    --red: #d6001c; --blue: #1d4e9e; --yellow: #f0c114;
  }
  * { box-sizing: border-box; margin: 0; }
  ::selection { background: var(--ink); color: #fff; }
  html { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
  body { background: #fff; color: var(--ink);
         font-family: 'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif;
         font-size: 15px; line-height: 1.5; min-height: 100vh;
         display: flex; flex-direction: column; }
  a { color: inherit; text-decoration: none; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }
  .num { font-variant-numeric: tabular-nums; }
  .label { font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; }
  .wrap { max-width: 1264px; width: 100%; margin: 0 auto; padding: 0 24px; }
  .sq { display: inline-block; width: .55em; height: .55em; background: var(--red); }
  :focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }

  /* header */
  .top { border-bottom: 1px solid var(--hair); }
  .top-in { display: flex; align-items: center; height: 64px; }
  .wordmark { font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
  .wordmark .sq { width: 8px; height: 8px; margin-left: 2px; }
  .nav { margin-left: auto; display: flex; gap: 26px; font-size: 13px; color: var(--grey); }
  .nav a:hover { color: var(--ink); }

  /* hero (idle only): a centered, symmetric composition */
  .hero { padding-top: 84px; text-align: center; }
  .hero h1 { font-size: clamp(38px, 5.5vw, 62px); font-weight: 700; letter-spacing: -.035em;
             line-height: 1.02; max-width: 900px; margin: 0 auto; text-wrap: balance; }
  .hero h1 .sq { width: .2em; height: .2em; }
  .hero .sub { margin: 20px auto 0; font-size: 18px; color: var(--grey); max-width: 540px;
               line-height: 1.55; text-wrap: balance; }
  body.run .hero { display: none; }

  /* search */
  .search { padding-top: 40px; padding-bottom: 28px; }
  body:not(.run) .search { max-width: 948px; padding-top: 34px; padding-bottom: 56px; }
  body:not(.run) .examples { justify-content: center; }
  .search .slabel { display: none; color: var(--faint); margin-bottom: 12px; }
  body.run .search { padding-top: 44px; }
  body.run .search .slabel { display: block; }
  .bar { display: flex; align-items: stretch; border: 1px solid var(--ink); background: #fff; }
  .bar:focus-within { box-shadow: 0 0 0 1px var(--ink); }
  #q { flex: 1; min-height: 64px; padding: 19px 20px; font: inherit; font-size: 17px;
       line-height: 1.45; letter-spacing: -.005em; border: 0; resize: none;
       background: transparent; color: var(--ink); outline: none; overflow: hidden; }
  #q::placeholder { color: var(--faint); }
  #pc { width: 128px; padding: 0 18px; font: inherit; font-size: 14px; border: 0;
        border-left: 1px solid var(--hair); background: transparent; color: var(--ink);
        outline: none; }
  #pc::placeholder { color: var(--faint); }
  #go { padding: 0 34px; background: var(--ink); color: #fff; font-size: 14px;
        font-weight: 600; letter-spacing: .04em; }
  #go:hover { background: #2a2a2e; }
  #go:disabled { opacity: .45; cursor: wait; }
  @media (max-width: 640px) {
    .bar { flex-wrap: wrap; }
    #q { flex: 1 1 100%; border-bottom: 1px solid var(--hair); }
    #pc { flex: 1; border-left: 0; padding: 12px 18px; }
    #go { padding: 12px 26px; }
  }

  .examples { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
  .ex { border: 1px solid var(--hair); padding: 9px 16px; font-size: 13px; color: var(--grey); }
  .ex:hover { border-color: var(--ink); color: var(--ink); }
  body.run .examples { display: none; }

  /* interpreted spec line */
  .spec { display: none; align-items: baseline; gap: 10px; flex-wrap: wrap;
          margin-top: 14px; color: var(--grey); font-size: 13px; }
  .spec.show { display: flex; }
  .spec .k { color: var(--faint); }
  .spec .sep { color: var(--hair); }
  .spec b { color: var(--ink); font-weight: 500; }
  .specnote { display: none; margin-top: 8px; font-size: 12.5px; color: var(--faint);
              line-height: 1.5; max-width: 900px; }
  .statusline { display: none; align-items: baseline; gap: 10px; margin-top: 14px;
                font-size: 13.5px; color: var(--grey); }
  .statusline b { color: var(--ink); font-weight: 600; }

  /* the rule: black line + travelling red square */
  .rulewrap { position: relative; height: 3px; background: var(--hair); display: none; }
  .rulewrap .fill { position: absolute; left: 0; top: 0; height: 3px; width: 0;
                    background: var(--ink); transition: width .4s ease; }
  .rulewrap .dot { position: absolute; top: -3px; left: 0; width: 9px; height: 9px;
                   background: var(--red); transition: left .4s ease; }
  .rulewrap.on { display: block; }
  .rulewrap.scan .dot { animation: scan 1.8s ease-in-out infinite alternate; }
  @keyframes scan { from { left: 0; } to { left: calc(100% - 9px); } }
  .rulewrap.done { background: var(--ink); }
  .rulewrap.done .fill { width: 100%; }
  .rulewrap.done .dot { left: 25%; animation: none; }

  /* notes */
  #notes { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
  .note { border: 1px solid var(--hair); border-left: 3px solid var(--yellow);
          padding: 10px 14px; font-size: 13px; color: var(--grey); }

  /* results head */
  .rhead { display: none; align-items: baseline; flex-wrap: wrap; gap: 8px 14px;
           padding: 26px 0 22px; }
  .rhead.show { display: flex; }
  .rhead h1 { font-size: 30px; font-weight: 600; letter-spacing: -.02em; }
  .rhead h1 .of { color: var(--faint); font-weight: 500; }
  .rhead .sub { color: var(--grey); font-size: 14px; }
  .rhead .actions { margin-left: auto; display: flex; gap: 10px; }
  .btn { border: 1px solid var(--ink); padding: 8px 18px; font-size: 13px; font-weight: 500;
         background: #fff; }
  .btn:hover { background: var(--panel); }

  /* tally strip */
  .tallyrow { display: none; align-items: center; gap: 14px; flex-wrap: wrap;
              padding: 0 0 22px; }
  .tallyrow.show { display: flex; }
  .tally { display: flex; gap: 4px; flex-wrap: wrap; max-width: 700px; }
  .tally i { width: 13px; height: 13px; background: var(--hair); }
  .tally i.pend { background: #fff; box-shadow: inset 0 0 0 1px var(--hair); }
  .tally i.m { background: var(--ink); }
  .tally i.best { background: var(--red); }
  .tally i.un { background: var(--yellow); }
  .tallycap { font-size: 12.5px; color: var(--grey); }
  .tallycap b.r { color: var(--red); } .tallycap b.k { color: var(--ink); }

  /* today's finds: the morning deal-hunt, homepage only */
  .deals { display: none; padding-top: 8px; }
  .deals.show { display: block; }
  body.run .deals { display: none; }
  .deals .dhead { display: flex; justify-content: center; align-items: baseline;
                  flex-wrap: wrap; gap: 8px 14px; padding: 34px 0 6px; }
  .deals .dhead h2 { font-size: 24px; font-weight: 600; letter-spacing: -.02em; }
  .deals .dhead h2 .sq { width: 7px; height: 7px; margin-left: 2px; }
  .deals .dsub { color: var(--grey); font-size: 13.5px; max-width: 620px; line-height: 1.55;
                 margin: 0 auto; text-align: center; text-wrap: balance; padding-bottom: 26px; }
  .deals .cat { display: flex; align-items: baseline; gap: 12px; padding: 22px 0 12px; }
  .deals .cat .label { color: var(--ink); }
  .deals .cat .n { color: var(--faint); font-size: 12.5px; }
  .deals.show { padding-bottom: 56px; }
  .deals .dgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
                  background: var(--hair); border: 1px solid var(--hair); }
  @media (max-width: 1000px) { .deals .dgrid { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 660px) { .deals .dgrid { grid-template-columns: 1fr; } }

  /* grid + cards */
  #results { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
             background: var(--hair); border: 1px solid var(--hair); }
  #results:empty { display: none; }
  @media (max-width: 1000px) { #results { grid-template-columns: 1fr 1fr; } }
  @media (max-width: 660px) { #results { grid-template-columns: 1fr; } }
  .card { background: #fff; padding: 0 0 22px; display: flex; flex-direction: column;
          position: relative; }
  .card:hover { outline: 1px solid var(--ink); outline-offset: -1px; z-index: 1; }
  .card .ph { background: var(--panel); border-bottom: 1px solid var(--hair); }
  .card .ph img { width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; }
  .card .ph .noimg { display: flex; align-items: center; justify-content: center;
                     aspect-ratio: 4/3; color: var(--faint); font-size: 12px; }
  .card .body { padding: 15px 20px 0; display: flex; flex-direction: column; flex: 1; }
  .rank { margin-bottom: 7px; }
  .rank .label { color: var(--faint); }
  .card.first .rank .label { color: var(--red); }
  .card.first::before { content: ''; position: absolute; top: -1px; left: -1px; right: -1px;
                        height: 3px; background: var(--red); z-index: 1; }
  .card h3 { font-size: 15.5px; font-weight: 600; letter-spacing: -.01em; line-height: 1.35; }
  .priceline { display: flex; align-items: baseline; justify-content: space-between;
               gap: 10px; margin-top: 10px; }
  .price { font-size: 20px; font-weight: 600; letter-spacing: -.01em; white-space: nowrap; }
  .price .cur { color: var(--faint); font-weight: 500; }
  .geo { color: var(--grey); font-size: 13px; text-align: right; }
  .desc { margin-top: 8px; font-size: 13px; color: var(--grey); line-height: 1.5;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
          overflow: hidden; }
  .why { margin-top: 13px; padding-top: 11px; border-top: 1px solid var(--hair);
         display: flex; gap: 10px; font-size: 13px; line-height: 1.5; color: var(--grey); }
  .why i { flex: none; width: 8px; height: 8px; margin-top: 5px; background: var(--ink); }
  .why b { color: var(--ink); font-weight: 500; }
  .card.first .why i, .card.deal .why i { background: var(--red); }
  .card.pending .why i { background: #fff; box-shadow: inset 0 0 0 1px var(--faint); }
  .card.pending .why { color: var(--faint); }
  .card.un .why i { background: var(--yellow); }
  .card.rejected .ph img, .card.rejected h3, .card.rejected .priceline,
  .card.rejected .desc { opacity: .32; }
  .card.rejected .ph img { filter: grayscale(1); }
  .card.rejected:hover .ph img, .card.rejected:hover h3,
  .card.rejected:hover .priceline, .card.rejected:hover .desc { opacity: .8; }
  .card.rejected .why { display: none; }

  main { flex: 1 0 auto; display: flex; flex-direction: column; }
  main > :first-child { margin-top: 0; }

  /* facts row (idle only) */
  .homefacts { border-top: 1px solid var(--hair); margin-top: auto; }
  .homefacts .in { display: grid; grid-template-columns: 1fr 1fr 1fr; }
  .fact { padding: 30px 28px; text-align: center; }
  .fact + .fact { border-left: 1px solid var(--hair); }
  .fact b { display: block; font-size: 18px; font-weight: 600; letter-spacing: -.01em; }
  .fact span { display: block; font-size: 13px; color: var(--grey); margin-top: 4px;
               text-wrap: balance; }
  body.run .homefacts { display: none; }
  @media (max-width: 800px) {
    .homefacts .in { grid-template-columns: 1fr; }
    .fact + .fact { padding-left: 0; border-left: 0; border-top: 1px solid var(--hair); }
  }

  footer { flex-shrink: 0; margin-top: 64px; border-top: 1px solid var(--hair); }
  body:not(.run) footer { margin-top: 0; }
  .foot-in { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 22px;
             padding-top: 24px; padding-bottom: 30px; color: var(--faint); font-size: 12.5px; }
  .foot-links { margin-left: auto; display: flex; gap: 22px; }
  .foot-links a:hover { color: var(--ink); }

  /* modal */
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(15,15,16,.42);
                   align-items: center; justify-content: center; z-index: 100; padding: 20px; }
  .modal-overlay.show { display: flex; }
  .modal { width: 520px; max-width: 100%; background: #fff; border: 1px solid var(--ink);
           position: relative; padding: 38px 38px 32px; }
  .modal::before { content: ''; position: absolute; top: -1px; left: -1px; right: -1px;
                   height: 3px; background: var(--red); }
  .modal h2 { font-size: 28px; font-weight: 700; letter-spacing: -.025em; line-height: 1.1; }
  .modal h2 .sq { width: 9px; height: 9px; }
  .modal p { margin: 14px 0 22px; color: var(--grey); line-height: 1.6; font-size: 14.5px; }
  .modal .btns { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn.solid { background: var(--ink); color: #fff; }
  .btn.solid:hover { background: #2a2a2e; }
  .modal .tag { margin-top: 24px; padding-top: 15px; border-top: 1px solid var(--hair);
                font-size: 12.5px; color: var(--faint); }

  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: .01s !important; transition-duration: .01s !important; }
  }
</style>
</head>
<body>
<header class="top"><div class="wrap top-in">
  <a class="wordmark" href="/">vindje<span class="sq"></span></a>
  <nav class="nav">
    <a href="/how-it-works">How it works</a>
    <a href="/history">History</a>
    <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
  </nav>
</div></header>

<main>
<section class="hero wrap">
  <h1>Say what you're looking&nbsp;for<span class="sq"></span></h1>
  <p class="sub">vindje reads every Marktplaats listing, text and photos, and shows you
     only what actually fits. In plain language, any language.</p>
</section>

<section class="search wrap">
  <div class="slabel label">Your search</div>
  <form id="f">
    <div class="bar">
      <textarea id="q" rows="1" placeholder="A wooden wardrobe with drawers, 2 m tall, within 15 min driving, max &euro;150"></textarea>
      <input type="text" id="pc" placeholder="Postcode" autocomplete="postal-code">
      <button id="go" type="submit">Search</button>
    </div>
  </form>
  <div class="examples">
    <button type="button" class="ex" data-q="vintage bikes that are in a perfect condition under 30 minutes driving distance">Vintage bike, perfect condition</button>
    <button type="button" class="ex" data-q="Louis Poulsen lamps in perfect condition between 1950 and 2005 under 30 minutes driving">Louis Poulsen lamp, 1950&ndash;2005</button>
    <button type="button" class="ex" data-q="very cheap art (under 50 EUR), that could be worth 500 EUR at resale">Cheap art worth 10&times; at resale</button>
  </div>
  <div class="spec num" id="spec"></div>
  <div class="specnote" id="specNote"></div>
  <div class="statusline" id="status"></div>
  <div id="notes"></div>
</section>

<div class="wrap"><div class="rulewrap" id="rule"><span class="fill"></span><i class="dot"></i></div></div>

<section class="wrap">
  <div class="rhead" id="rhead">
    <h1 class="num" id="rh1"></h1>
    <span class="sub num" id="rsub"></span>
    <span class="actions" id="shareRow" style="display:none">
      <button type="button" class="btn" id="shareBtn">Copy share link</button>
    </span>
  </div>
  <div class="tallyrow" id="tallyRow">
    <div class="tally" id="tally"></div>
    <span class="tallycap num" id="tallyCap"></span>
  </div>
  <div id="results"></div>
</section>

<section class="deals wrap" id="dealsSec"><div id="deals"></div></section>

<div class="homefacts"><div class="wrap in">
  <div class="fact"><b>Every listing, read</b><span>Descriptions and photos, not just keywords.</span></div>
  <div class="fact"><b>Junk never shows</b><span>Parts and look-alikes are rejected for you.</span></div>
  <div class="fact"><b>Every verdict shown</b><span>Rejections stay visible, with reasons.</span></div>
</div></div>
</main>

<footer><div class="wrap foot-in">
  <span>We'd rather show you nothing than junk.</span>
  <nav class="foot-links">
    <a href="/how-it-works">How it works</a>
    <a href="/history">History</a>
    <a href="/credits">Credits</a>
    <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
  </nav>
</div></footer>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <h2>Nothing fits yet<span class="sq" style="margin-left:4px"></span></h2>
    <p>We read every candidate closely and none met your bar, so we're showing you
       none of them. Try a bigger radius, a wider price range, or looser requirements.</p>
    <div class="btns">
      <button type="button" class="btn solid" id="modalEdit">Edit my wish</button>
      <button type="button" class="btn" id="modalClose">Got it</button>
    </div>
    <div class="tag">We'd rather show you nothing than junk.</div>
  </div>
</div>

<script>
const SHARED = __SHARED_DATA__;
const DEALS = __DEALS_DATA__;
const $ = id => document.getElementById(id);
const f = $('f');
const esc = s => (s || '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function post(body) {
  return fetch('/api/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  }).then(r => r.json());
}

let baseNotes = [];
let shareUrl = null;
let state = {listings: [], total: 0, matched: 0, rejected: 0, failed: 0, checked: 0};

/* ---------- small UI helpers ---------- */

function setRule(mode, pct) {
  // mode: '' hidden | 'scan' indeterminate | 'progress' | 'done'
  const r = $('rule');
  r.className = 'rulewrap' + (mode ? ' on ' + mode : '');
  if (mode === 'progress') {
    const w = Math.max(0, Math.min(100, pct || 0));
    r.querySelector('.fill').style.width = w + '%';
    r.querySelector('.dot').style.left = 'calc(' + w + '% - ' + Math.round(9 * w / 100) + 'px)';
  } else {
    r.querySelector('.fill').style.width = '';
    r.querySelector('.dot').style.left = '';
  }
}

function setStatus(html) {
  const el = $('status');
  el.innerHTML = html || '';
  el.style.display = html ? 'flex' : 'none';
}

function setHead(h1, sub) {
  $('rhead').classList.add('show');
  $('rh1').innerHTML = h1;
  $('rsub').innerHTML = sub || '';
}

function showNotes(notes) {
  $('notes').innerHTML = baseNotes.concat(notes || [])
    .map(n => '<div class="note">' + esc(n) + '</div>').join('');
}

function showSpec(i, ai) {
  const el = $('spec'), noteEl = $('specNote');
  if (!ai || !i) { el.classList.remove('show'); noteEl.style.display = 'none'; return; }
  const t = ['<span class="k">Reading it as</span> <b>' + esc(i.search_terms) + '</b>'];
  const lo = i.price_min_euro, hi = i.price_max_euro;
  if (lo != null && hi != null) t.push('<b>&euro;' + lo + ' to &euro;' + hi + '</b>');
  else if (hi != null) t.push('<b>under &euro;' + hi + '</b>');
  else if (lo != null) t.push('<b>from &euro;' + lo + '</b>');
  if (i.distance_meters) t.push('<b>within ' + (i.distance_meters / 1000) + ' km</b>');
  const shortReqs = [], longReqs = [];
  (i.requirements || []).forEach(r => (r.length > 45 ? longReqs : shortReqs).push(r));
  if (shortReqs.length) {
    t.push('<span class="k">must be</span> ' + shortReqs.map(r => '<b>' + esc(r) + '</b>').join(', '));
  }
  el.innerHTML = t.join('<span class="sep">|</span>');
  el.classList.add('show');
  noteEl.innerHTML = longReqs.map(esc).join(' &middot; ');
  noteEl.style.display = longReqs.length ? 'block' : 'none';
}

/* ---------- tally strip ---------- */

function buildTally(listings) {
  $('tally').innerHTML = listings.map(l =>
    '<i class="pend" id="t-' + esc(l.id) + '"></i>').join('');
  $('tallyCap').innerHTML = '1 square = 1 listing read &middot; <b class="k">black</b> match &middot; grey rejected';
  $('tallyRow').classList.add('show');
}

function setTally(id, cls) {
  const sq = $('t-' + id);
  if (sq) sq.className = cls;
}

function finalTallyCap(failed) {
  $('tallyCap').innerHTML =
    '<b class="r">red</b> best find &middot; <b class="k">black</b> match &middot; grey rejected' +
    (failed ? ' &middot; yellow unverified' : '');
}

/* ---------- cards ---------- */

function whyBlock(l) {
  if (l._deal) return '<div class="why"><i></i><span><b>Est. resale &euro;' +
    (+l.resale_low || 0) + ' to &euro;' + (+l.resale_high || 0) + '.</b> ' +
    esc(l.why || '') + '</span></div>';
  if (l._m) return '<div class="why"><i></i><span><b>Why it&#39;s here.</b> ' +
    (l.why ? esc(l.why) : 'Matches everything you asked for') + '.</span></div>';
  if (l._u) return '<div class="why"><i></i><span>The AI check failed for this one. Judge it yourself.</span></div>';
  if (l._pending) return '<div class="why"><i></i><span>Reading title, photos and description against your requirements&hellip;</span></div>';
  return '';
}

function rankText(l) {
  if (l._deal) return 'Spotted today';
  if (l._pending) return 'Reading…';
  if (l._best) return 'Best match';
  if (l._m) return 'Match ' + String(l._nr || 0).padStart(2, '0');
  if (l._u) return 'Not checked';
  if (l._r) return 'Rejected';
  return 'Listing';
}

function cardShell(l) {
  const cls = ['card'];
  if (l._deal) cls.push('deal');
  if (l._pending) cls.push('pending');
  if (l._best) cls.push('first');
  if (l._u) cls.push('un');
  if (l._r) cls.push('rejected');
  const priceNum = (l.price || '').replace(' (bid from)', '');
  const bid = /\(bid from\)/.test(l.price || '');
  return `
    <a class="${cls.join(' ')}" id="c-${esc(l.id)}" href="${esc(l.url)}" target="_blank" rel="noopener">
      <div class="ph">${l.image
        ? `<img src="${esc(l.image)}" alt="${esc(l.title)}" loading="lazy">`
        : '<div class="noimg">No photo</div>'}</div>
      <div class="body">
        <div class="rank"><span class="label" id="r-${esc(l.id)}">${rankText(l)}</span></div>
        <h3>${esc(l.title)}</h3>
        <div class="priceline">
          <span class="price num">${esc(priceNum)}${bid ? ' <span class="cur">bid</span>' : ''}</span>
          <span class="geo num">${esc(l.city)}${l.distance_km != null ? ' &middot; ' + l.distance_km + ' km' : ''}</span>
        </div>
        <div class="desc">${esc(l.description)}</div>
        <span id="w-${esc(l.id)}">${whyBlock(l)}</span>
      </div>
    </a>`;
}

function renderCards(listings, checking) {
  listings.forEach(l => { l._pending = checking; });
  $('results').innerHTML = listings.map(cardShell).join('');
}

function repaintCard(l) {
  const card = $('c-' + l.id);
  if (!card) return;
  card.className = 'card' + (l._pending ? ' pending' : '') + (l._best ? ' first' : '')
    + (l._u ? ' un' : '') + (l._r ? ' rejected' : '');
  $('r-' + l.id).textContent = rankText(l);
  $('w-' + l.id).innerHTML = whyBlock(l);
}

/* ---------- live counts ---------- */

function updateCount(checking) {
  const s = state;
  if (!checking) {
    setHead(s.listings.length + ' listings <span class="of">/ ' + s.total.toLocaleString('en') + '</span>',
            'keyword search &middot; AI filtering is off');
    return;
  }
  const left = s.listings.length - s.checked;
  if (left > 0) {
    setHead(s.matched + (s.matched === 1 ? ' match' : ' matches') + ' <span class="of">so far</span>',
            'reading ' + s.listings.length + ' of ' + s.total.toLocaleString('en') +
            ' listings &middot; ' + s.checked + ' done, ' + left + ' to go');
    setRule('progress', s.checked / s.listings.length * 100);
  } else {
    setHead(s.matched + (s.matched === 1 ? ' match' : ' matches') +
            ' <span class="of">/ ' + s.total.toLocaleString('en') + '</span>',
            s.listings.length + ' read closely by AI');
    setRule('done');
  }
}

/* ---------- verdicts ---------- */

function applyVerdict(l, why, failed) {
  state.checked++;
  l._pending = false;
  if (failed) {
    state.failed++; l._u = 1;
    setTally(l.id, 'un');
  } else if (why !== undefined) {
    state.matched++; l._m = 1; l._nr = state.matched;
    if (why) l.why = why;
    setTally(l.id, 'm');
  } else {
    state.rejected++; l._r = 1;
    setTally(l.id, '');
  }
  repaintCard(l);
}

function finishOrder(listings) {
  // matched first, then unchecked, rejected last; first match becomes the best find
  const res = $('results');
  const matched = listings.filter(l => l._m);
  const order = matched.concat(listings.filter(l => l._u), listings.filter(l => l._r));
  for (const l of order) {
    const c = $('c-' + l.id);
    if (c) res.appendChild(c);
  }
  matched.forEach((l, i) => { l._nr = i + 1; });
  if (matched.length) {
    matched[0]._best = 1;
    setTally(matched[0].id, 'best');
  }
  matched.forEach(repaintCard);
  finalTallyCap(state.failed);
}

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

/* ---------- sharing ---------- */

function orderResults(listings, checking) {
  if (!checking) return listings.map(l => ({...l, matched: false, rejected: false, unchecked: false}));
  return listings.filter(l => l._m).concat(listings.filter(l => l._u), listings.filter(l => l._r))
    .map(l => ({...l, matched: !!l._m, rejected: !!l._r, unchecked: !!l._u}));
}

async function saveSearch(payload) {
  try {
    const r = await post(payload);
    if (r && r.id) {
      shareUrl = location.origin + r.url;
      // Every search is saved automatically, so the address bar itself
      // becomes the shareable link, not just the copy button.
      history.pushState({shareId: r.id}, '', r.url);
      $('shareRow').style.display = 'flex';
    }
  } catch (err) { /* sharing is best-effort, never blocks a search */ }
}

$('shareBtn').addEventListener('click', async () => {
  if (!shareUrl) return;
  const btn = $('shareBtn');
  try {
    await navigator.clipboard.writeText(shareUrl);
    const orig = btn.textContent;
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  } catch (err) {
    prompt('Copy this link:', shareUrl);
  }
});

/* ---------- main flow ---------- */

f.addEventListener('submit', async e => {
  e.preventDefault();
  const q = $('q').value.trim();
  if (!q) return;
  const pc = $('pc').value.trim();
  localStorage.setItem('pc', pc);
  // Starting a fresh search leaves any previously shared URL behind;
  // the address bar gets the new search's own link once it's saved.
  if (location.pathname !== '/') history.pushState({}, '', '/');
  document.body.classList.add('run');
  $('go').disabled = true;
  $('results').innerHTML = '';
  $('notes').innerHTML = '';
  $('rhead').classList.remove('show');
  $('tallyRow').classList.remove('show');
  $('shareRow').style.display = 'none';
  $('spec').classList.remove('show');
  $('specNote').style.display = 'none';
  shareUrl = null;
  hideNoMatchesModal();
  setRule('scan');
  baseNotes = [];
  const t0 = Date.now();
  let stage = 'Reading your wish';
  let stageNote = 'turning it into a Marktplaats search';
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - t0) / 1000);
    setStatus('<b>' + stage + '</b><span>' + stageNote + ' &middot; ' + s + ' s' +
      (s > 30 ? ' &middot; free AI can take a minute' : '') + '</span>');
  }, 1000);
  setStatus('<b>' + stage + '</b><span>' + stageNote + '</span>');
  try {
    const p = await post({action: 'parse', wish: q});
    if (p.error) throw new Error(p.error);
    baseNotes = p.notes || [];
    showSpec(p.parsed, p.ai);
    showNotes([]);
    stage = 'Searching Marktplaats'; stageNote = 'pulling in every candidate';
    const d = await post({action: 'find', wish: q, postcode: pc, parsed: p.parsed});
    if (d.error) throw new Error(d.error);
    baseNotes = baseNotes.concat(d.notes || []);
    showNotes([]);
    const listings = d.listings || [];
    const reqs = d.requirements || [];
    state = {listings: listings, total: d.total_on_marktplaats || listings.length,
             matched: 0, rejected: 0, failed: 0, checked: 0};
    const checking = p.ai && reqs.length > 0 && listings.length > 0;
    renderCards(listings, checking);
    if (checking) {
      buildTally(listings);
      setRule('progress', 0);
      stage = 'Reading listings'; stageNote = 'every one, against your requirements';
      updateCount(true);
      await checkAll(listings, reqs);
      finishOrder(listings);
      updateCount(true);
    } else {
      setRule(listings.length ? 'done' : '');
      updateCount(false);
    }
    setStatus('');
    if ((checking && state.matched === 0) || (!checking && listings.length === 0)) {
      showNoMatchesModal();
    }
    await saveSearch({
      action: 'save', wish: q, postcode: pc,
      interpreted: p.parsed || null, ai: !!p.ai, notes: baseNotes,
      scanned: state.listings.length, total_on_marktplaats: state.total,
      results: orderResults(state.listings, checking),
    });
  } catch (err) {
    setRule('');
    showNotes(['Error: ' + err.message]);
  } finally {
    clearInterval(tick);
    setStatus('');
    $('go').disabled = false;
  }
});

/* ---------- shared view ---------- */

function renderSharedResults(rec) {
  document.body.classList.add('run');
  $('q').value = rec.wish || '';
  fitQ();
  $('pc').value = rec.postcode || '';
  showSpec(rec.interpreted, rec.ai);
  baseNotes = (rec.notes || []).concat(['Shared search results. Click the vindje logo to start your own.']);
  showNotes([]);
  const results = (rec.results || []).map(l => ({...l,
    _m: l.matched ? 1 : 0, _r: l.rejected ? 1 : 0, _u: l.unchecked ? 1 : 0}));
  const matched = results.filter(l => l._m);
  matched.forEach((l, i) => { l._nr = i + 1; });
  if (matched.length) matched[0]._best = 1;
  $('results').innerHTML = results.map(cardShell).join('');
  const rejected = results.filter(l => l._r).length;
  const unchecked = results.filter(l => l._u).length;
  const total = rec.total_on_marktplaats;
  if (matched.length + rejected + unchecked > 0) {
    setHead(matched.length + (matched.length === 1 ? ' match' : ' matches') +
            (total != null ? ' <span class="of">/ ' + total.toLocaleString('en') + '</span>' : ''),
            results.length + ' read closely by AI');
    $('tally').innerHTML = results.map(l => '<i class="' +
      (l._best ? 'best' : l._m ? 'm' : l._u ? 'un' : '') + '" id="t-' + esc(l.id) + '"></i>').join('');
    finalTallyCap(unchecked);
    $('tallyRow').classList.add('show');
  } else {
    setHead(results.length + ' listings' +
            (total != null ? ' <span class="of">/ ' + total.toLocaleString('en') + '</span>' : ''),
            'keyword search &middot; AI filtering was off');
  }
  setRule(results.length ? 'done' : '');
}

function renderDeals() {
  // "Today's finds": the morning deal-hunt, shown on an otherwise empty
  // homepage and hidden as soon as the visitor starts their own search.
  if (!DEALS || SHARED) return;
  const cats = (DEALS.categories || []).filter(c => (c.finds || []).length > 0);
  if (!cats.length) return;
  let when = '';
  try {
    when = ' on ' + new Date(DEALS.ts * 1000)
      .toLocaleDateString('en-GB', {day: 'numeric', month: 'short'});
  } catch (err) {}
  $('deals').innerHTML =
    '<div class="dhead"><h2>Today\u2019s finds<span class="sq"></span></h2></div>' +
    '<div class="dsub">Undervalued items our AI spotted' + when +
    ': asking under &euro;250, estimated to resell for &euro;500 or more.' +
    ' Estimates are AI-made; judge for yourself before buying.</div>' +
    cats.map(c =>
      '<div class="cat"><span class="label">' + esc(c.label) + '</span>' +
      '<span class="n num">' + c.finds.length +
      (c.finds.length === 1 ? ' find' : ' finds') + '</span></div>' +
      '<div class="dgrid">' +
      c.finds.map(l => cardShell({...l, _deal: 1})).join('') + '</div>'
    ).join('');
  $('dealsSec').classList.add('show');
}
renderDeals();

if (SHARED) {
  if (SHARED.error) {
    document.body.classList.add('run');
    showNotes([SHARED.error]);
  } else {
    renderSharedResults(SHARED);
  }
} else {
  $('pc').value = localStorage.getItem('pc') || '';
}

/* ---------- misc wiring ---------- */

function fitQ() {
  const q = $('q');
  q.style.height = 'auto';
  q.style.height = q.scrollHeight + 'px';
}
$('q').addEventListener('input', fitQ);

document.querySelectorAll('.ex').forEach(b => b.addEventListener('click', () => {
  const q = $('q');
  q.value = b.dataset.q || b.textContent.trim();
  fitQ();
  q.focus();
}));

$('q').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    f.requestSubmit();
  }
});

function showNoMatchesModal() { $('modalOverlay').classList.add('show'); }
function hideNoMatchesModal() { $('modalOverlay').classList.remove('show'); }
$('modalClose').addEventListener('click', hideNoMatchesModal);
$('modalEdit').addEventListener('click', () => { hideNoMatchesModal(); $('q').focus(); });
$('modalOverlay').addEventListener('click', e => {
  if (e.target.id === 'modalOverlay') hideNoMatchesModal();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') hideNoMatchesModal();
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------- static pages
#
# The secondary pages share one shell (chrome, tokens, typography) so the
# design system stays in one place; each page supplies its meta tags and body.

PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
__META__
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect x='18' y='18' width='64' height='64' fill='%23d6001c'/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --ink: #0f0f10; --grey: #6d6d73; --faint: #a4a4ab;
    --hair: #e4e4e8; --panel: #f7f7f8;
    --red: #d6001c; --blue: #1d4e9e; --yellow: #f0c114;
  }
  * { box-sizing: border-box; margin: 0; }
  ::selection { background: var(--ink); color: #fff; }
  html { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
  body { background: #fff; color: var(--ink);
         font-family: 'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif;
         font-size: 15px; line-height: 1.5; min-height: 100vh;
         display: flex; flex-direction: column; }
  a { color: inherit; text-decoration: none; }
  .num { font-variant-numeric: tabular-nums; }
  .label { font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; }
  .wrap { max-width: 1264px; width: 100%; margin: 0 auto; padding: 0 24px; }
  .sq { display: inline-block; width: .55em; height: .55em; background: var(--red); }
  :focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }

  .top { border-bottom: 1px solid var(--hair); }
  .top-in { display: flex; align-items: center; height: 64px; }
  .wordmark { font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
  .wordmark .sq { width: 8px; height: 8px; margin-left: 2px; }
  .nav { margin-left: auto; display: flex; gap: 26px; font-size: 13px; color: var(--grey); }
  .nav a:hover { color: var(--ink); }
  main { flex: 1 0 auto; }

  .phead { padding-top: 52px; padding-bottom: 26px; }
  .phead h1 { font-size: 36px; font-weight: 700; letter-spacing: -.03em; }
  .phead h1 .sq { width: 8px; height: 8px; margin-left: 3px; }
  .phead .sub { margin-top: 10px; font-size: 15.5px; color: var(--grey); max-width: 640px;
                line-height: 1.6; }
  .rulewrap { position: relative; height: 3px; background: var(--ink); }
  .rulewrap i { position: absolute; top: -3px; left: 25%; width: 9px; height: 9px;
                background: var(--red); }
  .section { padding-top: 30px; }
  .btn { display: inline-block; border: 1px solid var(--ink); padding: 10px 24px;
         font-size: 13.5px; font-weight: 500; background: #fff; }
  .btn.solid { background: var(--ink); color: #fff; }
  .btn.solid:hover { background: #2a2a2e; }
  .aside { margin-top: 16px; font-size: 12.5px; color: var(--faint); max-width: 560px;
           line-height: 1.55; }

  /* how-it-works steps */
  .steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
           background: var(--hair); border: 1px solid var(--hair); }
  .step { background: #fff; padding: 24px 26px 28px; }
  .step .label { color: var(--red); }
  .step h3 { margin: 10px 0 8px; font-size: 17px; font-weight: 600; letter-spacing: -.01em; }
  .step p { font-size: 14px; color: var(--grey); line-height: 1.6; }
  @media (max-width: 800px) { .steps { grid-template-columns: 1fr; } }

  /* credits rows */
  .crows { border-top: 1px solid var(--ink); }
  .crow { display: grid; grid-template-columns: 200px 1fr; gap: 24px; padding: 18px 0;
          border-bottom: 1px solid var(--hair); }
  .crow .label { color: var(--ink); padding-top: 2px; }
  .crow p { font-size: 14.5px; color: var(--grey); line-height: 1.6; max-width: 720px; }
  .crow p a { color: var(--ink); border-bottom: 1px solid var(--hair); }
  .crow p a:hover { border-color: var(--ink); }
  @media (max-width: 640px) { .crow { grid-template-columns: 1fr; gap: 6px; } }

  /* history rows */
  .hrows { border-top: 1px solid var(--ink); }
  .hrow { display: flex; align-items: baseline; gap: 24px; padding: 14px 4px;
          border-bottom: 1px solid var(--hair); }
  .hrow:hover { background: var(--panel); }
  .hrow .hwish { flex: 1; min-width: 0; font-weight: 500; font-size: 14.5px;
                 line-height: 1.45; overflow-wrap: break-word; }
  .hrow .hmeta { flex: none; color: var(--grey); font-size: 13px; white-space: nowrap; }
  .empty { padding: 48px 0; color: var(--grey); font-size: 14.5px; }

  footer { flex-shrink: 0; margin-top: 64px; border-top: 1px solid var(--hair); }
  .foot-in { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 22px;
             padding-top: 24px; padding-bottom: 30px; color: var(--faint); font-size: 12.5px; }
  .foot-links { margin-left: auto; display: flex; gap: 22px; }
  .foot-links a:hover { color: var(--ink); }
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
</style>
</head>
<body>
<header class="top"><div class="wrap top-in">
  <a class="wordmark" href="/">vindje<span class="sq"></span></a>
  <nav class="nav">
    <a href="/how-it-works">How it works</a>
    <a href="/history">History</a>
    <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
  </nav>
</div></header>
<main>
__BODY__
</main>
<footer><div class="wrap foot-in">
  <span>We'd rather show you nothing than junk.</span>
  <nav class="foot-links">
    <a href="/how-it-works">How it works</a>
    <a href="/history">History</a>
    <a href="/credits">Credits</a>
    <a href="https://timetuna.com/pavel" target="_blank" rel="noopener">Contact</a>
  </nav>
</div></footer>
</body>
</html>"""


def _page(meta, body):
    return PAGE_SHELL.replace("__META__", meta.strip()).replace("__BODY__", body.strip())


HOW_IT_WORKS_HTML = _page("""
<title>How vindje.com's AI Search Works &middot; Marktplaats</title>
<meta name="description" content="See how vindje.com turns a plain-language wish into a Marktplaats search, then uses AI to read every listing and keep only the ones that really match.">
<link rel="canonical" href="__ORIGIN__/how-it-works">
<meta property="og:type" content="website">
<meta property="og:site_name" content="vindje.com">
<meta property="og:title" content="How vindje.com's AI Search Works &middot; Marktplaats">
<meta property="og:description" content="See how vindje.com turns a plain-language wish into a Marktplaats search, then uses AI to keep only the listings that really match.">
<meta property="og:url" content="__ORIGIN__/how-it-works">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="How vindje.com's AI Search Works &middot; Marktplaats">
<meta name="twitter:description" content="See how vindje.com turns a plain-language wish into a Marktplaats search, then keeps only the listings that really match.">
<meta name="theme-color" content="#ffffff">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"vindje.com","item":"__ORIGIN__/"},{"@type":"ListItem","position":2,"name":"How it works","item":"__ORIGIN__/how-it-works"}]}
</script>
""", """
<section class="phead wrap">
  <h1>How vindje works<span class="sq"></span></h1>
  <p class="sub">Marktplaats is full of listings that almost fit. vindje reads every one
     of them for you, like a friend who knows exactly what you're looking for, and
     shows you only the ones that do.</p>
</section>
<div class="wrap"><div class="rulewrap"><i></i></div></div>
<section class="section wrap">
  <div class="steps">
    <div class="step">
      <span class="label num">Step 01</span>
      <h3>Say it in plain words</h3>
      <p>Describe your wish however it comes to mind, in any language: "a wooden
         closet with drawers, about 2 m tall, within 15 minutes driving, max
         &euro;150." An AI turns that into a real Marktplaats search: Dutch
         keywords, a price range, and a search radius.</p>
    </div>
    <div class="step">
      <span class="label num">Step 02</span>
      <h3>It searches Marktplaats</h3>
      <p>vindje queries Marktplaats' own search directly and pulls in every
         listing that could plausibly match: titles, descriptions, photos,
         prices, and distance, all at once.</p>
    </div>
    <div class="step">
      <span class="label num">Step 03</span>
      <h3>It keeps only real matches</h3>
      <p>The AI checks every result against what you actually asked for: size,
         condition, features, whatever you mentioned. Only listings that hold up
         are shown, each with a one-line reason why. Rejections stay visible, so
         you can double-check.</p>
    </div>
  </div>
  <div class="section">
    <a class="btn solid" href="/">Try a search</a>
    <p class="aside">No account needed. Every search talks to Marktplaats live;
       a completed search is saved so you can share a link showing anyone
       exactly what you saw.</p>
  </div>
</section>
""")


CREDITS_HTML = _page("""
<title>Credits &middot; vindje.com</title>
<meta name="description" content="Who and what made vindje.com happen: the idea, the model choices, and the name.">
<link rel="canonical" href="__ORIGIN__/credits">
<meta property="og:type" content="website">
<meta property="og:site_name" content="vindje.com">
<meta property="og:title" content="Credits &middot; vindje.com">
<meta property="og:description" content="Who and what made vindje.com happen: the idea, the model choices, and the name.">
<meta property="og:url" content="__ORIGIN__/credits">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Credits &middot; vindje.com">
<meta name="twitter:description" content="Who and what made vindje.com happen: the idea, the model choices, and the name.">
<meta name="theme-color" content="#ffffff">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"vindje.com","item":"__ORIGIN__/"},{"@type":"ListItem","position":2,"name":"Credits","item":"__ORIGIN__/credits"}]}
</script>
""", """
<section class="phead wrap">
  <h1>Credits<span class="sq"></span></h1>
  <p class="sub">vindje came together as a mix of ideas, tinkering, and a little AI
     help along the way. Who and what gets the credit:</p>
</section>
<div class="wrap"><div class="rulewrap"><i></i></div></div>
<section class="section wrap">
  <div class="crows">
    <div class="crow">
      <span class="label">The idea</span>
      <p>The idea belongs to Robin, from
         <a href="https://www.linkedin.com/feed/update/urn:li:activity:7495530682232954880/?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%287495539903926292481%2Curn%3Ali%3Aactivity%3A7495530682232954880%29" target="_blank" rel="noopener">his reply in this LinkedIn thread</a>.</p>
    </div>
    <div class="crow">
      <span class="label">The model</span>
      <p>Phanos suggested moving from free OpenRouter models to Claude Haiku,
         and later to GPT 5.6 Luna.</p>
    </div>
    <div class="crow">
      <span class="label">The name</span>
      <p>Claude suggested the name vindje.com.</p>
    </div>
  </div>
  <p class="aside">Know something that belongs here?
     <a href="https://timetuna.com/pavel" target="_blank" rel="noopener" style="color:var(--ink);border-bottom:1px solid var(--hair)">Let us know</a>.</p>
</section>
""")


HISTORY_HTML = _page("""
<title>Search History &middot; vindje.com</title>
<meta name="description" content="Every search run on vindje.com, newest first. Open any one of them to see the exact results it found.">
<link rel="canonical" href="__ORIGIN__/history">
<meta name="robots" content="noindex, follow">
<meta name="theme-color" content="#ffffff">
""", """
<section class="phead wrap">
  <h1>Search history<span class="sq"></span></h1>
  <p class="sub">Every search anyone has run, newest first. Open one to see the exact
     results it found. Searches aren't tied to any account, so this is everyone's.</p>
</section>
<div class="wrap"><div class="rulewrap"><i></i></div></div>
<section class="section wrap">
__ENTRIES__
</section>
""")


ROBOTS_TXT = """User-agent: *
Allow: /

Sitemap: __ORIGIN__/sitemap.xml
"""

SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>__ORIGIN__/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>
  <url><loc>__ORIGIN__/how-it-works</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>
  <url><loc>__ORIGIN__/credits</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>
</urlset>
"""


def render_history(entries, origin=""):
    """Render the /history page listing every saved search, newest first."""
    if not entries:
        inner = '<p class="empty">No searches yet. Run one to see it here.</p>'
    else:
        items = []
        for e in entries:
            share_id = str(e.get("id") or "")
            if not share_id:
                continue
            wish = html.escape(str(e.get("wish") or "")[:500])
            path = "/s/" + share_id
            count = e.get("count")
            ts = e.get("ts")
            when = ""
            if isinstance(ts, (int, float)):
                when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b %Y, %H:%M")
            meta_bits = [html.escape(b) for b in
                         (when, f"{count} results" if count is not None else "") if b]
            meta = " &middot; ".join(meta_bits)
            items.append(
                f'<a class="hrow" href="{html.escape(path)}">'
                f'<span class="hwish">{wish}</span>'
                f'<span class="hmeta num">{meta}</span></a>'
            )
        inner = '<div class="hrows">' + "".join(items) + "</div>"
    return HISTORY_HTML.replace("__ENTRIES__", inner).replace("__ORIGIN__", origin)


def render_page(record, origin="", error=None, deals=None):
    """Render the app shell, optionally pre-loaded with a saved (shared)
    search and/or the day's deal-hunt finds."""
    if error:
        shared_json = json.dumps({"error": error})
    elif record:
        shared_json = json.dumps({
            "wish": record.get("wish"),
            "postcode": record.get("postcode"),
            "interpreted": record.get("interpreted"),
            "ai": record.get("ai"),
            "notes": record.get("notes") or [],
            "results": record.get("results") or [],
            "total_on_marktplaats": record.get("total_on_marktplaats"),
        })
    else:
        shared_json = "null"
    return (HTML.replace("__SHARED_DATA__", shared_json)
                .replace("__DEALS_DATA__", json.dumps(deals) if deals else "null")
                .replace("__ORIGIN__", origin))


# WSGI application: GET -> the page, POST -> a search. Vercel's Python
# runtime picks up the top-level `app` in a root app.py automatically;
# locally the __main__ block below serves the same app.
def app(environ, start_response):
    req_id = _new_req_id()
    t0 = time.time()
    if environ.get("REQUEST_METHOD") == "POST":
        action = "-"
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            payload = json.loads(environ["wsgi.input"].read(length).decode())
            wish = (payload.get("wish") or "").strip()
            postcode = (payload.get("postcode") or "").strip()
            action = (payload.get("action") or "").strip() or "pipeline"
            log.info("[%s] POST action=%s wish=%r postcode=%s",
                     req_id, action, _preview(wish, 150), postcode)
            if action == "check":
                # validate one batch of listings against the requirements
                requirements = [str(r) for r in (payload.get("requirements") or [])]
                items = [i for i in (payload.get("listings") or [])
                         if isinstance(i, dict)]
                if not items:
                    raise ValueError("No listings to check")
                matches = _filter_chunk(requirements, items, 0, req_id=req_id)
                result = {"matches": {str(items[n].get("id")): why
                                      for n, why in matches.items()}}
            elif action == "save":
                share_id = save_search(payload)
                result = {"id": share_id, "url": "/s/" + share_id}
            elif not wish:
                raise ValueError("Empty search")
            elif action == "parse":
                parsed, notes = interpret(wish, req_id=req_id)
                result = {"ai": bool(parsed), "parsed": parsed, "notes": notes}
            elif action == "find":
                # search Marktplaats only — fast, no AI calls
                terms, distance, pmin, pmax, reqs, notes = search_params(
                    payload.get("parsed"), wish, postcode)
                listings, total = search_marktplaats(
                    terms, postcode=postcode, distance_meters=distance,
                    price_min_euro=pmin, price_max_euro=pmax, req_id=req_id)
                result = {"listings": listings, "total_on_marktplaats": total,
                          "requirements": reqs, "notes": notes}
            elif action == "results":
                result = smart_search(wish, postcode,
                                      parsed=payload.get("parsed"), req_id=req_id)
            else:  # single-call pipeline (curl-friendly)
                result = smart_search(wish, postcode, req_id=req_id)
            body = json.dumps(result).encode()
            status = "200 OK"
        except Exception as e:
            log.warning("[%s] POST action=%s FAILED after %.2fs: %s",
                        req_id, action, time.time() - t0, e)
            body = json.dumps({"error": str(e)}).encode()
            status = "500 Internal Server Error"
        log.info("[%s] POST action=%s -> %s in %.2fs, %d bytes",
                 req_id, action, status, time.time() - t0, len(body))
        headers = [("Content-Type", "application/json")]
    else:
        path = (environ.get("PATH_INFO") or "/").rstrip("/") or "/"
        scheme = environ.get(
            "HTTP_X_FORWARDED_PROTO", environ.get("wsgi.url_scheme", "https")
        ).split(",")[0].strip()
        host = environ.get("HTTP_HOST") or environ.get("SERVER_NAME") or "localhost"
        origin = f"{scheme}://{host}"
        status = "200 OK"
        if path == "/robots.txt":
            body = ROBOTS_TXT.replace("__ORIGIN__", origin).encode()
            headers = [("Content-Type", "text/plain; charset=utf-8")]
        elif path == "/sitemap.xml":
            body = SITEMAP_XML.replace("__ORIGIN__", origin).encode()
            headers = [("Content-Type", "application/xml; charset=utf-8")]
        elif path == "/how-it-works":
            body = HOW_IT_WORKS_HTML.replace("__ORIGIN__", origin).encode()
            headers = [("Content-Type", "text/html; charset=utf-8")]
        elif path == "/credits":
            body = CREDITS_HTML.replace("__ORIGIN__", origin).encode()
            headers = [("Content-Type", "text/html; charset=utf-8")]
        elif path == "/history":
            try:
                entries = get_history()
            except Exception:
                entries = []
            body = render_history(entries, origin=origin).encode()
            headers = [("Content-Type", "text/html; charset=utf-8")]
        elif path.startswith("/s/") and len(path) > 3:
            try:
                record = get_search(path[3:])
            except Exception:
                record = None
            if record:
                body = render_page(record, origin=origin).encode()
            else:
                body = render_page(None, origin=origin, error="Shared search not found.").encode()
                status = "404 Not Found"
            headers = [("Content-Type", "text/html; charset=utf-8")]
        else:
            body = render_page(None, origin=origin, deals=get_deals()).encode()
            headers = [("Content-Type", "text/html; charset=utf-8")]
        log.info("[%s] GET %s -> %s in %.2fs, %d bytes",
                 req_id, path, status, time.time() - t0, len(body))
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

    print(f"vindje.com → http://localhost:{PORT}")
    if not OPENROUTER_API_KEY:
        print("!! OPENROUTER_API_KEY not set: plain search only, no AI. "
              "Get a key (with credits) at https://openrouter.ai/keys")
    make_server("", PORT, app, server_class=ThreadingWSGIServer,
                handler_class=QuietHandler).serve_forever()
