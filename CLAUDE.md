# CLAUDE.md

@AGENTS.md

Everything for this repo lives in `AGENTS.md`, so every tool reads the same
rules. Add new conventions there, not here. This file only holds things
specific to Claude Code.

## Claude Code specifics

- Read `AGENTS.md` before the first edit in a session.
- `app.py` is ~2500 lines. Grep for the `# ---- name` section banners instead
  of reading it end to end.
- Verification is on you: run the commands under "Before you push" and report
  what actually happened, including failures.
- Never read or print secrets. If you need to know whether a variable is set,
  check that it exists, don't echo it.
