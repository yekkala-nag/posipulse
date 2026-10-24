"""
Comprehensive unit and integration tests for Attribution and Direct-Link Engine (Step 4).
Covers link cleaning, opt-in UTM parameters, verbatim excerpt enforcement across rights modes,
publisher attribution metadata, and API feed responses.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.presentation.attribution import AttributionEngine
from src.schemas.article import Article, ArticleStatus, PositivityLabel, PositivityMetadata
from src.schemas.source import RightsMode, SourceProfile, TrustTier, VerificationStatus
from src.storage.db import StorageEngine


@pytest.fixture
def headline_only_profile():
    return SourceProfile(
        id="pub-thehindu-national",
        publisher_id="the-hindu-group",
        publisher_name="The Hindu",
        primary_domain="thehindu.com",
        feed_urls=["https://thehindu.com/rss"],
        homepage_url="https://thehindu.com",
        language="en",
        rights_mode=RightsMode.HEADLINE_ONLY,
        utm_opt_in=False,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED
    )


@pytest.fixture
def excerpt_profile_opt_in():
    return SourceProfile(
        id="pub-indianexpress-national",
        publisher_id="indian-express-group",
        publisher_name="The Indian Express",
        primary_domain="indianexpress.com",
        feed_urls=["https://indianexpress.com/rss"],
        homepage_url="https://indianexpress.com",
        language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        excerpt_ceiling_chars=120,
        excerpt_ceiling_words=18,
        utm_opt_in=True,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
        extra_metadata={
            "logo_url": "https://indianexpress.com/static/logo.png",
            "utm_campaign": "express_positive_pulse"
        }
    )


@pytest.fixture
def longer_excerpt_profile():
    return SourceProfile(
        id="pub-mongabay-india",
        publisher_id="mongabay-org",
        publisher_name="Mongabay India",
        primary_domain="india.mongabay.com",
        feed_urls=["https://india.mongabay.com/rss"],
        homepage_url="https://india.mongabay.com",
        language="en",
        rights_mode=RightsMode.LONGER_EXCERPT,
        excerpt_ceiling_chars=500,
        excerpt_ceiling_words=80,
        utm_opt_in=False,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED
    )


# ============================================================================
# 1. Direct Link Formatting & UTM Privacy Tests
# ============================================================================

def test_clean_url_strips_tracking_and_preserves_legitimate_params():
    dirty_url = (
        "https://www.thehindu.com/sci-tech/science/clean-water-membrane/article12345.ece"
        "?utm_source=twitter&utm_medium=social&utm_campaign=breaking"
        "&fbclid=IwAR123abc&gclid=CjwKCAiA&ref=editorial_feed&article_id=9988#comments-section"
    )
    clean = AttributionEngine.clean_url(dirty_url)

    assert "utm_source" not in clean
    assert "utm_medium" not in clean
    assert "utm_campaign" not in clean
    assert "fbclid" not in clean
    assert "gclid" not in clean
    assert "ref" not in clean
    assert "#comments-section" not in clean
    assert "article_id=9988" in clean
    assert clean.startswith("https://www.thehindu.com/sci-tech/science/clean-water-membrane/article12345.ece?article_id=9988")


def test_format_direct_link_opt_out_default(headline_only_profile):
    dirty_url = "https://thehindu.com/story-1?utm_source=rss&fbclid=xyz"
    direct_link = AttributionEngine.format_direct_link(dirty_url, profile=headline_only_profile)

    assert direct_link == "https://thehindu.com/story-1"
    assert "utm_" not in direct_link
    assert "fbclid" not in direct_link


def test_format_direct_link_opt_in_appends_custom_campaign(excerpt_profile_opt_in):
    dirty_url = "https://indianexpress.com/article/technology/solar-village?utm_source=thirdparty"
    direct_link = AttributionEngine.format_direct_link(dirty_url, profile=excerpt_profile_opt_in)

    assert "utm_source=posipulse" in direct_link
    assert "utm_medium=referral" in direct_link
    assert "utm_campaign=express_positive_pulse" in direct_link
    assert "thirdparty" not in direct_link


# ============================================================================
# 2. Verbatim Excerpt Rights Mode Capping Tests
# ============================================================================

def test_verbatim_excerpt_strictly_omitted_for_headline_only(headline_only_profile):
    raw_text = "This is a detailed excerpt from the publisher's feed describing a community solar project."
    excerpt = AttributionEngine.format_verbatim_excerpt(raw_text, profile=headline_only_profile)

    # HEADLINE_ONLY must return None under all circumstances
    assert excerpt is None


def test_verbatim_excerpt_bounded_for_feed_provided_excerpt(excerpt_profile_opt_in):
    long_raw_text = (
        "Engineers and panchayat members in Vidarbha celebrated the successful commissioning "
        "of a breakthrough canal-top solar grid that saves twenty thousand liters of agricultural "
        "water from evaporation daily while powering over fifty remote villages with uninterrupted electricity."
    )
    excerpt = AttributionEngine.format_verbatim_excerpt(long_raw_text, profile=excerpt_profile_opt_in)

    assert excerpt is not None
    assert excerpt.endswith("...")
    assert len(excerpt) <= 123  # Within 120 chars + ellipsis
    assert len(excerpt.split()) <= 19


def test_verbatim_excerpt_longer_excerpt_allows_expanded_text(longer_excerpt_profile):
    medium_text = (
        "In the Western Ghats, conservation biologists documented a 40 percent recovery in endemic tree frog populations "
        "following community-led habitat restoration along riparian corridors."
    )
    excerpt = AttributionEngine.format_verbatim_excerpt(medium_text, profile=longer_excerpt_profile)

    assert excerpt is not None
    assert excerpt == medium_text  # Within 500 chars, so no truncation needed


# ============================================================================
# 3. Publisher Attribution Metadata Resolution Tests
# ============================================================================

def test_resolve_attribution_with_verified_profile(excerpt_profile_opt_in):
    attr = AttributionEngine.resolve_attribution(excerpt_profile_opt_in.id, profile=excerpt_profile_opt_in)

    assert attr.publisher_name == "The Indian Express"
    assert attr.primary_domain == "indianexpress.com"
    assert attr.homepage_url == "https://indianexpress.com"
    assert attr.logo_url == "https://indianexpress.com/static/logo.png"
    assert attr.rights_mode == "feed_provided_excerpt"
    assert attr.trust_tier == "tier_1"
    assert attr.verification_status == "verified"
    assert attr.utm_opt_in is True


def test_resolve_attribution_fallback_for_legacy_source():
    attr = AttributionEngine.resolve_attribution("legacy-unregistered-feed")

    assert attr.publisher_name == "legacy-unregistered-feed"
    assert attr.rights_mode == "headline_only"
    assert attr.utm_opt_in is False


# ============================================================================
# 4. Storage Engine & Migration 004 Tests
# ============================================================================

def test_storage_engine_persists_verbatim_excerpt():
    storage = StorageEngine(":memory:")
    article = Article(
        id="art-test-101",
        source_id="pub-thehindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/story?utm_source=twitter",
        canonical_url="https://thehindu.com/story",
        headline="Researchers Develop Indigenous Solar Membrane",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.95,
            reason="Technological breakthrough in clean energy",
            rubric_version="1.0.0"
        ),
        verbatim_excerpt="Indigenous solar membrane breakthrough."
    )
    storage.insert_article(article)

    retrieved = storage.get_article("art-test-101")
    assert retrieved is not None
    assert retrieved.verbatim_excerpt == "Indigenous solar membrane breakthrough."


# ============================================================================
# 5. REST API Feed Presentation Integration Tests
# ============================================================================

def test_api_feed_attribution_and_direct_links(headline_only_profile, excerpt_profile_opt_in):
    storage = StorageEngine(":memory:")
    storage.save_source_profile(headline_only_profile)
    storage.save_source_profile(excerpt_profile_opt_in)

    # 1. Insert article for headline-only source
    art_hl = Article(
        id="art-hl-1",
        source_id=headline_only_profile.id,
        source_name="The Hindu",
        url="https://thehindu.com/solar-canal?utm_medium=social&fbclid=bad",
        canonical_url="https://thehindu.com/solar-canal?utm_medium=social&fbclid=bad",
        headline="Solar Canal Powers 50 Villages",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.92, reason="Clean energy", rubric_version="1.0.0"
        ),
        verbatim_excerpt="Some raw text that should be suppressed in headline-only mode."
    )
    storage.insert_article(art_hl)

    # 2. Insert article for opted-in excerpt source
    art_ex = Article(
        id="art-ex-2",
        source_id=excerpt_profile_opt_in.id,
        source_name="The Indian Express",
        url="https://indianexpress.com/tech-grant?ref=rss",
        canonical_url="https://indianexpress.com/tech-grant?ref=rss",
        headline="Rural Tech Grants Awarded to 100 Innovators",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.88, reason="Education empowerment", rubric_version="1.0.0"
        ),
        verbatim_excerpt="A grant of fifty lakhs was awarded to young innovators developing bio-fertilizers."
    )
    storage.insert_article(art_ex)

    app = create_app(storage=storage)
    client = TestClient(app)

    resp = client.get("/v1/feed?language=en")
    assert resp.status_code == 200
    articles = resp.json()["articles"]
    assert len(articles) == 2

    by_id = {a["id"]: a for a in articles}

    # Verify Article 1 (Headline Only, Opted-Out)
    item_hl = by_id["art-hl-1"]
    assert item_hl["direct_url"] == "https://thehindu.com/solar-canal"
    assert "utm_" not in item_hl["direct_url"]
    assert item_hl["verbatim_excerpt"] is None  # Suppressed by rights mode
    assert item_hl["publisher_attribution"]["publisher_name"] == "The Hindu"
    assert item_hl["publisher_attribution"]["rights_mode"] == "headline_only"

    # Verify Article 2 (Excerpt, Opted-In)
    item_ex = by_id["art-ex-2"]
    assert "utm_source=posipulse" in item_ex["direct_url"]
    assert "utm_campaign=express_positive_pulse" in item_ex["direct_url"]
    assert item_ex["verbatim_excerpt"] is not None
    assert "young innovators" in item_ex["verbatim_excerpt"]
    assert item_ex["publisher_attribution"]["publisher_name"] == "The Indian Express"
    assert item_ex["publisher_attribution"]["utm_opt_in"] is True
