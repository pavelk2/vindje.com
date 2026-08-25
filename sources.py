#!/usr/bin/env python3
"""Extra listing sources beyond Marktplaats: eBay (live search, via the
Browse API) and Catawiki (via an Awin product feed). Both are optional —
each degrades to "no results, no error" when its credentials aren't
configured, so app.py's smart_search and deals.py's hunt_category can
always call them and just get fewer sources back.

Listings from every source share Marktplaats' shape (see
app.search_marktplaats): {id, title, description, price, city,
distance_km, attributes, image, url, source}. `price` is the same
formatted "€123" string app.format_price produces, so downstream code
(price parsing in deals.py, rendering in app.py) doesn't need to care
which source a listing came from. `url` is already an affiliate-tracked
link when the relevant program is configured — plain otherwise.
"""

import csv
import gzip
import io
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import affiliate

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)
log = logging.getLogger("vindje.sources")

EBAY_MARKETPLACE_ID = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_NL")
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

AWIN_CATAWIKI_FEED_URL = os.environ.get("AWIN_CATAWIKI_FEED_URL", "")
AWIN_CATAWIKI_ADVERTISER_ID = os.environ.get("AWIN_CATAWIKI_ADVERTISER_ID", "")

# ---------------------------------------------------------------- eBay

def _ebay_price_filter(price_min_euro, price_max_euro):
    if price_min_euro is None and price_max_euro is None:
        return None
    lo = "" if price_min_euro is None else str(price_min_euro)
    hi = "" if price_max_euro is None else str(price_max_euro)
    return f"price:[{lo}..{hi}],priceCurrency:EUR"


def search_ebay(terms, price_min_euro=None, price_max_euro=None, limit=50, req_id="-"):
    """Live eBay search via the Browse API. Returns (listings, total),
    ([], 0) if EBAY_CLIENT_ID/EBAY_CLIENT_SECRET aren't configured or the
    call fails — callers should treat that the same as "no eBay results",
    not an error, since eBay is an optional extra source."""
    token = affiliate.ebay_oauth_token()
    if not token:
        return [], 0

    params = [("q", terms), ("limit", str(max(1, min(int(limit), 200))))]
    price_filter = _ebay_price_filter(price_min_euro, price_max_euro)
    if price_filter:
        params.append(("filter", price_filter))
    url = EBAY_BROWSE_URL + "?" + urllib.parse.urlencode(params)
    headers = {
        "Authorization": "Bearer " + token,
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE_ID,
        "Accept": "application/json",
    }
    enduserctx = affiliate.ebay_enduserctx_header()
    if enduserctx:
        # asks the Browse API to return itemAffiliateWebUrl (EPN-tracked)
        # on every item, instead of the plain itemWebUrl.
        headers["X-EBAY-C-ENDUSERCTX"] = enduserctx

    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    log.info("[%s] search_ebay: terms=%r price=[%s,%s] limit=%d",
             req_id, terms, price_min_euro, price_max_euro, limit)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        log.warning("[%s] search_ebay: FAILED in %.2fs: %s", req_id, time.time() - t0, e)
        return [], 0

    listings = []
    for raw in data.get("itemSummaries", []):
        price_info = raw.get("price") or {}
        cents = round(float(price_info.get("value", 0)) * 100) if price_info.get("value") else 0
        currency = price_info.get("currency", "EUR")
        price = f"€{cents / 100:,.0f}".replace(",", ".") if currency == "EUR" and cents else \
            (f"{cents / 100:,.2f} {currency}".replace(",", ".") if cents else "?")
        loc = raw.get("itemLocation") or {}
        image = (raw.get("image") or {}).get("imageUrl", "")
        attrs = []
        if raw.get("condition"):
            attrs.append(f"condition: {raw['condition']}")
        listings.append({
            "id": "ebay:" + str(raw.get("itemId", "")),
            "title": raw.get("title", ""),
            "description": raw.get("shortDescription") or "",
            "price": price,
            "city": loc.get("city", "") or loc.get("country", ""),
            "distance_km": None,
            "attributes": attrs,
            "image": image,
            "url": raw.get("itemAffiliateWebUrl") or raw.get("itemWebUrl", ""),
            "source": "ebay",
        })
    total = data.get("total", len(listings))
    log.info("[%s] search_ebay: got %d listings of %d total, in %.2fs",
             req_id, len(listings), total, time.time() - t0)
    return listings, total


# ---------------------------------------------------------------- Catawiki (via Awin feed)

_feed_cache = {"url": None, "rows": None, "fetched_at": 0}
FEED_CACHE_TTL = 6 * 3600  # Awin feeds refresh a few times a day; no need to redownload every call


def _download_feed_rows(feed_url, req_id="-"):
    """Download and parse an Awin product-feed CSV/TXT. Returns a list of
    dict rows (csv.DictReader), or [] on any failure. Cached per feed URL
    for FEED_CACHE_TTL seconds so one deal-hunt run doesn't redownload it
    once per category."""
    now = time.time()
    if (_feed_cache["url"] == feed_url and _feed_cache["rows"] is not None
            and now - _feed_cache["fetched_at"] < FEED_CACHE_TTL):
        return _feed_cache["rows"]
    t0 = time.time()
    log.info("[%s] awin feed: downloading %s", req_id, feed_url)
    try:
        req = urllib.request.Request(
            feed_url, headers={"Accept-Encoding": "gzip", "User-Agent": "vindje.com/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or feed_url.endswith(".gz"):
                raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
        # Awin feeds are usually comma- or tab-delimited; sniff which.
        sample = text[:4096]
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    except Exception as e:
        log.warning("[%s] awin feed: FAILED in %.2fs: %s", req_id, time.time() - t0, e)
        return []
    log.info("[%s] awin feed: %d rows in %.2fs", req_id, len(rows), time.time() - t0)
    _feed_cache.update(url=feed_url, rows=rows, fetched_at=now)
    return rows


def _row_get(row, *keys):
    """Awin feed column names vary slightly by feed config; try a few
    case-insensitive spellings before giving up."""
    lower = {k.lower(): v for k, v in row.items() if k}
    for k in keys:
        v = lower.get(k.lower())
        if v:
            return v
    return ""


_WORD_RE = re.compile(r"[a-z0-9]+")


def search_catawiki(terms, price_max_euro=None, limit=50, req_id="-"):
    """Keyword search over the cached Catawiki Awin product feed. Returns
    (listings, total_matched) — ([], 0) if AWIN_CATAWIKI_FEED_URL isn't
    configured. Catawiki has no public live-search API, so this searches
    the last-downloaded feed snapshot rather than querying live.

    Note: Catawiki's own affiliate program may run through a different
    network than Awin depending on when you sign up (see README) — this
    function works for ANY Awin advertiser's product feed, not just
    Catawiki; point AWIN_CATAWIKI_FEED_URL/AWIN_CATAWIKI_ADVERTISER_ID at
    whichever Awin feed you actually have access to.
    """
    if not AWIN_CATAWIKI_FEED_URL:
        return [], 0
    rows = _download_feed_rows(AWIN_CATAWIKI_FEED_URL, req_id=req_id)
    if not rows:
        return [], 0

    words = [w for w in _WORD_RE.findall(terms.lower()) if len(w) > 2]
    matches = []
    for row in rows:
        name = _row_get(row, "product_name", "title", "name")
        desc = _row_get(row, "description", "merchant_category")
        haystack = (name + " " + desc).lower()
        if words and not all(w in haystack for w in words):
            continue
        price_str = _row_get(row, "search_price", "store_price", "price")
        try:
            price_val = float(re.sub(r"[^\d.]", "", price_str.replace(",", ".")) or 0)
        except ValueError:
            price_val = 0
        if price_max_euro is not None and price_val and price_val > price_max_euro:
            continue
        deep_link = _row_get(row, "aw_deep_link", "merchant_deep_link")
        currency = _row_get(row, "currency") or "EUR"
        price = f"€{price_val:,.0f}".replace(",", ".") if currency == "EUR" and price_val else \
            (f"{price_val:,.2f} {currency}".replace(",", ".") if price_val else "?")
        matches.append({
            "id": "catawiki:" + (_row_get(row, "aw_product_id", "merchant_product_id") or name[:40]),
            "title": name,
            "description": desc[:500],
            "price": price,
            "city": "",
            "distance_km": None,
            "attributes": [],
            "image": _row_get(row, "merchant_image_url", "image_url", "aw_image_url"),
            "url": affiliate.awin_link(deep_link, AWIN_CATAWIKI_ADVERTISER_ID) if deep_link else "",
            "source": "catawiki",
        })
        if len(matches) >= limit:
            break
    log.info("[%s] search_catawiki: %d matches of %d feed rows for %r",
             req_id, len(matches), len(rows), terms)
    return matches, len(matches)
