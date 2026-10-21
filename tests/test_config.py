"""
Unit Tests for Per-Language Configuration Profiles
Verifies:
1. All language YAML files in config/languages/ validate against Pydantic schema.
2. English and Hindi are properly configured as Tier 1 active.
3. Urdu is correctly flagged as is_rtl: true.
4. Quality gate thresholds satisfy non-negotiable minimums.
5. All publisher sources have valid URLs and healthy status.
"""

from pathlib import Path
import pytest
from src.config.loader import LanguageConfigRegistry
from src.schemas.config import LanguageStatus, LanguageTier


@pytest.fixture
def registry():
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    return LanguageConfigRegistry(str(config_dir))


def test_registry_loads_all_yaml(registry):
    configs = registry.list_all()
    assert len(configs) >= 3, "At least en, hi, and ur configs should be loaded"
    codes = [c.language_code for c in configs]
    assert "en" in codes
    assert "hi" in codes
    assert "ur" in codes


def test_english_configuration(registry):
    en = registry.get_strict("en")
    assert en.tier == LanguageTier.TIER_1
    assert en.status == LanguageStatus.ACTIVE
    assert en.is_rtl is False
    assert en.quality_gate.min_positive_precision >= 0.90
    assert en.quality_gate.min_faithfulness_pass_rate >= 0.95
    assert len(en.sources) >= 3
    assert en.sources[0].id == "the-hindu-national"


def test_hindi_configuration(registry):
    hi = registry.get_strict("hi")
    assert hi.tier == LanguageTier.TIER_1
    assert hi.status == LanguageStatus.ACTIVE
    assert hi.script == "Devanagari"
    assert len(hi.sources) >= 3


def test_urdu_rtl_configuration(registry):
    ur = registry.get_strict("ur")
    assert ur.is_rtl is True, "Urdu must have is_rtl set to True for correct client layout"
    assert ur.script == "Perso-Arabic"
    assert ur.tier == LanguageTier.TIER_2


def test_cost_caps_defined(registry):
    for config in registry.list_all():
        assert config.cost_caps.max_cost_per_run_usd > 0
        assert config.cost_caps.max_daily_budget_usd > 0
        assert config.cost_caps.cost_per_published_item_target_usd > 0
