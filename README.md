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

## Configuration (all optional, via environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key, funded with credits |
| `OPENROUTER_MODEL` | `anthropic/claude-haiku-4.5`, then `openrouter/free` | Comma-separated models to try in order |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
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
