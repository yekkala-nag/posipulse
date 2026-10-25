"""
Regression test for Vercel Cron scheduled news polling across all 16 languages.
Ensures no active language is omitted from background ingestion.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.storage.db import StorageEngine


@pytest.fixture
def test_env():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    storage = StorageEngine(":memory:")
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)
    return client, registry


def test_cron_endpoint_polls_all_sixteen_languages(test_env):
    """
    Regression Test:
    /api/cron previously hardcoded only 8 languages: ['en', 'hi', 'ur', 'bn', 'mr', 'te', 'ta', 'gu'].
    The other 8 languages ('kn', 'or', 'ml', 'pa', 'as', 'ne', 'mai', 'gom') were omitted,
    causing those languages to remain permanently empty in production.
    This test verifies that all 16 active languages are included in /api/cron.
    """
    client, registry = test_env
    all_codes = {c.language_code for c in registry.list_all() if c.status.value == "active"}
    assert len(all_codes) == 16

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

        processed_langs = {item["language"] for item in data["processed"]}
        # Verify all 16 languages were polled
        missing = all_codes - processed_langs
        assert not missing, f"The following active languages were omitted from /api/cron: {sorted(missing)}"
        assert len(processed_langs) == 16
