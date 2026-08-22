# Vercel serverless entry point. All routes are rewritten here (see
# vercel.json); the real logic lives in app.py at the repo root.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import Handler as handler  # noqa: E402,F401  (Vercel looks for `handler`)
