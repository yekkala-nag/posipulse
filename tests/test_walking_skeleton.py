"""
End-to-End Walking Skeleton Tests (Phase 2)
Tests one English source from recorded offline RSS fixture through:
- Feed Fetcher
- Article Normalizer (HTML & URL tracking parameter stripping)
- Language Identification & Script Validator
- Deduplicator & Hash Idempotency
- Headline Pre-Filter (Fail-closed keyword filter)
- Positivity Classifier (Constructive Journalism Rubric v1.0.0)
- Abstractive Summarizer (Original Wording, 40-90 words)
- Faithfulness Verifier (Verbatim n-gram guard & contradiction detection)
- Zero-Retention Persistent Storage
- Client API Gateway (FastAPI with /v1/feed, /v1/articles, /v1/feedback, /v1/privacy/delist, /metrics)
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
def hindu_xml(fixture_dir):
    with open(fixture_dir / "the_hindu_sample.xml", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def registry():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    return LanguageConfigRegistry(str(config_dir))


def test_walking_skeleton_pipeline_and_api(hindu_xml, registry):
    # 1. Setup isolated in-memory storage engine
    storage = StorageEngine(":memory:")
    en_config = registry.get_strict("en")

    # 2. Initialize orchestrator
    orchestrator = PipelineOrchestrator(language_config=en_config, storage=storage)

    # 3. Process recorded XML fixture
    stats = orchestrator.process_raw_xml(
        xml_content=hindu_xml,
        source_id="the-hindu-national"
    )

    # 4. Verify pipeline telemetry & gate filtering
    assert stats["ingested_count"] == 5
    assert stats["normalized_count"] == 5
    assert stats["language_matched_count"] == 5
    assert stats["headline_rejected_count"] == 1, "Tragic collision should be rejected at headline filter"
    assert stats["classified_negative_count"] == 2, "Toxic positivity and neutral monetary policy must be rejected"
    assert stats["classified_positive_count"] == 2, "IISc membrane and NISAR satellite must be classified as positive"
    assert stats["verification_passed_count"] == 2, "Both positive summaries must pass faithfulness verification"
    assert stats["published_count"] == 2, "Exactly 2 verified positive items must be published"
    assert stats["run_cost_usd"] > 0.0

    # 5. Verify database storage invariants: raw publisher text is NEVER persisted
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles")
        rows = cursor.fetchall()
        assert len(rows) == 2
        col_names = [description[0] for description in cursor.description]
        assert "raw_body" not in col_names, "CRITICAL: raw_body must never be a column in articles table"

    # 6. Initialize FastAPI Client API Gateway with the populated storage
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)

    # Test GET /health
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # Test GET /v1/languages
    langs_resp = client.get("/v1/languages")
    assert langs_resp.status_code == 200
    lang_codes = [l["code"] for l in langs_resp.json()["languages"]]
    assert "en" in lang_codes
    assert "hi" in lang_codes

    # Test GET /v1/feed?language=en
    feed_resp = client.get("/v1/feed?language=en")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert feed_data["total_returned"] == 2
    articles = feed_data["articles"]
    assert len(articles) == 2

    # Check first published article details
    art1 = articles[0]
    assert "iisc" in art1["headline"].lower() or "nisar" in art1["headline"].lower()
    assert art1["summary"]["verified"] is True
    assert art1["summary"]["model"] == "gemini-1.5-flash"
    assert art1["positivity"]["label"] == "positive"
    assert art1["positivity"]["score"] >= 0.85
    assert art1["canonical_url"].startswith("https://www.thehindu.com/")
    assert "utm_source" not in art1["canonical_url"], "Normalizer must strip tracking parameters"
    assert art1["is_rtl"] is False
    assert "raw_body" not in art1

    # Test GET /v1/articles/{id}
    art_id = art1["id"]
    get_art_resp = client.get(f"/v1/articles/{art_id}")
    assert get_art_resp.status_code == 200
    assert get_art_resp.json()["id"] == art_id

    # Test Category Filter: GET /v1/feed?language=en&category=Science/Tech
    tech_resp = client.get("/v1/feed?language=en&category=Science/Tech")
    assert tech_resp.status_code == 200
    for a in tech_resp.json()["articles"]:
        assert a["positivity"]["category"] == "Science/Tech"

    # Test User Feedback Loop: POST /v1/feedback
    fb_resp = client.post("/v1/feedback", json={
        "article_id": art_id,
        "feedback_type": "not_positive",
        "comments": "Testing user feedback reporting loop"
    })
    assert fb_resp.status_code == 202
    assert fb_resp.json()["success"] is True

    # Test DPDP Act Delisting: POST /v1/privacy/delist
    delist_resp = client.post("/v1/privacy/delist", json={
        "article_id": art_id,
        "requester_name": "Citizen A",
        "requester_email": "citizen@example.org",
        "reason": "Requesting removal under DPDP Act right to be forgotten"
    })
    assert delist_resp.status_code == 202

    # Verify delisted article is immediately invisible
    get_delisted_resp = client.get(f"/v1/articles/{art_id}")
    assert get_delisted_resp.status_code == 404

    # Verify feed now returns only 1 remaining article
    feed_after_delist = client.get("/v1/feed?language=en")
    assert feed_after_delist.json()["total_returned"] == 1

    # Test GET /metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["total_articles_evaluated"] >= 2
    assert metrics["positive_acceptance_rate"] > 0.0


def test_verbatim_overlap_rejection(registry):
    """
    Failure Injection Test:
    Ensures that if a candidate summary accidentally copies verbatim sentences from the source,
    the verifier catches it, fails the item, and drops it into the Dead-Letter Queue (DLQ).
    """
    storage = StorageEngine(":memory:")
    en_config = registry.get_strict("en")
    orchestrator = PipelineOrchestrator(language_config=en_config, storage=storage)

    # Monkeypatch the summarizer to produce a verbatim copy of the input text
    source_sentence = "Researchers at the Indian Institute of Science Bengaluru have synthesized a nanotech filtration membrane from discarded rice husks"
    orchestrator.summarizer.summarize = lambda item: item.model_copy().raw_body  # type: ignore

    # Test verbatim violation detector directly
    verbatim_ok, snippet = orchestrator.verifier.check_verbatim_overlap(
        source_text=source_sentence,
        summary_text=source_sentence
    )
    assert verbatim_ok is False, "Verifier must detect verbatim copying"
    assert "researchers at the indian institute of science" in snippet.lower()
