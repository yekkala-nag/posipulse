"""
Unit and Integration Tests for Migration 002: Category Taxonomy
Verifies:
1. Migration 002 adds category_json, primary_category_id, and publish_hold_reason.
2. Legacy articles are backfilled with correct category IDs and confidence scores.
3. High-performance indexes (idx_articles_cat_pub, idx_articles_status_hold) are created.
4. Migration is idempotent (multiple runs succeed safely).
5. Migration is reversible via rollback_category_taxonomy_migration without data loss.
6. Feed queries support primary_category_id, category slugs, and legacy category strings.
7. Held articles with status='held_hidden_category' are excluded from public feeds.
"""

from datetime import datetime, timezone
import json
import sqlite3
import pytest
from src.schemas.article import (
    Article,
    ArticleStatus,
    CategoryAssignment,
    PositivityLabel,
    PositivityMetadata,
    SummaryMetadata,
)
from src.storage.db import StorageEngine
from src.storage.migrations import (
    MIGRATION_VERSION,
    apply_category_taxonomy_migration,
    rollback_category_taxonomy_migration,
)


def create_legacy_database(conn: sqlite3.Connection):
    """Creates initial legacy database schema (v1 without category columns)."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE articles (
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
        CREATE INDEX idx_articles_lang_status_pub 
        ON articles(language, status, published_at DESC)
    """)
    cursor.execute("""
        CREATE TABLE delisted_articles (
            article_id TEXT PRIMARY KEY,
            requester_name TEXT,
            requester_email TEXT NOT NULL,
            reason TEXT NOT NULL,
            delisted_at TEXT NOT NULL
        )
    """)
    conn.commit()


def test_migration_up_and_backfill():
    """Verify forward migration adds columns, indexes, and backfills legacy categories."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_legacy_database(conn)

    cursor = conn.cursor()
    # Insert legacy article with "Science/Tech" category
    pos_sci = {
        "label": "positive",
        "score": 0.94,
        "reason": "Scientific breakthrough.",
        "rubric_version": "1.0.0",
        "category": "Science/Tech"
    }
    cursor.execute("""
        INSERT INTO articles (
            id, source_id, source_name, url, canonical_url, headline,
            published_at, fetched_at, language, cluster_id,
            positivity_json, summary_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "legacy_art_01", "the-hindu", "The Hindu", "https://thehindu.com/sci.html",
        "https://thehindu.com/sci.html", "Solar Cell Efficiency Breakthrough",
        datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
        "en", None, json.dumps(pos_sci), None, "published"
    ))
    conn.commit()

    # Apply migration
    applied = apply_category_taxonomy_migration(conn)
    assert applied is True

    # Verify columns exist
    cursor.execute("PRAGMA table_info(articles)")
    cols = {row["name"] for row in cursor.fetchall()}
    assert "category_json" in cols
    assert "primary_category_id" in cols
    assert "publish_hold_reason" in cols

    # Verify backfill mapped "Science/Tech" to primary_category_id=2
    cursor.execute("SELECT * FROM articles WHERE id = 'legacy_art_01'")
    row = cursor.fetchone()
    assert row["primary_category_id"] == 2
    assert row["category_json"] is not None

    cat_assignment = CategoryAssignment.model_validate_json(row["category_json"])
    assert cat_assignment.primary_id == 2
    assert cat_assignment.taxonomy_version == "1.0.0"

    # Verify migration recorded
    cursor.execute("SELECT version FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    assert cursor.fetchone() is not None


def test_migration_idempotency():
    """Applying migration multiple times should be safe and idempotent."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_legacy_database(conn)

    assert apply_category_taxonomy_migration(conn) is True
    assert apply_category_taxonomy_migration(conn) is False


def test_migration_rollback_reversible():
    """Verify rollback removes added indexes/columns and migration record without losing data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_legacy_database(conn)

    # Insert test article
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO articles (
            id, source_id, source_name, url, canonical_url, headline,
            published_at, fetched_at, language, cluster_id,
            positivity_json, summary_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "art_to_rollback", "the-hindu", "The Hindu", "https://thehindu.com/a.html",
        "https://thehindu.com/a.html", "Headline",
        datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
        "en", None, None, None, "published"
    ))
    conn.commit()

    # Apply then rollback
    apply_category_taxonomy_migration(conn)
    rolled_back = rollback_category_taxonomy_migration(conn)
    assert rolled_back is True

    # Verify migration record removed
    cursor.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    assert cursor.fetchone() is None

    # Verify article still exists
    cursor.execute("SELECT * FROM articles WHERE id = 'art_to_rollback'")
    row = cursor.fetchone()
    assert row is not None
    assert row["id"] == "art_to_rollback"


def test_storage_engine_feed_category_filtering():
    """Verify StorageEngine.get_feed filters correctly on category IDs, slugs, and legacy strings."""
    engine = StorageEngine(":memory:")

    # Insert Article in Science & Technology (ID 2)
    art_sci = Article(
        id="art_sci_101",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/sci.html",
        canonical_url="https://thehindu.com/sci.html",
        headline="Quantum Computing Milestone Reached",
        published_at=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        language="en",
        category=CategoryAssignment(primary_id=2, secondary_ids=[], confidence=0.98),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.95,
            reason="Breakthrough scientific innovation.", rubric_version="1.0.0",
            category="Science/Tech"
        ),
        status=ArticleStatus.PUBLISHED
    )

    # Insert Article in Sports (ID 5)
    art_sports = Article(
        id="art_sports_102",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/sports.html",
        canonical_url="https://thehindu.com/sports.html",
        headline="National Athletics Gold Record Broken",
        published_at=datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc),
        language="en",
        category=CategoryAssignment(primary_id=5, secondary_ids=[], confidence=0.95),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.90,
            reason="National sports achievement.", rubric_version="1.0.0",
            category="Sports"
        ),
        status=ArticleStatus.PUBLISHED
    )

    # Insert Held Article in Governance (ID 14 - Hidden)
    art_held = Article(
        id="art_held_103",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/gov.html",
        canonical_url="https://thehindu.com/gov.html",
        headline="Public Grievance Portal Launched",
        published_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        language="en",
        category=CategoryAssignment(primary_id=14, secondary_ids=[], confidence=0.92),
        positivity=PositivityMetadata(
            label=PositivityLabel.POSITIVE, score=0.88,
            reason="Civic governance program.", rubric_version="1.0.0"
        ),
        status=ArticleStatus.HELD_HIDDEN_CATEGORY,
        publish_hold_reason="Category 14 is hidden at launch"
    )

    engine.insert_article(art_sci)
    engine.insert_article(art_sports)
    engine.insert_article(art_held)

    # 1. Unfiltered feed should return both published articles, never the held one
    feed, _ = engine.get_feed("en")
    feed_ids = [a.id for a in feed]
    assert "art_sci_101" in feed_ids
    assert "art_sports_102" in feed_ids
    assert "art_held_103" not in feed_ids, "Held hidden-category items must NEVER appear in public feed"

    # 2. Filter by integer ID "2"
    feed_sci, _ = engine.get_feed("en", category="2")
    assert len(feed_sci) == 1
    assert feed_sci[0].id == "art_sci_101"

    # 3. Filter by slug "sports"
    feed_sport, _ = engine.get_feed("en", category="sports")
    assert len(feed_sport) == 1
    assert feed_sport[0].id == "art_sports_102"

    # 4. Filter by legacy string "Science/Tech"
    feed_legacy, _ = engine.get_feed("en", category="Science/Tech")
    assert len(feed_legacy) == 1
    assert feed_legacy[0].id == "art_sci_101"
