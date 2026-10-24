"""
Comprehensive unit and integration tests for Reader Category & Source Following (Step 6).
Validates DPDP Act 2023 compliance, anonymous device IDs, visible categories only
(fail-closed blocker for hidden categories), source takedown blockers,
following feed aggregation, and complete erasure rights.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
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
    apply_reader_following_migration,
    rollback_reader_following_migration,
)


@pytest.fixture
def storage():
    return StorageEngine(":memory:")


@pytest.fixture
def client(storage):
    app = create_app(storage=storage)
    return TestClient(app)


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
        verification_status=VerificationStatus.VERIFIED,
    )
    storage.save_source_profile(profile)
    return profile


@pytest.fixture
def delisted_source(storage):
    profile = SourceProfile(
        id="pub-delisted-source",
        publisher_id="delisted-group",
        publisher_name="Delisted Tribune",
        primary_domain="delistednews.com",
        feed_urls=["https://delistednews.com/rss"],
        homepage_url="https://delistednews.com",
        language="en",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.COMMUNITY,
        verification_status=VerificationStatus.UNVERIFIED,
        takedown_status="takedown_enforced",
    )
    storage.save_source_profile(profile)
    return profile


# ============================================================================
# 1. Migration 006 Reversibility Tests
# ============================================================================

def test_migration_006_schema_and_reversibility():
    """Verify Migration 006 creates reader_following table and rolls back cleanly."""
    storage = StorageEngine(":memory:")

    # Verify table reader_following exists (auto-applied on init)
    with storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reader_following'")
        assert cursor.fetchone() is not None

        # Verify index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_reader_following_device'")
        assert cursor.fetchone() is not None

        # Rollback migration 006
        assert rollback_reader_following_migration(conn) is True

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reader_following'")
        assert cursor.fetchone() is None

        # Re-apply migration 006
        assert apply_reader_following_migration(conn) is True

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reader_following'")
        assert cursor.fetchone() is not None


# ============================================================================
# 2. Storage Engine Direct CRUD Tests
# ============================================================================

def test_storage_engine_follow_crud(storage):
    """Test follow, duplicate follow, unfollow, and clear operations."""
    device_id = "anon-dev-12345"

    # Follow category 1 and source 'pub-1'
    assert storage.follow_target(device_id, "category", 1) is True
    assert storage.follow_target(device_id, "source", "pub-1") is True

    # Duplicate follow should return True without inserting duplicates (INSERT OR IGNORE)
    assert storage.follow_target(device_id, "category", 1) is True

    # Retrieve following preferences
    prefs = storage.get_reader_following(device_id)
    assert prefs["categories"] == [1]
    assert prefs["sources"] == ["pub-1"]

    # Unfollow category
    assert storage.unfollow_target(device_id, "category", 1) is True
    prefs = storage.get_reader_following(device_id)
    assert prefs["categories"] == []
    assert prefs["sources"] == ["pub-1"]

    # DPDP complete erasure
    deleted = storage.clear_reader_following(device_id)
    assert deleted == 1
    prefs = storage.get_reader_following(device_id)
    assert prefs["categories"] == []
    assert prefs["sources"] == []


# ============================================================================
# 3. REST API: Follow / Unfollow Validation & Fail-Closed Guardrails
# ============================================================================

def test_api_follow_visible_category(client):
    """Readers can follow active visible categories (1-13)."""
    device_id = "test-reader-device-1"

    res = client.post(
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "category", "target_id": 1},  # Agriculture & Rural Development
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["following_type"] == "category"
    assert data["target_id"] == 1

    # Check reader following list
    res_list = client.get(f"/v1/reader/{device_id}/following")
    assert res_list.status_code == 200
    assert 1 in res_list.json()["categories"]


def test_api_follow_hidden_category_blocked(client):
    """
    Fail-closed policy: Readers CANNOT follow hidden categories (e.g., ID 14-18, Option A).
    Attempting to follow a hidden category must be rejected immediately with HTTP 400.
    """
    device_id = "test-reader-device-2"

    # Category 14 is a hidden/withheld category
    res = client.post(
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "category", "target_id": 14},
    )
    assert res.status_code == 400
    assert "Hidden news categories cannot be followed" in res.json()["detail"]


def test_api_follow_publisher_source(client, publisher_source):
    """Readers can follow verified publisher sources."""
    device_id = "test-reader-device-3"

    res = client.post(
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "source", "target_id": publisher_source.id},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    res_list = client.get(f"/v1/reader/{device_id}/following")
    assert publisher_source.id in res_list.json()["sources"]


def test_api_follow_delisted_source_blocked(client, delisted_source):
    """
    Readers CANNOT follow a source whose takedown status is 'takedown_enforced'.
    Must return HTTP 400.
    """
    device_id = "test-reader-device-4"

    res = client.post(
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "source", "target_id": delisted_source.id},
    )
    assert res.status_code == 400
    assert "Delisted publisher sources cannot be followed" in res.json()["detail"]


def test_api_unfollow_target(client, publisher_source):
    """Readers can unfollow previously followed categories or sources."""
    device_id = "test-reader-device-5"

    # Follow first
    client.post(
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "source", "target_id": publisher_source.id},
    )

    # Unfollow
    res = client.request(
        "DELETE",
        f"/v1/reader/{device_id}/follow",
        json={"following_type": "source", "target_id": publisher_source.id},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify empty
    res_list = client.get(f"/v1/reader/{device_id}/following")
    assert publisher_source.id not in res_list.json()["sources"]


# ============================================================================
# 4. DPDP Act Right to Erasure
# ============================================================================

def test_api_dpdp_clear_following(client, publisher_source):
    """DELETE /v1/reader/{device_id}/following permanently erases all preferences."""
    device_id = "test-reader-device-dpdp"

    # Follow category 1 and source
    client.post(f"/v1/reader/{device_id}/follow", json={"following_type": "category", "target_id": 1})
    client.post(f"/v1/reader/{device_id}/follow", json={"following_type": "source", "target_id": publisher_source.id})

    # Erase
    res = client.delete(f"/v1/reader/{device_id}/following")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["deleted_count"] == 2

    # Verify completely empty
    res_list = client.get(f"/v1/reader/{device_id}/following")
    assert res_list.json()["categories"] == []
    assert res_list.json()["sources"] == []


# ============================================================================
# 5. Following Feed Aggregation & Filtering
# ============================================================================

def test_following_feed_empty_when_no_follows(client):
    """Following feed returns empty array when reader has no followed targets."""
    res = client.get("/v1/feed/following?device_id=empty-device&language=en")
    assert res.status_code == 200
    data = res.json()
    assert data["articles"] == []
    assert data["has_more"] is False


def test_following_feed_filters_by_followed_topics_and_sources(storage, client):
    """
    Insert articles across different categories and sources.
    Ensure /v1/feed/following only serves articles matching followed categories OR sources.
    """
    device_id = "feed-test-reader"

    # Source 1: The Hindu
    s1 = SourceProfile(
        id="pub-thehindu",
        publisher_id="hindu-grp",
        publisher_name="The Hindu",
        primary_domain="thehindu.com",
        feed_urls=["https://thehindu.com/rss"],
        homepage_url="https://thehindu.com",
        language="en",
        rights_mode=RightsMode.HEADLINE_ONLY,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
    )
    storage.save_source_profile(s1)

    # Source 2: PIB
    s2 = SourceProfile(
        id="pub-pib",
        publisher_id="pib-gov",
        publisher_name="PIB",
        primary_domain="pib.gov.in",
        feed_urls=["https://pib.gov.in/rss"],
        homepage_url="https://pib.gov.in",
        language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        trust_tier=TrustTier.TIER_1,
        verification_status=VerificationStatus.VERIFIED,
    )
    storage.save_source_profile(s2)

    # Article 1: Category 1 (Agriculture), Source 1
    art1 = Article(
        id="art-agri-1",
        source_id=s1.id,
        source_name="The Hindu",
        url="https://thehindu.com/agri-millets",
        canonical_url="https://thehindu.com/agri-millets",
        headline="Millets Revolution Boosts Smallholder Income",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=1, confidence=0.98),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.95, reason="Constructive farming", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art1)

    # Article 2: Category 2 (Science & Tech), Source 2
    art2 = Article(
        id="art-science-2",
        source_id=s2.id,
        source_name="PIB",
        url="https://pib.gov.in/isro-mission",
        canonical_url="https://pib.gov.in/isro-mission",
        headline="ISRO Successfully Validates Deep Space Sensor",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=2, confidence=0.99),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.98, reason="Scientific breakthrough", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art2)

    # Article 3: Category 3 (Education), Source 1
    art3 = Article(
        id="art-edu-3",
        source_id=s1.id,
        source_name="The Hindu",
        url="https://thehindu.com/rural-schools",
        canonical_url="https://thehindu.com/rural-schools",
        headline="Digital Libraries Reach 500 Rural Schools",
        published_at=datetime.now(timezone.utc),
        language="en",
        status=ArticleStatus.PUBLISHED,
        category=CategoryAssignment(primary_id=3, confidence=0.95),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.92, reason="Education empowerment", rubric_version="1.0.0"
        ),
    )
    storage.insert_article(art3)

    # Reader follows Category 2 (Science & Tech) only
    client.post(f"/v1/reader/{device_id}/follow", json={"following_type": "category", "target_id": 2})

    res = client.get(f"/v1/feed/following?device_id={device_id}&language=en")
    assert res.status_code == 200
    articles = res.json()["articles"]
    assert len(articles) == 1
    assert articles[0]["id"] == "art-science-2"

    # Reader now also follows Source 1 (The Hindu)
    client.post(f"/v1/reader/{device_id}/follow", json={"following_type": "source", "target_id": s1.id})

    res = client.get(f"/v1/feed/following?device_id={device_id}&language=en")
    assert res.status_code == 200
    articles = res.json()["articles"]
    # Should now see art1 (cat 1, source 1), art2 (cat 2, source 2), art3 (cat 3, source 1)
    article_ids = {a["id"] for a in articles}
    assert article_ids == {"art-agri-1", "art-science-2", "art-edu-3"}
