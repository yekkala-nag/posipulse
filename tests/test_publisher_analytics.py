"""
Comprehensive unit and integration tests for Privacy-Preserving Publisher Analytics (Step 5).
Validates DPDP Act 2023 compliance, hourly pre-aggregation, zero-PII storage,
k-anonymity minimum threshold suppression, click beacon, and publisher dashboard API.
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.schemas.article import Article, ArticleStatus, PositivityLabel, PositivityMetadata
from src.schemas.source import RightsMode, SourceProfile, TrustTier, VerificationStatus
from src.storage.db import StorageEngine


@pytest.fixture
def storage():
    return StorageEngine(":memory:")


@pytest.fixture
def publisher_source(storage):
    profile = SourceProfile(
        id="pub-thehindu-national",
        publisher_id="the-hindu-group",
        publisher_name="The Hindu",
        primary_domain="thehindu.com",
        feed_urls=["https://thehindu.com/rss"],
        homepage_url="https://thehindu.com",
        language="en",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED
    )
    storage.save_source_profile(profile)
    return profile


@pytest.fixture
def sample_article(storage, publisher_source):
    art = Article(
        id="art-solar-101",
        source_id=publisher_source.id,
        source_name="The Hindu",
        url="https://thehindu.com/solar-canal-vidarbha",
        canonical_url="https://thehindu.com/solar-canal-vidarbha",
        headline="Solar Canal Powers 50 Rural Villages",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.95, reason="Clean energy", rubric_version="1.0.0"
        )
    )
    storage.insert_article(art)
    return art


# ============================================================================
# 1. DPDP Act 2023 Schema & Zero-PII Invariant Tests
# ============================================================================

def test_dpdp_zero_pii_table_schema_verification(storage):
    """Verify publisher_analytics_hourly table contains ZERO user/identifiable columns."""
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(publisher_analytics_hourly)")
        cols = {row["name"].lower() for row in cursor.fetchall()}

        # Allowed strictly pre-aggregated columns
        expected_cols = {
            "source_id", "article_id", "language", "category_id",
            "time_bucket", "impressions", "clicks"
        }
        assert cols == expected_cols

        # Strictly forbidden PII and tracking columns
        forbidden_patterns = ["ip", "user_agent", "user_id", "reader_id", "cookie", "fingerprint", "session"]
        for col in cols:
            for pattern in forbidden_patterns:
                assert pattern not in col, f"Forbidden column '{col}' violates DPDP Act 2023 privacy guarantee!"


# ============================================================================
# 2. Hourly Pre-Aggregation & Counting Tests
# ============================================================================

def test_record_impression_and_click_hourly_bucketing(storage, publisher_source, sample_article):
    fixed_time = datetime(2026, 10, 24, 14, 25, 0, tzinfo=timezone.utc)

    # 1. Record 3 impressions in hour 14
    for _ in range(3):
        storage.record_impression(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4,  # Environment
            timestamp=fixed_time
        )

    # 2. Record 2 clicks in hour 14
    for _ in range(2):
        storage.record_click(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4,
            timestamp=fixed_time
        )

    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM publisher_analytics_hourly WHERE source_id = ? AND article_id = ?",
            (publisher_source.id, sample_article.id)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["time_bucket"] == "2026-10-24T14:00:00Z"
        assert row["impressions"] == 3
        assert row["clicks"] == 2


def test_record_impressions_batch(storage, publisher_source, sample_article):
    fixed_time = datetime(2026, 10, 24, 15, 10, 0, tzinfo=timezone.utc)
    batch = [
        {"source_id": publisher_source.id, "article_id": sample_article.id, "language": "en", "category_id": 4},
        {"source_id": publisher_source.id, "article_id": sample_article.id, "language": "en", "category_id": 4},
    ]
    storage.record_impressions_batch(batch, timestamp=fixed_time)

    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT impressions FROM publisher_analytics_hourly WHERE time_bucket = '2026-10-24T15:00:00Z'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["impressions"] == 2


# ============================================================================
# 3. K-Anonymity & Minimum Threshold Enforcement Tests
# ============================================================================

def test_k_anonymity_suppression_under_threshold(storage, publisher_source, sample_article):
    fixed_time = datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc)

    # Record 3 events (below default k-anonymity threshold 5)
    for _ in range(3):
        storage.record_impression(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4,
            timestamp=fixed_time
        )

    analytics = storage.get_publisher_analytics(
        source_id=publisher_source.id,
        since=fixed_time - timedelta(hours=1),
        min_threshold=5
    )

    # Hourly timeline bucket should be suppressed
    assert len(analytics["hourly_timeline"]) == 1
    bucket = analytics["hourly_timeline"][0]
    assert bucket["suppressed"] is True
    assert bucket["impressions"] is None
    assert bucket["clicks"] is None

    # Overall source low-traffic flag
    assert analytics["k_anonymity_suppressed"] is True


def test_k_anonymity_revealed_above_threshold(storage, publisher_source, sample_article):
    fixed_time = datetime(2026, 10, 24, 11, 0, 0, tzinfo=timezone.utc)

    # Record 10 impressions and 2 clicks (impressions >= 5)
    for _ in range(10):
        storage.record_impression(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4,
            timestamp=fixed_time
        )
    for _ in range(2):
        storage.record_click(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4,
            timestamp=fixed_time
        )

    analytics = storage.get_publisher_analytics(
        source_id=publisher_source.id,
        since=fixed_time - timedelta(hours=1),
        min_threshold=5
    )

    assert analytics["k_anonymity_suppressed"] is False
    assert analytics["total_impressions"] == 10
    assert analytics["total_clicks"] == 2
    assert analytics["overall_ctr"] == 0.2

    # Timeline bucket unsuppressed
    bucket = analytics["hourly_timeline"][0]
    assert bucket["suppressed"] is False
    assert bucket["impressions"] == 10
    assert bucket["clicks"] == 2


# ============================================================================
# 4. REST API Click Beacon & Publisher Dashboard Endpoints
# ============================================================================

def test_api_outbound_click_beacon(storage, publisher_source, sample_article):
    app = create_app(storage=storage)
    client = TestClient(app)

    # 1. Post click with dummy tracking headers (verifies all headers ignored)
    resp = client.post(
        "/v1/analytics/click",
        json={"article_id": sample_article.id},
        headers={
            "X-Forwarded-For": "203.0.113.195",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Cookie": "session_id=secret123; user=alice"
        }
    )
    assert resp.status_code == 204

    # 2. Verify click incremented in hourly storage
    now_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT clicks FROM publisher_analytics_hourly WHERE article_id = ? AND time_bucket = ?",
            (sample_article.id, now_bucket)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["clicks"] == 1


def test_api_click_beacon_not_found(storage):
    app = create_app(storage=storage)
    client = TestClient(app)

    resp = client.post("/v1/analytics/click", json={"article_id": "non-existent-id"})
    assert resp.status_code == 404


def test_api_publisher_analytics_dashboard(storage, publisher_source, sample_article):
    # Populate test data
    for _ in range(8):
        storage.record_impression(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4
        )
    for _ in range(2):
        storage.record_click(
            source_id=publisher_source.id,
            article_id=sample_article.id,
            language="en",
            category_id=4
        )

    app = create_app(storage=storage)
    client = TestClient(app)

    resp = client.get(f"/v1/publishers/{publisher_source.id}/analytics?period=7d&min_threshold=5")
    assert resp.status_code == 200
    data = resp.json()

    assert data["source_id"] == publisher_source.id
    assert data["publisher_name"] == "The Hindu"
    assert data["period"] == "7d"
    assert data["total_impressions"] == 8
    assert data["total_clicks"] == 2
    assert data["overall_ctr"] == 0.25
    assert len(data["top_articles"]) >= 1
    assert data["top_articles"][0]["article_id"] == sample_article.id


def test_api_feed_automatically_records_impressions(storage, publisher_source, sample_article):
    app = create_app(storage=storage)
    client = TestClient(app)

    # Initial impressions
    now_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")

    # Fetch feed
    resp = client.get("/v1/feed?language=en")
    assert resp.status_code == 200
    assert len(resp.json()["articles"]) >= 1

    # Check impression was logged
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT impressions FROM publisher_analytics_hourly WHERE article_id = ? AND time_bucket = ?",
            (sample_article.id, now_bucket)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["impressions"] >= 1
