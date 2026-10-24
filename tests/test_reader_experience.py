"""
Tests for Step 7: Reader Experience & Verbatim Excerpt Presentation
Verifies:
1. Web and mobile presentation contracts for original publisher branding.
2. Verbatim excerpt enforcement across rights modes (headline_only vs feed_provided_excerpt vs longer_excerpt).
3. Privacy-preserving direct links (tracking params stripped by default, opt-in UTM).
4. Web reader UI and CSS integration (publisher cards, verbatim quote boxes, rights notes).
5. Mobile React Native ArticleCard and TypeScript contracts.
6. Outbound referral click analytics recording.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schemas.article import (
    Article,
    ArticleStatus,
    CategoryAssignment,
    PositivityLabel,
    PositivityMetadata,
    SummaryMetadata,
)
from src.schemas.source import (
    PublisherReviewState,
    RightsMode,
    SourceProfile,
    SourceProfileAuditEntry,
    TakedownStatus,
    TermsReviewStatus,
    TrustTier,
    VerificationStatus,
)
from src.storage.db import StorageEngine


@pytest.fixture
def test_setup():
    storage = StorageEngine(":memory:")

    # 1. Headline-only publisher
    prof_headline = SourceProfile(
        id="pub-headline-only",
        publisher_id="hindu_media_grp",
        publisher_name="The Hindu",
        language="en",
        feed_urls=["https://thehindu.com/rss/national.xml"],
        primary_domain="thehindu.com",
        homepage_url="https://thehindu.com",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
        review_state=PublisherReviewState.ACTIVE,
        takedown_status=TakedownStatus.ACTIVE,
        terms_review_status=TermsReviewStatus.REVIEWED_ACCEPTED,
        contact_email="editor@thehindu.co.in",
        utm_opt_in=False,
        excerpt_ceiling_chars=400,
        excerpt_ceiling_words=60,
    )
    storage.save_source_profile(prof_headline, actor="setup", action="init")

    # 2. Feed-excerpt publisher with UTM opt-in
    prof_excerpt = SourceProfile(
        id="pub-feed-excerpt",
        publisher_id="indian_express_grp",
        publisher_name="The Indian Express",
        language="en",
        feed_urls=["https://indianexpress.com/section/india/feed/"],
        primary_domain="indianexpress.com",
        homepage_url="https://indianexpress.com",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
        review_state=PublisherReviewState.ACTIVE,
        takedown_status=TakedownStatus.ACTIVE,
        terms_review_status=TermsReviewStatus.REVIEWED_ACCEPTED,
        contact_email="syndication@indianexpress.com",
        utm_opt_in=True,
        excerpt_ceiling_chars=500,
        excerpt_ceiling_words=70,
    )
    storage.save_source_profile(prof_excerpt, actor="setup", action="init")

    # 3. Seed article for headline-only publisher
    art_headline = Article(
        id="art-headline-1",
        source_id="pub-headline-only",
        source_name="The Hindu",
        url="https://thehindu.com/news/national/isro-solar-mission?utm_medium=social&fbclid=123",
        canonical_url="https://thehindu.com/news/national/isro-solar-mission",
        headline="ISRO Successfully Completes Aditya-L1 Halo Orbit Maneuver",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        verbatim_excerpt="Scientists confirmed the spacecraft entered its planned halo orbit around Lagrange Point 1.",
        category=CategoryAssignment(primary_id=2, confidence=0.98, taxonomy_version="1.0.0"),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.96,
            reason="Scientific achievement in solar astronomy",
            rubric_version="1.0.0"
        ),
        summary=SummaryMetadata(
            text="India's solar observatory successfully settled into its definitive observation trajectory.",
            model="gemini-2.0-flash",
            prompt_version="1.0.0",
            verified=True,
            word_count=12
        )
    )
    storage.insert_article(art_headline)

    # 4. Seed article for feed-provided excerpt publisher
    art_excerpt = Article(
        id="art-excerpt-1",
        source_id="pub-feed-excerpt",
        source_name="The Indian Express",
        url="https://indianexpress.com/article/india/solar-canals-gujarat?gclid=xyz456",
        canonical_url="https://indianexpress.com/article/india/solar-canals-gujarat",
        headline="Gujarat Commissions Next-Gen Canal Top Solar Project",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        verbatim_excerpt="The 100 MW solar canal installation conserves millions of litres of irrigation water while generating round-the-clock green power for farmers.",
        category=CategoryAssignment(primary_id=4, confidence=0.94, taxonomy_version="1.0.0"),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.91,
            reason="Water conservation and renewable energy synergy",
            rubric_version="1.0.0"
        ),
        summary=SummaryMetadata(
            text="Canal top panels eliminate evaporation while feeding green energy directly to agricultural pumps.",
            model="gemini-2.0-flash",
            prompt_version="1.0.0",
            verified=True,
            word_count=14
        )
    )
    storage.insert_article(art_excerpt)

    app = create_app(storage=storage)
    client = TestClient(app)
    return client, storage


def test_feed_verbatim_excerpt_and_branding_enforcement(test_setup):
    """Verifies reader feed output under headline_only vs feed_provided_excerpt."""
    client, _ = test_setup

    resp = client.get("/v1/feed?language=en")
    assert resp.status_code == 200
    articles = resp.json()["articles"]
    assert len(articles) == 2

    by_id = {a["id"]: a for a in articles}

    # 1. Headline-Only Article
    h_art = by_id["art-headline-1"]
    assert h_art["headline"] == "ISRO Successfully Completes Aditya-L1 Halo Orbit Maneuver"
    assert h_art["verbatim_excerpt"] is None, "Headline-only source MUST NOT output verbatim excerpt"
    assert h_art["publisher_attribution"]["rights_mode"] == "headline_only"
    assert h_art["publisher_attribution"]["publisher_name"] == "The Hindu"
    assert h_art["publisher_attribution"]["verification_status"] == "verified"
    assert "utm_" not in h_art["direct_url"], "UTM parameters must be stripped when utm_opt_in is False"
    assert "fbclid" not in h_art["direct_url"]

    # 2. Feed-Provided Excerpt Article
    e_art = by_id["art-excerpt-1"]
    assert e_art["headline"] == "Gujarat Commissions Next-Gen Canal Top Solar Project"
    assert e_art["verbatim_excerpt"] is not None
    assert "100 MW solar canal" in e_art["verbatim_excerpt"]
    assert e_art["publisher_attribution"]["rights_mode"] == "feed_provided_excerpt"
    assert e_art["publisher_attribution"]["publisher_name"] == "The Indian Express"
    assert "utm_source=posipulse" in e_art["direct_url"], "UTM parameters must be present when utm_opt_in is True"
    assert "gclid" not in e_art["direct_url"]


def test_outbound_referral_click_tracking(test_setup):
    """Verifies recording anonymous outbound clicks when readers click to original publisher."""
    client, storage = test_setup

    click_payload = {
        "article_id": "art-excerpt-1",
        "source_id": "pub-feed-excerpt",
        "language": "en",
        "category_id": 4
    }
    resp = client.post("/v1/analytics/click", json=click_payload)
    assert resp.status_code == 204

    # Verify click was aggregated in storage
    stats = storage.get_publisher_analytics("pub-feed-excerpt")
    assert stats["total_clicks"] >= 1


def test_web_ui_assets_have_publisher_branding_and_excerpts():
    """Verifies that web client HTML, CSS, and JS include publisher attribution and verbatim excerpt styling."""
    web_dir = Path(__file__).resolve().parent.parent / "src" / "web"

    # 1. index.html
    html_content = (web_dir / "index.html").read_text(encoding="utf-8")
    assert "/publisher" in html_content
    assert "inaccurate_summary" in html_content
    assert "broken_link" in html_content

    # 2. index.css
    css_content = (web_dir / "index.css").read_text(encoding="utf-8")
    assert ".card-publisher-header" in css_content
    assert ".card-verbatim-box" in css_content
    assert ".verified-domain-pill" in css_content
    assert ".rights-mode-pill" in css_content
    assert ".card-rights-note" in css_content

    # 3. app.js
    js_content = (web_dir / "app.js").read_text(encoding="utf-8")
    assert "card-publisher-header" in js_content
    assert "card-verbatim-box" in js_content
    assert "card-rights-note" in js_content
    assert "/v1/analytics/click" in js_content
    assert "directUrl" in js_content


def test_mobile_reader_components_and_types():
    """Verifies mobile React Native components and TypeScript definitions support publisher attribution."""
    mobile_dir = Path(__file__).resolve().parent.parent / "src" / "mobile"

    # 1. types/index.ts
    types_content = (mobile_dir / "src" / "types" / "index.ts").read_text(encoding="utf-8")
    assert "interface PublisherAttribution" in types_content
    assert "verbatim_excerpt?: string | null;" in types_content
    assert "publisher_attribution?: PublisherAttribution | null;" in types_content
    assert "direct_url?: string;" in types_content

    # 2. ArticleCard.tsx
    card_content = (mobile_dir / "src" / "components" / "ArticleCard.tsx").read_text(encoding="utf-8")
    assert "publisherBrandRow" in card_content
    assert "verbatimExcerptContainer" in card_content
    assert "headlineOnlyNote" in card_content
    assert "apiClient.recordClick" in card_content
    assert "openPublisherStory" in card_content

    # 3. client.ts
    client_content = (mobile_dir / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    assert "recordClick" in client_content
    assert "/v1/analytics/click" in client_content
