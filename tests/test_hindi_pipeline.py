"""
End-to-End Hindi Pipeline and Source Tests (Phase 3)
Tests adding Hindi (Tier 1 core language) through:
- BBC Hindi RSS feed fixture parsing
- Article Normalizer (Devanagari text & URL cleaning)
- Language Detection (Devanagari script validation)
- Deduplication & Idempotency
- Hindi Headline Pre-Filter (Rejects fatal boiler explosion)
- Positivity Classifier (Constructive Rubric v1.0.0 on Devanagari text)
- Hindi Abstractive Summarizer (Original Wording, 35-85 words)
- Faithfulness Verifier (Unicode Indic word tokenization & verbatim guard)
- Storage & FastAPI Gateway (/v1/feed?language=hi)
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.pipeline.orchestrator import PipelineOrchestrator
from src.storage.db import StorageEngine


@pytest.fixture
def fixture_dir():
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def bbc_hindi_xml(fixture_dir):
    with open(fixture_dir / "bbc_hindi_sample.xml", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def registry():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    return LanguageConfigRegistry(str(config_dir))


def test_hindi_pipeline_end_to_end(bbc_hindi_xml, registry):
    # 1. Setup isolated storage and load Hindi configuration
    storage = StorageEngine(":memory:")
    hi_config = registry.get_strict("hi")

    # 2. Initialize orchestrator for Hindi
    orchestrator = PipelineOrchestrator(language_config=hi_config, storage=storage)

    # 3. Process recorded Hindi XML fixture
    stats = orchestrator.process_raw_xml(
        xml_content=bbc_hindi_xml,
        source_id="bbc-hindi"
    )

    # 4. Verify telemetry and gate filtering in Devanagari
    assert stats["ingested_count"] == 5
    assert stats["normalized_count"] == 5
    assert stats["language_matched_count"] == 5
    assert stats["headline_rejected_count"] == 1, "Boiler blast with casualties must be rejected at pre-filter"
    assert stats["classified_negative_count"] == 2, "Toxic positivity and neutral RBI rate must be rejected"
    assert stats["classified_positive_count"] == 2, "Solar health centers and low-water paddy must be positive"
    assert stats["verification_passed_count"] == 2, "Both positive summaries must pass faithfulness verification"
    assert stats["published_count"] == 2, "Exactly 2 verified positive items must be published"
    assert stats["run_cost_usd"] > 0.0

    # 5. Verify database storage invariants: raw publisher text is NEVER persisted
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles WHERE language = 'hi'")
        rows = cursor.fetchall()
        assert len(rows) == 2
        col_names = [description[0] for description in cursor.description]
        assert "raw_body" not in col_names

    # 6. Test FastAPI Client API Gateway for Hindi
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)

    feed_resp = client.get("/v1/feed?language=hi")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert feed_data["total_returned"] == 2
    articles = feed_data["articles"]
    assert len(articles) == 2

    # Verify first published Hindi article
    art1 = articles[0]
    assert art1["language"] == "hi"
    assert art1["is_rtl"] is False, "Devanagari is Left-to-Right"
    assert art1["summary"]["verified"] is True
    assert art1["positivity"]["label"] == "positive"
    assert art1["positivity"]["score"] >= 0.85
    assert art1["canonical_url"].startswith("https://www.bbc.com/hindi/")
    assert "utm_source" not in art1["canonical_url"], "Normalizer must strip tracking query parameters"
    assert "raw_body" not in art1

    # Verify single article endpoint
    art_id = art1["id"]
    single_resp = client.get(f"/v1/articles/{art_id}")
    assert single_resp.status_code == 200
    assert single_resp.json()["id"] == art_id

    # Test DPDP Act Delisting on Hindi article
    delist_resp = client.post("/v1/privacy/delist", json={
        "article_id": art_id,
        "requester_name": "नागरिक",
        "requester_email": "citizen@example.org",
        "reason": "DPDP Act privacy delisting request"
    })
    assert delist_resp.status_code == 202

    # Assert article is now immediately 404
    assert client.get(f"/v1/articles/{art_id}").status_code == 404
    # Assert feed now has only 1 remaining Hindi article
    assert client.get("/v1/feed?language=hi").json()["total_returned"] == 1
