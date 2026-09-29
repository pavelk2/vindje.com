#!/usr/bin/env python3
"""
Nightly saved-search digest for vindje.com (issue #28): each saved search
gets re-run through the same AI-filtered pipeline as a live search, and
whoever saved it is emailed only the genuinely new matches.

Pipeline (reuses app.py's search + filter + Redis helpers):
  1. Enumerate saved searches from the `search:saved:index` Set (never a
     Redis KEYS scan). Stale entries — expired since the last run — are
     dropped from the index as they're found, so the index self-heals.
  2. For each saved search, in a plain sequential loop (never threaded —
     be gentle with Marktplaats, see AGENTS.md hard limit 4), call
     smart_search with the parsed filters saved at subscribe time, so no
     LLM re-parses the wish every night.
  3. Diff the matches against `search:sent:<user>:<id>`, the set of
     Marktplaats item ids already emailed for this search. Only genuinely
     new matches get sent.
  4. Email the new matches via Resend's HTTP API (urllib, no dependency).

v1 is daily-only: every saved search stores "frequency": "daily", so a
faster tier for rare/urgent items later is an additive change (a new
frequency value plus a second, more frequent workflow), not a rework.

Run it manually:
  OPENROUTER_API_KEY=sk-or-... python3 digest.py --dry-run   # print only
  OPENROUTER_API_KEY=... UPSTASH_REDIS_REST_URL=... \
    UPSTASH_REDIS_REST_TOKEN=... RESEND_API_KEY=... python3 digest.py

In production a GitHub Actions cron runs this every night at 03:00 UTC
(see .github/workflows/nightly-digest.yml).
"""

import argparse
import html
import json
import os
import sys
import time

from app import (OPENROUTER_API_KEY, SAVED_SEARCH_INDEX_KEY,
                 SAVED_SEARCH_TTL_SECONDS, UPSTASH_REDIS_REST_TOKEN,
                 UPSTASH_REDIS_REST_URL, send_email, smart_search,
                 upstash_command)

PAUSE_BETWEEN_SEARCHES_SECONDS = 2  # be gentle with Marktplaats — batched, no rush

SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://vindje.com")

INK, BODY, MUTED, LINE, FIELD = "#1d1d1f", "#48484a", "#86868b", "#e8e8ed", "#f5f5f7"


# ---------------------------------------------------------------- storage

def sent_key(saved_key):
    return saved_key.replace("search:saved:", "search:sent:", 1)


def iter_saved_searches():
    """Yield (key, row) for every saved search, self-healing the index by
    dropping any entry whose search has expired or is unreadable."""
    for key in upstash_command("SMEMBERS", SAVED_SEARCH_INDEX_KEY) or []:
        raw = upstash_command("GET", key)
        if not raw:
            upstash_command("SREM", SAVED_SEARCH_INDEX_KEY, key)
            continue
        try:
            yield key, json.loads(raw)
        except (TypeError, ValueError):
            upstash_command("SREM", SAVED_SEARCH_INDEX_KEY, key)


def _card_html(l):
    title = html.escape(str(l.get("title", "")))
    price = html.escape(str(l.get("price", "")))
    city = html.escape(str(l.get("city", "")))
    dist = l.get("distance_km")
    meta = city + (f" &middot; {dist} km" if dist else "")
    why = html.escape(str(l.get("why", "")))
    url = html.escape(str(l.get("url", "")))
    img = l.get("image") or ""
    thumb = (f'<img src="{html.escape(img)}" width="88" height="88" '
             f'style="border-radius:12px;object-fit:cover;background:{FIELD}" alt="">'
             if img else
             f'<div style="width:88px;height:88px;border-radius:12px;background:{FIELD}"></div>')
    return f"""
<a href="{url}" style="display:block;text-decoration:none;color:inherit;
   border:1px solid {LINE};border-radius:18px;padding:12px;margin:0 0 10px">
  <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    <td style="vertical-align:top;padding-right:14px">{thumb}</td>
    <td style="vertical-align:middle">
      <div style="font-size:14.5px;font-weight:600;color:{INK};margin:0 0 3px">{title}</div>
      <div style="font-size:12.5px;color:{MUTED};margin:0 0 3px">{meta}
        &middot; <span style="font-weight:600;color:{INK}">{price}</span></div>
      {"<div style='font-size:12px;color:" + MUTED + "'><b style='color:" + INK + "'>Match:</b> " + why + "</div>" if why else ""}
    </td>
  </tr></table>
</a>"""


def render_digest_html(row, new_listings, unsubscribe_url):
    wish = html.escape(str(row.get("wish", "")))
    n = len(new_listings)
    cards = "".join(_card_html(l) for l in new_listings)
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
     Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;padding:26px 6px">
  <p style="font-size:13px;font-weight:700;letter-spacing:-.01em;color:{MUTED};
     margin:0 0 22px">vindje.com</p>
  <h1 style="font-size:19px;font-weight:700;letter-spacing:-.02em;margin:0 0 6px;
     color:{INK}">{n} new match{'es' if n != 1 else ''} found</h1>
  <p style="font-size:13.5px;color:{BODY};margin:0 0 22px;line-height:1.5">
     For "{wish}"</p>
  {cards}
  <a href="{SITE_ORIGIN}/" style="display:block;text-align:center;margin:24px 0 4px;
     padding:12px;background:{INK};color:#fff;font-size:13.5px;font-weight:600;
     border-radius:980px;text-decoration:none">See more on vindje.com</a>
  <p style="margin-top:26px;padding-top:18px;border-top:1px solid {LINE};
     font-size:11.5px;color:{MUTED};line-height:1.7">
     Sent because you subscribed to this search on vindje.com.<br>
     <a href="{unsubscribe_url}" style="color:{MUTED}">Unsubscribe</a></p>
</div>"""


# ---------------------------------------------------------------- run

def run(dry_run=False):
    if not (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN):
        print("Upstash Redis is not configured — nothing to do.")
        return
    if not OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY is not set — the filtering step needs an LLM.")

    sent_count = 0
    skipped_total = 0
    for key, row in iter_saved_searches():
        email = row.get("email", "?")
        wish = row.get("wish", "")
        print(f"{email}: {wish!r}")
        try:
            result = smart_search(row["wish"], row.get("postcode"),
                                  parsed=row.get("parsed"),
                                  exclude_bids=bool(row.get("exclude_bids")),
                                  req_id=f"digest:{row['id']}")
        except Exception as e:
            print(f"  ! search failed: {e}", file=sys.stderr)
            time.sleep(PAUSE_BETWEEN_SEARCHES_SECONDS)
            continue

        # When the AI filter was supposed to run (there were requirements) but
        # a chunk failed, smart_search still includes those listings so a
        # human on the live search page can eyeball them (it adds a note
        # saying so). Nobody reads this email unattended, so here a listing
        # without a "why" is unverified, not a match, and must not go out.
        candidates = result["results"]
        if result.get("interpreted", {}).get("requirements"):
            verified = [l for l in candidates if l.get("why")]
            skipped = len(candidates) - len(verified)
            if skipped:
                print(f"  skipped {skipped} unverified listing(s) (AI filter failed)")
                skipped_total += skipped
            candidates = verified

        seen = set(str(x) for x in (upstash_command("SMEMBERS", sent_key(key)) or []))
        new = [l for l in candidates if str(l.get("id")) not in seen]

        if not new:
            print("  no new matches")
        elif dry_run:
            print(f"  would send {len(new)} new match(es)")
        else:
            unsubscribe_url = f"{SITE_ORIGIN}/unsubscribe?token={row['token']}"
            subject = f"{len(new)} new match{'es' if len(new) != 1 else ''}: {wish[:60]}"
            try:
                send_email(email, subject, render_digest_html(row, new, unsubscribe_url))
                ids = [str(l.get("id")) for l in new]
                upstash_command("SADD", sent_key(key), *ids)
                upstash_command("EXPIRE", sent_key(key), str(SAVED_SEARCH_TTL_SECONDS))
                sent_count += 1
                print(f"  sent {len(new)} new match(es)")
            except Exception as e:
                print(f"  ! send failed: {e}", file=sys.stderr)

        time.sleep(PAUSE_BETWEEN_SEARCHES_SECONDS)

    skip_note = f", {skipped_total} unverified listing(s) skipped" if skipped_total else ""
    print(f"Done. {sent_count} email(s) sent{skip_note}."
          if not dry_run else f"Done (dry run){skip_note}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Nightly saved-search digest.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be sent, send nothing")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
