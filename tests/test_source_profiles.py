"""
Unit and Integration Tests for Source Profile Foundation (Step 1)
Verifies:
1. Pydantic schema validation, domain normalization, and rights mode excerpt truncation.
2. Migration 003 forward application, idempotent re-run, and clean rollback.
3. Automated migration of all existing sources across 16 language configurations.
4. StorageEngine CRUD operations, audit history preservation, and immediate takedown cascading.
"""

from datetime import datetime, timezone
import sqlite3
import pytest

from src.config.loader import LanguageConfigRegistry
from src.schemas.article import Article, ArticleStatus
from src.schemas.source import (
    RightsMode,
    SourceProfile,
    SourceProfileAuditEntry,
    TakedownStatus,
    TermsReviewStatus,
    TrustTier,
    VerificationStatus,
)
from src.storage.db import StorageEngine
from src.storage.migrations import (
    apply_source_profiles_migration,
    migrate_existing_yaml_sources_to_profiles,
    rollback_source_profiles_migration,
)


@pytest.fixture
def memory_db():
    return StorageEngine(":memory:")


@pytest.fixture
def raw_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ============================================================================
# 1. Schema Validation & Business Invariant Tests
# ============================================================================

def test_source_profile_defaults_and_domain_normalization():
    """Verify default values adhere to non-negotiable rules and domains are normalized."""
    profile = SourceProfile(
        id="test-publisher-national",
        publisher_id="test-publisher",
        publisher_name="Test Publisher",
        primary_domain="https://www.TestPublisher.com/news/india",
        feed_urls=["https://testpublisher.com/rss/all.xml"],
        homepage_url="https://testpublisher.com",
        language="en"
    )

    # Invariants
    assert profile.primary_domain == "testpublisher.com"
    assert profile.rights_mode == RightsMode.HEADLINE_ONLY
    assert profile.utm_opt_in is False  # Non-negotiable default
    assert profile.verification_status == VerificationStatus.UNVERIFIED
    assert profile.terms_review_status == TermsReviewStatus.PENDING
    assert profile.takedown_status == TakedownStatus.ACTIVE
    assert profile.excerpt_ceiling_chars == 400
    assert profile.excerpt_ceiling_words == 60
    assert profile.is_eligible_for_publishing() is True


def test_invalid_domain_rejected():
    with pytest.raises(ValueError, match="Invalid primary domain format"):
        SourceProfile(
            id="bad-source",
            publisher_id="bad",
            publisher_name="Bad",
            primary_domain="not-a-domain",
            feed_urls=["https://bad.com/rss"],
            homepage_url="https://bad.com",
            language="en"
        )


def test_rights_mode_excerpt_truncation():
    """Verify excerpt truncation strictly respects rights mode and ceiling limits."""
    # 1. HEADLINE_ONLY: Always returns None
    headline_profile = SourceProfile(
        id="pub-1-source", publisher_id="pub-1", publisher_name="Publisher 1",
        primary_domain="pub1.com", feed_urls=["https://pub1.com/rss"],
        homepage_url="https://pub1.com", language="en",
        rights_mode=RightsMode.HEADLINE_ONLY
    )
    sample_text = "This is a constructive milestone achieved by local researchers in solar energy."
    assert headline_profile.truncate_excerpt(sample_text) is None

    # 2. FEED_PROVIDED_EXCERPT: Returns bounded text
    excerpt_profile = SourceProfile(
        id="pub-2-source", publisher_id="pub-2", publisher_name="Publisher 2",
        primary_domain="pub2.com", feed_urls=["https://pub2.com/rss"],
        homepage_url="https://pub2.com", language="en",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        excerpt_ceiling_chars=120,
        excerpt_ceiling_words=16
    )
    long_text = (
        "This is a long sentence describing a major breakthrough in agricultural wastewater treatment "
        "pioneered by local community researchers who discovered that natural bio-enzymes accelerate purification "
        "without requiring artificial chemicals or high energy inputs."
    )
    truncated = excerpt_profile.truncate_excerpt(long_text)
    assert truncated is not None
    assert len(truncated) <= 123  # includes ellipsis
    assert len(truncated.split()) <= 17


# ============================================================================
# 2. Reversible Database Migration Tests
# ============================================================================

def test_migration_003_forward_idempotent_and_rollback(raw_conn):
    """Test full forward migration, idempotent re-run, and complete rollback."""
    # 1. Forward
    applied = apply_source_profiles_migration(raw_conn)
    assert applied is True

    # Verify tables exist
    cursor = raw_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_profiles'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_profile_audit_log'")
    assert cursor.fetchone() is not None

    # 2. Idempotent check
    reapplied = apply_source_profiles_migration(raw_conn)
    assert reapplied is False

    # 3. Rollback
    rolled_back = rollback_source_profiles_migration(raw_conn)
    assert rolled_back is True

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_profiles'")
    assert cursor.fetchone() is None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_profile_audit_log'")
    assert cursor.fetchone() is None

    # 4. Re-apply after rollback
    re_applied = apply_source_profiles_migration(raw_conn)
    assert re_applied is True


# ============================================================================
# 3. Existing YAML Source Migration Tests
# ============================================================================

def test_existing_yaml_sources_migrated_to_profiles(raw_conn):
    """Verify all 56+ sources across all 16 languages are migrated cleanly."""
    apply_source_profiles_migration(raw_conn)

    registry = LanguageConfigRegistry()
    total_sources = sum(len(c.sources) for c in registry.list_all())
    assert total_sources >= 56

    inserted_count = migrate_existing_yaml_sources_to_profiles(raw_conn, registry)
    assert inserted_count == total_sources

    # Idempotent re-run should insert 0 new rows
    re_run = migrate_existing_yaml_sources_to_profiles(raw_conn, registry)
    assert re_run == 0

    cursor = raw_conn.cursor()
    cursor.execute("SELECT count(*) as cnt FROM source_profiles")
    assert cursor.fetchone()["cnt"] == total_sources

    # Verify Hindu, BBC Hindi, Loksatta, etc. exist with safe defaults
    cursor.execute("SELECT * FROM source_profiles WHERE id = 'the-hindu-national'")
    hindu = cursor.fetchone()
    assert hindu is not None
    assert hindu["primary_domain"] == "thehindu.com"
    assert hindu["rights_mode"] == "headline_only"
    assert hindu["utm_opt_in"] == 0
    assert hindu["takedown_status"] == "active"

    # Verify audit entries were created
    cursor.execute("SELECT count(*) as cnt FROM source_profile_audit_log WHERE action = 'initial_yaml_migration'")
    assert cursor.fetchone()["cnt"] == total_sources


# ============================================================================
# 4. StorageEngine CRUD & Immediate Takedown Enforcement Tests
# ============================================================================

def test_storage_engine_source_profile_crud_and_audit(memory_db):
    """Verify save, fetch, and audit history preservation."""
    profile = SourceProfile(
        id="regional-herald-kannada",
        publisher_id="regional-herald",
        publisher_name="Regional Herald",
        primary_domain="https://regionalherald.in/news",
        feed_urls=["https://regionalherald.in/rss.xml"],
        homepage_url="https://regionalherald.in",
        language="kn",
        rights_mode=RightsMode.FEED_PROVIDED_EXCERPT,
        utm_opt_in=False,
        contact_email="editor@regionalherald.in",
        contact_name="Chief Editor"
    )

    memory_db.save_source_profile(profile, actor="admin@posipulse.in", action="manual_registration")

    fetched = memory_db.get_source_profile("regional-herald-kannada")
    assert fetched is not None
    assert fetched.id == "regional-herald-kannada"
    assert fetched.primary_domain == "regionalherald.in"
    assert fetched.rights_mode == RightsMode.FEED_PROVIDED_EXCERPT
    assert fetched.contact_email == "editor@regionalherald.in"
    assert len(fetched.audit_history) >= 1
    assert fetched.audit_history[-1].action == "manual_registration"
    assert fetched.audit_history[-1].actor == "admin@posipulse.in"

    # List profiles
    kn_profiles = memory_db.list_source_profiles(language="kn")
    assert any(p.id == "regional-herald-kannada" for p in kn_profiles)


def test_immediate_takedown_cascade(memory_db):
    """
    Non-negotiable requirement:
    A takedown request removes the publisher's items from every surface immediately
    and blocks re-ingestion.
    """
    # 1. Insert active source profile
    profile = SourceProfile(
        id="takedown-target-source",
        publisher_id="takedown-pub",
        publisher_name="Takedown Pub",
        primary_domain="target-pub.com",
        feed_urls=["https://target-pub.com/rss"],
        homepage_url="https://target-pub.com",
        language="en"
    )
    memory_db.save_source_profile(profile)

    # 2. Insert published articles for this source and another source
    now = datetime.now(timezone.utc)
    art1 = Article(
        id="art-target-1",
        source_id="takedown-target-source",
        source_name="Takedown Pub",
        url="https://target-pub.com/art1",
        canonical_url="https://target-pub.com/art1",
        headline="Positive milestone in water conservation",
        published_at=now,
        fetched_at=now,
        language="en",
        status=ArticleStatus.PUBLISHED
    )
    art2 = Article(
        id="art-other-1",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/art2",
        canonical_url="https://thehindu.com/art2",
        headline="Clean energy progress in rural microgrids",
        published_at=now,
        fetched_at=now,
        language="en",
        status=ArticleStatus.PUBLISHED
    )
    memory_db.insert_article(art1)
    memory_db.insert_article(art2)

    # Verify both are initially published
    active_articles, _ = memory_db.get_feed("en")
    assert any(a.id == "art-target-1" for a in active_articles)
    assert any(a.id == "art-other-1" for a in active_articles)
    assert memory_db.can_fetch_source("takedown-target-source") is True

    # 3. Enforce takedown
    delisted_count = memory_db.enforce_source_takedown(
        source_id="takedown-target-source",
        actor="legal_counsel@posipulse.in",
        reason="Publisher Section 52 Copyright Opt-Out"
    )
    assert delisted_count == 1

    # 4. Invariant: Source items vanish from every public feed surface
    updated_articles, _ = memory_db.get_feed("en")
    assert not any(a.id == "art-target-1" for a in updated_articles)
    assert any(a.id == "art-other-1" for a in updated_articles)

    # 5. Invariant: Article status transitioned to delisted with explicit hold reason
    art_stored = memory_db.get_article("art-target-1")
    assert art_stored.status == ArticleStatus.DELISTED
    assert "Publisher takedown enforced" in art_stored.publish_hold_reason

    # 6. Invariant: Source profile marked takedown_enforced
    prof_updated = memory_db.get_source_profile("takedown-target-source")
    assert prof_updated.takedown_status == TakedownStatus.TAKEDOWN_ENFORCED
    assert prof_updated.takedown_requested_at is not None
    assert prof_updated.is_eligible_for_publishing() is False

    # 7. Invariant: Re-ingestion is immediately blocked
    assert memory_db.can_fetch_source("takedown-target-source") is False
    assert not any(p.id == "takedown-target-source" for p in memory_db.list_source_profiles(active_only=True))
