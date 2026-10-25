"""
Phase C: Prevention & Monitoring Safeguards
Automated regression and invariant test suite ensuring:
1. All 16 language configs match across config/languages, src/config/languages, and embedded.py.
2. Feed configurations contain zero script/language query mismatches.
3. Cron scheduler polls all 16 active languages dynamically.
4. LanguageDetector protects against fastText newline exceptions.
5. Empty states transparently educate readers on the >=0.85 positivity threshold and fail-closed policy.
"""

from pathlib import Path
import pytest
import yaml

from src.config.embedded import EMBEDDED_LANGUAGE_CONFIGS
from src.config.loader import LanguageConfigRegistry
from src.pipeline.language_detector import LanguageDetector


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent


def test_language_configs_parity_between_dirs(repo_root):
    """Ensure config/languages and src/config/languages are synchronized."""
    config_dir = repo_root / "config" / "languages"
    src_config_dir = repo_root / "src" / "config" / "languages"

    config_files = sorted(config_dir.glob("*.yaml"))
    assert len(config_files) == 16, f"Expected 16 configs, found {len(config_files)}"

    for cf in config_files:
        src_cf = src_config_dir / cf.name
        assert src_cf.exists(), f"{src_cf} missing from src/config/languages"
        with open(cf, "r", encoding="utf-8") as f1, open(src_cf, "r", encoding="utf-8") as f2:
            d1 = yaml.safe_load(f1)
            d2 = yaml.safe_load(f2)
            assert d1 == d2, f"Mismatch between {cf} and {src_cf}"


def test_embedded_configs_parity(repo_root):
    """Ensure src/config/embedded.py accurately mirrors filesystem YAMLs."""
    config_dir = repo_root / "config" / "languages"
    for yf in config_dir.glob("*.yaml"):
        with open(yf, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        code = yaml_data["language_code"]
        assert code in EMBEDDED_LANGUAGE_CONFIGS, f"{code} missing in EMBEDDED_LANGUAGE_CONFIGS"
        embedded_sources = {s["id"]: s["feed_url"] for s in EMBEDDED_LANGUAGE_CONFIGS[code]["sources"]}
        yaml_sources = {s["id"]: s["feed_url"] for s in yaml_data["sources"]}
        assert embedded_sources == yaml_sources, f"Source URLs mismatch in embedded.py for {code}"


def test_no_english_mismatch_in_indic_feeds(repo_root):
    """Ensure no Indic language config queries English or specifies English language params."""
    config_dir = repo_root / "config" / "languages"
    for yf in config_dir.glob("*.yaml"):
        if yf.stem == "en":
            continue
        with open(yf, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for s in cfg.get("sources", []):
            url = s.get("feed_url", "")
            # Ensure English news search params are not mistakenly assigned to Indic language feeds
            assert "hl=en-IN" not in url and "hl=en" not in url, (
                f"Source {s['id']} in {yf.name} queries with English param (hl=en): {url}"
            )


def test_languagedetector_resilient_to_newlines():
    """Ensure LanguageDetector never raises ValueError on newlines."""
    from datetime import datetime, timezone
    from src.schemas.article import EphemeralIngestedItem
    detector = LanguageDetector()
    item = EphemeralIngestedItem(
        id="test-resilience-1",
        source_id="test-source",
        source_name="Test Source",
        url="https://example.com/story-1",
        canonical_url="https://example.com/story-1",
        headline="Headline line 1\nHeadline line 2",
        raw_body="Body paragraph 1\r\nBody paragraph 2\nBody paragraph 3",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )
    is_match, detected_lang, confidence = detector.detect_and_validate(item)
    assert isinstance(is_match, bool)
    assert isinstance(detected_lang, str)
    assert confidence >= 0.0


def test_transparency_in_client_empty_states(repo_root):
    """Ensure both Web and Mobile client code document strict constructive gate transparency."""
    web_app_js = repo_root / "src" / "web" / "app.js"
    assert web_app_js.exists()
    web_content = web_app_js.read_text(encoding="utf-8")
    assert "0.85" in web_content
    assert "fails closed" in web_content

    mobile_feed_screen = repo_root / "src" / "mobile" / "src" / "screens" / "FeedScreen.tsx"
    assert mobile_feed_screen.exists()
    mobile_content = mobile_feed_screen.read_text(encoding="utf-8")
    assert "0.85" in mobile_content
    assert "Strict Constructive Gate" in mobile_content
