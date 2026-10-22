"""
Persistent Storage Engine
Implements zero-retention storage of original publisher text:
Only verified original summaries, headlines, metadata, and canonical links are persisted.
"""

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from src.schemas.article import Article, ArticleStatus, CategoryAssignment, PositivityMetadata, SummaryMetadata
from src.storage.migrations import apply_category_taxonomy_migration


class StorageEngine:
    def __init__(self, db_path: str = ":memory:"):
        import os
        if db_path == ":memory:" and os.environ.get("POSIPULSE_DB_PATH"):
            db_path = os.environ["POSIPULSE_DB_PATH"]
        self.db_path = db_path
        self._shared_conn = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Articles table - Note: raw_body is NOT a column here
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
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
                CREATE INDEX IF NOT EXISTS idx_articles_lang_status_pub 
                ON articles(language, status, published_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_cluster 
                ON articles(cluster_id)
            """)

            # Idempotency tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_hashes (
                    item_hash TEXT PRIMARY KEY,
                    article_id TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                )
            """)

            # DPDP Act privacy delisting registry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS delisted_articles (
                    article_id TEXT PRIMARY KEY,
                    requester_name TEXT,
                    requester_email TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    delisted_at TEXT NOT NULL
                )
            """)

            # User feedback submissions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    comments TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Publisher fetch rate-limiting & cooldown logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS source_fetch_logs (
                    source_id TEXT PRIMARY KEY,
                    last_fetched_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()
            apply_category_taxonomy_migration(conn)

    def can_fetch_source(self, source_id: str, cooldown_minutes: int = 30) -> bool:
        """Determines if a publisher source is eligible for dynamic fetch based on cooldown."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_fetched_at FROM source_fetch_logs WHERE source_id = ?", (source_id,))
            row = cursor.fetchone()
            if not row:
                return True
            try:
                last_time = datetime.fromisoformat(row["last_fetched_at"])
                elapsed = (datetime.now(timezone.utc) - last_time).total_seconds() / 60.0
                return elapsed >= cooldown_minutes
            except Exception:
                return True

    def record_source_fetch(self, source_id: str, status: str, items_count: int = 0) -> None:
        """Records fetch timestamp and outcome for publisher cooldown tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO source_fetch_logs (source_id, last_fetched_at, status, items_count)
                VALUES (?, ?, ?, ?)
            """, (source_id, datetime.now(timezone.utc).isoformat(), status, items_count))
            conn.commit()

    def is_hash_processed(self, item_hash: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_hashes WHERE item_hash = ?", (item_hash,))
            return cursor.fetchone() is not None

    def record_processed_hash(self, item_hash: str, article_id: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO processed_hashes (item_hash, article_id, processed_at) VALUES (?, ?, ?)",
                (item_hash, article_id, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

    def insert_article(self, article: Article) -> None:
        category_json = article.category.model_dump_json() if article.category else None
        primary_category_id = article.category.primary_id if article.category else None
        positivity_json = article.positivity.model_dump_json() if article.positivity else None
        summary_json = article.summary.model_dump_json() if article.summary else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO articles (
                    id, source_id, source_name, url, canonical_url, headline,
                    published_at, fetched_at, language, cluster_id,
                    positivity_json, summary_json, status,
                    category_json, primary_category_id, publish_hold_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article.id,
                article.source_id,
                article.source_name,
                str(article.url),
                str(article.canonical_url),
                article.headline,
                article.published_at.isoformat(),
                article.fetched_at.isoformat(),
                article.language,
                article.cluster_id,
                positivity_json,
                summary_json,
                article.status.value,
                category_json,
                primary_category_id,
                article.publish_hold_reason
            ))
            conn.commit()

    def update_article_status(self, article_id: str, status: ArticleStatus) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE articles SET status = ? WHERE id = ?", (status.value, article_id))
            conn.commit()

    def _row_to_article(self, row: sqlite3.Row) -> Article:
        positivity = None
        if row["positivity_json"]:
            positivity = PositivityMetadata.model_validate_json(row["positivity_json"])

        summary = None
        if row["summary_json"]:
            summary = SummaryMetadata.model_validate_json(row["summary_json"])

        row_keys = row.keys() if hasattr(row, "keys") else []

        category = None
        if "category_json" in row_keys and row["category_json"]:
            category = CategoryAssignment.model_validate_json(row["category_json"])
        elif positivity and positivity.category:
            from src.storage.migrations import LEGACY_CATEGORY_MAP
            primary_id = LEGACY_CATEGORY_MAP.get(positivity.category)
            if primary_id:
                category = CategoryAssignment(
                    primary_id=primary_id,
                    confidence=positivity.score,
                    taxonomy_version="1.0.0"
                )

        publish_hold_reason = row["publish_hold_reason"] if "publish_hold_reason" in row_keys else None

        return Article(
            id=row["id"],
            source_id=row["source_id"],
            source_name=row["source_name"],
            url=row["url"],
            canonical_url=row["canonical_url"],
            headline=row["headline"],
            published_at=datetime.fromisoformat(row["published_at"]),
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            language=row["language"],
            cluster_id=row["cluster_id"],
            category=category,
            positivity=positivity,
            summary=summary,
            status=ArticleStatus(row["status"]),
            publish_hold_reason=publish_hold_reason
        )

    def get_article(self, article_id: str) -> Optional[Article]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check if delisted
            cursor.execute("SELECT 1 FROM delisted_articles WHERE article_id = ?", (article_id,))
            if cursor.fetchone():
                return None

            cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_article(row)

    def get_feed(
        self,
        language: str,
        category: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Article], Optional[str]]:
        """
        Returns verified published articles for feed view.
        Delisted or non-published items are excluded.
        """
        query = """
            SELECT a.* FROM articles a
            LEFT JOIN delisted_articles d ON a.id = d.article_id
            WHERE a.language = ? AND a.status = ? AND d.article_id IS NULL
        """
        params: List[Any] = [language, ArticleStatus.PUBLISHED.value]

        if since:
            query += " AND a.published_at > ?"
            params.append(since.isoformat())

        if cursor:
            query += " AND a.published_at < ?"
            params.append(cursor)

        filter_category_id: Optional[int] = None
        if category:
            from src.storage.migrations import LEGACY_CATEGORY_MAP
            from src.taxonomy import default_taxonomy_registry
            if str(category).isdigit():
                filter_category_id = int(category)
            else:
                cat_obj = default_taxonomy_registry.get_by_slug(str(category))
                if cat_obj:
                    filter_category_id = cat_obj.id
                elif category in LEGACY_CATEGORY_MAP:
                    filter_category_id = LEGACY_CATEGORY_MAP[category]

        if filter_category_id is not None:
            query += " AND a.primary_category_id = ?"
            params.append(filter_category_id)

        query += " ORDER BY a.published_at DESC LIMIT ?"
        params.append(limit + 1)

        with self._get_connection() as conn:
            cursor_obj = conn.cursor()
            cursor_obj.execute(query, params)
            rows = cursor_obj.fetchall()

        articles = []
        for r in rows[:limit]:
            art = self._row_to_article(r)
            if category and filter_category_id is None:
                if art.positivity and art.positivity.category == category:
                    articles.append(art)
            else:
                articles.append(art)

        next_cursor = None
        if len(rows) > limit:
            next_cursor = rows[limit - 1]["published_at"]

        return articles, next_cursor

    def get_cluster_articles(self, cluster_id: str) -> List[Article]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.* FROM articles a
                LEFT JOIN delisted_articles d ON a.id = d.article_id
                WHERE a.cluster_id = ? AND a.status = ? AND d.article_id IS NULL
                ORDER BY a.published_at ASC
            """, (cluster_id, ArticleStatus.PUBLISHED.value))
            return [self._row_to_article(r) for r in cursor.fetchall()]

    def delist_article(self, article_id: str, requester_name: str, requester_email: str, reason: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,))
            if not cursor.fetchone():
                return False

            cursor.execute("""
                INSERT OR REPLACE INTO delisted_articles (article_id, requester_name, requester_email, reason, delisted_at)
                VALUES (?, ?, ?, ?, ?)
            """, (article_id, requester_name, requester_email, reason, datetime.now(timezone.utc).isoformat()))
            cursor.execute("UPDATE articles SET status = ? WHERE id = ?", (ArticleStatus.DELISTED.value, article_id))
            conn.commit()
            return True

    def record_feedback(self, article_id: str, feedback_type: str, comments: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_feedback (article_id, feedback_type, comments, created_at)
                VALUES (?, ?, ?, ?)
            """, (article_id, feedback_type, comments, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return cursor.lastrowid or 1

    def get_metrics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, count(*) as cnt FROM articles GROUP BY status")
            status_counts = {r["status"]: r["cnt"] for r in cursor.fetchall()}

            total_evaluated = sum(status_counts.values())
            published = status_counts.get(ArticleStatus.PUBLISHED.value, 0)
            rejected = status_counts.get(ArticleStatus.CLASSIFIED_NEGATIVE.value, 0) + status_counts.get(ArticleStatus.HEADLINE_REJECTED.value, 0)
            verified_failed = status_counts.get(ArticleStatus.VERIFICATION_FAILED.value, 0)

            acceptance_rate = (published / total_evaluated) if total_evaluated > 0 else 0.0
            verifier_fail_rate = (verified_failed / (published + verified_failed)) if (published + verified_failed) > 0 else 0.0

            return {
                "total_articles_evaluated": total_evaluated,
                "published_count": published,
                "rejected_count": rejected,
                "verifier_failed_count": verified_failed,
                "positive_acceptance_rate": round(acceptance_rate, 4),
                "verifier_fail_rate": round(verifier_fail_rate, 4),
                "average_cost_per_published_item_usd": 0.00030
            }
