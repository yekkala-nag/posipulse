"""
Tests for Step 6: Publisher Self-Service Dashboard & Ingestion Health Monitoring
Covers:
1. GET /v1/publishers/{source_id}/dashboard
2. PATCH /v1/publishers/{source_id}/settings
3. POST /v1/publishers/{source_id}/test-feed
4. GET /publisher (web portal route)
5. Audit trail generation and circuit breaker detection
"""

import pytest
from datetime import datetime, timezone
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
def client():
    storage = StorageEngine(":memory:")

    # Pre-seed a test publisher source
    profile = SourceProfile(
        id="test_partner_pub",
        publisher_id="partner_express_media",
        publisher_name="Partner Express",
        language="en",
        feed_urls=["https://partner.example.com/rss.xml"],
        primary_domain="partner.example.com",
        homepage_url="https://partner.example.com",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
        review_state=PublisherReviewState.ACTIVE,
        takedown_status=TakedownStatus.ACTIVE,
        terms_review_status=TermsReviewStatus.REVIEWED_ACCEPTED,
        contact_email="editor@partner.example.com",
        contact_name="Chief Editor",
        utm_opt_in=False,
        excerpt_ceiling_chars=500,
        excerpt_ceiling_words=80,
        audit_history=[
            SourceProfileAuditEntry(
                timestamp=datetime.now(timezone.utc),
                action="created",
                actor="system",
                details={"note": "Initial source creation"}
            )
        ]
    )
    storage.save_source_profile(profile, actor="setup", action="init")

    # Seed an article for this source
    article = Article(
        id="art_dash_1",
        source_id="test_partner_pub",
        source_name="Partner Express",
        url="https://partner.example.com/solar-farm?utm_source=twitter&fbclid=xyz",
        canonical_url="https://partner.example.com/solar-farm",
        headline="Largest Solar Microgrid Powers 50 Rural Villages",
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        language="en",
        cluster_id=None,
        status=ArticleStatus.PUBLISHED,
        verbatim_excerpt="A 50MW solar microgrid was inaugurated today, providing steady clean energy to 50 remote hamlets.",
        category=CategoryAssignment(
            primary_id=4,
            confidence=0.95,
            taxonomy_version="1.0.0"
        ),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.92,
            reason="Clean energy infrastructure transition",
            rubric_version="1.0.0"
        ),
        summary=SummaryMetadata(
            text="Clean power microgrid now serves 50 rural communities across the district.",
            model="gemini-2.0-flash",
            prompt_version="1.0.0",
            verified=True,
            verifier_model="gemini-2.0-flash",
            verifier_score=0.98,
            word_count=11
        )
    )
    storage.insert_article(article)

    app_instance = create_app(storage=storage)
    # Store storage reference on client for test manipulations
    client_instance = TestClient(app_instance)
    client_instance.storage = storage
    return client_instance


def test_publisher_dashboard_retrieval(client):
    """Verifies assembling profile, ingestion health, counts, recent articles, and audit log."""
    resp = client.get("/v1/publishers/test_partner_pub/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    assert "source_profile" in data
    assert data["source_profile"]["id"] == "test_partner_pub"
    assert data["source_profile"]["publisher_name"] == "Partner Express"

    # Ingestion health & metrics
    health = data["ingestion_health"]
    assert health["status"] == "healthy"
    assert health["circuit_breaker_tripped"] is False
    assert health["metrics"]["total_ingested"] >= 1
    assert health["metrics"]["total_published"] >= 1

    # Recent articles enrichment
    assert len(data["recent_articles"]) >= 1
    art = data["recent_articles"][0]
    assert art["id"] == "art_dash_1"
    assert art["headline"] == "Largest Solar Microgrid Powers 50 Rural Villages"
    # Because rights_mode is HEADLINE_ONLY, verbatim_excerpt must be None in enriched output
    assert art["verbatim_excerpt"] is None
    # Direct link must have tracking parameters stripped
    assert "fbclid" not in art["direct_url"]
    assert "utm_source" not in art["direct_url"]
    assert art["publisher_attribution"]["publisher_name"] == "Partner Express"

    # Sanitized audit trail
    assert len(data["recent_audit"]) >= 1
    assert data["recent_audit"][0]["actor"] in ("system", "setup")


def test_publisher_dashboard_not_found(client):
    """Non-existent publisher returns 404."""
    resp = client.get("/v1/publishers/unknown_publisher/dashboard")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_publisher_settings_patch_utm_and_contacts(client):
    """Verifies updating contact info and toggling utm_opt_in."""
    payload = {
        "contact_name": "Senior Newsroom Director",
        "contact_email": "director@partner.example.com",
        "utm_opt_in": True,
        "actor": "partner_admin"
    }
    resp = client.patch("/v1/publishers/test_partner_pub/settings", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["contact_name"] == "Senior Newsroom Director"
    assert data["contact_email"] == "director@partner.example.com"
    assert data["utm_opt_in"] is True

    # Re-query dashboard to verify persistence and direct link UTM behavior
    dash_resp = client.get("/v1/publishers/test_partner_pub/dashboard")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert dash_data["source_profile"]["utm_opt_in"] is True
    # Article direct link should now contain posipulse attribution UTM parameters
    art = dash_data["recent_articles"][0]
    assert "utm_source=posipulse" in art["direct_url"]
    assert "utm_medium=referral" in art["direct_url"]


def test_publisher_settings_patch_rights_mode_longer_excerpt(client):
    """
    Verifies requesting LONGER_EXCERPT requires pending agreement review
    and updates excerpt ceiling bounds.
    """
    payload = {
        "rights_mode": "longer_excerpt",
        "excerpt_ceiling_chars": 800,
        "excerpt_ceiling_words": 120,
        "actor": "legal_representative"
    }
    resp = client.patch("/v1/publishers/test_partner_pub/settings", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["rights_mode"] == "longer_excerpt"
    assert data["excerpt_ceiling_chars"] == 800
    assert data["excerpt_ceiling_words"] == 120
    # Requesting longer excerpt flags terms review status as pending
    assert data["terms_review_status"] == "pending"

    # Check that audit log recorded the transition
    dash_resp = client.get("/v1/publishers/test_partner_pub/dashboard")
    dash_data = dash_resp.json()
    latest_audit = dash_data["recent_audit"][-1]
    assert latest_audit["actor"] == "legal_representative"
    assert latest_audit["action"] == "publisher_settings_updated"


def test_publisher_settings_validation_errors(client):
    """Validation constraints on excerpt ceilings (chars: 100-2500, words: 15-400)."""
    # Excerpt chars too small (< 100)
    resp = client.patch(
        "/v1/publishers/test_partner_pub/settings",
        json={"excerpt_ceiling_chars": 50}
    )
    assert resp.status_code == 422

    # Excerpt chars too large (> 2500)
    resp = client.patch(
        "/v1/publishers/test_partner_pub/settings",
        json={"excerpt_ceiling_chars": 3000}
    )
    assert resp.status_code == 422


def test_publisher_circuit_breaker_detection(client):
    """When a publisher is suspended or takedown requested, circuit breaker trips."""
    storage: StorageEngine = client.storage
    profile = storage.get_source_profile("test_partner_pub")
    profile.review_state = PublisherReviewState.SUSPENDED
    storage.save_source_profile(profile, actor="admin", action="suspended_for_audit")

    resp = client.get("/v1/publishers/test_partner_pub/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingestion_health"]["circuit_breaker_tripped"] is True


def test_publisher_test_feed_endpoint(client, monkeypatch):
    """Verifies on-demand feed validation audit via the API."""
    rss_sample = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>Partner Express News</title>
        <link>https://partner.example.com</link>
        <description>Verified Constructive News</description>
        <item>
          <title>Solar Microgrid Project Complete</title>
          <link>https://partner.example.com/solar-microgrid</link>
          <description>Full installation completed across 50 villages.</description>
          <pubDate>Wed, 23 Oct 2024 10:00:00 GMT</pubDate>
          <guid>https://partner.example.com/solar-microgrid</guid>
        </item>
      </channel>
    </rss>"""

    class MockResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code
            self.headers = {"content-type": "application/rss+xml"}

        def raise_for_status(self):
            pass

    import httpx
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kwargs: MockResponse(rss_sample))

    resp = client.post("/v1/publishers/test_partner_pub/test-feed", json={})
    assert resp.status_code == 200
    res_data = resp.json()

    assert res_data["status"] in ("valid", "valid_with_warnings")
    assert res_data["total_items"] == 1
    assert len(res_data["item_previews"]) == 1
    assert res_data["item_previews"][0]["title"] == "Solar Microgrid Project Complete"


def test_web_publisher_portal_served(client):
    """Verifies the GET /publisher route serves the HTML dashboard UI."""
    resp = client.get("/publisher")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PosiPulse" in resp.text
    assert "Publisher Self-Service" in resp.text
