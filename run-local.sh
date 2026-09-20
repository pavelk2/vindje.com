#!/usr/bin/env bash
# Load .env and run app.py locally.
#
# First run: creates .env from .env.example automatically (no manual
# copying needed) and starts the app. Open .env afterward and fill in
# your real keys to enable AI search and sharing, then run this again.
#
# .env is gitignored — it holds real secrets and must never be committed
# or made public (this repo is public, see AGENTS.md).
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
set -a
source .env
set +a
python3 app.py
