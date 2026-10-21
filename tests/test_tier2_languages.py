"""
End-to-End Pipeline & API Tests for Tier 2 Indic Languages (Phase 4)
Covers:
1. Urdu (ur) - Perso-Arabic script, RTL bidirectional layout
2. Gujarati (gu) - Gujarati script
3. Kannada (kn) - Kannada script, agglutinative Dravidian length band
4. Odia (or) - Odia script, high-fertility token handling
5. Malayalam (ml) - Malayalam script, agglutinative Dravidian length band
6. Punjabi (pa) - Gurmukhi script

Verifies:
- Config schema validation, source health, and script assignments
- RSS fixture ingestion and URL tracking query parameter stripping
- Unicode script-based language identification
- Headline pre-filtering for crime/disaster triggers
- Positivity classification and toxic positivity rejection
- Abstractive summarization respecting Dravidian & Indic length bands
- Adversarial faithfulness verifier & verbatim overlap guard
- Ephemeral raw body invariant: publisher text NEVER stored in database
- FastAPI Gateway endpoints (/v1/languages, /v1/feed) including Urdu is_rtl flag
"""

from datetime import datetime, timezone
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


def test_tier2_language_configs_loaded(registry):
    """Verify all 6 Tier 2 language configs are loaded, valid, and satisfy quality gate criteria."""
    tier2_expected = {
        "ur": {"script": "Perso-Arabic", "is_rtl": True, "min_words": 35},
        "gu": {"script": "Gujarati", "is_rtl": False, "min_words": 30},
        "kn": {"script": "Kannada", "is_rtl": False, "min_words": 25},
        "or": {"script": "Odia", "is_rtl": False, "min_words": 30},
        "ml": {"script": "Malayalam", "is_rtl": False, "min_words": 25},
        "pa": {"script": "Gurmukhi", "is_rtl": False, "min_words": 30},
    }

    for code, expected in tier2_expected.items():
        cfg = registry.get_strict(code)
        assert cfg.language_code == code
        assert cfg.tier.value == "tier_2"
        assert cfg.status.value == "active"
        assert cfg.script == expected["script"]
        assert cfg.is_rtl == expected["is_rtl"]
        assert cfg.quality_gate.min_positive_precision >= 0.90
        assert cfg.quality_gate.min_faithfulness_pass_rate >= 0.95
        assert len(cfg.sources) >= 3
        healthy_sources = [s for s in cfg.sources if s.health_status == "healthy"]
        assert len(healthy_sources) >= 3
        assert cfg.length_band.min_words == expected["min_words"]
        assert cfg.length_band.max_words <= 90


@pytest.mark.parametrize("lang_code,fixture_name,source_id,expected_script,is_rtl", [
    ("ur", "inquilab_urdu_sample.xml", "inquilab-mumbai", "Perso-Arabic", True),
    ("gu", "gujaratsamachar_sample.xml", "gujarat-samachar", "Gujarati", False),
    ("kn", "prajavani_kannada_sample.xml", "prajavani-kannada", "Kannada", False),
    ("or", "sambad_odia_sample.xml", "sambad-odia", "Odia", False),
    ("ml", "mathrubhumi_malayalam_sample.xml", "mathrubhumi-malayalam", "Malayalam", False),
    ("pa", "jagbani_punjabi_sample.xml", "jagbani-punjabi", "Gurmukhi", False),
])
def test_tier2_pipeline_end_to_end(
    lang_code, fixture_name, source_id, expected_script, is_rtl, fixture_dir, registry
):
    """Run full ingestion-to-publishing pipeline on all Tier 2 RSS fixtures."""
    fixture_path = fixture_dir / fixture_name
    assert fixture_path.exists(), f"Fixture {fixture_name} not found"
    with open(fixture_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    # 1. Setup isolated in-memory DB and get config
    storage = StorageEngine(":memory:")
    config = registry.get_strict(lang_code)
    assert config.script == expected_script
    assert config.is_rtl == is_rtl

    orchestrator = PipelineOrchestrator(language_config=config, storage=storage)

    # 2. Process XML fixture
    stats = orchestrator.process_raw_xml(xml_content=xml_content, source_id=source_id)

    # 3. Assert stage transition invariants
    assert stats["ingested_count"] == 5, f"{lang_code}: expected 5 ingested items"
    assert stats["normalized_count"] == 5
    assert stats["language_matched_count"] == 5
    assert stats["headline_rejected_count"] == 1, f"{lang_code}: disaster/crime headline must be rejected"
    assert stats["classified_negative_count"] == 2, f"{lang_code}: toxic positivity & neutral must be rejected"
    assert stats["classified_positive_count"] == 2, f"{lang_code}: 2 constructive milestones must be classified positive"
    assert stats["verification_passed_count"] == 2, f"{lang_code}: both positive summaries must pass verification"
    assert stats["published_count"] == 2, f"{lang_code}: exactly 2 verified items published"
    assert stats["run_cost_usd"] > 0.0

    # 4. Invariant: Raw publisher body text is NEVER stored in database
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles WHERE language = ?", (lang_code,))
        rows = cursor.fetchall()
        assert len(rows) == 2
        col_names = [d[0] for d in cursor.description]
        assert "raw_body" not in col_names, "Raw publisher body text must NEVER be persisted in SQLite"

    # 5. Client Gateway Verification
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)

    # Test /v1/languages reflects correct RTL metadata
    lang_resp = client.get("/v1/languages")
    assert lang_resp.status_code == 200
    languages = lang_resp.json()["languages"]
    matched_lang = next((l for l in languages if l["code"] == lang_code), None)
    assert matched_lang is not None
    assert matched_lang["is_rtl"] == is_rtl

    # Test /v1/feed?language={code}
    feed_resp = client.get(f"/v1/feed?language={lang_code}")
    assert feed_resp.status_code == 200
    feed_data = feed_resp.json()
    assert feed_data["total_returned"] == 2
    articles = feed_data["articles"]
    assert len(articles) == 2

    for art in articles:
        assert art["language"] == lang_code
        assert art["is_rtl"] == is_rtl
        assert art["summary"]["verified"] is True
        assert art["positivity"]["label"] == "positive"
        assert art["positivity"]["score"] >= 0.85
        assert "utm_source" not in art["canonical_url"], "Tracking query parameters must be stripped"
        assert "raw_body" not in art
        words = art["summary"]["text"].split()
        assert len(words) >= config.length_band.min_words, (
            f"{lang_code}: summary length {len(words)} below minimum {config.length_band.min_words}"
        )
        assert len(words) <= config.length_band.max_words, (
            f"{lang_code}: summary length {len(words)} above maximum {config.length_band.max_words}"
        )


def test_urdu_rtl_and_verbatim_guard():
    """Verify verbatim overlap guard catches >= 7 consecutive copied words in Urdu Perso-Arabic text."""
    verifier = FaithfulnessVerifier(max_consecutive_verbatim_tokens=7)

    urdu_body = (
        "جامعہ ملیہ اسلامیہ کے باصلاحیت طلباء نے بصارت سے محروم افراد کی سہولت کے لیے سمارٹ نیویگیشن ڈیوائس تیار کی ہے"
    )
    # Summary containing >= 7 consecutive verbatim words
    violating_urdu_summary = (
        "ایک اہم پیش رفت میں بصارت سے محروم افراد کی سہولت کے لیے سمارٹ نیویگیشن ڈیوائس تیار کی ہے اور طلباء نے کامیابی حاصل کی۔"
    )

    verbatim_ok, snippet = verifier.check_verbatim_overlap(urdu_body, violating_urdu_summary)
    assert verbatim_ok is False, "Urdu verbatim overlap of 7+ words must be detected"
    assert snippet is not None

    item_ur = EphemeralIngestedItem(
        id="test-ur-verbatim",
        source_id="inquilab",
        source_name="The Inquilab",
        url="https://example.com/ur",
        canonical_url="https://example.com/ur",
        headline="جامعہ کے طلباء کی ایجاد",
        raw_body=urdu_body,
        published_at=datetime.now(timezone.utc),
        declared_language="ur",
    )
    summary_ur = SummaryMetadata(
        text=violating_urdu_summary,
        model="gemini-1.5-flash",
        prompt_version="1.0.0",
        verified=False,
        word_count=len(violating_urdu_summary.split()),
    )
    passed, score, reasons = verifier.verify(item_ur, summary_ur)
    assert passed is False
    assert any("Verbatim copy violation" in r for r in reasons)


def test_odia_script_verbatim_guard():
    """Verify verbatim overlap guard in Odia script prevents copying."""
    verifier = FaithfulnessVerifier(max_consecutive_verbatim_tokens=7)

    odia_body = (
        "କୋରାପୁଟ ଜିଲ୍ଲାର ଆଦିବାସୀ ମହିଳା ସ୍ୱୟଂ ସହାୟକ ଗୋଷ୍ଠୀ ପାରମ୍ପରିକ ଜୈବିକ ମାଣ୍ଡିଆ ଚାଷରେ ଐତିହାସିକ ସଫଳତା ହାସଲ କରିଛନ୍ତି"
    )
    violating_odia_summary = (
        "ପରିବେଶ ସୁରକ୍ଷା ପାଇଁ କୋରାପୁଟ ଜିଲ୍ଲାର ଆଦିବାସୀ ମହିଳା ସ୍ୱୟଂ ସହାୟକ ଗୋଷ୍ଠୀ ପାରମ୍ପରିକ ଜୈବିକ ମାଣ୍ଡିଆ ଚାଷରେ କାର୍ଯ୍ୟ କରି ନୂତନ ଇତିହାସ ରଚିଛନ୍ତି।"
    )

    verbatim_ok, snippet = verifier.check_verbatim_overlap(odia_body, violating_odia_summary)
    assert verbatim_ok is False
    assert snippet is not None
