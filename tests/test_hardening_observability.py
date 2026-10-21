"""
Observability & DPDP Safe Harbor Audit Tests (Phase 6)
Verifies:
1. Standard Prometheus exposition format on GET /metrics?format=prometheus.
2. Structured JSON telemetry on GET /metrics.
3. Structured JSON logging with trace context.
4. DPDP Act 2023 compliance: immediate delisting propagation across feeds, clusters, and articles.
5. In-database raw-body non-retention invariant audit.
"""

import json
import logging
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.observability.logger import JSONFormatter
from src.observability.metrics import metrics_collector
from src.storage.db import StorageEngine


@pytest.fixture
def test_setup():
    metrics_collector.reset_for_testing()
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    storage = StorageEngine(":memory:")
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)
    return client, storage, registry


def test_prometheus_metrics_export(test_setup):
    """Verify Prometheus text format exposition at /metrics?format=prometheus."""
    client, _, _ = test_setup

    # Record some sample telemetry
    metrics_collector.increment_counter("posipulse_articles_published_total", language="en")
    metrics_collector.record_stage_execution("summarize", 0.125, "success")
    metrics_collector.set_gauge("posipulse_active_languages", 16)

    # 1. Query with query param
    resp = client.get("/metrics?format=prometheus")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    content = resp.text
    assert "# HELP posipulse_pipeline_stage_total" in content
    assert "# TYPE posipulse_pipeline_stage_total counter" in content
    assert "posipulse_articles_published_total_language_en 1.0" in content
    assert "posipulse_active_languages 16.0" in content

    # 2. Query with Accept header
    resp_hdr = client.get("/metrics", headers={"Accept": "text/plain; version=0.0.4"})
    assert resp_hdr.status_code == 200
    assert "posipulse_active_languages 16.0" in resp_hdr.text


def test_structured_json_metrics(test_setup):
    """Verify JSON metrics include both storage counts and pipeline telemetry."""
    client, _, _ = test_setup

    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_articles_evaluated" in data
    assert "published_count" in data
    assert "positive_acceptance_rate" in data
    assert "telemetry" in data
    assert "counters" in data["telemetry"]
    assert "gauges" in data["telemetry"]


def test_structured_json_logging():
    """Verify JSONFormatter creates valid JSON objects with trace context."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="posipulse.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=50,
        msg="Processed item successfully",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace_abc123"
    record.run_id = "run_xyz789"
    record.stage = "verifier"

    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Processed item successfully"
    assert parsed["trace_id"] == "trace_abc123"
    assert parsed["run_id"] == "run_xyz789"
    assert parsed["stage"] == "verifier"
    assert "timestamp" in parsed


def test_dpdp_delisting_and_invariants_audit(test_setup):
    """
    DPDP Safe Harbor Audit:
    1. Seed demo articles
    2. Request privacy delist
    3. Verify article vanishes from feed, single-article, and cluster endpoints
    4. Audit database to confirm no raw publisher text exists
    """
    client, storage, _ = test_setup

    # 1. Seed demo articles
    seed_res = client.post("/v1/demo/seed?language=en")
    assert seed_res.status_code == 200

    feed_res = client.get("/v1/feed?language=en")
    assert feed_res.status_code == 200
    articles = feed_res.json()["articles"]
    assert len(articles) >= 1
    target = articles[0]
    art_id = target["id"]

    # 2. Submit DPDP Delist Request
    delist_payload = {
        "article_id": art_id,
        "requester_name": "Jane Citizen",
        "requester_email": "jane@example.com",
        "reason": "Requesting erasure under Section 12 of the DPDP Act 2023."
    }
    delist_res = client.post("/v1/privacy/delist", json=delist_payload)
    assert delist_res.status_code == 202
    assert delist_res.json()["success"] is True

    # 3. Verify immediate exclusion from feed
    feed_after = client.get("/v1/feed?language=en")
    ids_after = [a["id"] for a in feed_after.json()["articles"]]
    assert art_id not in ids_after

    # 4. Verify 404 from single-article lookup
    art_res = client.get(f"/v1/articles/{art_id}")
    assert art_res.status_code == 404

    # 5. Verify cluster isolation if cluster_id present
    if target.get("cluster_id"):
        cluster_res = client.get(f"/v1/clusters/{target['cluster_id']}")
        if cluster_res.status_code == 200:
            cluster_ids = [a["id"] for a in cluster_res.json()["articles"]]
            assert art_id not in cluster_ids

    # 6. Database Schema & Data Non-Retention Invariant Audit
    with storage._get_connection() as conn:
        cursor = conn.cursor()

        # Check table schemas
        cursor.execute("PRAGMA table_info(articles)")
        cols = [r[1] for r in cursor.fetchall()]
        assert "raw_body" not in cols, "CRITICAL: raw_body found in articles columns!"
        assert "body" not in cols, "CRITICAL: body found in articles columns!"

        # Check delisted record status
        cursor.execute("SELECT status FROM articles WHERE id = ?", (art_id,))
        row = cursor.fetchone()
        assert row["status"] == "delisted"

        # Check audit trail record
        cursor.execute("SELECT requester_email, reason FROM delisted_articles WHERE article_id = ?", (art_id,))
        audit_row = cursor.fetchone()
        assert audit_row["requester_email"] == "jane@example.com"
