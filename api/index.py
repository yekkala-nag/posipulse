"""
Vercel Serverless Function Entrypoint
Bridges Vercel's Python ASGI runtime to the PosiPulse FastAPI Gateway.
"""

from pathlib import Path
import sys

import traceback

# Ensure repository root is on sys.path for internal imports
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.api.app import app

# Top-level ASGI variable declarations required by Vercel's build scanner
app = app
application = app
handler = app
