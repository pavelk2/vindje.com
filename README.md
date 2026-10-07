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
   Tick **Fixed price only** to drop auction ads (pure bidding, and ones
   priced "from" an opening bid), where the price shown isn't what you'd
   actually pay.
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

### Alternative: `.env` file + `run-local.sh`

Typing keys inline on the command line every time gets old, and leaves them
sitting in your shell history. `run-local.sh` loads them from a `.env` file
instead:

```bash
./run-local.sh
```

The first run creates `.env` for you from `.env.example` (no manual copying
needed) and starts the app with whatever's in it. Open `.env` afterward,
fill in your real keys, and run `./run-local.sh` again to pick them up.

`.env` is listed in `.gitignore` — it holds real secrets and must never be
committed or made public (this repo is public, see `AGENTS.md`).

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

Auction listings are skipped outright: their price is only an opening
bid, so there's no asking price to measure the upside against and no way
to just buy the item at the number shown.

The LLM values each listing skeptically (replicas, "stijl van"
lookalikes, bare frames and parts are rejected),
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

## Notify me (nightly saved-search digest)

Under any search's results, "Notify me about new matches" saves that
search, including the AI-parsed filters, not just the raw text, and
emails you once a day with only the listings that are genuinely new
*and* still pass the same AI filter as a live search. No account or
password: just an email address, and an unsubscribe link in every
email.

A GitHub Actions cron (`.github/workflows/nightly-digest.yml`) runs
`digest.py` every night at 03:00 UTC. It re-runs each saved search once,
sequentially — never in parallel, to stay gentle on Marktplaats — and
skips listings it already emailed for that search.

v1 is daily-only: a saved search that's genuinely time-sensitive (a rare
item that can sell within hours) isn't well served by a once-a-day email
yet. That's a known, deliberate limitation, not an oversight.

Try it by hand:

```bash
OPENROUTER_API_KEY=sk-or-... UPSTASH_REDIS_REST_URL=... \
  UPSTASH_REDIS_REST_TOKEN=... python3 digest.py --dry-run   # print only
RESEND_API_KEY=... python3 digest.py                         # send too
```

Needs an [Upstash Redis](https://upstash.com) database (same one as
sharing, above) and a [Resend](https://resend.com) account with a
verified sending domain. The workflow needs `RESEND_API_KEY` as a fourth
repository secret alongside the three deal-hunt ones.

## Overlooked (photo recognition, pilot: lamps)

Issue #50: find second-hand items whose listing doesn't name the brand, but
whose photos look like a valuable model. `overlooked.py` shows the model up
to 3 large photos plus the listing text with every brand, model and designer
name cut out, and asks which model from `data/vintage_resale_icons.json` it
is, if any.

Every morning, right after the deal hunt, the same GitHub Actions workflow runs
`overlooked.py`. It searches in the plain words of a seller who doesn't know the
brand ("lamp contragewicht", "glazen blokken lamp"), skips listings that already
name a brand or designer, and keeps the ones the model recognizes at or under
the model's buy price. `/flip` shows the strong matches under **Overlooked**;
`/flip?possible=1` (not indexed) also shows possible ones, for testing. No Redis,
no section.

```bash
OPENROUTER_API_KEY=sk-or-... python3 overlooked.py --dry-run   # print only
```

The accuracy test (`data/overlooked_eval_lamps.json`) holds listings whose title
names the lamp, so the answer is known but hidden from the model, plus ordinary
lamps that name no brand:

```bash
python3 overlooked.py --collect lamps                       # build the test set
OPENROUTER_API_KEY=sk-or-... python3 overlooked.py --eval lamps   # score it
python3 overlooked.py --eval lamps --no-text                 # photos only
```

Adding a category means data, not code: an entry in `CATEGORIES` in
`overlooked.py` that points at a category in the data file, plus what each
model looks like in a photo.

## Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key, funded with credits |
| `OPENROUTER_MODEL` | `openai/gpt-5.6-luna`, then `openrouter/free` | Comma-separated models to try in order |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
| `UPSTASH_REDIS_REST_URL` | — | Your Upstash Redis REST URL, for saving/sharing searches |
| `UPSTASH_REDIS_REST_TOKEN` | — | Upstash Redis REST token (secret, server-side only) |
| `PORT` | `8000` | HTTP port |
| `RESEND_API_KEY` | — | Resend API key, for outgoing email: subscribe confirmations and `digest.py`'s nightly digest (secret) |
| `RESEND_FROM_EMAIL` | `vindje.com <alerts@vindje.com>` | Verified Resend sender address |
| `SITE_ORIGIN` | `https://vindje.com` | Origin used for links in digest emails |

If the primary model errors or rate-limits, the app automatically falls
through the model list (ending with OpenRouter's free-model router as a
last resort), and if all AI calls fail it degrades to a plain search and
tells you so.

## Notes

- Everything lives in a single file, `app.py` (stdlib only: `http.server` +
  `urllib`).
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

`search_marktplaats_listings(query, postcode=None, radius_km=None, price_min_euro=None, price_max_euro=None, exclude_bids=False, limit=60)`
— searches live Marktplaats listings by Dutch keywords, price and radius,
and returns each one's full title, description, attributes, price,
location, image and URL. Each listing also carries a `bid` flag (true for
auction ads, where the price is only an opening bid); pass
`exclude_bids=True` to leave those out entirely. Claude reads that data
itself to decide which listings satisfy what you actually asked for.

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
