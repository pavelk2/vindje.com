#!/usr/bin/env python3
"""
Daily deal hunter for vindje.com: scans Marktplaats for undervalued
items — asking price under €250 that an expert would expect to resell
for €500+ — and saves the day's finds so the homepage can show them.

Pipeline (reuses app.py's LLM + search + Redis helpers):
  1. Search Marktplaats nationwide for each category's brand queries
     (vintage racing bikes, designer lamps, design chairs, Mac minis),
     capped at €250 asking price.
  2. An LLM values every listing: is it a genuine, complete item from a
     target brand (not a replica, part, or accessory), what would it
     realistically resell for on the Dutch market, and is the upside
     real? Only finds valued at €500+ (conservative low end) survive.
  3. The result is stored in Upstash Redis under deals:latest (and a
     dated deals:<YYYY-MM-DD> copy), which the homepage renders as
     "Today's finds".

Run it manually:
  OPENROUTER_API_KEY=sk-or-... python3 deals.py --dry-run   # print only
  OPENROUTER_API_KEY=... UPSTASH_REDIS_REST_URL=... \
    UPSTASH_REDIS_REST_TOKEN=... python3 deals.py           # save too

In production a GitHub Actions cron runs this every morning at 8:00
Amsterdam time (see .github/workflows/daily-deals.yml).
"""

import argparse
import difflib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app import (DEALS_KEY, OPENROUTER_API_KEY, llm_json, search_marktplaats,
                 upstash_command)

# ---------------------------------------------------------------- what to hunt

PRICE_MAX_EURO = 250    # asking price cap: "costs under €250..."
RESALE_MIN_EURO = 500   # "...with good reason to resell for €500+"
FINDS_PER_CATEGORY = 8  # keep at most this many finds per category

CATEGORIES = [
    {
        "key": "bikes",
        "label": "Vintage racing bikes",
        "queries": ["koga miyata racefiets", "rih racefiets", "gitane racefiets",
                    "peugeot racefiets vintage", "raleigh racefiets", "bianchi racefiets"],
        "target": ("a complete, ridable vintage/classic racing bike from a quality "
                   "brand such as RIH, Peugeot, Gitane, Koga Miyata, Raleigh or "
                   "Bianchi, in good original condition (bikes needing a full "
                   "restoration, bare frames, kids' bikes and city bikes don't count)"),
    },
    {
        "key": "lamps",
        "label": "Designer lamps",
        "queries": ["louis poulsen lamp", "artemide lamp"],
        "target": ("a genuine designer lamp by Louis Poulsen or Artemide (an "
                   "original, not a replica, 'in de stijl van' lookalike, or a "
                   "loose shade/part), in working, sellable condition"),
    },
    {
        "key": "chairs",
        "label": "Design chairs",
        "queries": ["vitra stoel", "herman miller stoel", "herman miller bureaustoel"],
        "target": ("a genuine design chair by Vitra or Herman Miller (an original, "
                   "not a replica or lookalike), in good, sellable condition"),
    },
    {
        "key": "macmini",
        "label": "Mac mini",
        "queries": ["apple mac mini"],
        "target": ("a working Apple Mac mini computer (the machine itself, not an "
                   "accessory, mount, or broken/parts unit); only recent models "
                   "with Apple Silicon (M1/M2/M4) resell above €500 — old Intel "
                   "Mac minis are nearly worthless, reject them"),
    },
]

# ---------------------------------------------------------------- valuation

VALUE_PROMPT = """You are an expert reseller valuing Dutch classifieds listings.
The buyer hunts for: %s.

Below are numbered listings (title | asking price | description | attributes, in Dutch).
For each, decide whether it is genuinely the target item (reject replicas, lookalikes,
'stijl van' / 'geïnspireerd' items, spare parts, bare frames, shades, accessories,
defective units, and wrong kinds of item) and estimate what it would REALISTICALLY
resell for on the Dutch second-hand market (Marktplaats/Catawiki), as a conservative
low–high range in euros. Be skeptical: when the text leaves brand, model, originality
or condition unclear, value it low.

Keep ONLY listings where the conservative LOW end of your resale estimate is at least
€%d AND at least twice the asking price. Reply with ONLY JSON:
{"finds": [{"n": <listing number>, "resale_low": <euro>, "resale_high": <euro>,
            "why": "<max 15 words, English: what makes this undervalued>"}]}
If nothing qualifies, reply {"finds": []}."""

VALUE_CHUNK = 12  # listings per LLM call; chunks are valued concurrently


def parse_asking_price(price_str):
    """€-string from app.format_price -> euros (int), or None if no fixed
    number (pure bidding / on request / see description). '€179 (bid from)'
    counts: the bid floor is the effective asking price."""
    m = re.match(r"€([\d.]+)", str(price_str or ""))
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


def _value_chunk(target, listings, base):
    lines = []
    for i, l in enumerate(listings):
        desc = str(l.get("description") or "")[:300]
        attrs = "; ".join(str(a) for a in (l.get("attributes") or [])[:8])
        lines.append(f"[{base + i}] {l.get('title', '')} | asking {l.get('price', '?')}"
                     f" | {desc} | {attrs}")
    result = llm_json(
        [
            {"role": "system", "content": VALUE_PROMPT % (target, RESALE_MIN_EURO)},
            {"role": "user", "content": "\n".join(lines)},
        ],
        max_tokens=4000,
    )
    finds = {}
    for f in result.get("finds", []):
        try:
            n = int(f["n"])
            low = int(f["resale_low"])
            high = int(f["resale_high"])
        except (KeyError, TypeError, ValueError):
            continue
        if base <= n < base + len(listings):
            finds[n] = {"resale_low": low, "resale_high": high,
                        "why": str(f.get("why", ""))[:200]}
    return finds


def value_listings(target, listings):
    """LLM-value all listings concurrently. Returns {index: valuation}."""
    chunks = [(i, listings[i : i + VALUE_CHUNK])
              for i in range(0, len(listings), VALUE_CHUNK)]
    finds = {}
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(chunks)))) as ex:
        futures = {ex.submit(_value_chunk, target, chunk, base): base
                   for base, chunk in chunks}
        for fut in as_completed(futures):
            try:
                finds.update(fut.result())
            except Exception as e:
                print(f"  ! valuation batch failed: {e}", file=sys.stderr)
    return finds


_TITLE_WORD_RE = re.compile(r"[a-z0-9]+")

def _normalized_title(title):
    return " ".join(sorted(_TITLE_WORD_RE.findall(title.lower())))


def dedupe_relistings(listings, threshold=0.6):
    """Drop near-duplicate listings: same city + same asking price + a
    similar title almost always means the same seller relisting the same
    item under a new ad ID, which the exact-id `seen` set can't catch."""
    kept = []
    for l in listings:
        norm = _normalized_title(l["title"])
        is_dupe = False
        for k in kept:
            if k["city"] != l["city"] or k["asking_euro"] != l["asking_euro"]:
                continue
            ratio = difflib.SequenceMatcher(None, norm, k["_norm_title"]).ratio()
            if ratio >= threshold:
                is_dupe = True
                break
        if not is_dupe:
            l["_norm_title"] = norm
            kept.append(l)
    for l in kept:
        del l["_norm_title"]
    return kept


# ---------------------------------------------------------------- per category

def hunt_category(cat):
    """Search all of a category's queries, dedupe, value, and return the
    qualifying finds (best upside first) plus how many listings were scanned."""
    listings, seen = [], set()
    for q in cat["queries"]:
        try:
            found, _total = search_marktplaats(q, price_max_euro=PRICE_MAX_EURO)
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            continue
        for l in found:
            asking = parse_asking_price(l.get("price"))
            # no fixed price -> no way to establish the upside; skip
            if asking is None or asking == 0 or asking > PRICE_MAX_EURO:
                continue
            if l["id"] in seen:
                continue
            seen.add(l["id"])
            l["asking_euro"] = asking
            listings.append(l)
    before = len(listings)
    listings = dedupe_relistings(listings)
    if len(listings) < before:
        print(f"  dropped {before - len(listings)} likely relisting(s) of the same item")
    print(f"  {len(listings)} priced candidates from {len(cat['queries'])} queries")

    valuations = value_listings(cat["target"], listings)
    finds = []
    for i, v in valuations.items():
        l = listings[i]
        # re-check the bar in code; the model's word alone isn't enough
        if v["resale_low"] < max(RESALE_MIN_EURO, 2 * l["asking_euro"]):
            continue
        finds.append({**l, **v})
    finds.sort(key=lambda f: f["resale_low"] / f["asking_euro"], reverse=True)
    return finds[:FINDS_PER_CATEGORY], len(listings)


# ---------------------------------------------------------------- run + store

def run(categories=None, save=True):
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set — the valuation step needs an LLM.")
    cats = [c for c in CATEGORIES
            if categories is None or c["key"] in categories]
    if not cats:
        sys.exit(f"No such category; pick from: "
                 f"{', '.join(c['key'] for c in CATEGORIES)}")
    now = datetime.now(timezone.utc)
    record = {"date": now.strftime("%Y-%m-%d"), "ts": time.time(),
              "scanned": 0, "categories": []}
    for cat in cats:
        print(f"{cat['label']}...")
        finds, scanned = hunt_category(cat)
        record["scanned"] += scanned
        record["categories"].append(
            {"key": cat["key"], "label": cat["label"], "finds": finds})
        print(f"  -> {len(finds)} find(s)")
    if save:
        payload = json.dumps(record)
        upstash_command("SET", DEALS_KEY, payload)
        upstash_command("SET", f"deals:{record['date']}", payload)
        print(f"Saved to Redis as {DEALS_KEY} and deals:{record['date']}")
    return record


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Hunt undervalued Marktplaats items.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the finds as JSON, don't write to Redis")
    ap.add_argument("--category", action="append",
                    help="only run this category key (repeatable): "
                         + ", ".join(c["key"] for c in CATEGORIES))
    args = ap.parse_args()
    rec = run(categories=args.category, save=not args.dry_run)
    print(json.dumps(rec, indent=2, ensure_ascii=False))
