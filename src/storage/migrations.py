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
