"""
Comprehensive unit and integration tests for Pilot Rollout Readiness & Hardening (Step 8).
Validates:
1. Operational Admin Dashboard API (`GET /v1/admin/dashboard`).
2. Granular Ingestion Funnel Metrics & Conversion Ratios.
3. Publisher Takedown SLA Compliance Tracking (<24h vs breached).
4. Reader Topic Adoption & Newsletter List Telemetry (Zero-PII).
5. Anti-SSRF Guards across FeedValidator and DomainVerifier.
6. Fail-Closed Hidden Category Leak Auditing.
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.ingestion.validator import FeedValidator
from src.newsletter.esp import MockEmailProvider
from src.publisher.verification import DomainVerifier
from src.schemas.article import (
    Article,
    ArticleStatus,
    CategoryAssignment,
    PositivityLabel,
    PositivityMetadata,
)
from src.schemas.source import (
    PublisherReviewState,
    RightsMode,
    SourceProfile,
    TakedownStatus,
    TrustTier,
    VerificationStatus,
)
from src.storage.db import StorageEngine


@pytest.fixture
def storage():
    return StorageEngine(":memory:")


@pytest.fixture
def mock_esp():
    return MockEmailProvider()


@pytest.fixture
def client(storage, mock_esp):
    app = create_app(storage=storage, esp_provider=mock_esp)
    return TestClient(app)


@pytest.fixture
def sample_publisher(storage):
    profile = SourceProfile(
        id="pub-thehindu-com-en",
        publisher_id="the-hindu-group",
        publisher_name="The Hindu",
        primary_domain="thehindu.com",
        homepage_url="https://thehindu.com",
        feed_urls=["https://thehindu.com/news/national/feeder/default.rss"],
        language="en",
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        takedown_status=TakedownStatus.ACTIVE,
        review_state=PublisherReviewState.ACTIVE,
        contact_email="syndication@thehindu.co.in"
    )
    storage.save_source_profile(profile, actor="fixture", action="seed")
    return profile


def test_anti_ssrf_feed_validator_guards():
    """Verify FeedValidator blocks loopbacks, private subnets, cloud metadata, and invalid schemes."""
    # Loopback targets
    blocked, msg = FeedValidator.is_safe_feed_url("http://127.0.0.1/rss.xml")
    assert not blocked
    assert "localhost" in msg.lower() or "loopback" in msg.lower() or "forbidden" in msg.lower()

    blocked, msg = FeedValidator.is_safe_feed_url("http://localhost:8080/feed")
    assert not blocked
    assert "localhost" in msg.lower()

    # Cloud metadata service (AWS/GCP/Azure)
    blocked, msg = FeedValidator.is_safe_feed_url("http://169.254.169.254/latest/meta-data/")
    assert not blocked
    assert "private" in msg.lower() or "reserved" in msg.lower() or "forbidden" in msg.lower()

    # RFC 1918 Private subnets
    blocked, _ = FeedValidator.is_safe_feed_url("http://10.0.0.1/feed.rss")
    assert not blocked

    blocked, _ = FeedValidator.is_safe_feed_url("http://192.168.1.1/feed.rss")
    assert not blocked

    blocked, _ = FeedValidator.is_safe_feed_url("http://172.16.0.10/feed.rss")
    assert not blocked

    # Non-HTTP schemes
    blocked, msg = FeedValidator.is_safe_feed_url("file:///etc/passwd")
    assert not blocked
    assert "scheme" in msg.lower()

    blocked, _ = FeedValidator.is_safe_feed_url("ftp://example.com/feed.xml")
    assert not blocked

    # Legitimate public domains
    is_safe, msg = FeedValidator.is_safe_feed_url("https://thehindu.com/news/national/feeder/default.rss")
    assert is_safe
    assert msg == ""

    # Live validator invocation with SSRF target returns invalid result
    validator = FeedValidator()
    result = validator.validate_url("http://127.0.0.1:8000/internal-feed")
    assert result.status == "invalid"
    assert any(i.code == "SSRF_SECURITY_VIOLATION" for i in result.issues)


def test_anti_ssrf_domain_verifier_guards():
    """Verify DomainVerifier.verify_html_meta blocks SSRF attempts."""
    success, msg, token = DomainVerifier.verify_html_meta(
        primary_domain="127.0.0.1",
        expected_token="posipulse_verify_test"
    )
    assert not success
    assert "blocked" in msg.lower()
    assert token is None

    success, msg, token = DomainVerifier.verify_html_meta(
        primary_domain="169.254.169.254",
        expected_token="posipulse_verify_test"
    )
    assert not success
    assert "blocked" in msg.lower()
    assert token is None


def test_takedown_sla_metrics_compliant(storage, sample_publisher):
    """Verify takedown SLA calculation when enforcement occurs within < 24 hours."""
    # Initial state: 0 takedowns
    metrics = storage.get_takedown_sla_metrics()
    assert metrics["total_takedowns_requested"] == 0
    assert metrics["sla_compliance_rate_percent"] == 100.0
    assert metrics["sla_status"] == "COMPLIANT"

    # Simulate takedown request 2 hours ago
    now = datetime.now(timezone.utc)
    takedown_time = now - timedelta(hours=2)
    with storage._get_connection() as conn:
        conn.execute(
            "UPDATE source_profiles SET takedown_status = 'takedown_requested', takedown_requested_at = ? WHERE id = ?",
            (takedown_time.isoformat(), sample_publisher.id)
        )
        conn.commit()

    # Enforce takedown (latency ~2 hours, well within 24.0h SLA)
    storage.enforce_source_takedown(source_id=sample_publisher.id, reason="Legal notice", actor="ops")

    metrics_after = storage.get_takedown_sla_metrics()
    assert metrics_after["total_takedowns_requested"] == 1
    assert metrics_after["total_takedowns_enforced"] == 1
    assert metrics_after["sla_compliant_count"] == 1
    assert metrics_after["sla_breached_count"] == 0
    assert metrics_after["sla_compliance_rate_percent"] == 100.0
    assert metrics_after["sla_status"] == "COMPLIANT"
    assert metrics_after["average_enforcement_time_hours"] > 0


def test_takedown_sla_metrics_breached(storage, sample_publisher):
    """Verify takedown SLA breach detection when enforcement takes > 24 hours."""
    # Simulate request made 48 hours ago, enforced 20 hours ago (latency = 28 hours)
    t_requested = datetime.now(timezone.utc) - timedelta(hours=48)
    t_enforced = datetime.now(timezone.utc) - timedelta(hours=20)

    with storage._get_connection() as conn:
        conn.execute(
            "UPDATE source_profiles SET takedown_status = 'takedown_enforced', takedown_requested_at = ?, updated_at = ? WHERE id = ?",
            (t_requested.isoformat(), t_enforced.isoformat(), sample_publisher.id)
        )
        conn.commit()

    metrics = storage.get_takedown_sla_metrics()
    assert metrics["total_takedowns_requested"] == 1
    assert metrics["total_takedowns_enforced"] == 1
    assert metrics["sla_compliant_count"] == 0
    assert metrics["sla_breached_count"] == 1
    assert metrics["sla_compliance_rate_percent"] == 0.0
    assert metrics["sla_status"] == "WARNING"


def test_ingestion_funnel_and_integrity_audit(storage, sample_publisher):
    """Verify granular ingestion funnel metrics and system integrity leak checks."""
    now = datetime.now(timezone.utc)

    # 1. Published article in visible Category 1 (Renewable Energy)
    art_pub = Article(
        id="art-test-pub",
        source_id=sample_publisher.id,
        source_name=sample_publisher.publisher_name,
        url="https://thehindu.com/article-1",
        canonical_url="https://thehindu.com/article-1",
        headline="India Achieves Solar Milestone",
        verbatim_excerpt="India reached a massive milestone in solar energy.",
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=1, confidence=0.95),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.98,
            reason="Constructive development in solar technology",
            rubric_version="1.0.0"
        ),
        published_at=now
    )
    storage.insert_article(art_pub)

    # 2. Article classified negative
    art_neg = Article(
        id="art-test-neg",
        source_id=sample_publisher.id,
        source_name=sample_publisher.publisher_name,
        url="https://thehindu.com/article-2",
        canonical_url="https://thehindu.com/article-2",
        headline="Severe Flooding Disrupts Transit",
        verbatim_excerpt="Flooding hits transit routes.",
        language="en",
        status=ArticleStatus.CLASSIFIED_NEGATIVE,
        category=CategoryAssignment(primary_id=1, confidence=0.7),
        positivity=PositivityMetadata(
            label=PositivityLabel.NEGATIVE,
            score=0.15,
            reason="Severe flooding damage with no constructive focus",
            rubric_version="1.0.0"
        ),
        published_at=now
    )
    storage.insert_article(art_neg)

    # 3. Article held in hidden category 14 (Crime/Disasters)
    art_held = Article(
        id="art-test-held",
        source_id=sample_publisher.id,
        source_name=sample_publisher.publisher_name,
        url="https://thehindu.com/article-3",
        canonical_url="https://thehindu.com/article-3",
        headline="Police Investigation Continues",
        verbatim_excerpt="Investigation details here.",
        language="en",
        status=ArticleStatus.HELD_HIDDEN_CATEGORY,
        category=CategoryAssignment(primary_id=14, confidence=0.92),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.6,
            reason="Held under fail-closed category 14 policy",
            rubric_version="1.0.0"
        ),
        published_at=now
    )
    storage.insert_article(art_held)

    funnel = storage.get_ingestion_funnel_metrics()
    assert funnel["total_articles_ingested"] == 3
    assert funnel["stage_counts"]["published"] == 1
    assert funnel["stage_counts"]["classified_negative"] == 1
    assert funnel["stage_counts"]["held_hidden_category"] == 1
    assert funnel["fail_closed_held_count"] == 1

    # Check dashboard and system integrity
    dashboard = storage.get_admin_dashboard_data()
    assert dashboard["status"] == "operational"
    assert dashboard["system_integrity"]["hidden_category_leak_count"] == 0
    assert dashboard["system_integrity"]["integrity_audit_passed"] is True


def test_hidden_category_leak_triggers_integrity_failure(storage, sample_publisher):
    """Ensure that if a hidden category article is somehow published, the integrity audit fails."""
    now = datetime.now(timezone.utc)
    rogue_art = Article(
        id="art-rogue-leak",
        source_id=sample_publisher.id,
        source_name=sample_publisher.publisher_name,
        url="https://thehindu.com/article-rogue",
        canonical_url="https://thehindu.com/article-rogue",
        headline="Rogue Story in Crime Category",
        verbatim_excerpt="Content",
        language="en",
        status=ArticleStatus.PUBLISHED,  # Rogue status!
        category=CategoryAssignment(primary_id=14, confidence=0.95),  # Hidden category!
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.9,
            reason="Erroneously marked published",
            rubric_version="1.0.0"
        ),
        published_at=now
    )
    storage.insert_article(rogue_art)

    dashboard = storage.get_admin_dashboard_data()
    assert dashboard["system_integrity"]["hidden_category_leak_count"] == 1
    assert dashboard["system_integrity"]["integrity_audit_passed"] is False


def test_reader_adoption_metrics_zero_pii(storage, client, sample_publisher):
    """Verify reader following and newsletter aggregation metrics maintain zero-PII."""
    # Seed following
    storage.follow_target(device_id="dev-anon-1", following_type="category", target_id="1")
    storage.follow_target(device_id="dev-anon-2", following_type="category", target_id="1")
    storage.follow_target(device_id="dev-anon-1", following_type="source", target_id=sample_publisher.id)

    # Seed newsletter subscription via API
    res = client.post("/v1/newsletter/subscribe", json={"email": "reader@example.com", "language": "en"})
    assert res.status_code == 200
    sub_raw = storage.get_newsletter_subscription(email="reader@example.com", language="en")
    assert sub_raw is not None
    conf_token = sub_raw["confirmation_token"]

    # Confirm subscription
    res_conf = client.get(f"/v1/newsletter/confirm?token={conf_token}")
    assert res_conf.status_code == 200

    adoption = storage.get_reader_adoption_metrics()
    assert adoption["reader_following"]["total_anonymous_devices"] == 2
    assert len(adoption["reader_following"]["top_followed_categories"]) >= 1
    assert adoption["reader_following"]["top_followed_categories"][0]["category_id"] == "1"
    assert adoption["reader_following"]["top_followed_categories"][0]["followers"] == 2

    assert adoption["newsletters"]["total_confirmed_subscribers"] == 1
    assert adoption["newsletters"]["subscribers_by_language"]["en"]["confirmed"] == 1


def test_admin_dashboard_api_endpoint(client, sample_publisher):
    """Test GET /v1/admin/dashboard HTTP endpoint."""
    resp = client.get("/v1/admin/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "ingestion_funnel" in data
    assert "takedown_sla" in data
    assert "reader_adoption" in data
    assert "system_integrity" in data
    assert data["system_integrity"]["integrity_audit_passed"] is True
