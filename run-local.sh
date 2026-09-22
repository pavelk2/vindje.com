#!/usr/bin/env bash
# Load .env and run app.py locally, auto-restarting it whenever a watched
# source file changes (app.py, deals.py, digest.py, listing_cards_ui.py).
#
# First run: creates .env from .env.example automatically (no manual
# copying needed) and starts the app. Open .env afterward and fill in
# your real keys to enable AI search and sharing, then run this again.
#
# .env is gitignored — it holds real secrets and must never be committed
# or made public (this repo is public, see AGENTS.md).
#
# The auto-restart is polling-based on purpose (devserver.py, stdlib
# only, no watchdog dependency), so it works for every teammate with
# nothing but the python3 the project already requires. The browser tab
# still needs a manual refresh (F5) after each restart to see the change.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
set -a
source .env
set +a

PORT="${PORT:-8000}"

# A previous run left running (Ctrl-C missed it, terminal closed, etc.)
# holds the port and the new one fails with "Address already in use".
# Free it instead of hunting the PID by hand each time — only kills a
# leftover app.py, never anything else bound to the port.
for pid in $(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true); do
  if ps -p "$pid" -o command= 2>/dev/null | grep -q "app\.py"; then
    echo "Port $PORT is held by a leftover app.py (PID $pid), stopping it..."
    kill "$pid"
  fi
done

python3 devserver.py
