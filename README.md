# Robin-Bobin

Smart search for Dutch second-hand marketplaces: **Marktplaats**,
**Reliving**, **VNTG** and **Whoppah** — in one go.

Marketplaces are littered with ads and inapplicable listings. Here you just say:

> *"wooden closet with drawers and hangers of about 1.5-2 meter height, within
> 15 minutes driving distance"*

...and get **all and only the applicable results**, instead of endlessly
searching through trash.

## How it works

1. **Parse** — a free LLM (via [OpenRouter](https://openrouter.ai)) turns your
   wish (any language) into a real search: Dutch + English keywords, price
   range, and a search radius (it even converts "15 minutes driving" into km).
2. **Search** — the app queries Marktplaats' own search API with those filters,
   and in parallel searches Reliving, VNTG and Whoppah (Dutch keywords for the
   Dutch-first sites, English for VNTG). Results are merged, each card labeled
   with its marketplace.
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

Without an API key the app still works as a plain multi-marketplace search —
just without the smart parsing and filtering.

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
- Reliving, VNTG and Whoppah have no documented public search API, so the app
  fetches their public search-results page and reads the machine-readable
  product data those pages embed anyway (schema.org JSON-LD and Next.js
  hydration JSON). Each of these sources is best-effort: when a site is down,
  blocks the request, or changes its markup, it simply contributes zero
  results and the UI shows a note — the rest of the search still works. The
  distance filter applies to Marktplaats only (the others ship nationwide),
  while the price filter is applied to all sources.
