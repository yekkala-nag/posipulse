"""
Taxonomy v1 Validation Test Suite
Enforces all non-negotiable taxonomy invariants:
1. Permanent, unique category IDs (1-18) with no reused or duplicate IDs.
2. Globally unique subcategory IDs across the entire taxonomy.
3. Every visible category has a non-empty localized display name in all 16 enabled languages.
4. Hidden categories (14-18) are marked with visibility='hidden' and low positive-fit rating.
5. Special-rule flags match specifications:
   - Economy & Business (ID 9): promotional_content_check=True
   - Health & Wellness (ID 10): corroboration_required=True
   - Entertainment & Media (ID 12): gossip_excluded=True
6. IPTC Media Topics crosswalk conforms to the 2024.1 standard and valid URI formats.
7. Any modification to categories requires a checksum update and version bump.
8. Feature flag controls enable/disable status with documented rollback.
"""

import json
from pathlib import Path
import pytest
from src.taxonomy import (
    CategoryVisibility,
    PositiveFitRating,
    TaxonomyRegistry,
    default_taxonomy_registry,
    is_category_taxonomy_enabled,
)
from src.taxonomy.models import TaxonomyVersion


ENABLED_LANGUAGES = [
    "en", "hi", "bn", "mr", "te", "ta", "ur", "gu",
    "kn", "or", "ml", "pa", "as", "ne", "mai", "gom"
]


def test_taxonomy_total_categories_and_version():
    """Verify taxonomy v1 versioning and category counts."""
    registry = default_taxonomy_registry
    assert registry.version == "1.0.0"
    all_categories = registry.list_all()
    assert len(all_categories) == 18

    visible = registry.list_visible()
    hidden = registry.list_hidden()
    assert len(visible) == 13
    assert len(hidden) == 5


def test_permanent_and_unique_category_ids():
    """Verify permanent IDs 1-18 are sequential, unique, and strictly within 1-18."""
    registry = default_taxonomy_registry
    ids = [c.id for c in registry.list_all()]
    assert len(ids) == len(set(ids)), "Category IDs must be unique"
    assert ids == list(range(1, 19)), "Category IDs must be precisely 1 through 18 in sequence"

    slugs = [c.slug for c in registry.list_all()]
    assert len(slugs) == len(set(slugs)), "Category slugs must be unique"


def test_globally_unique_subcategory_ids():
    """Verify every subcategory ID is globally unique across the entire taxonomy."""
    registry = default_taxonomy_registry
    subcategory_ids = []
    for cat in registry.list_all():
        assert len(cat.subcategories) >= 1, f"Category {cat.slug} must have subcategories"
        for sub in cat.subcategories:
            subcategory_ids.append(sub.id)
            assert sub.slug, f"Subcategory {sub.id} must have a slug"
            assert sub.name_en, f"Subcategory {sub.id} must have an English name"

    assert len(subcategory_ids) == len(set(subcategory_ids)), "Subcategory IDs must be globally unique"


def test_visible_categories_have_display_names_in_all_enabled_languages():
    """Every visible category must provide a display name in all 16 supported languages."""
    registry = default_taxonomy_registry
    visible_categories = registry.list_visible()

    for cat in visible_categories:
        for lang in ENABLED_LANGUAGES:
            name = cat.display_names.get(lang)
            assert name and name.strip(), (
                f"Visible category '{cat.slug}' (ID {cat.id}) is missing display name for language '{lang}'"
            )
            # Verify lookup helper returns the localized name
            assert registry.get_display_name(cat.id, lang) == name


def test_hidden_categories_policy():
    """Categories 14-18 must be hidden at launch and have positive_fit='low'."""
    registry = default_taxonomy_registry
    hidden_ids = {14, 15, 16, 17, 18}

    for cat_id in hidden_ids:
        cat = registry.get_by_id(cat_id)
        assert cat is not None
        assert cat.visibility == CategoryVisibility.HIDDEN
        assert cat.positive_fit == PositiveFitRating.LOW
        assert registry.is_hidden(cat_id) is True

    # Check visible categories are NOT hidden
    for cat in registry.list_visible():
        assert cat.id not in hidden_ids
        assert cat.visibility == CategoryVisibility.VISIBLE
        assert registry.is_hidden(cat.id) is False


def test_special_rules_configuration():
    """
    Verify domain-specific special rule flags:
    - Economy (ID 9): promotional_content_check=True
    - Health (ID 10): corroboration_required=True
    - Entertainment (ID 12): gossip_excluded=True
    - All other categories must have these set to False.
    """
    registry = default_taxonomy_registry

    for cat in registry.list_all():
        if cat.id == 9:
            assert cat.special_rules.promotional_content_check is True
            assert cat.special_rules.corroboration_required is False
            assert cat.special_rules.gossip_excluded is False
        elif cat.id == 10:
            assert cat.special_rules.promotional_content_check is False
            assert cat.special_rules.corroboration_required is True
            assert cat.special_rules.gossip_excluded is False
        elif cat.id == 12:
            assert cat.special_rules.promotional_content_check is False
            assert cat.special_rules.corroboration_required is False
            assert cat.special_rules.gossip_excluded is True
        else:
            assert cat.special_rules.promotional_content_check is False
            assert cat.special_rules.corroboration_required is False
            assert cat.special_rules.gossip_excluded is False


def test_iptc_media_topics_crosswalk():
    """Verify IPTC Media Topics 2024.1 standard references and URI syntax."""
    registry = default_taxonomy_registry

    for cat in registry.list_all():
        iptc = cat.iptc_reference
        assert iptc.standard_version == "2024.1"
        assert iptc.qcode.startswith("medtop:")
        assert iptc.uri.startswith("http://cv.iptc.org/newscodes/mediatopic/")
        assert iptc.name_en.strip() != ""


def test_checksum_enforcement_and_tamper_detection(tmp_path):
    """Verify that tampering with category data without updating the checksum raises an error."""
    valid_file = Path(__file__).resolve().parent.parent / "config" / "taxonomy" / "v1.json"
    data = json.loads(valid_file.read_text(encoding="utf-8"))

    # Tamper with a category name
    data["categories"][0]["display_names"]["en"] = "Tampered Agriculture"

    tampered_file = tmp_path / "tampered.json"
    tampered_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Taxonomy integrity checksum mismatch"):
        TaxonomyRegistry(config_path=tampered_file)


def test_feature_flag_toggle(monkeypatch):
    """Verify that the feature flag POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1 can be toggled for rollback."""
    # Default is enabled
    monkeypatch.delenv("POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1", raising=False)
    assert is_category_taxonomy_enabled() is True

    # Explicitly enabled
    monkeypatch.setenv("POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1", "true")
    assert is_category_taxonomy_enabled() is True

    # Toggled off for rollback
    monkeypatch.setenv("POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1", "false")
    assert is_category_taxonomy_enabled() is False

    monkeypatch.setenv("POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1", "0")
    assert is_category_taxonomy_enabled() is False
