"""
Comprehensive unit and integration tests for Per-Language Newsletters (Step 7).
Validates DPDP Act 2023 compliance, double opt-in confirmation tokens,
single-click RFC 8058 unsubscription, right to erasure, rights-mode ceilings,
RTL directionality (Urdu), and Mock ESP dispatching.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.newsletter.esp import MockEmailProvider
from src.newsletter.models import SubscriptionStatus
from src.schemas.article import (
    Article,
    ArticleStatus,
    CategoryAssignment,
    PositivityLabel,
    PositivityMetadata,
)
from src.schemas.source import RightsMode, SourceProfile, TrustTier, VerificationStatus
from src.storage.db import StorageEngine
from src.storage.migrations import (
    apply_newsletter_subscriptions_migration,
    rollback_newsletter_subscriptions_migration,
)


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
def headline_only_publisher(storage):
    profile = SourceProfile(
        id="pub-hindu-national",
        publisher_id="the-hindu",
        publisher_name="The Hindu",
        primary_domain="thehindu.com",
        feed_urls=["https://thehindu.com/rss"],
        homepage_url="https://thehindu.com",
        language="en",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
    )
    storage.save_source_profile(profile)
    return profile


@pytest.fixture
def excerpt_publisher(storage):
    profile = SourceProfile(
        id="pub-pib-delhi",
        publisher_id="pib",
        publisher_name="Press Information Bureau",
        primary_domain="pib.gov.in",
        feed_urls=["https://pib.gov.in/rss"],
        homepage_url="https://pib.gov.in",
        language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        excerpt_ceiling_chars=200,
        excerpt_ceiling_words=35,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
    )
    storage.save_source_profile(profile)
    return profile


# ============================================================================
# 1. Migration 007 Reversibility Tests
# ============================================================================

def test_migration_007_schema_and_reversibility():
    """Verify Migration 007 creates newsletter tables and rolls back cleanly."""
    storage = StorageEngine(":memory:")

    with storage._get_connection() as conn:
        cursor = conn.cursor()
        # Verify tables auto-created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_subscriptions'")
        assert cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_issues'")
        assert cursor.fetchone() is not None

        # Verify index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_newsletter_sub_email'")
        assert cursor.fetchone() is not None

        # Rollback migration 007
        assert rollback_newsletter_subscriptions_migration(conn) is True
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_subscriptions'")
        assert cursor.fetchone() is None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_issues'")
        assert cursor.fetchone() is None

        # Re-apply migration 007
        assert apply_newsletter_subscriptions_migration(conn) is True
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletter_subscriptions'")
        assert cursor.fetchone() is not None


# ============================================================================
# 2. Subscription Lifecycle (Double Opt-In, Confirm, Unsubscribe, DPDP Erasure)
# ============================================================================

def test_newsletter_subscribe_flow_double_opt_in(client, mock_esp, storage):
    """
    POST /v1/newsletter/subscribe initiates double opt-in.
    Verification email is queued via ESP; status starts as pending_confirmation.
    """
    mock_esp.clear()
    email = "reader@example.in"

    res = client.post("/v1/newsletter/subscribe", json={"email": email, "language": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "pending_confirmation"
    assert "Confirmation link sent" in data["message"]
    conf_link = data["confirmation_link"]
    assert "token=" in conf_link

    # Check ESP outbox
    emails = mock_esp.get_emails_for(email)
    assert len(emails) == 1
    assert "confirm" in emails[0].subject.lower()
    assert conf_link in emails[0].html_body

    # Check DB record
    sub = storage.get_newsletter_subscription(email, "en")
    assert sub is not None
    assert sub["status"] == "pending_confirmation"
    assert sub["confirmed_at"] is None


def test_newsletter_confirm_flow(client, storage, mock_esp):
    """GET /v1/newsletter/confirm?token=... confirms subscriber."""
    email = "confirmed_reader@example.in"
    res_sub = client.post("/v1/newsletter/subscribe", json={"email": email, "language": "hi"})
    conf_link = res_sub.json()["confirmation_link"]
    token = conf_link.split("token=")[1]

    # Confirm
    res_conf = client.get(f"/v1/newsletter/confirm?token={token}")
    assert res_conf.status_code == 200
    assert res_conf.json()["success"] is True
    assert res_conf.json()["status"] == "confirmed"

    # Verify DB record
    sub = storage.get_newsletter_subscription(email, "hi")
    assert sub["status"] == "confirmed"
    assert sub["confirmed_at"] is not None


def test_newsletter_confirm_invalid_token(client):
    """Invalid token returns HTTP 404."""
    res = client.get("/v1/newsletter/confirm?token=INVALID_TOKEN_1234567890")
    assert res.status_code == 404


def test_newsletter_unsubscribe_one_click(client, storage):
    """
    GET /v1/newsletter/unsubscribe?token=... and POST /v1/newsletter/unsubscribe
    immediately transitions subscriber to unsubscribed (RFC 8058 compliant).
    """
    email = "unsub_reader@example.in"
    client.post("/v1/newsletter/subscribe", json={"email": email, "language": "en"})
    sub_raw = storage.get_newsletter_subscription(email, "en")
    unsub_token = sub_raw["unsubscribe_token"]

    # Unsubscribe via GET
    res_unsub = client.get(f"/v1/newsletter/unsubscribe?token={unsub_token}")
    assert res_unsub.status_code == 200
    assert res_unsub.json()["status"] == "unsubscribed"

    # Verify in DB
    updated = storage.get_newsletter_subscription(email, "en")
    assert updated["status"] == "unsubscribed"
    assert updated["unsubscribed_at"] is not None

    # Unsubscribe via POST (RFC 8058 One-Click)
    res_post = client.post("/v1/newsletter/unsubscribe", json={"token": unsub_token})
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "unsubscribed"


def test_newsletter_dpdp_erasure(client, storage):
    """DELETE /v1/newsletter/subscription?email=... permanently wipes data."""
    email = "delete_me@example.in"
    client.post("/v1/newsletter/subscribe", json={"email": email, "language": "te"})
    assert storage.get_newsletter_subscription(email, "te") is not None

    res = client.delete(f"/v1/newsletter/subscription?email={email}")
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["records_deleted"] == 1

    # Verify DB has zero records
    assert storage.get_newsletter_subscription(email, "te") is None


# ============================================================================
# 3. Digest Assembly & Rights Mode Ceilings
# ============================================================================

def test_newsletter_digest_builder_honors_rights_modes(storage, headline_only_publisher, excerpt_publisher):
    """
    Digest builder must enforce rights modes:
    - headline_only: headline + direct link ONLY (no excerpt).
    - feed_provided_excerpt: verbatim excerpt clipped to ceiling.
    """
    from src.newsletter.builder import NewsletterDigestBuilder

    # Story 1: Headline Only source
    art1 = Article(
        id="art-digest-1",
        source_id=headline_only_publisher.id,
        source_name="The Hindu",
        url="https://thehindu.com/green-corridor",
        canonical_url="https://thehindu.com/green-corridor",
        headline="National Green Corridor Opens in Karnataka",
        verbatim_excerpt="This raw excerpt should NEVER appear because rights mode is headline_only.",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=4, confidence=0.96),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.95, reason="Clean ecology progress", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art1)

    # Story 2: Excerpt permitted source
    art2 = Article(
        id="art-digest-2",
        source_id=excerpt_publisher.id,
        source_name="PIB",
        url="https://pib.gov.in/solar-pump-initiative",
        canonical_url="https://pib.gov.in/solar-pump-initiative",
        headline="PM-KUSUM Deploys 200,000 Solar Water Pumps",
        verbatim_excerpt="Over 200,000 farmers received solar pumps reducing grid dependency and lowering diesel costs across agricultural districts.",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=1, confidence=0.98),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.98, reason="Rural agricultural clean power", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art2)

    builder = NewsletterDigestBuilder(storage=storage)
    issue = builder.build_digest(language="en", days=7, limit=10)

    assert "art-digest-1" in issue.article_ids
    assert "art-digest-2" in issue.article_ids

    # Story 1 in HTML: headline present, but NO verbatim excerpt
    assert "National Green Corridor Opens in Karnataka" in issue.html_content
    assert "Headline-only rights agreement" in issue.html_content
    assert "This raw excerpt should NEVER appear" not in issue.html_content

    # Story 2 in HTML: verbatim excerpt present
    assert "PM-KUSUM Deploys 200,000 Solar Water Pumps" in issue.html_content
    assert "Over 200,000 farmers received solar pumps" in issue.html_content


def test_newsletter_digest_rtl_directionality_for_urdu(storage, client):
    """Urdu (ur) digest must render with dir='rtl' and proper typography styling."""
    from src.newsletter.builder import NewsletterDigestBuilder

    builder = NewsletterDigestBuilder(storage=storage)
    issue = builder.build_digest(language="ur", days=7, limit=10)

    assert 'dir="rtl"' in issue.html_content
    assert 'lang="ur"' in issue.html_content
    assert "Noto Nastaliq Urdu" in issue.html_content


# ============================================================================
# 4. Digest Dispatch to Confirmed Subscribers via ESP
# ============================================================================

def test_newsletter_dispatch_to_confirmed_subscribers_only(client, storage, mock_esp, headline_only_publisher):
    """
    POST /v1/newsletter/digest/send dispatches only to confirmed subscribers.
    Injects unique unsubscribe token into recipient emails and includes RFC 8058 headers.
    """
    mock_esp.clear()

    # Create published article for the digest
    art = Article(
        id="art-send-test",
        source_id=headline_only_publisher.id,
        source_name="The Hindu",
        url="https://thehindu.com/tech-innovation",
        canonical_url="https://thehindu.com/tech-innovation",
        headline="Breakthrough Desalination Unit Scales in Tamil Nadu",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=2, confidence=0.99),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.97, reason="Clean water tech", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art)

    # Subscriber 1: Confirmed
    client.post("/v1/newsletter/subscribe", json={"email": "active1@example.in", "language": "en"})
    sub1 = storage.get_newsletter_subscription("active1@example.in", "en")
    client.get(f"/v1/newsletter/confirm?token={sub1['confirmation_token']}")

    # Subscriber 2: Pending confirmation (never confirmed)
    client.post("/v1/newsletter/subscribe", json={"email": "pending2@example.in", "language": "en"})

    mock_esp.clear()

    # Dispatch digest
    res_send = client.post("/v1/newsletter/digest/send?language=en&days=7&limit=10")
    assert res_send.status_code == 200
    data = res_send.json()
    assert data["success"] is True
    assert data["recipients_sent"] == 1

    # Verify ESP received exactly 1 message for active1@example.in
    assert len(mock_esp.outbox) == 1
    msg = mock_esp.outbox[0]
    assert msg.to_email == "active1@example.in"
    assert "List-Unsubscribe" in msg.headers
    assert sub1["unsubscribe_token"] in msg.headers["List-Unsubscribe"]
    assert "Breakthrough Desalination Unit" in msg.html_body


def test_newsletter_preview_endpoint(client, headline_only_publisher, storage):
    """POST /v1/newsletter/digest/preview returns HTML and text preview without sending emails."""
    res = client.post("/v1/newsletter/digest/preview?language=en&days=7&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "html_content" in data
    assert "text_content" in data
    assert data["language"] == "en"
    assert "PosiPulse" in data["subject"]
