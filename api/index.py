# Vercel serverless entry point: exposes the WSGI app from app.py at the
# repo root. All routes are rewritten here (see vercel.json).
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402,F401  (Vercel loads the top-level `app`)
