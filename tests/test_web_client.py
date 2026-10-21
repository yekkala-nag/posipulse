"""
Web Client & Static Gateway Tests (Phase 5)
Verifies:
1. Web reader client HTML entrypoint at '/' and '/app'.
2. Static asset distribution ('/static/index.css', '/static/app.js').
3. Multi-language demo seeding endpoint ('/v1/demo/seed').
4. RTL directionality flag on feed items for Perso-Arabic scripts (Urdu).
5. Prominent publisher link integrity and non-retention of raw publisher text.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.storage.db import StorageEngine


@pytest.fixture
def client():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    storage = StorageEngine(":memory:")
    app = create_app(storage=storage, registry=registry)
    return TestClient(app)


def test_web_index_html_serving(client):
    """Verify that the root endpoint serves the PosiPulse HTML5 client."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert "PosiPulse" in content
    assert "शुद्ध समाचार" in content
    assert 'rel="stylesheet" href="/static/index.css"' in content
    assert 'src="/static/app.js"' in content
    assert 'id="language-strip"' in content
    assert 'id="articles-grid"' in content


def test_web_app_alias_serving(client):
    """Verify /app alias serves the same HTML document."""
    response = client.get("/app")
    assert response.status_code == 200
    assert "PosiPulse" in response.text


def test_static_css_serving(client):
    """Verify CSS design system stylesheet is available and properly formatted."""
    response = client.get("/static/index.css")
    assert response.status_code == 200
    content = response.text
    assert "--bg-primary" in content
    assert "--accent-emerald" in content
    assert "[data-theme=" in content
    assert '[dir="rtl"]' in content
    assert ".substance-meter" in content


def test_static_js_serving(client):
    """Verify JS application controller is available."""
    response = client.get("/static/app.js")
    assert response.status_code == 200
    content = response.text
    assert "loadLanguages" in content
    assert "loadFeed" in content
    assert "seedDemoStories" in content


def test_demo_seeding_and_feed_display(client):
    """Verify seeding demo content for English and querying feed."""
    # 1. Feed is initially empty
    feed_res = client.get("/v1/feed?language=en")
    assert feed_res.status_code == 200
    assert feed_res.json()["total_returned"] == 0

    # 2. Seed English demo fixture
    seed_res = client.post("/v1/demo/seed?language=en")
    assert seed_res.status_code == 200
    seed_data = seed_res.json()
    assert seed_data["success"] is True
    assert seed_data["published_count"] >= 1

    # 3. Feed now contains constructive articles
    feed_res = client.get("/v1/feed?language=en")
    assert feed_res.status_code == 200
    feed_data = feed_res.json()
    assert feed_data["total_returned"] >= 1

    article = feed_data["articles"][0]
    # Invariants
    assert article["language"] == "en"
    assert article["is_rtl"] is False
    assert "body" not in article
    assert "raw_body" not in article
    assert article["canonical_url"].startswith("http")
    assert "utm_" not in article["canonical_url"]
    assert len(article["summary"]["text"]) > 0
    assert article["summary"]["word_count"] > 0


def test_demo_seeding_urdu_rtl(client):
    """Verify Urdu demo fixture seeds and preserves RTL layout flag."""
    seed_res = client.post("/v1/demo/seed?language=ur")
    assert seed_res.status_code == 200
    assert seed_res.json()["published_count"] >= 1

    feed_res = client.get("/v1/feed?language=ur")
    assert feed_res.status_code == 200
    feed_data = feed_res.json()
    assert feed_data["total_returned"] >= 1

    article = feed_data["articles"][0]
    assert article["language"] == "ur"
    assert article["is_rtl"] is True
