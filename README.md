# Robin-Bobin

Smart search for Marktplaats.

Marktplaats is littered with ads and inapplicable listings. Here you just say:

> *"wooden closet with drawers and hangers of about 1.5-2 meter height, within
> 15 minutes driving distance"*

...and get **all and only the applicable results**, instead of endlessly
searching through trash.

## How it works

1. **Parse** — a free LLM (via [OpenRouter](https://openrouter.ai)) turns your
   wish (any language) into a real Marktplaats search: Dutch keywords, price
   range, and a search radius (it even converts "15 minutes driving" into km).
2. **Search** — the app queries Marktplaats' own search API with those filters.
3. **Filter** — the LLM reads every returned listing (title, description,
   attributes) and keeps only the ones that actually satisfy your requirements,
   each with a one-line reason.

## Run it

Requires only Python 3.8+ — **no dependencies to install**.

```bash
# 1. Get a free API key at https://openrouter.ai/keys (free models cost €0)
# 2. Run:
OPENROUTER_API_KEY=sk-or-... python3 app.py
# 3. Open http://localhost:8000
```

Type what you want, add your postcode (needed for the distance filter), hit
Search.

Without an API key the app still works as a plain Marktplaats search — just
without the smart parsing and filtering.

## Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key (free tier is enough) |
| `OPENROUTER_MODEL` | `z-ai/glm-5.2:free`, then `nvidia/nemotron-3-ultra-550b-a55b:free`, `google/gemma-4-31b-it:free`, `openrouter/free` | Comma-separated models to try in order |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
| `PORT` | `8000` | HTTP port |

Free models are rate-limited and occasionally overloaded; the app automatically
falls through the model list, and if all AI calls fail it degrades to a plain
search and tells you so.

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

### Run it locally first

```bash
pip install mcp uvicorn
python3 mcp_server.py
# MCP endpoint at http://localhost:8001/mcp — point an MCP client
# (e.g. `npx @modelcontextprotocol/inspector`) at it to try it out.
```
