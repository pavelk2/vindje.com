# Robin-Bobin

Smart search for Marktplaats.

Marktplaats is littered with ads and inapplicable listings. Here you just say:

> *"wooden closet with drawers and hangers of about 1.5-2 meter height, within
> 15 minutes driving distance"*

...and get **all and only the applicable results**, instead of endlessly
searching through trash.

## How it works

1. **Parse** — an LLM (via [OpenRouter](https://openrouter.ai), Claude Haiku
   4.5 by default) turns your wish (any language) into a real Marktplaats
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
#    default model (Claude Haiku 4.5) is paid, not free
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

## Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key, funded with credits |
| `OPENROUTER_MODEL` | `anthropic/claude-haiku-4.5`, then `openrouter/free` | Comma-separated models to try in order |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
| `UPSTASH_REDIS_REST_URL` | — | Your Upstash Redis REST URL, for saving/sharing searches |
| `UPSTASH_REDIS_REST_TOKEN` | — | Upstash Redis REST token (secret, server-side only) |
| `PORT` | `8000` | HTTP port |

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
