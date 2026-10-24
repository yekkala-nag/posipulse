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

try:
    from src.api.app import app as application
    app = application
except Exception as e:
    err_tb = traceback.format_exc()
    print("FATAL SERVERLESS BOOT ERROR:\n" + err_tb, file=sys.stderr)

    async def fallback_app(scope, receive, send):
        if scope["type"] == "http":
            body = (
                "<!DOCTYPE html><html><head><title>Serverless Boot Error</title></head>"
                "<body style='font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;'>"
                "<h1 style='color:#c00;'>⚠️ Serverless Initialization Error</h1>"
                "<p>PosiPulse failed to boot in this serverless runtime environment:</p>"
                f"<pre style='background:#f7f7f7;padding:16px;border-radius:6px;border:1px solid #ddd;overflow:auto;line-height:1.4;'>{err_tb}</pre>"
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

    app = fallback_app
