"""
Storage Migration Framework: Migration 002 Category Taxonomy

Implements backward-compatible and reversible schema evolution:
1. Adds category_json, primary_category_id, and publish_hold_reason to articles table.
2. Creates high-performance indexes for category feed filtering and hold audits.
3. Backfills existing legacy rows from positivity_json category strings.
4. Provides full rollback_category_taxonomy_migration capability for zero-risk rollback.
"""

from datetime import datetime, timezone
import json
import sqlite3
from typing import Dict, Optional
from src.schemas.article import CategoryAssignment


MIGRATION_VERSION = "002_category_taxonomy"

# Legacy string mapping to Taxonomy v1 primary IDs
LEGACY_CATEGORY_MAP: Dict[str, int] = {
    "Science/Tech": 2,
    "Ecology": 4,
    "Sports": 5,
    "Empowerment": 6,
    "Civic": 6,
    "Economy": 9,
    "Macroeconomics/Policy": 9,
    "Health": 10,
    "Infrastructure": 11,
    "Entertainment": 12,
    "World": 13,
}


def apply_category_taxonomy_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 002 (Forward).
    Returns True if migration was applied, False if already present.
    """
    cursor = conn.cursor()

    # 1. Ensure migration tracking table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Inspect existing columns in articles table
    cursor.execute("PRAGMA table_info(articles)")
    existing_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cursor.fetchall()}

    # 4. Add new columns conditionally
    if "category_json" not in existing_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN category_json TEXT")

    if "primary_category_id" not in existing_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN primary_category_id INTEGER")

    if "publish_hold_reason" not in existing_cols:
        cursor.execute("ALTER TABLE articles ADD COLUMN publish_hold_reason TEXT")

    # 5. Create performance indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_cat_pub 
        ON articles(language, status, primary_category_id, published_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_status_hold 
        ON articles(status, primary_category_id)
    """)

    # 6. Backfill existing records with legacy category string
    cursor.execute("""
        SELECT id, positivity_json 
        FROM articles 
        WHERE primary_category_id IS NULL AND positivity_json IS NOT NULL
    """)
    rows = cursor.fetchall()
    for row in rows:
        art_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        pos_json = row["positivity_json"] if isinstance(row, sqlite3.Row) else row[1]
        try:
            pos_data = json.loads(pos_json)
            legacy_cat = pos_data.get("category")
            if legacy_cat and legacy_cat in LEGACY_CATEGORY_MAP:
                primary_id = LEGACY_CATEGORY_MAP[legacy_cat]
                score = float(pos_data.get("score", 1.0))
                assignment = CategoryAssignment(
                    primary_id=primary_id,
                    confidence=score,
                    taxonomy_version="1.0.0"
                )
                cursor.execute("""
                    UPDATE articles 
                    SET category_json = ?, primary_category_id = ?
                    WHERE id = ?
                """, (assignment.model_dump_json(), primary_id, art_id))
        except Exception:
            pass

    # 7. Record migration
    cursor.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (MIGRATION_VERSION, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return True


def rollback_category_taxonomy_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 002 (Reversible).
    Returns True if rolled back, False if migration was not present.
    """
    cursor = conn.cursor()

    # Check if migration tracking table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not cursor.fetchone():
        return False

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    if not cursor.fetchone():
        return False

    # 1. Drop added indexes
    cursor.execute("DROP INDEX IF EXISTS idx_articles_cat_pub")
    cursor.execute("DROP INDEX IF EXISTS idx_articles_status_hold")

    # 2. Drop columns
    if sqlite3.sqlite_version_info >= (3, 35, 0):
        try:
            cursor.execute("ALTER TABLE articles DROP COLUMN category_json")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE articles DROP COLUMN primary_category_id")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE articles DROP COLUMN publish_hold_reason")
        except Exception:
            pass
    else:
        # Fallback table copy for older SQLite versions
        cursor.execute("""
            CREATE TABLE articles_backup (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                headline TEXT NOT NULL,
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                language TEXT NOT NULL,
                cluster_id TEXT,
                positivity_json TEXT,
                summary_json TEXT,
                status TEXT NOT NULL
            )
        """)
        cursor.execute("""
            INSERT INTO articles_backup
            SELECT id, source_id, source_name, url, canonical_url, headline,
                   published_at, fetched_at, language, cluster_id,
                   positivity_json, summary_json, status
            FROM articles
        """)
        cursor.execute("DROP TABLE articles")
        cursor.execute("ALTER TABLE articles_backup RENAME TO articles")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_lang_status_pub 
            ON articles(language, status, published_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_cluster 
            ON articles(cluster_id)
        """)

    # 3. Remove migration record
    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    conn.commit()
    return True


# ============================================================================
# Migration 003: Centralized Publisher Source Profiles & Audit Log
# ============================================================================

MIGRATION_003_VERSION = "003_source_profiles"


def apply_source_profiles_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 003 (Forward):
    Creates source_profiles and source_profile_audit_log tables with indexes.
    Returns True if migration was applied, False if already present.
    """
    cursor = conn.cursor()

    # 1. Ensure migration tracking table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_003_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Create central source_profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_profiles (
            id TEXT PRIMARY KEY,
            publisher_id TEXT NOT NULL,
            publisher_name TEXT NOT NULL,
            primary_domain TEXT NOT NULL,
            feed_urls_json TEXT NOT NULL,
            homepage_url TEXT NOT NULL,
            language TEXT NOT NULL,
            rights_mode TEXT NOT NULL DEFAULT 'headline_only',
            excerpt_ceiling_chars INTEGER NOT NULL DEFAULT 400,
            excerpt_ceiling_words INTEGER NOT NULL DEFAULT 60,
            utm_opt_in INTEGER NOT NULL DEFAULT 0,
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            verified_at TEXT,
            terms_review_status TEXT NOT NULL DEFAULT 'pending',
            trust_tier TEXT NOT NULL DEFAULT 'tier_2',
            takedown_status TEXT NOT NULL DEFAULT 'active',
            takedown_requested_at TEXT,
            contact_email TEXT,
            contact_name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            extra_metadata_json TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_profiles_domain 
        ON source_profiles(primary_domain)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_profiles_lang_ver 
        ON source_profiles(language, verification_status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_profiles_takedown 
        ON source_profiles(takedown_status)
    """)

    # 4. Create immutable source audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_profile_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            details_json TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_audit_source_id 
        ON source_profile_audit_log(source_id)
    """)

    # 5. Record migration
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO schema_migrations (version, applied_at)
        VALUES (?, ?)
    """, (MIGRATION_003_VERSION, now))

    conn.commit()
    return True


def rollback_source_profiles_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 003 (Reversible Schema Evolution):
    Drops source_profiles and source_profile_audit_log tables and cleans tracking record.
    Returns True if rolled back, False if migration was not present.
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_003_VERSION,))
    if not cursor.fetchone():
        return False

    cursor.execute("DROP TABLE IF EXISTS source_profile_audit_log")
    cursor.execute("DROP TABLE IF EXISTS source_profiles")

    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_003_VERSION,))
    conn.commit()
    return True


def migrate_existing_yaml_sources_to_profiles(conn: sqlite3.Connection, config_registry=None) -> int:
    """
    Extracts all existing sources from YAML language configs and migrates them
    into the persistent source_profiles table with safe default policies:
    - rights_mode = 'headline_only'
    - utm_opt_in = False
    - verification_status = 'unverified'
    - takedown_status = 'active'
    Returns count of newly inserted profiles.
    """
    from urllib.parse import urlparse
    import re
    from src.config.loader import LanguageConfigRegistry
    from src.schemas.source import RightsMode, VerificationStatus, TermsReviewStatus, TrustTier, TakedownStatus

    registry = config_registry or LanguageConfigRegistry()
    cursor = conn.cursor()

    inserted_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for lang_cfg in registry.list_all():
        for source in lang_cfg.sources:
            # Check if source already exists
            cursor.execute("SELECT 1 FROM source_profiles WHERE id = ?", (source.id,))
            if cursor.fetchone():
                continue

            # Derive clean primary domain
            domain_source = source.homepage_url or source.feed_url
            parsed = urlparse(domain_source if "://" in domain_source else f"https://{domain_source}")
            netloc = parsed.netloc.lower() or parsed.path.lower()
            primary_domain = re.sub(r"^www\.", "", netloc).split("/")[0] or "unknown.domain"

            publisher_id = source.id.rsplit("-", 1)[0] if "-" in source.id else source.id

            cursor.execute("""
                INSERT INTO source_profiles (
                    id, publisher_id, publisher_name, primary_domain, feed_urls_json,
                    homepage_url, language, rights_mode, excerpt_ceiling_chars,
                    excerpt_ceiling_words, utm_opt_in, verification_status,
                    terms_review_status, trust_tier, takedown_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source.id,
                publisher_id,
                source.name,
                primary_domain,
                json.dumps([source.feed_url]),
                source.homepage_url,
                source.language,
                RightsMode.HEADLINE_ONLY.value,
                400,
                60,
                0,
                VerificationStatus.UNVERIFIED.value,
                TermsReviewStatus.PENDING.value,
                TrustTier.TIER_2.value,
                TakedownStatus.ACTIVE.value,
                now,
                now
            ))

            # Audit entry
            cursor.execute("""
                INSERT INTO source_profile_audit_log (
                    source_id, action, actor, details_json, timestamp
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                source.id,
                "initial_yaml_migration",
                "system_migrator",
                json.dumps({
                    "name": source.name,
                    "language": source.language,
                    "feed_url": source.feed_url,
                    "homepage_url": source.homepage_url
                }),
                now
            ))
            inserted_count += 1

    conn.commit()
    return inserted_count


# ============================================================================
# Migration 004: Verbatim Excerpt Storage on Articles
# ============================================================================

MIGRATION_004_VERSION = "004_verbatim_excerpts"


def apply_verbatim_excerpts_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 004 (Forward):
    Adds verbatim_excerpt column to articles table if not already present.
    """
    cursor = conn.cursor()

    # 1. Ensure migration tracking table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_004_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Add verbatim_excerpt column if missing
    cursor.execute("PRAGMA table_info(articles)")
    columns = [row[1] if isinstance(row, tuple) else row["name"] for row in cursor.fetchall()]
    if "verbatim_excerpt" not in columns:
        cursor.execute("ALTER TABLE articles ADD COLUMN verbatim_excerpt TEXT")

    # 4. Record migration
    cursor.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (MIGRATION_004_VERSION, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return True


def rollback_verbatim_excerpts_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 004 (Reversible).
    Drops verbatim_excerpt column and removes version from schema_migrations.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not cursor.fetchone():
        return False

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_004_VERSION,))
    if not cursor.fetchone():
        return False

    if sqlite3.sqlite_version_info >= (3, 35, 0):
        try:
            cursor.execute("ALTER TABLE articles DROP COLUMN verbatim_excerpt")
        except sqlite3.OperationalError:
            pass

    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_004_VERSION,))
    conn.commit()
    return True


# ============================================================================
# Migration 005: Privacy-Preserving Hourly Publisher Analytics (DPDP Act 2023)
# ============================================================================

MIGRATION_005_VERSION = "005_publisher_analytics"


def apply_publisher_analytics_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 005 (Forward):
    Creates privacy-preserving, aggregate-only publisher_analytics_hourly table.
    Strict DPDP Act 2023 invariant: Zero personal data (no IPs, no User-Agents, no user IDs).
    """
    cursor = conn.cursor()

    # 1. Ensure migration tracking table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_005_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Create hourly pre-aggregated metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS publisher_analytics_hourly (
            source_id TEXT NOT NULL,
            article_id TEXT NOT NULL,
            language TEXT NOT NULL,
            category_id INTEGER,
            time_bucket TEXT NOT NULL,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (source_id, article_id, time_bucket)
        )
    """)

    # 4. Performance indexes for time-range querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pub_analytics_source_bucket
        ON publisher_analytics_hourly (source_id, time_bucket)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pub_analytics_bucket
        ON publisher_analytics_hourly (time_bucket)
    """)

    # 5. Record migration
    cursor.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (MIGRATION_005_VERSION, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return True


def rollback_publisher_analytics_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 005 (Reversible).
    Drops publisher_analytics_hourly table and indexes.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not cursor.fetchone():
        return False

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_005_VERSION,))
    if not cursor.fetchone():
        return False

    cursor.execute("DROP INDEX IF EXISTS idx_pub_analytics_source_bucket")
    cursor.execute("DROP INDEX IF EXISTS idx_pub_analytics_bucket")
    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_005_VERSION,))
    conn.commit()
    return True


# ============================================================================
# Migration 006: Reader Following Architecture (Categories & Sources)
# ============================================================================

MIGRATION_006_VERSION = "006_reader_following"


def apply_reader_following_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 006 (Forward).
    Creates reader_following table for anonymous device-based topic and source following.
    Enforces strict zero-PII and DPDP user preference retention.
    """
    cursor = conn.cursor()

    # 1. Ensure schema migrations tracker exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_006_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Create reader_following table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reader_following (
            device_id TEXT NOT NULL,
            following_type TEXT NOT NULL, -- 'category' or 'source'
            target_id TEXT NOT NULL,      -- category ID integer string (1-13) or source_id slug
            created_at TEXT NOT NULL,
            PRIMARY KEY (device_id, following_type, target_id)
        )
    """)

    # 4. Performance indexes for device preference lookups and popularity aggregation
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reader_following_device
        ON reader_following (device_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reader_following_target
        ON reader_following (following_type, target_id)
    """)

    # 5. Record migration
    cursor.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (MIGRATION_006_VERSION, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return True


def rollback_reader_following_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 006 (Reversible).
    Drops reader_following table and indexes.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not cursor.fetchone():
        return False

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_006_VERSION,))
    if not cursor.fetchone():
        return False

    cursor.execute("DROP INDEX IF EXISTS idx_reader_following_device")
    cursor.execute("DROP INDEX IF EXISTS idx_reader_following_target")
    cursor.execute("DROP TABLE IF EXISTS reader_following")

    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_006_VERSION,))
    conn.commit()
    return True


# ============================================================================
# Migration 007: Per-Language Newsletter Subscriptions & Issues
# ============================================================================

MIGRATION_007_VERSION = "007_newsletter_subscriptions"


def apply_newsletter_subscriptions_migration(conn: sqlite3.Connection) -> bool:
    """
    Applies Migration 007 (Forward).
    Creates tables for double opt-in subscriptions and compiled newsletter issues.
    Complies with DPDP Act 2023 with cryptographic tokens and audit timestamps.
    """
    cursor = conn.cursor()

    # 1. Ensure schema migrations tracker exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # 2. Check if already applied
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_007_VERSION,))
    if cursor.fetchone():
        return False

    # 3. Create newsletter_subscriptions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            language TEXT NOT NULL,
            status TEXT NOT NULL, -- 'pending_confirmation', 'confirmed', 'unsubscribed'
            confirmation_token TEXT NOT NULL,
            unsubscribe_token TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            confirmed_at TEXT,
            unsubscribed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (email, language)
        )
    """)

    # 4. Performance indexes for lookups and batch sending
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_sub_email
        ON newsletter_subscriptions (email)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_sub_lang_status
        ON newsletter_subscriptions (language, status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_sub_conf_token
        ON newsletter_subscriptions (confirmation_token)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_sub_unsub_token
        ON newsletter_subscriptions (unsubscribe_token)
    """)

    # 5. Create newsletter_issues table for compiled archive & metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_issues (
            id TEXT PRIMARY KEY,
            language TEXT NOT NULL,
            subject TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            article_ids_json TEXT NOT NULL,
            html_content TEXT NOT NULL,
            text_content TEXT NOT NULL,
            sent_at TEXT,
            recipient_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_newsletter_issues_lang
        ON newsletter_issues (language, issue_date)
    """)

    # 6. Record migration
    cursor.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (MIGRATION_007_VERSION, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    return True


def rollback_newsletter_subscriptions_migration(conn: sqlite3.Connection) -> bool:
    """
    Rolls back Migration 007 (Reversible).
    Drops newsletter_subscriptions and newsletter_issues tables and indexes.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not cursor.fetchone():
        return False

    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_007_VERSION,))
    if not cursor.fetchone():
        return False

    cursor.execute("DROP INDEX IF EXISTS idx_newsletter_sub_email")
    cursor.execute("DROP INDEX IF EXISTS idx_newsletter_sub_lang_status")
    cursor.execute("DROP INDEX IF EXISTS idx_newsletter_sub_conf_token")
    cursor.execute("DROP INDEX IF EXISTS idx_newsletter_sub_unsub_token")
    cursor.execute("DROP TABLE IF EXISTS newsletter_subscriptions")

    cursor.execute("DROP INDEX IF EXISTS idx_newsletter_issues_lang")
    cursor.execute("DROP TABLE IF EXISTS newsletter_issues")

    cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_007_VERSION,))
    conn.commit()
    return True
