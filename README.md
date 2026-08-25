# vindje.com

Smart search for Marktplaats.

Marktplaats is littered with ads and inapplicable listings. Here you just say:

> *"wooden closet with drawers and hangers of about 1.5-2 meter height, within
> 15 minutes driving distance"*

...and get **all and only the applicable results**, instead of endlessly
searching through trash.

## How it works

1. **Parse** — an LLM (via [OpenRouter](https://openrouter.ai), GPT-5.6
   Luna by default) turns your wish (any language) into a real Marktplaats
   search: Dutch keywords, price range, and a search radius (it even converts
   "15 minutes driving" into km).
2. **Search** — the app queries Marktplaats' own search API with those filters.
3. **Filter** — the LLM reads every returned listing (title, description,
   attributes) and keeps only the ones that actually satisfy your requirements,
   each with a one-line reason.

## Run it

Requires only Python 3.8+ — **no dependencies to install**.

```bash
# 1. Get an API key at https://openrouter.ai/keys and add credits — the
#    default model (GPT-5.6 Luna) is paid, not free
# 2. Run:
OPENROUTER_API_KEY=sk-or-... python3 app.py
# 3. Open http://localhost:8000
```

Type what you want, add your postcode (needed for the distance filter), hit
Search.

Without an API key the app still works as a plain Marktplaats search — just
without the smart parsing and filtering.

## Sharing a search

Every completed search is automatically saved (a frozen snapshot of the
exact listings you saw, with their AI match/reject verdicts) and a "Copy
share link" button appears once it's done. The link (`/s/<id>`) shows
anyone who opens it precisely what you saw — no re-running of the search or
the AI filtering, so it's instant and doesn't re-spend AI credits.

This requires an [Upstash Redis](https://upstash.com) database (the free
tier is plenty) as storage. Without it configured, saving/sharing just
silently degrades to a no-op — search still works fully, only the "Copy
share link" button never appears.

1. Create an Upstash account, then create a Redis database (any region).
   No schema or setup needed — it's a plain key-value store; each saved
   search is written as one JSON value under a `search:<id>` key.
2. On the database's page, grab the **REST URL** and **REST token** (under
   "REST API") and set them as env vars below. The token is secret — it's
   only ever used server-side, never sent to the browser.

## Today's finds (daily deal hunt)

The homepage isn't empty anymore: every morning at 8:00 Amsterdam time a
GitHub Actions cron (`.github/workflows/daily-deals.yml`) runs
`deals.py`, which hunts Marktplaats nationwide for undervalued items —
asking price under €250 with a conservative, LLM-estimated resale value
of €500+ — across four curated categories:

- vintage racing bikes (RIH, Peugeot, Gitane, Koga Miyata, Raleigh, Bianchi)
- designer lamps (Louis Poulsen, Artemide)
- design chairs (Vitra, Herman Miller)
- Mac minis (Apple Silicon only — Intel ones aren't worth flipping)

The LLM values each listing skeptically (replicas, "stijl van"
lookalikes, bare frames, parts and bidding-only listings are rejected),
and only finds whose low-end estimate clears €500 *and* 2× the asking
price survive. The result is stored in Upstash Redis (`deals:latest`
plus a dated `deals:<YYYY-MM-DD>` copy) and rendered on the homepage as
"Today's finds", hidden as soon as the visitor starts their own search.

Run it by hand to try it (or from the Actions tab via "Run workflow"):

```bash
OPENROUTER_API_KEY=sk-or-... python3 deals.py --dry-run          # print only
OPENROUTER_API_KEY=... UPSTASH_REDIS_REST_URL=... \
  UPSTASH_REDIS_REST_TOKEN=... python3 deals.py                  # save too
python3 deals.py --dry-run --category bikes                      # one category
```

The workflow needs `OPENROUTER_API_KEY`, `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN` as repository secrets (Settings → Secrets and
variables → Actions) — the same values the Vercel deployment uses.

## Affiliate integrations (eBay & Catawiki)

Marktplaats itself has no affiliate program — vindje.com never earns anything
from a Marktplaats click. eBay and Catawiki do, so `app.py` and `deals.py`
both optionally pull in listings from those two as well, wrapped with
affiliate-tracked links:

- **Live search**: when you run a search, eBay (via its Browse API) is
  searched alongside Marktplaats and matching results are blended into the
  same AI-filtered result list, each labelled with a small "EBAY" badge and
  linked through an [eBay Partner Network](https://partnernetwork.ebay.com)
  (EPN) tracking URL. Catawiki has no live search API, so it isn't part of
  live search — see the deal hunter below.
- **Daily deal hunt**: `deals.py`'s per-category scans (see "Today's finds"
  above) also search eBay, and separately search a downloaded snapshot of a
  Catawiki product feed via [Awin](https://www.awin.com), for the same
  undervalued-item categories — any qualifying find gets the same
  affiliate-tracked link treatment.

Both integrations degrade silently when unconfigured — the app and deal
hunter just run Marktplaats-only, exactly as before, until you set the
relevant env vars below.

**eBay (via eBay Partner Network):**
1. Create an [eBay Developer Program](https://developer.ebay.com) account,
   then a **production** keyset under "Application Keys" — that gives you
   `EBAY_CLIENT_ID` (App ID) and `EBAY_CLIENT_SECRET` (Cert ID). This alone
   enables live eBay search (no affiliate tracking yet, plain links).
2. Separately join the [eBay Partner Network](https://partnernetwork.ebay.com)
   and create a Campaign — that gives you a 10-digit `EBAY_EPN_CAMPAIGN_ID`.
   With this set, eBay links returned by the app carry EPN tracking and
   commissions apply.
3. Optionally set `EBAY_MARKETPLACE_ID` (default `EBAY_NL`) to search a
   different eBay marketplace, e.g. `EBAY_GB` or `EBAY_US`.

**Catawiki (via Awin):**
1. Apply to Catawiki's affiliate program (contact `affiliates@catawiki.nl`
   or check [Catawiki's partner page](https://www.catawiki.com/en/pages/p/partners-creators))
   and confirm which affiliate network they currently run on for your
   account — this has moved between networks over time, so verify before
   assuming Awin.
2. If (once accepted) it's on Awin: create an
   [Awin publisher account](https://www.awin.com) to get `AWIN_PUBLISHER_ID`,
   then from Awin's "Advertisers" / product feed area grab Catawiki's
   `AWIN_CATAWIKI_ADVERTISER_ID` and the direct CSV/TXT download URL for
   their product feed as `AWIN_CATAWIKI_FEED_URL` (an uncompressed feed is
   simplest; the app also handles gzip). The deal hunter re-downloads and
   caches this feed (up to every 6h) rather than hitting it per request.
3. `sources.search_catawiki()` isn't actually Catawiki-specific — it reads
   whatever Awin product feed you point it at, so the same env vars work
   for any other Awin advertiser's feed if you'd rather monetize with
   something else.

**Disclosure**: whenever a search or "Today's finds" includes an eBay or
Catawiki result, a note is shown ("vindje.com may earn a commission…") and
those cards link out with `rel="sponsored"` — required for compliance with
FTC/ACM affiliate-marketing disclosure rules. Don't remove this if you
enable these integrations.

**Known limitation**: the AI still turns a wish into *Dutch* search terms
(Marktplaats needs that), and those same terms are reused verbatim for eBay
and Catawiki search — cross-language recall for those two is weaker than
for Marktplaats as a result. Full bilingual query generation is a possible
future improvement, not implemented yet.

## Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key, funded with credits |
| `OPENROUTER_MODEL` | `openai/gpt-5.6-luna`, then `openrouter/free` | Comma-separated models to try in order |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
| `UPSTASH_REDIS_REST_URL` | — | Your Upstash Redis REST URL, for saving/sharing searches |
| `UPSTASH_REDIS_REST_TOKEN` | — | Upstash Redis REST token (secret, server-side only) |
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | — | eBay Developer Program production App ID / Cert ID — enables live eBay search |
| `EBAY_EPN_CAMPAIGN_ID` | — | eBay Partner Network Campaign ID — enables affiliate-tracked eBay links |
| `EBAY_MARKETPLACE_ID` | `EBAY_NL` | Which eBay marketplace to search |
| `AWIN_PUBLISHER_ID` | — | Your Awin publisher (affiliate) ID |
| `AWIN_CATAWIKI_FEED_URL` | — | Direct URL to an Awin product feed (Catawiki or otherwise) to search for deals |
| `AWIN_CATAWIKI_ADVERTISER_ID` | — | The Awin advertiser ID that feed belongs to, for link wrapping |
| `PORT` | `8000` | HTTP port |

If the primary model errors or rate-limits, the app automatically falls
through the model list (ending with OpenRouter's free-model router as a
last resort), and if all AI calls fail it degrades to a plain search and
tells you so.

## Notes

- The core app is `app.py`, plus `sources.py` (eBay/Catawiki search) and
  `affiliate.py` (affiliate link building) for the integrations above —
  all stdlib only (`http.server` + `urllib`), no dependencies to install.
- The app uses Marktplaats' public website search endpoint
  (`/lrp/api/search`) — the same one your browser calls. Be gentle with it;
  this is a personal search tool, not a scraper.

## MCP server (use your own Claude subscription instead of OpenRouter)

`mcp_server.py` exposes Marktplaats search as an [MCP](https://modelcontextprotocol.io)
tool. It runs **no AI at all** — it only fetches and returns raw listings.
Add it to Claude as a custom connector and Claude itself (using your normal
subscription, no API key) does the parsing of your wish into Dutch keywords
and the judging of which listings actually match.

### Deploy

It deploys alongside the web app on the same Vercel project (`api/mcp.py` +
the `/mcp` rewrite in `vercel.json`). Push to your Vercel-connected repo and
the MCP endpoint is live at:

```
https://<your-app>.vercel.app/mcp
```

### Add it to Claude.ai

Settings → Connectors → Add custom connector → paste that URL. No
authentication is required (it's a read-only proxy onto public Marktplaats
search results, so there's nothing sensitive to protect).

### The tool

`search_marktplaats_listings(query, postcode=None, radius_km=None, price_min_euro=None, price_max_euro=None, limit=60)`
— searches live Marktplaats listings by Dutch keywords, price and radius,
and returns each one's full title, description, attributes, price,
location, image and URL. Claude reads that data itself to decide which
listings satisfy what you actually asked for.

### Listing cards (MCP Apps)

The server also declares an [MCP Apps](https://github.com/modelcontextprotocol/ext-apps)
(SEP-1865) `ui://marktplaats/listing-cards` resource on the search tool
(`listing_cards_ui.py`). On a host that supports MCP Apps, this renders each
search result as a photo card (image, price, title, city/distance) with a
link straight to the listing, the way the Booking.com MCP server renders
hotel cards — instead of, or alongside, Claude's plain-text answer. It's
dependency-free (hand-rolled `postMessage`/JSON-RPC handshake, no npm
package or build step) and purely additive: a host that ignores `ui://`
resources just falls back to the tool's normal text/structured output.

**Known limitation:** as of this writing, claude.ai's MCP Apps host support
for *custom* remote connectors (Settings → Connectors → Add custom
connector — the way this server is added) doesn't reliably render the
widget yet and can fall back to text-only, even for a spec-compliant server
([anthropics/claude-ai-mcp#471](https://github.com/anthropics/claude-ai-mcp/issues/471)).
Nothing is lost either way — the tool's normal text answer works regardless
— but don't be surprised if the cards don't show up yet on claude.ai.

### Run it locally first

```bash
pip install mcp uvicorn
python3 mcp_server.py
# MCP endpoint at http://localhost:8001/mcp — point an MCP client
# (e.g. `npx @modelcontextprotocol/inspector`) at it to try it out.
```
