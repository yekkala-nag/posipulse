"""
End-to-End Pipeline & API Tests for Tier 1 Indic Languages (Phase 4)
Covers Bengali (bn), Marathi (mr), Telugu (te), and Tamil (ta):
1. Configuration loading & schema validation
2. RSS fixture parsing & normalization (URL tracking stripping)
3. Script-level language detection
4. Headline pre-filter for disaster/crime triggers
5. Positivity classifier & toxic positivity rejection
6. Abstractive summarization & substance length bands
7. Faithfulness verifier & Indic verbatim overlap guard
8. Zero raw body persistence invariant
9. FastAPI client endpoints (/v1/languages, /v1/feed?language={code})
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.verifier import FaithfulnessVerifier
from src.schemas.article import EphemeralIngestedItem, SummaryMetadata
from src.storage.db import StorageEngine


@pytest.fixture
def fixture_dir():
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def registry():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    return LanguageConfigRegistry(str(config_dir))


def test_tier1_language_configs_loaded(registry):
    """Verify all Tier 1 language configurations are valid and meet quality gate specifications."""
    tier1_codes = ["bn", "mr", "te", "ta"]
    for code in tier1_codes:
        cfg = registry.get_strict(code)
        assert cfg.language_code == code
        assert cfg.tier.value == "tier_1"
        assert cfg.status.value == "active"
        assert cfg.quality_gate.min_positive_precision >= 0.90
        assert cfg.quality_gate.min_faithfulness_pass_rate >= 0.95
        assert len(cfg.sources) >= 3
        healthy_sources = [s for s in cfg.sources if s.health_status == "healthy"]
        assert len(healthy_sources) >= 3
        assert cfg.length_band.min_words >= 25
        assert cfg.length_band.max_words <= 90


@pytest.mark.parametrize("lang_code,fixture_name,source_id,expected_script", [
    ("bn", "anandabazar_sample.xml", "anandabazar-patrika", "Eastern Nagri"),
    ("mr", "loksatta_marathi_sample.xml", "loksatta-national", "Devanagari"),
    ("te", "eenadu_telugu_sample.xml", "eenadu-national", "Telugu"),
    ("ta", "dinamalar_tamil_sample.xml", "dinamalar-national", "Tamil"),
])
def test_tier1_pipeline_end_to_end(lang_code, fixture_name, source_id, expected_script, fixture_dir, registry):
    # 1. Load fixture XML
    fixture_path = fixture_dir / fixture_name
    assert fixture_path.exists(), f"Fixture {fixture_name} not found"
    with open(fixture_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    # 2. Setup isolated storage and load config
    storage = StorageEngine(":memory:")
    config = registry.get_strict(lang_code)
    assert config.script == expected_script

    orchestrator = PipelineOrchestrator(language_config=config, storage=storage)

    # 3. Process XML fixture
    stats = orchestrator.process_raw_xml(xml_content=xml_content, source_id=source_id)

    # 4. Verify telemetry across stages
    assert stats["ingested_count"] == 5, f"{lang_code}: expected 5 ingested items"
    assert stats["normalized_count"] == 5
    assert stats["language_matched_count"] == 5
    assert stats["headline_rejected_count"] == 1, f"{lang_code}: fatal accident must be rejected at pre-filter"
    assert stats["classified_negative_count"] == 2, f"{lang_code}: toxic positivity & neutral policy must be rejected"
    assert stats["classified_positive_count"] == 2, f"{lang_code}: 2 constructive milestones must be positive"
    assert stats["verification_passed_count"] == 2, f"{lang_code}: both summaries must pass faithfulness verification"
    assert stats["published_count"] == 2, f"{lang_code}: exactly 2 verified items published"
    assert stats["run_cost_usd"] > 0.0

    # 5. Invariant: Raw publisher body text is NEVER stored in SQLite
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles WHERE language = ?", (lang_code,))
        rows = cursor.fetchall()
        assert len(rows) == 2
        col_names = [d[0] for d in cursor.description]
        assert "raw_body" not in col_names

    # 6. Test FastAPI Gateway for this language
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)

    # Verify /languages includes this language
    lang_resp = client.get("/v1/languages")
    assert lang_resp.status_code == 200
    languages = lang_resp.json()["languages"]
    matched_lang = next((l for l in languages if l["code"] == lang_code), None)
    assert matched_lang is not None
    assert matched_lang["is_rtl"] is False

    # Verify /feed?language={code}
    feed_resp = client.get(f"/v1/feed?language={lang_code}")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert feed_data["total_returned"] == 2
    articles = feed_data["articles"]
    assert len(articles) == 2

    # Verify article fields and constraints
    for art in articles:
        assert art["language"] == lang_code
        assert art["is_rtl"] is False
        assert art["summary"]["verified"] is True
        assert art["positivity"]["label"] == "positive"
        assert art["positivity"]["score"] >= 0.85
        assert "utm_source" not in art["canonical_url"], "Tracking query parameters must be stripped"
        assert "raw_body" not in art
        assert len(art["summary"]["text"].split()) >= config.length_band.min_words
        assert len(art["summary"]["text"].split()) <= config.length_band.max_words


def test_verbatim_guard_indic_scripts():
    """Verify verbatim overlap guard catches >= 7 consecutive copied tokens in Indic scripts."""
    from datetime import datetime, timezone
    verifier = FaithfulnessVerifier(max_consecutive_verbatim_tokens=7)

    # Bengali test: exact 7-word copy from source body
    bn_body = "ঘূর্ণিঝড়প্রবণ সুন্দরবনের গোসাবা ব্লকে পাঁচশত জন স্থানীয় গ্রামবাসী নারী স্বেচ্ছায় ম্যানগ্রোভ নার্সারি তৈরি করে নদীবাঁধ বরাবর নতুন বন সৃজন করেছেন"
    bn_violating_summary = "এই উদ্যোগ সুন্দরবনের গোসাবা ব্লকে পাঁচশত জন স্থানীয় গ্রামবাসী নারী স্বেচ্ছায় কাজ করে পরিবেশ রক্ষা করেছে এবং নারীদের স্বাবলম্বী করেছে অনেক বছর ধরে।"
    
    verbatim_ok, snippet = verifier.check_verbatim_overlap(bn_body, bn_violating_summary)
    assert verbatim_ok is False
    assert snippet is not None

    item_bn = EphemeralIngestedItem(
        id="test-bn-verbatim",
        source_id="test",
        source_name="Test Source",
        url="https://example.com/bn",
        canonical_url="https://example.com/bn",
        headline="টেস্ট শিরোনাম",
        raw_body=bn_body,
        published_at=datetime.now(timezone.utc),
        declared_language="bn"
    )
    summary_bn = SummaryMetadata(
        text=bn_violating_summary,
        model="gemini-1.5-flash",
        prompt_version="1.0.0",
        verified=False,
        word_count=len(bn_violating_summary.split())
    )
    passed, score, reasons = verifier.verify(item_bn, summary_bn)
    assert passed is False
    assert any("Verbatim copy violation" in r for r in reasons)
