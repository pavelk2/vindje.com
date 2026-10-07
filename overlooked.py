#!/usr/bin/env python3
"""
Overlooked finds for vindje.com (issue #50, pilot: lamps): second-hand items
whose listing doesn't name the brand, but whose photos look like a valuable
model. Sellers who don't know what they have tend to ask the least.

The valuable models, with typical resale and buy prices, come from
data/vintage_resale_icons.json. A category here only says which part of that
file to use and how to search for it, so adding one is data, not code.

Daily hunt: search Marktplaats in a seller's plain words ("lamp contragewicht"),
drop listings that already name a brand or designer, show the model up to 3
large photos plus the listing text with every name cut out, and keep the
listings it recognizes at or under the model's buy price. The record goes to
Redis as overlooked:latest, and /flip shows the strong matches under
"Overlooked" (?possible=1 also shows possible ones, for testing). In
production a step in .github/workflows/daily-deals.yml runs it every morning.

  python3 overlooked.py --dry-run         # hunt and print, save nothing
  python3 overlooked.py                   # hunt and save to Redis

Accuracy test: the same recognition on listings whose title names the model,
so the answer is known but hidden. Listings that name the brand tend to be
written in a more expert style even with the names cut out, so --no-text
gives the cautious, photos-only number.

  python3 overlooked.py --collect lamps   # build data/overlooked_eval_lamps.json
  python3 overlooked.py --refresh lamps   # update photos and text of saved cases
  python3 overlooked.py --eval lamps      # ask the model, print the score
  python3 overlooked.py --eval lamps --no-text    # photos only
  python3 overlooked.py --eval lamps --limit 24   # cheap first look

Searches run one at a time with a pause in between. --eval only calls the LLM.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import (FLIP_PAGES, MODELS, OPENROUTER_API_KEY, OVERLOOKED_KEY, llm_json,
                 search_marktplaats, upstash_command)
from deals import dedupe_relistings, is_auction_lot

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_FILE = os.path.join(HERE, "data", "vintage_resale_icons.json")

# ---------------------------------------------------------------- categories

# key -> which items in MODELS_FILE ("source") and which /flip page it feeds.
# The flip page supplies the plain Dutch search and Marktplaats category ids.
#   search:  what sellers type when a model's own name finds nothing
#   aliases: names sellers use instead of the brand ("Kaiser Idell", not
#            "Fritz Hansen"); they count as naming the brand
#   looks:   what each model looks like in a photo. The data file's
#            descriptions are about value, and the model needs shapes.
#   copied:  models so widely copied that a photo can't tell an original from
#            a copy; they're never a "strong" match, so never public
#   designers: names that also give the model away; cut from the listing text
#            the model sees, and a listing that names one is skipped
#   queries: the daily hunt's searches, in the words of a seller who doesn't
#            know the brand: by type, by era, and by what the item looks like
CATEGORIES = {
    "lamps": {
        "source": "Lamps", "flip": "lamps", "noun": "lamps",
        "queries": ["vintage bureaulamp", "vintage vloerlamp", "vintage hanglamp",
                    "vintage wandlamp", "oude lamp", "retro lamp", "jaren 60 lamp",
                    "jaren 70 lamp", "lamp contragewicht", "glazen blokken lamp",
                    "opaline lamp", "industriele lamp scharnier", "lamp marmeren voet",
                    "paddenstoel lamp", "papieren lamp", "schalenlamp"],
        "designers": ["poul henningsen", "henningsen", "arne jacobsen", "jacobsen",
                      "verner panton", "panton", "verpan", "achille castiglioni",
                      "pier giacomo", "castiglioni", "vico magistretti", "magistretti",
                      "gae aulenti", "aulenti", "hoogervorst", "willem van oyen",
                      "van oyen", "christian dell", "isamu noguchi", "noguchi",
                      "mouille", "vitra"],
        "copied": ["Louis Poulsen PH5", "Flos Arco", "Louis Poulsen Panthella Floor",
                   "Noguchi Akari Floor (10A, UF4)", "Ingo Maurer Uchiwa",
                   "Serge Mouille Three-Arm Floor Lamp"],
        "looks": {
            "Louis Poulsen PH5": "pendant of three separate stacked curved shades with "
                "small inner reflectors, bulb hidden, flat and wide. Many Danish shell "
                "lamps and cheap copies look alike",
            "Louis Poulsen PH Artichoke": "pendant of many leaf-shaped metal blades in "
                "staggered rows, like an artichoke or pine cone",
            "Louis Poulsen PH 3/2 Table": "table lamp with three stacked opal or frosted "
                "glass shades on a curved stem and round base",
            "Louis Poulsen PH Snowball": "white ball-shaped pendant of eight stacked "
                "metal shades with open gaps between them",
            "Louis Poulsen AJ Floor": "slim floor lamp, tilted asymmetric cone shade on "
                "a thin straight stem, round base with a circular cut-out",
            "Louis Poulsen Panthella Floor": "mushroom floor lamp: wide dome shade on a "
                "trumpet-shaped stem that flares out to the floor",
            "Flos Arco": "huge steel arc reaching far out, dome reflector at the end, "
                "rectangular white marble block as the base",
            "Flos Taccia": "wide glass bowl resting on top of a ribbed cylindrical "
                "aluminium base, light shines up into the bowl",
            "Flos Snoopy": "table lamp: tilted enamel helmet-shaped shade on a round "
                "marble base, small glass disc on top, like a beagle's head",
            "Oluce Atollo 233": "table lamp of pure shapes: cylinder base, cone neck, "
                "half-sphere dome balanced on top",
            "Martinelli Luce Pipistrello": "table lamp with one white shade whose edge "
                "has four or five scalloped lobes like bat wings, on a telescopic "
                "stem and flared base",
            "Verner Panton VP Globe": "clear acrylic sphere pendant with coloured or "
                "metal reflector discs visible inside the clear ball",
            "Ingo Maurer Uchiwa": "rice paper stretched over radiating bamboo ribs, "
                "shaped like Japanese hand fans, often several together",
            "Raak Amsterdam Chartres": "ceiling or wall lamp built from thick chunky "
                "clear glass blocks set in a metal frame",
            "Anvia Counterbalance Lamp": "1950s Dutch wall, floor or ceiling lamp with "
                "a thin black or brass arm and a visible round counterweight at the "
                "other end of the arm; small cone shade",
            "Gispen Giso": "1930s lamp with a white opaline glass globe or shade on "
                "chrome or black tubular metal fittings",
            "Jielde Standard Floor Lamp": "French workshop lamp: thick enamelled metal "
                "tubes joined by round knuckle joints, conical metal shade, no "
                "counterweight and no visible wires, heavy round base",
            "Fritz Hansen Kaiser Idell 6631 Luxus": "Bauhaus desk lamp: conical "
                "metal shade on a short arm with a ball joint, round stepped base; "
                "no counterweight",
            "Noguchi Akari Floor (10A, UF4)": "white washi paper over thin bamboo or "
                "wire ribs, lantern or column shape, on thin metal legs",
            "Serge Mouille Three-Arm Floor Lamp": "black floor lamp with three long thin "
                "curved arms, each ending in a pointed, breast-shaped shade",
        },
        "search": {
            "Louis Poulsen PH 3/2 Table": "poulsen ph 3/2",
            "Louis Poulsen PH Snowball": "poulsen snowball",
            "Oluce Atollo 233": "atollo lamp",
            "Fritz Hansen Kaiser Idell 6631 Luxus": "kaiser idell",
            "Noguchi Akari Floor (10A, UF4)": "noguchi akari",
        },
        "aliases": {
            "Fritz Hansen Kaiser Idell 6631 Luxus": ["kaiser idell"],
            "Oluce Atollo 233": ["atollo"],
        },
    },
}

HUNT_PRICE_MAX = 250    # asking price cap, the same as the rest of /flip
HUNT_PRICE_MIN = 10     # €1 "n.o.t.k." placeholders aren't real prices
HUNT_MAX = 100          # photos sent to the model per category per day: the cost cap
EVAL_PER_MODEL = 5      # positives kept per model
EVAL_NEGATIVES = 30     # ordinary listings that name no listed brand
SEARCH_PAUSE_S = 2      # between Marktplaats searches: be gentle

# Words in a model name that say nothing about which model it is.
_GENERIC = {"lamp", "lamps", "floor", "table", "pendant", "desk", "wall", "light",
            "standard", "series", "the", "and", "with", "three", "arm"}
# "Nieuw" in a title means new retail stock, never a vintage find; "zo goed als
# nieuw" is only the condition of an old one.
_NEW_RE = re.compile(r"(?<!als )\bnieuwe?\b|\bnew\b")
# Brand words too common to mean the brand on their own ("Raak" alone does).
_BRAND_STOP = {"louis", "luce", "amsterdam"}
# Titles that aren't the lamp itself: copies, parts, wanted ads, books.
_REPLICA_RE = re.compile(r"replica|stijl|style|look ?a ?like|geinspireerd|inspired|"
                         r"kopie|copy|onderdel|kap\b|shade\b|gezocht|fitting|"
                         r"\bvoor\b|boek|book|poster", re.I)


def _norm(text):
    """Lowercase, accents stripped, only letters and digits: 'Jieldé' -> 'jielde'."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore")
    return re.sub(r"[^a-z0-9]+", " ", text.decode().lower()).strip()


def load_models(key):
    """The valuable models for one category, each with a display name, the words
    that would mean the seller already knows what it is, and prices."""
    with open(MODELS_FILE, encoding="utf-8") as f:
        items = json.load(f)["items"]
    cat = CATEGORIES[key]
    models = []
    for it in items:
        if it.get("category") != cat["source"]:
            continue
        brand, model = it["brand"], it["model"]
        words = [w for w in _norm(model).split() if w not in _GENERIC]
        # "PH 3/2" -> "ph32", matched with spaces squashed out ("PH 3 2", "PH3/2")
        # ("AJ" is too short to squash, so it only counts as a whole word)
        squashed = "".join(words)
        keys = [w for w in words if len(w) >= 3] + ([squashed] if squashed else [])
        brand_words = [w for w in _norm(brand).split()
                       if len(w) >= 4 and w not in _BRAND_STOP]
        name = f"{brand} {model}"
        aliases = [_norm(a) for a in cat.get("aliases", {}).get(name, [])]
        # plain words a seller would type: no "Table", "Floor (10A, UF4)"
        query = " ".join([brand] + [w for w in re.sub(r"\(.*?\)", "", model).split()
                                    if _norm(w) not in _GENERIC])
        models.append({
            "name": name,
            "query": cat.get("search", {}).get(name, query),
            "brand_keys": sorted({_norm(brand), *brand_words, *aliases}),
            "model_keys": sorted(set(keys)),
            "model_words": sorted(set(words + ([squashed] if squashed else []))),
            "look": cat.get("looks", {}).get(name, ""),
            "hint": it.get("description", ""),
            "resell_eur": it["resell_eur"],
            "buy_eur": it["buy_eur"],
        })
    return models


def _has(text, phrase):
    """Whole-word match of a normalized phrase in normalized text."""
    return bool(phrase) and f" {phrase} " in f" {text} "


def _has_key(text, key):
    """A model key in normalized text: as a whole word, or for keys of 3+
    characters also with the spaces squashed out ("ph 5" matches "ph5")."""
    if _has(text, key):
        return True
    return len(key) >= 3 and key in text.replace(" ", "")


def names_model(text, m):
    """True when the text names this model: its brand and its model name."""
    t = _norm(text)
    return (any(_has(t, b) for b in m["brand_keys"])
            and (not m["model_keys"] or any(_has_key(t, k) for k in m["model_keys"])))


def names_any_brand(text, models, designers=()):
    """True when the text names any listed brand, model or designer, i.e. the
    seller already knows what they have."""
    t = _norm(text)
    return (any(_has(t, _norm(d)) for d in designers)
            or any(any(_has(t, b) for b in m["brand_keys"])
                   or any(_has_key(t, k) for k in m["model_keys"] if len(k) >= 4)
                   for m in models))


_MODEL_NUMBER_RE = re.compile(r"\b(?!19\d\d\b|20\d\d\b)[a-z]?\d{3,4}\b")


def masked_text(listing, key, models, limit=400):
    """The listing's title and description with every brand, model, designer
    and model number cut out: what a seller who doesn't know the brand might
    write ("oude wandlamp met contragewicht, jaren 50")."""
    words = set(_norm(d) for d in CATEGORIES[key].get("designers", []))
    for m in models:
        words.update(m["brand_keys"])
        words.update(w for w in m["model_words"] if not (w.isdigit() and len(w) < 3))
    t = _norm(f"{listing.get('title', '')}. {listing.get('description', '')}")
    # "ph5" also cuts "ph 5": an optional space where letters meet digits
    names = "|".join(re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ?", w)
                     for w in sorted(words, key=len, reverse=True) if w)
    t = re.sub(rf"\b(?:{names})\b", " ", t)
    t = _MODEL_NUMBER_RE.sub(" ", t)
    return " ".join(t.split())[:limit]


# ---------------------------------------------------------------- recognition

RECOGNIZE_PROMPT = """You are an expert in vintage design %s. You see up to 3 photos of one
second-hand listing, plus the seller's Dutch text with all brand, model and designer names
cut out. The text can help ("contragewicht", "opaline glas", "jaren 50", a stamp under the
base), but the seller may be wrong, and the photos decide.

Valuable models to look for (name: what it looks like. Notes on value and originality):
%s

Decide which ONE model on the list the item in the photos is, or "unknown". Judge only what
you see: shape, proportions, materials, construction, stamps and labels. Sellers rarely
photograph stamps, so a missing stamp alone is no reason to doubt. Loose shades and parts
are "unknown". When the item looks like none of the models, answer "unknown". A different
type of lamp (table, floor, wall, pendant) than the model is never that model.
- "strong": the overall shape and its distinctive details clearly match the description,
  and nothing visible (cheap materials, wrong proportions, modern fittings) argues
  against it.
- "possible": it resembles the model, but the photo is unclear or it could be a copy or
  a similar design by another maker.

Reply with ONLY JSON:
{"match": "<exact name from the list, or unknown>", "confidence": "strong" or "possible",
 "why": "<max 15 words, English, no em dashes: what in the photos shows it>"}"""


def recognize(key, models, images, text=""):
    """Ask the model which listed model these photos (and the brand-free
    listing text) show. Returns
    {"match": name or None, "confidence": "strong"|"possible", "why": str}."""
    catalog = "\n".join(f"- {m['name']}: {m['look']}. {m['hint']}".replace(": . ", ": ")
                        for m in models)
    content = [{"type": "text",
                "text": f"Seller's text, names removed: {text or '(none)'}\nPhotos:"}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in images[:3]]
    result = llm_json(
        [
            {"role": "system",
             "content": RECOGNIZE_PROMPT % (CATEGORIES[key]["noun"], catalog)},
            {"role": "user", "content": content},
        ],
        max_tokens=400,
        # the free fallback can't be trusted with photos; a failed call is skipped
        models=MODELS[:1],
    )
    names = {m["name"] for m in models}
    match = str(result.get("match") or "").strip()
    confidence = "strong" if result.get("confidence") == "strong" else "possible"
    if match in CATEGORIES[key].get("copied", []):
        confidence = "possible"
    why = str(result.get("why") or "").replace("\u2014", ",").replace("\u2013", "-")
    return {"match": match if match in names else None,   # check it in code
            "confidence": confidence,
            "why": why[:200]}


# ---------------------------------------------------------------- eval: collect

def _eval_path(key):
    return os.path.join(HERE, "data", f"overlooked_eval_{key}.json")


def collect(key):
    """Build the test set: listings whose title names a listed model (the answer
    is known) plus ordinary ones that name none. Only the brand-free text is
    stored, so names can't leak into the test. Re-running tops up an existing
    set: only models with fewer than 3 cases are searched again."""
    models = load_models(key)
    page = FLIP_PAGES[CATEGORIES[key]["flip"]]
    designers = CATEGORIES[key].get("designers", [])
    cases = []
    if os.path.exists(_eval_path(key)):
        with open(_eval_path(key), encoding="utf-8") as f:
            cases = json.load(f)["cases"]
    have = Counter(c["truth"] for c in cases)
    seen = {c["id"] for c in cases}

    def add(l, truth):
        if l["id"] in seen or not l.get("images"):
            return False
        seen.add(l["id"])
        cases.append({"id": l["id"], "url": l["url"], "images": l["images"],
                      "text": masked_text(l, key, models), "truth": truth})
        return True

    for m in models:
        kept = have[m["name"]]
        if kept >= 3:
            print(f"  {m['name']}: {kept} (already collected)")
            continue
        try:
            found, _total = search_marktplaats(m["query"], limit=30)
        except Exception as e:
            print(f"  ! search '{m['query']}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            if kept >= EVAL_PER_MODEL:
                break
            if names_model(l["title"], m) and not _REPLICA_RE.search(_norm(l["title"])):
                kept += add(l, m["name"])
        note = "" if kept >= 3 else "  <- too few, check by hand"
        print(f"  {m['name']}: {kept}{note}")
        time.sleep(SEARCH_PAUSE_S)

    negatives = have["none"]
    found = []
    if negatives < EVAL_NEGATIVES:
        try:
            found, _total = search_marktplaats(page["fresh_query"], price_min_euro=20,
                                               price_max_euro=250, limit=60)
        except Exception as e:
            print(f"  ! negatives search failed: {e}", file=sys.stderr)
    for l in found:
        if negatives >= EVAL_NEGATIVES:
            break
        text = f"{l['title']} {l['description']}"
        if (l.get("category_id") in page["fresh_categories"]
                and not names_any_brand(text, models, designers)
                and not any(_has(_norm(text), _norm(w)) for w in page["watch"])):
            negatives += add(l, "none")
    print(f"  ordinary listings (negatives): {negatives}")
    _save_eval(key, cases)


def _save_eval(key, cases):
    """Write the cases back, keeping other top-level fields such as "note"."""
    data = {}
    if os.path.exists(_eval_path(key)):
        with open(_eval_path(key), encoding="utf-8") as f:
            data = json.load(f)
    data.update(category=key, collected=time.strftime("%Y-%m-%d"), cases=cases)
    with open(_eval_path(key), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    print(f"Saved {len(cases)} cases to {os.path.relpath(_eval_path(key), HERE)}")


def refresh(key):
    """Re-fetch the saved cases with the same searches and update their photos
    and brand-free text in place. Adds nothing, so hand-checked labels stay;
    cases whose listing is gone are dropped."""
    models = load_models(key)
    page = FLIP_PAGES[CATEGORIES[key]["flip"]]
    with open(_eval_path(key), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    by_id = {c["id"]: c for c in cases}
    fresh = {}
    queries = []
    for m in models:
        # the first collection searched by full name, top-ups by m["query"]
        for q in dict.fromkeys([m["name"], m["query"]]):
            if any(c["truth"] == m["name"] for c in cases):
                queries.append((q, {}))
    queries.append((page["fresh_query"],
                    {"price_min_euro": 20, "price_max_euro": 250, "limit": 60}))
    for q, kw in queries:
        try:
            found, _total = search_marktplaats(q, **{"limit": 30, **kw})
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            if l["id"] in by_id and l.get("images"):
                fresh[l["id"]] = l
        time.sleep(SEARCH_PAUSE_S)
    kept = []
    for c in cases:
        l = fresh.get(c["id"])
        if l:
            c.update(images=l["images"], text=masked_text(l, key, models))
            kept.append(c)
    print(f"  {len(kept)} of {len(cases)} cases refreshed, {len(cases) - len(kept)} gone")
    _save_eval(key, kept)


# ---------------------------------------------------------------- eval: score

def _spread(cases, limit):
    """Up to `limit` cases: a quarter ordinary listings, the rest taken
    round-robin across models so a small run still covers every model."""
    negatives = [c for c in cases if c["truth"] == "none"]
    picked = negatives[:limit // 4]
    by_truth = {}
    for c in cases:
        if c["truth"] != "none":
            by_truth.setdefault(c["truth"], []).append(c)
    while len(picked) < limit and any(by_truth.values()):
        for group in by_truth.values():
            if group and len(picked) < limit:
                picked.append(group.pop(0))
    return picked


def evaluate(key, limit=None, use_text=True):
    """Run recognition on the test cases and print how often it was right."""
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set: the test needs the LLM.")
    models = load_models(key)
    with open(_eval_path(key), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    if limit:
        cases = _spread(cases, limit)
    print(f"Testing {len(cases)} listings...")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(recognize, key, models, c["images"],
                             c.get("text", "") if use_text else ""): c
                   for c in cases}
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                results.append((c, fut.result()))
            except Exception as e:
                print(f"  ! {c['id']}: recognition failed: {e}", file=sys.stderr)

    pos = [(c, r) for c, r in results if c["truth"] != "none"]
    neg = [(c, r) for c, r in results if c["truth"] == "none"]
    score = Counter()
    confused = Counter()
    for c, r in pos:
        if r["match"] is None:
            score["unknown"] += 1
            continue
        ok = r["match"] == c["truth"]
        score[(r["confidence"], ok)] += 1
        if not ok:
            confused[(c["truth"], r["match"])] += 1
    false_hits = Counter(r["confidence"] for _c, r in neg if r["match"])

    def pct(a, b):
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else f"{a}/0"

    s_ok, s_bad = score[("strong", True)], score[("strong", False)]
    p_ok, p_bad = score[("possible", True)], score[("possible", False)]
    print(f"\nKnown models, title hidden: {len(pos)} listings")
    print(f"  strong match right:   {pct(s_ok, s_ok + s_bad)}")
    print(f"  possible match right: {pct(p_ok, p_ok + p_bad)}")
    print(f"  said unknown:         {pct(score['unknown'], len(pos))}")
    print(f"Ordinary listings: {len(neg)}")
    print(f"  wrongly strong:       {pct(false_hits['strong'], len(neg))}")
    print(f"  wrongly possible:     {pct(false_hits['possible'], len(neg))}")
    if confused:
        print("Confusions (truth -> answer):")
        for (truth, got), n in confused.most_common():
            print(f"  {truth} -> {got}: {n}")
    misses = [(c, r) for c, r in results
              if r["match"] and r["match"] != c["truth"]]
    if misses:
        print("Wrong answers, to look at by hand:")
        for c, r in misses:
            print(f"  {c['url']}  truth={c['truth']}  got={r['match']} "
                  f"({r['confidence']}): {r['why']}")


# ---------------------------------------------------------------- daily hunt

def hunt(key):
    """Search in plain words, keep listings that name no brand, recognize their
    photos, and return the finds: a listed model at or under its buy price.
    Strong matches first, then by margin. Also returns how many were checked."""
    models = load_models(key)
    by_name = {m["name"]: m for m in models}
    cat = CATEGORIES[key]
    page = FLIP_PAGES[cat["flip"]]
    designers = cat.get("designers", [])
    listings, seen = [], set()
    for q in cat["queries"]:
        try:
            found, _total = search_marktplaats(q, price_max_euro=HUNT_PRICE_MAX,
                                               limit=60, exclude_bids=True)
        except Exception as e:
            print(f"  ! search '{q}' failed: {e}", file=sys.stderr)
            found = []
        for l in found:
            text = f"{l['title']} {l['description']}"
            ask = l.get("asking_euro")
            if (l["id"] in seen or not ask or not HUNT_PRICE_MIN <= ask <= HUNT_PRICE_MAX
                    or not l.get("images") or is_auction_lot(l)
                    or _NEW_RE.search(_norm(l["title"]))
                    or l.get("category_id") not in page["fresh_categories"]
                    # the seller already knows what it is: not overlooked
                    or names_any_brand(text, models, designers)
                    or any(_has(_norm(text), _norm(w)) for w in page["watch"])):
                continue
            seen.add(l["id"])
            listings.append(l)
        time.sleep(SEARCH_PAUSE_S)
    listings = dedupe_relistings(listings)[:HUNT_MAX]
    print(f"  {len(listings)} unbranded listings from {len(cat['queries'])} searches")

    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(recognize, key, models, l["images"],
                             masked_text(l, key, models)): l for l in listings}
        for fut in as_completed(futures):
            try:
                results.append((futures[fut], fut.result()))
            except Exception as e:
                print(f"  ! {futures[fut]['id']}: recognition failed: {e}",
                      file=sys.stderr)

    finds = []
    for l, r in results:
        m = by_name.get(r["match"])
        # re-check the price in code: at or under what the model is worth buying at
        if not m or l["asking_euro"] > m["buy_eur"][1]:
            continue
        finds.append({
            "id": l["id"], "title": l["title"], "url": l["url"], "image": l["image"],
            "city": l["city"], "asking_euro": l["asking_euro"],
            "match": m["name"], "confidence": r["confidence"], "why": r["why"],
            "resale_low": m["resell_eur"][0], "resale_high": m["resell_eur"][1],
        })
    finds.sort(key=lambda f: (f["confidence"] != "strong",
                              f["asking_euro"] - f["resale_low"]))
    strong = sum(f["confidence"] == "strong" for f in finds)
    print(f"  {len(finds)} find(s): {strong} strong, {len(finds) - strong} possible")
    return finds, len(listings)


def run(categories=None, save=True):
    """Hunt every category (or the given keys) and store the record in Redis."""
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set: recognition needs the LLM.")
    keys = [k for k in CATEGORIES if categories is None or k in categories]
    record = {"date": time.strftime("%Y-%m-%d", time.gmtime()), "ts": time.time(),
              "scanned": 0, "categories": []}
    for key in keys:
        print(f"{key}...")
        finds, scanned = hunt(key)
        record["scanned"] += scanned
        record["categories"].append({"key": CATEGORIES[key]["flip"], "finds": finds})
    if save:
        payload = json.dumps(record)
        try:
            upstash_command("SET", OVERLOOKED_KEY, payload)
            upstash_command("SET", f"overlooked:{record['date']}", payload)
            print(f"Saved to Redis as {OVERLOOKED_KEY} and overlooked:{record['date']}")
        except Exception as e:
            print(f"  ! not saved to Redis: {e}", file=sys.stderr)
    return record


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Overlooked finds: unbranded items "
                                             "recognized from their photos.")
    ap.add_argument("--collect", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="build the test set for a category (searches Marktplaats)")
    ap.add_argument("--eval", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="score photo recognition on the saved test set")
    ap.add_argument("--refresh", metavar="CATEGORY", choices=sorted(CATEGORIES),
                    help="update the saved test set's photos and text (searches "
                         "Marktplaats, adds no new cases)")
    ap.add_argument("--no-text", action="store_true",
                    help="with --eval: photos only, to see what the text adds")
    ap.add_argument("--limit", type=int,
                    help="with --eval: test only this many listings, spread over models")
    ap.add_argument("--dry-run", action="store_true",
                    help="daily hunt: print the finds as JSON, don't write to Redis")
    ap.add_argument("--category", action="append", choices=sorted(CATEGORIES),
                    help="daily hunt: only this category (repeatable)")
    args = ap.parse_args()
    if args.collect:
        collect(args.collect)
    elif args.refresh:
        refresh(args.refresh)
    elif args.eval:
        evaluate(args.eval, limit=args.limit, use_text=not args.no_text)
    else:
        rec = run(categories=args.category, save=not args.dry_run)
        if args.dry_run:
            print(json.dumps(rec, indent=2, ensure_ascii=False))
