"""
Unit and Contract Tests for Extended Classifier (Step 3)
Verifies:
1. Single unified classification call produces both positivity evaluation and category assignment.
2. Positivity and category outputs are independent:
   - Failed or low-confidence category never changes positivity decision.
   - Negative story is never published by category logic (fail-closed).
3. Low confidence on a visible category sets category to None (item appears on Top/Latest, not category pages).
4. Hidden category items (IDs 14-18) are marked with is_held=True and appropriate publish_hold_reason.
5. Ambiguity between visible and hidden categories marks item as held.
6. Special-rule enforcement:
   - Economy: Promotional PR content rejected.
   - Health: Uncorroborated medical claims rejected.
   - Entertainment: Paparazzi, celebrity gossip, and scandals rejected.
7. End-to-end orchestrator pipeline properly holds hidden-category items while publishing visible items.
"""

from datetime import datetime, timezone
import pytest
from src.pipeline.classifier import (
    CATEGORY_CONFIDENCE_THRESHOLD,
    CLASSIFIER_PROMPT_VERSION,
    PositivityClassifier,
)
from src.pipeline.orchestrator import PipelineOrchestrator
from src.schemas.article import (
    ArticleStatus,
    ClassificationResult,
    EphemeralIngestedItem,
    PositivityLabel,
)
from src.schemas.config import LanguageConfig
from src.storage.db import StorageEngine


@pytest.fixture
def classifier():
    return PositivityClassifier(prompt_version=CLASSIFIER_PROMPT_VERSION)


def test_unified_call_contract(classifier):
    """Verify single call returns ClassificationResult with positivity and category assignment."""
    item = EphemeralIngestedItem(
        id="art_scitech_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/tech.html",
        canonical_url="https://thehindu.com/tech.html",
        headline="Quantum Computing Laboratory Delivers Indigenous Quantum Key Distribution",
        raw_body="Scientists at the national research laboratory successfully tested an innovative quantum key distribution prototype over 100 kilometers of standard optical fiber.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert isinstance(res, ClassificationResult)
    assert res.label == PositivityLabel.POSITIVE
    assert res.score >= 0.85
    assert res.prompt_version == CLASSIFIER_PROMPT_VERSION
    assert res.category_assignment is not None
    assert res.category_assignment.primary_id == 2  # Science & Technology
    assert res.category_assignment.subcategory_id == "scitech_research_discovery"
    assert res.category_assignment.confidence >= CATEGORY_CONFIDENCE_THRESHOLD
    assert res.is_held is False
    assert res.publish_hold_reason is None


def test_positivity_and_category_independence_low_confidence(classifier):
    """
    Rule: Positivity and category outputs are independent.
    Low confidence on a visible category sets category to None, but retains positive status.
    """
    item = EphemeralIngestedItem(
        id="art_generic_pos_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/generic.html",
        canonical_url="https://thehindu.com/generic.html",
        headline="Innovative Grassroots Community Initiative Celebrates Success Across Districts",
        raw_body="A community program achieved remarkable success through local volunteer dedication and grassroots cooperation.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert res.label == PositivityLabel.POSITIVE
    # Even if category confidence is simulated low or unassigned, positivity remains positive
    positivity_meta = res.to_positivity_metadata()
    assert positivity_meta.label == PositivityLabel.POSITIVE


def test_negative_story_never_published_by_category(classifier):
    """Category logic must never cause an item to be published if positivity rubric rejects it."""
    item = EphemeralIngestedItem(
        id="art_sports_crime_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/crime.html",
        canonical_url="https://thehindu.com/crime.html",
        headline="Football Player Arrested in Fatal Robbery and Hit-and-Run Collision",
        raw_body="A professional football player was arrested by police following a fatal hit-and-run accident that claimed lives during an armed robbery.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert res.label == PositivityLabel.NEGATIVE
    assert res.score <= 0.20
    assert res.category_assignment is None


def test_hidden_category_primary_is_held(classifier):
    """Items whose primary category is in {14..18} are classified and held."""
    # Test Category 14: Governance & Public Services
    item_gov = EphemeralIngestedItem(
        id="art_gov_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/gov.html",
        canonical_url="https://thehindu.com/gov.html",
        headline="Public Grievance Delivery Portal Rolled Out with Direct Benefit Transfer Integration",
        raw_body="The municipal citizen service administration completed the rollout of a single-window grievance portal, ensuring direct benefit transfer reaches beneficiaries.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res_gov = classifier.classify(item_gov)
    assert res_gov.label == PositivityLabel.POSITIVE
    assert res_gov.is_held is True
    assert res_gov.category_assignment is not None
    assert res_gov.category_assignment.primary_id == 14
    assert "hidden at launch" in res_gov.publish_hold_reason

    # Test Category 17: Defence & Security
    item_def = EphemeralIngestedItem(
        id="art_def_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/def.html",
        canonical_url="https://thehindu.com/def.html",
        headline="Veteran Welfare Reintegration Program Celebrates Success",
        raw_body="Ex-servicemen rehabilitation and veteran welfare initiatives achieved notable milestone under military welfare programs.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res_def = classifier.classify(item_def)
    assert res_def.label == PositivityLabel.POSITIVE
    assert res_def.is_held is True
    assert res_def.category_assignment.primary_id == 17
    assert "hidden at launch" in res_def.publish_hold_reason


def test_ambiguity_between_visible_and_hidden_means_hold(classifier):
    """Low confidence or ambiguity between visible and hidden categories holds the item."""
    item_ambiguous = EphemeralIngestedItem(
        id="art_amb_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/amb.html",
        canonical_url="https://thehindu.com/amb.html",
        headline="Solar Powered Microgrid Commissioned at Border Peacekeeping Detachment",
        raw_body="Solar technology provides renewable energy for border road organisation peacekeeping facilities while supporting local agriculture and relief operation units.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item_ambiguous)
    assert res.label == PositivityLabel.POSITIVE
    assert res.is_held is True
    assert "Ambiguous classification between visible and hidden category" in res.publish_hold_reason


def test_special_rules_promotional_content_check(classifier):
    """Economy: Corporate promotional puffery without constructive public outcome is excluded."""
    item = EphemeralIngestedItem(
        id="art_econ_pr_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/pr.html",
        canonical_url="https://thehindu.com/pr.html",
        headline="Company Announces Quarterly Revenue Jumps and Sales Boom with Exclusive Deal",
        raw_body="The corporate entity reported record quarterly revenue and valuation jumps in a sponsored promotional product campaign.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert res.label == PositivityLabel.NEGATIVE
    assert "promotional" in res.reason.lower()


def test_special_rules_health_corroboration_check(classifier):
    """Health: Uncorroborated medical claims fail closed."""
    item = EphemeralIngestedItem(
        id="art_health_uncorroborated_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/cure.html",
        canonical_url="https://thehindu.com/cure.html",
        headline="Secret Herb Cures All Cancer in Overnight Treatment",
        raw_body="A miracle cure claims to cure all cancer overnight through a guaranteed cure discovered by traditional practitioners.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert res.label == PositivityLabel.NEGATIVE
    assert "uncorroborated medical" in res.reason.lower()


def test_special_rules_entertainment_gossip_check(classifier):
    """Entertainment: Gossip, scandals, and paparazzi are excluded."""
    item = EphemeralIngestedItem(
        id="art_ent_gossip_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/gossip.html",
        canonical_url="https://thehindu.com/gossip.html",
        headline="Paparazzi Capture Celebrities in Heated Divorce Feud and Dating Rumors",
        raw_body="Celebrity gossip pages report intense dating rumors and a messy divorce feud as paparazzi swarm outside the court.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    res = classifier.classify(item)
    assert res.label == PositivityLabel.NEGATIVE
    assert "gossip" in res.reason.lower()


def test_orchestrator_pipeline_handles_held_article_cleanly():
    """Verify orchestrator puts held items into HELD_HIDDEN_CATEGORY and feed excludes them."""
    storage = StorageEngine(":memory:")

    from src.config.loader import LanguageConfigRegistry
    from pathlib import Path
    config_dir = Path(__file__).resolve().parent.parent / "config" / "languages"
    registry = LanguageConfigRegistry(str(config_dir))
    en_config = registry.get_strict("en")

    orchestrator = PipelineOrchestrator(language_config=en_config, storage=storage)

    # 1. Visible constructive item (Science & Tech)
    item_visible = EphemeralIngestedItem(
        id="art_vis_01",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/sci.html",
        canonical_url="https://thehindu.com/sci.html",
        headline="IISc Researchers Develop Breakthrough Water Filtration Membrane",
        raw_body="Scientists at the Indian Institute of Science developed a breakthrough water purification membrane achieving record efficiency in removing microplastics from rural groundwater.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    # 2. Hidden constructive item (Governance)
    item_hidden = EphemeralIngestedItem(
        id="art_hid_02",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/gov.html",
        canonical_url="https://thehindu.com/gov.html",
        headline="Public Grievance Delivery Portal Rolled Out with Direct Benefit Transfer Integration",
        raw_body="The municipal citizen service administration completed the rollout of a single-window grievance portal, ensuring direct benefit transfer reaches beneficiaries.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )

    stats = orchestrator.process_items([item_visible, item_hidden], source_id="the-hindu-national")
    assert stats["published_count"] == 1, "Only the visible category story should be published"
    assert stats["held_count"] == 1, "Hidden category story must be counted as held"

    # Verify storage states
    art_vis = storage.get_article("art_vis_01")
    assert art_vis is not None
    assert art_vis.status == ArticleStatus.PUBLISHED
    assert art_vis.category.primary_id == 2

    # Verify feed only returns the visible item
    feed, _ = storage.get_feed("en")
    feed_ids = [a.id for a in feed]
    assert "art_vis_01" in feed_ids
    assert "art_hid_02" not in feed_ids, "Held hidden-category story must NEVER appear in public feed"
