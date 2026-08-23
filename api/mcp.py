# Vercel serverless entry point: exposes the ASGI app from mcp_server.py at
# the repo root, served at /mcp (see the rewrite in vercel.json).
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_server import app  # noqa: E402,F401
