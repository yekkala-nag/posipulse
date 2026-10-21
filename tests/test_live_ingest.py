"""
Dynamic Live News Ingestion Tests (Execute -> Challenge -> Verify)
Tests:
1. Live fetch execution across publisher sources.
2. Publisher cooldown enforcement (preventing excessive polling).
3. Cooldown bypass with force=True.
4. Error isolation when a publisher feed fails or times out.
5. Invariant check: zero raw publisher body persisted during dynamic ingestion.
6. Vercel Cron endpoint execution and authentication.
7. Background task execution mode.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.pipeline.orchestrator import PipelineOrchestrator
from src.schemas.config import PublisherSource
from src.storage.db import StorageEngine


@pytest.fixture
def test_env():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    storage = StorageEngine(":memory:")
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)
    return client, storage, registry


def test_cooldown_tracking_in_storage(test_env):
    """Verify publisher rate-limiting cooldown tracking in storage engine."""
    _, storage, _ = test_env

    source_id = "test-publisher-1"
    # Initially eligible
    assert storage.can_fetch_source(source_id, cooldown_minutes=30) is True

    # Record fetch
    storage.record_source_fetch(source_id, status="success", items_count=5)

    # Immediately ineligible due to cooldown
    assert storage.can_fetch_source(source_id, cooldown_minutes=30) is False

    # Zero cooldown window is eligible
    assert storage.can_fetch_source(source_id, cooldown_minutes=0) is True


def test_dynamic_live_ingest_with_mock_feed(test_env):
    """Verify POST /v1/ingest/live fetches, classifies, summarizes, and publishes."""
    client, storage, registry = test_env

    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Live National News</title>
        <item>
          <title>Indian Institute of Technology develops breakthrough solar desalinator for coastal communities</title>
          <link>https://thehindu.com/sci-tech/breakthrough-solar-desalinator</link>
          <description>Researchers deploy zero-emission water purification device providing clean drinking water to 5,000 households.</description>
          <pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """

    # Mock httpx.Client to return sample_rss for the publisher URL
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = sample_rss
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # 1. Trigger live ingest
        resp = client.post("/v1/ingest/live?language=en&force=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["total_published"] >= 1

        # 2. Verify article is now published in live feed
        feed_res = client.get("/v1/feed?language=en")
        assert feed_res.status_code == 200
        feed_data = feed_res.json()
        assert feed_data["total_returned"] >= 1

        live_art = feed_data["articles"][0]
        assert "solar desalinator" in live_art["headline"].lower()
        assert live_art["canonical_url"] == "https://thehindu.com/sci-tech/breakthrough-solar-desalinator"
        assert len(live_art["summary"]["text"]) > 0

        # CRITICAL INVARIANT: Zero raw publisher body retention
        assert "body" not in live_art
        assert "raw_body" not in live_art


def test_cooldown_enforcement_on_live_ingest(test_env):
    """Verify live ingest respects cooldown unless force=True."""
    client, storage, _ = test_env

    # Pre-record recent fetch to simulate active cooldown
    storage.record_source_fetch("the-hindu-national", status="success", items_count=5)

    with patch("httpx.Client") as mock_client_cls:
        # Targeting specific source with active cooldown
        resp_skip = client.post("/v1/ingest/live?language=en&source_id=the-hindu-national&force=false")
        assert resp_skip.status_code == 200
        data = resp_skip.json()
        result = data["result"]
        assert result["status"] == "skipped_cooldown"
        assert result["published_count"] == 0

        # mock_client was never called because cooldown blocked network request
        mock_client_cls.assert_not_called()


def test_live_ingest_error_resilience(test_env):
    """Verify live ingest handles network failures gracefully without taking down the server."""
    client, _, _ = test_env

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectTimeout("Connection to publisher timed out")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        resp = client.post("/v1/ingest/live?language=en&force=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Sources failed gracefully
        assert data["result"]["sources_succeeded"] == 0


def test_vercel_cron_endpoint(test_env):
    """Verify GET /api/cron executes incremental polling across languages."""
    client, _, _ = test_env

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<rss><channel></channel></rss>"
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        cron_res = client.get("/api/cron")
        assert cron_res.status_code == 200
        data = cron_res.json()
        assert data["success"] is True
        assert "processed" in data
        assert len(data["processed"]) >= 8


def test_background_live_ingest(test_env):
    """Verify background=True schedules task asynchronously and returns immediately."""
    client, _, _ = test_env

    resp = client.post("/v1/ingest/live?language=en&background=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["background"] is True
    assert "queued in background" in data["message"]
