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

real_app = None
init_error = None

try:
    from src.api.app import app as _fastapi_app
    real_app = _fastapi_app
except Exception:
    init_error = traceback.format_exc()
    print("CRITICAL_STARTUP_ERROR:\n" + init_error, file=sys.stderr)


async def app(scope, receive, send):
    """Top-level ASGI callable recognized by Vercel's build scanner."""
    if init_error:
        if scope["type"] == "http":
            body = (
                "<!DOCTYPE html><html><head><title>PosiPulse Serverless Startup Error</title></head>"
                "<body style='font-family:monospace;padding:24px;background:#1e1e1e;color:#ff6b6b;'>"
                "<h2>⚠️ Startup Exception in Vercel Serverless Runtime</h2>"
                f"<pre style='background:#2a2a2a;padding:16px;border-radius:8px;border:1px solid #444;color:#eee;overflow:auto;line-height:1.5;'>{init_error}</pre>"
                "</body></html>"
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
        return

    try:
        await real_app(scope, receive, send)
    except Exception as exc:
        err = traceback.format_exc()
        print("REQUEST_RUNTIME_ERROR:\n" + err, file=sys.stderr)
        if scope["type"] == "http":
            body = (
                "<!DOCTYPE html><html><head><title>PosiPulse Request Error</title></head>"
                "<body style='font-family:monospace;padding:24px;background:#1e1e1e;color:#f39c12;'>"
                "<h2>⚠️ Request Exception in Vercel Serverless Runtime</h2>"
                f"<pre style='background:#2a2a2a;padding:16px;border-radius:8px;border:1px solid #444;color:#eee;overflow:auto;line-height:1.5;'>{err}</pre>"
                "</body></html>"
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })


# Top-level ASGI variable declarations required by Vercel's build scanner
application = app
handler = app
