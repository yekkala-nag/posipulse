"""
Comprehensive unit and integration tests for Publisher Onboarding and Domain Verification (Step 3).
Covers registration, cryptographic challenges, DNS TXT verification, HTML meta tag verification,
manual admin verification, terms review state transitions, and API endpoints.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.publisher.onboarding import PublisherOnboardingService
from src.publisher.verification import DomainVerifier
from src.schemas.source import (
    PublisherRegistrationRequest,
    PublisherReviewState,
    RightsMode,
    TermsReviewStatus,
    VerificationMethod,
    VerificationStatus,
)
from src.storage.db import StorageEngine


@pytest.fixture
def storage():
    """In-memory SQLite storage engine with migrations applied."""
    return StorageEngine(":memory:")


@pytest.fixture
def onboarding(storage):
    return PublisherOnboardingService(storage)


@pytest.fixture
def sample_registration():
    return PublisherRegistrationRequest(
        publisher_name="The Hindu Group",
        primary_domain="https://www.thehindu.com/news",
        contact_email="syndication@thehindu.co.in",
        contact_name="Editorial Syndication Team",
        feed_urls=["https://www.thehindu.com/news/national/feeder/default.rss"],
        homepage_url="https://www.thehindu.com",
        language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        utm_opt_in=False,
        requested_excerpt_chars=350,
        requested_excerpt_words=50
    )


# ============================================================================
# 1. Registration & Domain Normalization Tests
# ============================================================================

def test_register_publisher_success(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration, actor="editor@thehindu.co.in")

    assert profile.id == "pub-thehindu-com-en"
    assert profile.primary_domain == "thehindu.com"
    assert profile.publisher_name == "The Hindu Group"
    assert profile.language == "en"
    assert profile.rights_mode == RightsMode.FEED_PROVIDED_EXCERPT
    assert profile.excerpt_ceiling_chars == 350
    assert profile.excerpt_ceiling_words == 50
    assert profile.utm_opt_in is False
    assert profile.verification_status == VerificationStatus.PENDING
    assert profile.terms_review_status == TermsReviewStatus.PENDING
    assert profile.review_state == PublisherReviewState.PENDING_REVIEW

    # Verification challenge generated in extra_metadata
    challenge_data = profile.extra_metadata.get("verification_challenge")
    assert challenge_data is not None
    assert challenge_data["token"].startswith("posipulse_verify_")
    assert challenge_data["primary_domain"] == "thehindu.com"


def test_register_publisher_duplicate_rejection(onboarding, sample_registration):
    onboarding.register_publisher(sample_registration)
    with pytest.raises(ValueError, match="already registered"):
        onboarding.register_publisher(sample_registration)


# ============================================================================
# 2. Challenge Lifecycle & Renewal Tests
# ============================================================================

def test_challenge_expiration_and_renewal(onboarding, sample_registration, storage):
    profile = onboarding.register_publisher(sample_registration)
    ch1 = onboarding.get_or_create_challenge(profile.id)

    # Manually expire the challenge in database
    expired_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    profile.extra_metadata["verification_challenge"]["expires_at"] = expired_time
    storage.save_source_profile(profile)

    # Retrieval should detect expiration and renew
    ch2 = onboarding.get_or_create_challenge(profile.id)
    assert ch2.token != ch1.token
    assert ch2.expires_at > datetime.now(timezone.utc)


# ============================================================================
# 3. DNS TXT Verification Tests
# ============================================================================

def test_verify_dns_txt_success(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration)
    challenge = onboarding.get_or_create_challenge(profile.id)

    # Mock DNS Resolver
    mock_rdata = MagicMock()
    mock_rdata.strings = [f"posipulse-site-verification={challenge.token}".encode("utf-8")]
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = [mock_rdata]

    result = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.DNS_TXT,
        custom_resolver=mock_resolver
    )

    assert result.verified is True
    assert "Valid DNS TXT record found" in result.message

    # Check that profile updated to VERIFIED
    updated_profile = onboarding.storage.get_source_profile(profile.id)
    assert updated_profile.verification_status == VerificationStatus.VERIFIED
    assert updated_profile.review_state == PublisherReviewState.VERIFIED
    assert updated_profile.verified_at is not None


def test_verify_dns_txt_wrong_token(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration)

    mock_rdata = MagicMock()
    mock_rdata.strings = [b"posipulse-site-verification=wrong_token_here"]
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = [mock_rdata]

    result = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.DNS_TXT,
        custom_resolver=mock_resolver
    )

    assert result.verified is False
    assert "No matching DNS TXT record" in result.message


# ============================================================================
# 4. HTML Meta Tag Verification Tests
# ============================================================================

def test_verify_html_meta_success(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration)
    challenge = onboarding.get_or_create_challenge(profile.id)

    html_content = f"""<!DOCTYPE html>
    <html>
      <head>
        <title>The Hindu</title>
        <meta name="posipulse-verification" content="{challenge.token}">
      </head>
      <body><h1>News</h1></body>
    </html>"""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_content

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    result = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.HTML_META,
        custom_client=mock_client
    )

    assert result.verified is True
    assert "Verified via HTML meta tag" in result.message


def test_verify_html_meta_failure_modes(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration)

    # 1. Mismatched token
    bad_html = '<meta name="posipulse-verification" content="invalid-token">'
    mock_resp = MagicMock(status_code=200, text=bad_html)
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp

    res_mismatch = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.HTML_META,
        custom_client=mock_client
    )
    assert res_mismatch.verified is False
    assert "Mismatched" in res_mismatch.message or "mismatched" in res_mismatch.message

    # 2. HTTP 500 error
    mock_client.get.return_value = MagicMock(status_code=500, text="Server Error")
    res_500 = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.HTML_META,
        custom_client=mock_client
    )
    assert res_500.verified is False


# ============================================================================
# 5. Manual Admin Verification & State Transitions
# ============================================================================

def test_manual_admin_verification(onboarding, sample_registration):
    profile = onboarding.register_publisher(sample_registration)

    # System actor fails
    res_system = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.MANUAL_ADMIN,
        actor="system"
    )
    assert res_system.verified is False

    # Admin actor succeeds
    res_admin = onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.MANUAL_ADMIN,
        actor="chief-editor@posipulse.in"
    )
    assert res_admin.verified is True
    assert "Manually verified by admin" in res_admin.message


def test_end_to_end_state_machine_transitions(onboarding, sample_registration):
    # 1. Initial State: PENDING_REVIEW
    profile = onboarding.register_publisher(sample_registration)
    assert profile.review_state == PublisherReviewState.PENDING_REVIEW
    assert profile.is_eligible_for_publishing() is True  # Profile exists but inactive in schedule

    # 2. Domain Verification -> VERIFIED
    onboarding.verify_domain(
        profile.id,
        method=VerificationMethod.MANUAL_ADMIN,
        actor="admin@posipulse.in"
    )
    prof_verified = onboarding.storage.get_source_profile(profile.id)
    assert prof_verified.review_state == PublisherReviewState.VERIFIED

    # 3. Terms Review Approved -> ACTIVE
    prof_active = onboarding.review_terms(
        profile.id,
        new_terms_status=TermsReviewStatus.REVIEWED_ACCEPTED,
        actor="legal@posipulse.in",
        notes="Syndication contract executed 2026-10-24"
    )
    assert prof_active.review_state == PublisherReviewState.ACTIVE
    assert prof_active.terms_review_status == TermsReviewStatus.REVIEWED_ACCEPTED
    assert prof_active.is_eligible_for_publishing() is True

    # 4. Suspension by Admin -> SUSPENDED
    prof_suspended = onboarding.update_lifecycle_state(
        profile.id,
        new_state=PublisherReviewState.SUSPENDED,
        actor="admin@posipulse.in",
        reason="Temporary technical maintenance on publisher RSS feed"
    )
    assert prof_suspended.review_state == PublisherReviewState.SUSPENDED
    assert prof_suspended.is_eligible_for_publishing() is False

    # 5. Takedown Enforcement -> Cascades delisting and locks ingestion
    prof_takedown = onboarding.update_lifecycle_state(
        profile.id,
        new_state=PublisherReviewState.TAKEDOWN_REQUESTED,
        actor="publisher-legal@thehindu.co.in",
        reason="Formal copyright withdrawal notice"
    )
    assert prof_takedown.takedown_status.value == "takedown_enforced"
    assert prof_takedown.is_eligible_for_publishing() is False


# ============================================================================
# 6. REST API Endpoints Verification
# ============================================================================

def test_api_publisher_onboarding_flow(storage):
    app = create_app(storage=storage)
    client = TestClient(app)

    # 1. Register publisher
    reg_payload = {
        "publisher_name": "Deccan Herald",
        "primary_domain": "https://www.deccanherald.com",
        "contact_email": "editor@deccanherald.co.in",
        "feed_urls": ["https://www.deccanherald.com/rss/national.rss"],
        "language": "en",
        "rights_mode": "feed_provided_excerpt",
        "requested_excerpt_chars": 400,
        "requested_excerpt_words": 60
    }
    resp = client.post("/v1/publishers/register", json=reg_payload)
    assert resp.status_code == 201
    source_data = resp.json()
    source_id = source_data["id"]
    assert source_id == "pub-deccanherald-com-en"
    assert source_data["review_state"] == "pending_review"

    # 2. Retrieve challenge
    ch_resp = client.get(f"/v1/publishers/{source_id}/challenge")
    assert ch_resp.status_code == 200
    challenge = ch_resp.json()
    assert "posipulse-site-verification=" in challenge["dns_txt_expected"]

    # 3. Trigger manual admin verification
    verify_resp = client.post(
        f"/v1/publishers/{source_id}/verify",
        json={"method": "manual_admin", "admin_actor": "admin@posipulse.in"}
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verified"] is True

    # 4. Review terms
    review_resp = client.post(
        f"/v1/publishers/{source_id}/review",
        json={
            "terms_review_status": "reviewed_accepted",
            "admin_actor": "legal@posipulse.in",
            "notes": "Approved standard Tier 1 syndication license"
        }
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["review_state"] == "active"

    # 5. Lifecycle state transition to suspended
    state_resp = client.post(
        f"/v1/publishers/{source_id}/state",
        json={
            "new_state": "suspended",
            "actor": "admin@posipulse.in",
            "reason": "Routine feed maintenance"
        }
    )
    assert state_resp.status_code == 200
    assert state_resp.json()["review_state"] == "suspended"
