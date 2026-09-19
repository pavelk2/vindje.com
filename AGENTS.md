# AGENTS.md

Instructions for AI coding agents (and humans) working on vindje.com.
Claude Code, Cursor, Copilot, Codex and friends read this file automatically.
`CLAUDE.md` just points here, so there is one source of truth.

Keep it short. When an agent makes a mistake we don't want repeated, add one
line, not a paragraph.

## What this is

Smart search for Marktplaats: you describe what you want in any language, an
LLM turns it into a real Dutch search, and a second LLM pass keeps only the
listings that actually match. Plus a daily hunt for undervalued items
(`deals.py`), a shared-search page, a public ideas board, and an MCP server
that hands raw listings to Claude.

The project is deliberately open: code, roadmap, analytics and finances are
public. Two consequences for you:

- **Never commit a secret.** No API keys, tokens, Redis URLs, postcodes of
  real people. Everything here ends up readable by strangers. Secrets live in
  Vercel env vars and GitHub Actions secrets.
- Write code and comments assuming an outsider will read them next week.

## Run it

```bash
OPENROUTER_API_KEY=sk-or-... python3 app.py     # http://localhost:8000
```

Python 3.8+, no install step. Without a key the app degrades to a plain
Marktplaats search. That path must keep working.

Deal hunter:

```bash
python3 deals.py --dry-run                      # print, save nothing
python3 deals.py --dry-run --category bikes     # one category
```

MCP server (needs `pip install mcp uvicorn`):

```bash
python3 mcp_server.py                           # http://localhost:8001/mcp
```

## Environment variables

All optional. Missing ones degrade gracefully, never crash.

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key with credits. Absent: plain search, no AI. |
| `OPENROUTER_MODEL` | Comma-separated models tried in order. |
| `OPENROUTER_BASE_URL` | Any OpenAI-compatible endpoint. |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST URL: sharing, history, deals, ideas. |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash REST token. Server-side only, never sent to the browser. |
| `IDEA_VOTE_THRESHOLD` | Votes before an idea is highlighted. Default 3. |
| `PORT` | HTTP port. Default 8000. |

Add a variable → add a row here and in `README.md`, and set it in Vercel.

## Hard limits

1. **`app.py`, `deals.py` and `listing_cards_ui.py` are standard library
   only.** No requests, no flask, no jinja. `requirements.txt` exists for
   Vercel detection and carries `mcp` for `mcp_server.py` alone. Adding any
   other dependency is a PR conversation, not a drive-by commit.
2. **Don't split `app.py` "for cleanliness".** One file is a choice, not an
   accident. Restructuring is its own PR with its own reason.
3. **Anything Upstash-backed must degrade to a no-op.** No Redis configured
   means no sharing, no history, no deals, no ideas, and a working search.
   Never let a storage failure take down a page.
4. **Be gentle with Marktplaats.** We use their public search endpoint, the
   same one a browser calls. No parallel hammering, no scraping loops, no
   retry storms. This is a search tool, not a crawler.
5. **No new analytics or third-party scripts** without asking. GTM
   (`GTM-N3P8QL6S`) is the only tag, injected once via `_with_gtm`.

## Layout

| File | What lives there |
|---|---|
| `app.py` | Everything for the web app: LLM calls, Marktplaats search, filtering, Upstash storage, ideas board, HTML templates, WSGI router. ~2500 lines, sectioned by `# ---- name` comment banners. |
| `deals.py` | Daily deal hunt. Imports from `app.py`. Run by GitHub Actions. |
| `mcp_server.py` | MCP server. Raw listings only, no AI on our side. |
| `listing_cards_ui.py` | MCP Apps widget HTML for listing cards. |
| `api/index.py`, `api/mcp.py` | Vercel serverless entry points. Thin shims. |
| `vercel.json` | Route rewrites. Every public path needs an entry. |
| `.github/workflows/` | CI and the daily deal cron. |

## Conventions

**Python.** 4 spaces, double quotes, code lines under ~90 chars (embedded
HTML/CSS/JS blocks are exempt). Functions get a one-line docstring when the
name isn't enough. Section banners stay in the
`# ---------------- name` style already used.

**Logging.** Every request has a `req_id`; thread it through
(`log.info("[%s] ...", req_id, ...)`). Log what an LLM call cost us in time
and what it returned in outline. That's how we debug production from Vercel
logs. Never log an API key or a full prompt payload.

**HTML templates.** Five page templates live as module-level strings in
`app.py` (`HTML`, `HOW_IT_WORKS_HTML`, `CREDITS_HTML`, `HISTORY_HTML`,
`IDEAS_HTML`), each wrapped once by `_with_gtm`. The CSS custom properties
(`--ink`, `--body`, `--muted`, `--line`, `--line2`, `--field`) are duplicated
in all five. Change the palette in one, change it in all five.

**Escaping.** Anything user-supplied that reaches HTML goes through
`html.escape`. Ideas, comments and search wishes are attacker-controlled
input; treat them that way.

**LLM prompts.** Prompts live as module-level constants. They demand JSON
back and are parsed by `llm_json`. Three rules, learned the hard way:
- Ask for **JSON only**, and keep the shape example in the prompt.
- User-facing generated text (the `why` line on a listing) is **English, no
  em dashes**, under the word cap already in the prompt.
- Be skeptical by default: replicas, "in de stijl van", parts and bare frames
  get rejected. Vague listing → value it low.

**Writing for humans.** Product copy, commit messages and PR descriptions:
plain words, no em dashes, no "leverage", no "seamless", no "simply". Say the
thing.

## Adding things

**A deal category.** One dict in `CATEGORIES` in `deals.py`: `key`, `label`,
Dutch `queries` a seller would actually type, and a `target` sentence that
tells the valuer what counts and what to reject. Then
`python3 deals.py --dry-run --category <key>` and read the output before you
open the PR. If the finds are junk, the `target` is too loose.

**A page/route.** Five places, all of them:
1. the `*_HTML` template string in `app.py`,
2. the `_with_gtm(...)` wrap next to the others,
3. a branch in the GET section of `app()`,
4. a rewrite in `vercel.json`,
5. an entry in `SITEMAP_XML` if it should be indexed.

**A POST action.** A branch in the POST section of `app()`, dispatched on
`payload["action"]`. Validate input, raise `ValueError` with a readable
message on bad input; the handler turns it into a 500 with that text.

## Branches, commits, PRs

- **No direct pushes to `main`.** One PR per task, one review before merge.
- Branch names: a meaningful slug, `claude/<slug>` for agent-authored work.
- Commit messages: imperative, one line, what and why.
  "Dedupe relisted items in daily deal hunt", not "fix stuff".
- Keep the PR to the task. Spotted something else? Say so in the PR body or
  open an issue. Don't smuggle it in.
- PR description: what changed, how you checked it, what you deliberately
  left out.

## Before you push

There is no linter or test suite in CI yet (it's on the backlog). Until there
is, the floor is:

```bash
python3 -m py_compile app.py deals.py mcp_server.py listing_cards_ui.py api/*.py
python3 app.py            # open localhost:8000, run a real search
```

Touched `deals.py`? Run `--dry-run` on at least one category. Touched a
template? Load that page. Touched the MCP server? Start it and call the tool.
"It looks right" is not a check.

Don't claim a check you didn't run. If you couldn't verify something, write
that in the PR.

## Things we don't want repeated

Append here when an agent gets something wrong. One line each.

- Don't add a dependency to make a small thing easier. Stdlib or nothing.
- Don't swallow exceptions silently in the request path. Log them with the
  `req_id`.
- Don't let a broken Upstash call render an error page; fall back to empty.
- Don't put em dashes in generated user-facing text.
