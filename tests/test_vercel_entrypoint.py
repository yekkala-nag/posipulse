"""
Vercel Serverless Entrypoint & Deployment Readiness Tests
Verifies:
1. api/index.py imports and exposes ASGI app correctly.
2. Root and static routes resolve through the Vercel entrypoint.
3. vercel.json configuration schema is valid.
4. .vercelignore excludes heavyweight build artifacts.
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient

from api.index import app as vercel_app


def test_vercel_app_entrypoint():
    """Verify api/index.py boots the FastAPI application cleanly."""
    client = TestClient(vercel_app)

    # Health check
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    # Languages endpoint
    lang_res = client.get("/v1/languages")
    assert lang_res.status_code == 200
    languages = lang_res.json()["languages"]
    assert len(languages) == 16

    # Web reader UI entrypoint
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "PosiPulse" in root_res.text
    assert "text/html" in root_res.headers.get("content-type", "")

    # Static CSS
    css_res = client.get("/static/index.css")
    assert css_res.status_code == 200
    assert "--bg-primary" in css_res.text

    # Static JS
    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert "loadFeed" in js_res.text


def test_vercel_config_validity():
    """Verify vercel.json contains valid build and route directives."""
    repo_root = Path(__file__).resolve().parent.parent
    vercel_json_path = repo_root / "vercel.json"
    assert vercel_json_path.exists()

    cfg = json.loads(vercel_json_path.read_text(encoding="utf-8"))
    assert cfg.get("version") == 2
    assert "builds" in cfg
    assert any(b.get("use") == "@vercel/python" for b in cfg["builds"])
    assert "routes" in cfg


def test_vercel_ignore_rules():
    """Verify .vercelignore excludes heavy local folders."""
    repo_root = Path(__file__).resolve().parent.parent
    ignore_path = repo_root / ".vercelignore"
    assert ignore_path.exists()

    rules = ignore_path.read_text(encoding="utf-8")
    assert ".venv" in rules
    assert "__pycache__" in rules
    assert "tests/" in rules
