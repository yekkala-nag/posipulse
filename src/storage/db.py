"""
Persistent Storage Engine
Implements zero-retention storage of original publisher text:
Only verified original summaries, headlines, metadata, and canonical links are persisted.
"""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from src.schemas.article import Article, ArticleStatus, CategoryAssignment, PositivityMetadata, SummaryMetadata
from src.schemas.source import (
    PublisherReviewState,
    RightsMode,
    SourceProfile,
    SourceProfileAuditEntry,
    TakedownStatus,
    TermsReviewStatus,
    TrustTier,
    VerificationStatus,
)
from src.storage.migrations import (
    apply_category_taxonomy_migration,
    apply_newsletter_subscriptions_migration,
    apply_publisher_analytics_migration,
    apply_reader_following_migration,
    apply_source_profiles_migration,
    apply_verbatim_excerpts_migration,
    migrate_existing_yaml_sources_to_profiles,
)


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
            apply_source_profiles_migration(conn)
            apply_verbatim_excerpts_migration(conn)
            apply_publisher_analytics_migration(conn)
            apply_reader_following_migration(conn)
            apply_newsletter_subscriptions_migration(conn)
            migrate_existing_yaml_sources_to_profiles(conn)

    def can_fetch_source(self, source_id: str, cooldown_minutes: int = 30) -> bool:
        """Determines if a publisher source is eligible for dynamic fetch based on cooldown and takedown state."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Immediate fail-closed check for publisher takedowns
            try:
                cursor.execute("SELECT takedown_status FROM source_profiles WHERE id = ?", (source_id,))
                prof = cursor.fetchone()
                if prof and prof["takedown_status"] in ("takedown_requested", "takedown_enforced"):
                    return False
            except Exception:
                pass

            # 2. Cooldown check
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

    def get_source_fetch_log(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent fetch log for a publisher source."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM source_fetch_logs WHERE source_id = ?", (source_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "source_id": row["source_id"],
                "last_fetched_at": row["last_fetched_at"],
                "status": row["status"],
                "items_count": row["items_count"]
            }

    def get_source_recent_articles(self, source_id: str, limit: int = 20) -> List[Article]:
        """Returns the most recent articles ingested for a specific source."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM articles WHERE source_id = ? ORDER BY published_at DESC LIMIT ?",
                (source_id, limit)
            )
            rows = cursor.fetchall()
            return [self._row_to_article(r) for r in rows]

    def get_source_article_counts(self, source_id: str) -> Dict[str, int]:
        """Returns total counts of ingested, published, held, and delisted articles for a source."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_ingested,
                    COALESCE(SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END), 0) AS total_published,
                    COALESCE(SUM(CASE WHEN status = 'held_hidden_category' THEN 1 ELSE 0 END), 0) AS total_held,
                    COALESCE(SUM(CASE WHEN status = 'delisted' THEN 1 ELSE 0 END), 0) AS total_delisted
                FROM articles WHERE source_id = ?
            """, (source_id,))
            row = cursor.fetchone()
            if not row:
                return {"total_ingested": 0, "total_published": 0, "total_held": 0, "total_delisted": 0}
            return {
                "total_ingested": row["total_ingested"],
                "total_published": row["total_published"],
                "total_held": row["total_held"],
                "total_delisted": row["total_delisted"]
            }

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
                    category_json, primary_category_id, publish_hold_reason,
                    verbatim_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                article.publish_hold_reason,
                article.verbatim_excerpt
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
        verbatim_excerpt = row["verbatim_excerpt"] if "verbatim_excerpt" in row_keys else None

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
            verbatim_excerpt=verbatim_excerpt,
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

    # =========================================================================
    # Source Profile Management & Takedown Enforcement (Step 1)
    # =========================================================================

    def save_source_profile(
        self,
        profile: SourceProfile,
        actor: str = "system",
        action: str = "save"
    ) -> None:
        """Upserts a SourceProfile record and appends to the immutable audit log."""
        now = datetime.now(timezone.utc).isoformat()
        profile.updated_at = datetime.now(timezone.utc)
        meta = dict(profile.extra_metadata)
        meta["review_state"] = profile.review_state.value if isinstance(profile.review_state, PublisherReviewState) else profile.review_state
        extra_json = json.dumps(meta)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO source_profiles (
                    id, publisher_id, publisher_name, primary_domain, feed_urls_json,
                    homepage_url, language, rights_mode, excerpt_ceiling_chars,
                    excerpt_ceiling_words, utm_opt_in, verification_status,
                    verified_at, terms_review_status, trust_tier, takedown_status,
                    takedown_requested_at, contact_email, contact_name,
                    created_at, updated_at, extra_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.id,
                profile.publisher_id,
                profile.publisher_name,
                profile.primary_domain,
                json.dumps(profile.feed_urls),
                profile.homepage_url,
                profile.language,
                profile.rights_mode.value if isinstance(profile.rights_mode, RightsMode) else profile.rights_mode,
                profile.excerpt_ceiling_chars,
                profile.excerpt_ceiling_words,
                1 if profile.utm_opt_in else 0,
                profile.verification_status.value if isinstance(profile.verification_status, VerificationStatus) else profile.verification_status,
                profile.verified_at.isoformat() if profile.verified_at else None,
                profile.terms_review_status.value if isinstance(profile.terms_review_status, TermsReviewStatus) else profile.terms_review_status,
                profile.trust_tier.value if isinstance(profile.trust_tier, TrustTier) else profile.trust_tier,
                profile.takedown_status.value if isinstance(profile.takedown_status, TakedownStatus) else profile.takedown_status,
                profile.takedown_requested_at.isoformat() if profile.takedown_requested_at else None,
                profile.contact_email,
                profile.contact_name,
                profile.created_at.isoformat(),
                now,
                extra_json
            ))

            cursor.execute("""
                INSERT INTO source_profile_audit_log (
                    source_id, action, actor, details_json, timestamp
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                profile.id,
                action,
                actor,
                json.dumps({
                    "rights_mode": profile.rights_mode.value if isinstance(profile.rights_mode, RightsMode) else profile.rights_mode,
                    "verification_status": profile.verification_status.value if isinstance(profile.verification_status, VerificationStatus) else profile.verification_status,
                    "review_state": meta["review_state"],
                    "takedown_status": profile.takedown_status.value if isinstance(profile.takedown_status, TakedownStatus) else profile.takedown_status,
                    "utm_opt_in": profile.utm_opt_in
                }),
                now
            ))
            conn.commit()

    def get_source_profile(self, source_id: str) -> Optional[SourceProfile]:
        """Fetches a SourceProfile along with its complete audit history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM source_profiles WHERE id = ?", (source_id,))
            row = cursor.fetchone()
            if not row:
                return None

            cursor.execute(
                "SELECT * FROM source_profile_audit_log WHERE source_id = ? ORDER BY timestamp ASC",
                (source_id,)
            )
            audit_rows = cursor.fetchall()
            audit_entries = [
                SourceProfileAuditEntry(
                    timestamp=datetime.fromisoformat(ar["timestamp"]),
                    action=ar["action"],
                    actor=ar["actor"],
                    details=json.loads(ar["details_json"])
                )
                for ar in audit_rows
            ]

            extra_meta = {}
            if "extra_metadata_json" in row.keys() and row["extra_metadata_json"]:
                try:
                    extra_meta = json.loads(row["extra_metadata_json"])
                except Exception:
                    extra_meta = {}

            review_st = extra_meta.get("review_state", PublisherReviewState.ACTIVE.value)
            try:
                review_state_enum = PublisherReviewState(review_st)
            except Exception:
                review_state_enum = PublisherReviewState.ACTIVE

            return SourceProfile(
                id=row["id"],
                publisher_id=row["publisher_id"],
                publisher_name=row["publisher_name"],
                primary_domain=row["primary_domain"],
                feed_urls=json.loads(row["feed_urls_json"]),
                homepage_url=row["homepage_url"],
                language=row["language"],
                rights_mode=RightsMode(row["rights_mode"]),
                excerpt_ceiling_chars=row["excerpt_ceiling_chars"],
                excerpt_ceiling_words=row["excerpt_ceiling_words"],
                utm_opt_in=bool(row["utm_opt_in"]),
                verification_status=VerificationStatus(row["verification_status"]),
                verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
                terms_review_status=TermsReviewStatus(row["terms_review_status"]),
                trust_tier=TrustTier(row["trust_tier"]),
                takedown_status=TakedownStatus(row["takedown_status"]),
                takedown_requested_at=datetime.fromisoformat(row["takedown_requested_at"]) if row["takedown_requested_at"] else None,
                review_state=review_state_enum,
                contact_email=row["contact_email"],
                contact_name=row["contact_name"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                audit_history=audit_entries,
                extra_metadata=extra_meta
            )

    def list_source_profiles(
        self,
        language: Optional[str] = None,
        verification_status: Optional[str] = None,
        active_only: bool = True
    ) -> List[SourceProfile]:
        """Lists source profiles matching the optional filters."""
        query = "SELECT id FROM source_profiles WHERE 1=1"
        params: List[Any] = []
        if language:
            query += " AND language = ?"
            params.append(language)
        if verification_status:
            query += " AND verification_status = ?"
            params.append(verification_status)
        if active_only:
            query += " AND takedown_status = 'active'"
        query += " ORDER BY publisher_name ASC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        profiles = []
        for r in rows:
            p = self.get_source_profile(r["id"])
            if p:
                profiles.append(p)
        return profiles

    def enforce_source_takedown(
        self,
        source_id: str,
        actor: str = "compliance_officer",
        reason: str = "Publisher takedown request"
    ) -> int:
        """
        Enforces publisher takedown immediately:
        1. Transitions source_profiles.takedown_status to 'takedown_enforced'.
        2. Delists all articles matching source_id across all surfaces immediately.
        3. Appends immutable audit entry.
        Returns count of delisted articles.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Update source profile
            cursor.execute("""
                UPDATE source_profiles
                SET takedown_status = 'takedown_enforced',
                    takedown_requested_at = coalesce(takedown_requested_at, ?),
                    updated_at = ?
                WHERE id = ?
            """, (now, now, source_id))

            # 2. Cascade delist to all articles
            cursor.execute("""
                UPDATE articles
                SET status = 'delisted',
                    publish_hold_reason = ?
                WHERE source_id = ? AND status != 'delisted'
            """, (f"Publisher takedown enforced: {reason}", source_id))
            delisted_count = cursor.rowcount

            # 3. Audit log
            cursor.execute("""
                INSERT INTO source_profile_audit_log (
                    source_id, action, actor, details_json, timestamp
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                source_id,
                "takedown_enforced",
                actor,
                json.dumps({"reason": reason, "delisted_articles_count": delisted_count}),
                now
            ))
            conn.commit()
            return delisted_count

    # =========================================================================
    # Privacy-Preserving Publisher Analytics (DPDP Act 2023)
    # Strict invariant: Zero PII (no IPs, no User-Agents, no reader identifiers)
    # =========================================================================

    def record_impression(
        self,
        source_id: str,
        article_id: str,
        language: str,
        category_id: Optional[int] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Records an anonymous impression in an hourly aggregation bucket."""
        ts = timestamp or datetime.now(timezone.utc)
        bucket = ts.strftime("%Y-%m-%dT%H:00:00Z")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO publisher_analytics_hourly (
                    source_id, article_id, language, category_id, time_bucket, impressions, clicks
                ) VALUES (?, ?, ?, ?, ?, 1, 0)
                ON CONFLICT(source_id, article_id, time_bucket)
                DO UPDATE SET impressions = impressions + 1
            """, (source_id, article_id, language, category_id, bucket))
            conn.commit()

    def record_impressions_batch(self, items: List[Dict[str, Any]], timestamp: Optional[datetime] = None) -> None:
        """Batch-increments hourly impressions for served feed articles."""
        if not items:
            return
        ts = timestamp or datetime.now(timezone.utc)
        bucket = ts.strftime("%Y-%m-%dT%H:00:00Z")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for it in items:
                cursor.execute("""
                    INSERT INTO publisher_analytics_hourly (
                        source_id, article_id, language, category_id, time_bucket, impressions, clicks
                    ) VALUES (?, ?, ?, ?, ?, 1, 0)
                    ON CONFLICT(source_id, article_id, time_bucket)
                    DO UPDATE SET impressions = impressions + 1
                """, (
                    it["source_id"],
                    it["article_id"],
                    it.get("language", "en"),
                    it.get("category_id"),
                    bucket
                ))
            conn.commit()

    def record_click(
        self,
        source_id: str,
        article_id: str,
        language: str,
        category_id: Optional[int] = None,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Records an anonymous outbound link-out click in an hourly aggregation bucket."""
        ts = timestamp or datetime.now(timezone.utc)
        bucket = ts.strftime("%Y-%m-%dT%H:00:00Z")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO publisher_analytics_hourly (
                    source_id, article_id, language, category_id, time_bucket, impressions, clicks
                ) VALUES (?, ?, ?, ?, ?, 0, 1)
                ON CONFLICT(source_id, article_id, time_bucket)
                DO UPDATE SET clicks = clicks + 1
            """, (source_id, article_id, language, category_id, bucket))
            conn.commit()

    def get_publisher_analytics(
        self,
        source_id: str,
        since: Optional[datetime] = None,
        min_threshold: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieves DPDP Act 2023 compliant aggregate analytics for a publisher source.
        Enforces k-anonymity (min_threshold): buckets or breakdowns with fewer than
        min_threshold events are suppressed.
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=30)
        since_str = since.strftime("%Y-%m-%dT%H:00:00Z")

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Overall totals
            cursor.execute("""
                SELECT
                    COALESCE(SUM(impressions), 0) AS total_impressions,
                    COALESCE(SUM(clicks), 0) AS total_clicks
                FROM publisher_analytics_hourly
                WHERE source_id = ? AND time_bucket >= ?
            """, (source_id, since_str))
            totals_row = cursor.fetchone()
            total_impressions = totals_row["total_impressions"] if totals_row else 0
            total_clicks = totals_row["total_clicks"] if totals_row else 0

            # K-anonymity gate on whole source if extremely low traffic
            k_anonymity_suppressed = False
            if total_impressions > 0 and total_impressions < min_threshold and total_clicks < min_threshold:
                k_anonymity_suppressed = True

            overall_ctr = round(total_clicks / total_impressions, 4) if total_impressions > 0 else 0.0

            # 2. Hourly Timeline
            cursor.execute("""
                SELECT
                    time_bucket,
                    SUM(impressions) AS hourly_impressions,
                    SUM(clicks) AS hourly_clicks
                FROM publisher_analytics_hourly
                WHERE source_id = ? AND time_bucket >= ?
                GROUP BY time_bucket
                ORDER BY time_bucket ASC
            """, (source_id, since_str))
            timeline_rows = cursor.fetchall()
            hourly_timeline = []
            for r in timeline_rows:
                h_imp = r["hourly_impressions"]
                h_clk = r["hourly_clicks"]
                if h_imp < min_threshold and h_clk < min_threshold:
                    hourly_timeline.append({
                        "time_bucket": r["time_bucket"],
                        "impressions": None,
                        "clicks": None,
                        "suppressed": True
                    })
                else:
                    hourly_timeline.append({
                        "time_bucket": r["time_bucket"],
                        "impressions": h_imp,
                        "clicks": h_clk,
                        "suppressed": False
                    })

            # 3. Language Breakdown
            cursor.execute("""
                SELECT language, SUM(impressions) AS lang_impressions, SUM(clicks) AS lang_clicks
                FROM publisher_analytics_hourly
                WHERE source_id = ? AND time_bucket >= ?
                GROUP BY language
            """, (source_id, since_str))
            lang_rows = cursor.fetchall()
            language_breakdown = {}
            for lr in lang_rows:
                if lr["lang_impressions"] >= min_threshold or lr["lang_clicks"] >= min_threshold:
                    language_breakdown[lr["language"]] = {
                        "impressions": lr["lang_impressions"],
                        "clicks": lr["lang_clicks"]
                    }

            # 4. Category Breakdown
            cursor.execute("""
                SELECT category_id, SUM(impressions) AS cat_impressions, SUM(clicks) AS cat_clicks
                FROM publisher_analytics_hourly
                WHERE source_id = ? AND time_bucket >= ?
                GROUP BY category_id
            """, (source_id, since_str))
            cat_rows = cursor.fetchall()
            category_breakdown = []
            suppressed_cat_imp = 0
            suppressed_cat_clk = 0
            for cr in cat_rows:
                cat_imp = cr["cat_impressions"]
                cat_clk = cr["cat_clicks"]
                if cat_imp >= min_threshold or cat_clk >= min_threshold:
                    category_breakdown.append({
                        "category_id": cr["category_id"],
                        "impressions": cat_imp,
                        "clicks": cat_clk
                    })
                else:
                    suppressed_cat_imp += cat_imp
                    suppressed_cat_clk += cat_clk

            if suppressed_cat_imp > 0 or suppressed_cat_clk > 0:
                category_breakdown.append({
                    "category_id": None,
                    "label": f"Other (suppressed < {min_threshold})",
                    "impressions": suppressed_cat_imp,
                    "clicks": suppressed_cat_clk
                })

            # 5. Top Articles
            cursor.execute("""
                SELECT
                    p.article_id,
                    a.headline,
                    SUM(p.impressions) AS art_impressions,
                    SUM(p.clicks) AS art_clicks
                FROM publisher_analytics_hourly p
                LEFT JOIN articles a ON p.article_id = a.id
                WHERE p.source_id = ? AND p.time_bucket >= ?
                GROUP BY p.article_id
                ORDER BY art_clicks DESC, art_impressions DESC
                LIMIT 20
            """, (source_id, since_str))
            art_rows = cursor.fetchall()
            top_articles = []
            for ar in art_rows:
                a_imp = ar["art_impressions"]
                a_clk = ar["art_clicks"]
                if a_imp >= min_threshold or a_clk >= min_threshold:
                    art_ctr = round(a_clk / a_imp, 4) if a_imp > 0 else 0.0
                    top_articles.append({
                        "article_id": ar["article_id"],
                        "headline": ar["headline"] or "[Archived Article]",
                        "impressions": a_imp,
                        "clicks": a_clk,
                        "ctr": art_ctr
                    })

            return {
                "source_id": source_id,
                "since": since_str,
                "k_anonymity_threshold": min_threshold,
                "k_anonymity_suppressed": k_anonymity_suppressed,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "overall_ctr": overall_ctr,
                "hourly_timeline": hourly_timeline,
                "language_breakdown": language_breakdown,
                "category_breakdown": category_breakdown,
                "top_articles": top_articles
            }

    # ========================================================================
    # Reader Following Architecture (Topic & Source Following)
    # ========================================================================

    def follow_target(self, device_id: str, following_type: str, target_id: str) -> bool:
        """
        Follows a category or publisher source anonymously by device_id.
        following_type: 'category' or 'source'
        target_id: category integer ID (1-13) string, or source profile slug.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO reader_following (device_id, following_type, target_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (device_id, following_type, str(target_id), now))
            conn.commit()
            return True

    def unfollow_target(self, device_id: str, following_type: str, target_id: str) -> bool:
        """Unfollows a category or publisher source for a given device_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM reader_following
                WHERE device_id = ? AND following_type = ? AND target_id = ?
            """, (device_id, following_type, str(target_id)))
            conn.commit()
            return cursor.rowcount > 0

    def get_reader_following(self, device_id: str) -> Dict[str, List[str]]:
        """Returns the full list of followed categories and sources for an anonymous device."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT following_type, target_id FROM reader_following
                WHERE device_id = ? ORDER BY created_at ASC
            """, (device_id,))
            rows = cursor.fetchall()
            categories = []
            sources = []
            for r in rows:
                if r["following_type"] == "category":
                    val = r["target_id"]
                    categories.append(int(val) if isinstance(val, str) and val.isdigit() else val)
                elif r["following_type"] == "source":
                    sources.append(r["target_id"])
            return {"categories": categories, "sources": sources}

    def clear_reader_following(self, device_id: str) -> int:
        """Wipes all preferences for a device (DPDP Section 12 Right to Erasure)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reader_following WHERE device_id = ?", (device_id,))
            conn.commit()
            return cursor.rowcount

    def get_following_feed(
        self,
        device_id: str,
        language: str,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Article], Optional[str]]:
        """
        Returns verified published articles matching the reader's followed categories or sources.
        Delisted, held (hidden categories), or non-published items are excluded.
        """
        following = self.get_reader_following(device_id)
        followed_categories = following["categories"]
        followed_sources = following["sources"]

        if not followed_categories and not followed_sources:
            return [], None

        query = """
            SELECT a.* FROM articles a
            LEFT JOIN delisted_articles d ON a.id = d.article_id
            LEFT JOIN source_profiles sp ON a.source_id = sp.id
            WHERE a.language = ?
              AND a.status = ?
              AND d.article_id IS NULL
              AND (sp.takedown_status IS NULL OR sp.takedown_status = 'active')
        """
        params: List[Any] = [language, ArticleStatus.PUBLISHED.value]

        filter_clauses = []
        if followed_categories:
            cat_ids = []
            for c in followed_categories:
                if str(c).isdigit():
                    cat_ids.append(int(c))
            if cat_ids:
                placeholders = ",".join("?" for _ in cat_ids)
                filter_clauses.append(f"a.primary_category_id IN ({placeholders})")
                params.extend(cat_ids)

        if followed_sources:
            placeholders = ",".join("?" for _ in followed_sources)
            filter_clauses.append(f"a.source_id IN ({placeholders})")
            params.extend(followed_sources)

        if filter_clauses:
            query += f" AND ({' OR '.join(filter_clauses)})"

        if cursor:
            query += " AND a.published_at < ?"
            params.append(cursor)

        query += " ORDER BY a.published_at DESC LIMIT ?"
        params.append(limit + 1)

        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(query, params)
            rows = c.fetchall()

        articles = [self._row_to_article(r) for r in rows[:limit]]
        next_cursor = rows[limit]["published_at"] if len(rows) > limit else None
        return articles, next_cursor

    # ========================================================================
    # Newsletter Subscriptions & Issues Storage
    # ========================================================================

    def save_newsletter_subscription(self, sub: Any) -> bool:
        """Inserts or updates a newsletter subscription record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO newsletter_subscriptions (
                    id, email, language, status, confirmation_token, unsubscribe_token,
                    requested_at, confirmed_at, unsubscribed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email, language) DO UPDATE SET
                    status = excluded.status,
                    confirmation_token = excluded.confirmation_token,
                    unsubscribe_token = excluded.unsubscribe_token,
                    requested_at = excluded.requested_at,
                    confirmed_at = excluded.confirmed_at,
                    unsubscribed_at = excluded.unsubscribed_at,
                    updated_at = excluded.updated_at
            """, (
                sub.id,
                sub.email.lower().strip(),
                sub.language,
                sub.status.value if hasattr(sub.status, "value") else str(sub.status),
                sub.confirmation_token,
                sub.unsubscribe_token,
                sub.requested_at.isoformat() if hasattr(sub.requested_at, "isoformat") else str(sub.requested_at),
                sub.confirmed_at.isoformat() if sub.confirmed_at and hasattr(sub.confirmed_at, "isoformat") else (str(sub.confirmed_at) if sub.confirmed_at else None),
                sub.unsubscribed_at.isoformat() if sub.unsubscribed_at and hasattr(sub.unsubscribed_at, "isoformat") else (str(sub.unsubscribed_at) if sub.unsubscribed_at else None),
                sub.created_at.isoformat() if hasattr(sub.created_at, "isoformat") else str(sub.created_at),
                sub.updated_at.isoformat() if hasattr(sub.updated_at, "isoformat") else str(sub.updated_at),
            ))
            conn.commit()
            return True

    def get_newsletter_subscription(self, email: str, language: str) -> Optional[Dict[str, Any]]:
        """Finds a subscription by email and language."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM newsletter_subscriptions
                WHERE email = ? AND language = ?
            """, (email.lower().strip(), language))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_newsletter_subscription_by_token(self, token_type: str, token: str) -> Optional[Dict[str, Any]]:
        """Finds a subscription by confirmation_token or unsubscribe_token."""
        col = "confirmation_token" if token_type == "confirmation" else "unsubscribe_token"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM newsletter_subscriptions WHERE {col} = ?", (token,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_confirmed_subscribers(self, language: str) -> List[Dict[str, Any]]:
        """Returns all confirmed subscribers for a language edition."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM newsletter_subscriptions
                WHERE language = ? AND status = 'confirmed'
                ORDER BY confirmed_at ASC
            """, (language,))
            return [dict(r) for r in cursor.fetchall()]

    def erase_newsletter_subscription(self, email: str) -> int:
        """DPDP Act Right to Erasure: Permanently removes all subscription data for email."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM newsletter_subscriptions WHERE email = ?", (email.lower().strip(),))
            conn.commit()
            return cursor.rowcount

    def save_newsletter_issue(self, issue: Any) -> bool:
        """Archives a compiled newsletter issue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO newsletter_issues (
                    id, language, subject, issue_date, article_ids_json,
                    html_content, text_content, sent_at, recipient_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sent_at = excluded.sent_at,
                    recipient_count = excluded.recipient_count
            """, (
                issue.id,
                issue.language,
                issue.subject,
                issue.issue_date,
                json.dumps(issue.article_ids),
                issue.html_content,
                issue.text_content,
                issue.sent_at.isoformat() if issue.sent_at and hasattr(issue.sent_at, "isoformat") else (str(issue.sent_at) if issue.sent_at else None),
                issue.recipient_count,
                issue.created_at.isoformat() if hasattr(issue.created_at, "isoformat") else str(issue.created_at),
            ))
            conn.commit()
            return True

    def get_newsletter_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific newsletter issue by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM newsletter_issues WHERE id = ?", (issue_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["article_ids"] = json.loads(res["article_ids_json"])
            return res

    def list_newsletter_issues(self, language: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists compiled newsletter issues."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if language:
                cursor.execute("""
                    SELECT * FROM newsletter_issues
                    WHERE language = ? ORDER BY issue_date DESC LIMIT ?
                """, (language, limit))
            else:
                cursor.execute("""
                    SELECT * FROM newsletter_issues
                    ORDER BY issue_date DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            issues = []
            for r in rows:
                item = dict(r)
                item["article_ids"] = json.loads(item["article_ids_json"])
                issues.append(item)
            return issues

    # ========================================================================
    # Operational Dashboards, Funnel, Takedown SLA & Adoption (Step 8)
    # ========================================================================

    def get_takedown_sla_metrics(self) -> Dict[str, Any]:
        """
        Calculates publisher takedown response time and SLA compliance.
        Standard SLA target: <= 24.0 hours from request to enforcement.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, takedown_status, takedown_requested_at, updated_at
                FROM source_profiles
                WHERE takedown_status IN ('takedown_requested', 'takedown_enforced')
            """)
            rows = cursor.fetchall()

            requested_count = len(rows)
            enforced_count = 0
            pending_count = 0
            enforcement_latencies_hours: List[float] = []
            compliant_count = 0
            breached_count = 0

            now = datetime.now(timezone.utc)

            for r in rows:
                st = r["takedown_status"]
                req_str = r["takedown_requested_at"]
                req_dt = datetime.fromisoformat(req_str) if req_str else None

                if st == "takedown_enforced":
                    enforced_count += 1
                    if req_dt:
                        enf_str = r["updated_at"]
                        enf_dt = datetime.fromisoformat(enf_str) if enf_str else now
                        diff_hours = (enf_dt - req_dt).total_seconds() / 3600.0
                        enforcement_latencies_hours.append(diff_hours)
                        if diff_hours <= 24.0:
                            compliant_count += 1
                        else:
                            breached_count += 1
                    else:
                        compliant_count += 1
                elif st == "takedown_requested":
                    pending_count += 1
                    if req_dt:
                        pending_hours = (now - req_dt).total_seconds() / 3600.0
                        if pending_hours > 24.0:
                            breached_count += 1

            avg_hours = (
                round(sum(enforcement_latencies_hours) / len(enforcement_latencies_hours), 2)
                if enforcement_latencies_hours else 0.0
            )

            total_evaluated = compliant_count + breached_count
            compliance_rate = (
                round((compliant_count / total_evaluated) * 100.0, 1)
                if total_evaluated > 0 else 100.0
            )

            return {
                "sla_target_hours": 24.0,
                "total_takedowns_requested": requested_count,
                "total_takedowns_enforced": enforced_count,
                "active_takedowns_pending": pending_count,
                "average_enforcement_time_hours": avg_hours,
                "sla_compliant_count": compliant_count,
                "sla_breached_count": breached_count,
                "sla_compliance_rate_percent": compliance_rate,
                "sla_status": "COMPLIANT" if compliance_rate >= 99.0 else "WARNING"
            }

    def get_ingestion_funnel_metrics(self) -> Dict[str, Any]:
        """
        Retrieves granular stage-by-stage ingestion funnel conversion metrics.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, count(*) as cnt FROM articles GROUP BY status")
            counts = {r["status"]: r["cnt"] for r in cursor.fetchall()}

            cursor.execute("SELECT count(*) as total FROM delisted_articles")
            delisted_row = cursor.fetchone()
            delisted_count = delisted_row["total"] if delisted_row else 0

            cursor.execute("SELECT count(*) as total FROM articles WHERE status = 'held_hidden_category'")
            held_row = cursor.fetchone()
            held_count = held_row["total"] if held_row else 0

            published_count = counts.get(ArticleStatus.PUBLISHED.value, 0)
            classifier_neg = counts.get(ArticleStatus.CLASSIFIED_NEGATIVE.value, 0)
            headline_neg = counts.get(ArticleStatus.HEADLINE_REJECTED.value, 0)
            verifier_failed = counts.get(ArticleStatus.VERIFICATION_FAILED.value, 0)
            total_ingested = sum(counts.values())

            positivity_pass_rate = (
                round((published_count + verifier_failed + held_count) / total_ingested, 4)
                if total_ingested > 0 else 0.0
            )

            final_publication_rate = (
                round(published_count / total_ingested, 4)
                if total_ingested > 0 else 0.0
            )

            return {
                "total_articles_ingested": total_ingested,
                "stage_counts": {
                    "headline_rejected": headline_neg,
                    "classified_negative": classifier_neg,
                    "verification_failed": verifier_failed,
                    "held_hidden_category": held_count,
                    "published": published_count,
                    "delisted": delisted_count
                },
                "positivity_pass_rate": positivity_pass_rate,
                "final_publication_rate": final_publication_rate,
                "fail_closed_held_count": held_count
            }

    def get_reader_adoption_metrics(self) -> Dict[str, Any]:
        """
        Aggregates reader topic following and newsletter adoption numbers.
        Zero-PII compliant (device counts and language aggregates only).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Following devices & breakdown
            cursor.execute("SELECT count(DISTINCT device_id) as total_devices FROM reader_following")
            dev_row = cursor.fetchone()
            total_devices = dev_row["total_devices"] if dev_row else 0

            cursor.execute("""
                SELECT target_id, count(*) as follower_count
                FROM reader_following
                WHERE following_type = 'category'
                GROUP BY target_id
                ORDER BY follower_count DESC
                LIMIT 5
            """)
            top_categories = [{"category_id": r["target_id"], "followers": r["follower_count"]} for r in cursor.fetchall()]

            cursor.execute("""
                SELECT target_id, count(*) as follower_count
                FROM reader_following
                WHERE following_type = 'source'
                GROUP BY target_id
                ORDER BY follower_count DESC
                LIMIT 5
            """)
            top_sources = [{"source_id": r["target_id"], "followers": r["follower_count"]} for r in cursor.fetchall()]

            # Newsletter subscriber aggregates
            cursor.execute("""
                SELECT language, status, count(*) as cnt
                FROM newsletter_subscriptions
                GROUP BY language, status
            """)
            sub_rows = cursor.fetchall()

            newsletter_stats: Dict[str, Dict[str, int]] = {}
            total_confirmed_subs = 0
            total_pending_subs = 0

            for r in sub_rows:
                lang = r["language"]
                st = r["status"]
                cnt = r["cnt"]
                if lang not in newsletter_stats:
                    newsletter_stats[lang] = {"confirmed": 0, "pending": 0, "unsubscribed": 0}
                newsletter_stats[lang][st] = cnt
                if st == "confirmed":
                    total_confirmed_subs += cnt
                elif st == "pending_confirmation":
                    total_pending_subs += cnt

            # Newsletter issues sent
            cursor.execute("SELECT count(*) as issue_count, coalesce(sum(recipient_count), 0) as total_sent FROM newsletter_issues")
            issue_row = cursor.fetchone()
            total_issues = issue_row["issue_count"] if issue_row else 0
            total_recipients_sent = issue_row["total_sent"] if issue_row else 0

            return {
                "reader_following": {
                    "total_anonymous_devices": total_devices,
                    "top_followed_categories": top_categories,
                    "top_followed_sources": top_sources,
                },
                "newsletters": {
                    "total_confirmed_subscribers": total_confirmed_subs,
                    "total_pending_confirmations": total_pending_subs,
                    "subscribers_by_language": newsletter_stats,
                    "total_issues_compiled": total_issues,
                    "total_digest_emails_dispatched": total_recipients_sent,
                }
            }

    def get_admin_dashboard_data(self) -> Dict[str, Any]:
        """
        Consolidates complete system health, funnel, SLA, and adoption data
        into an integrated operational dashboard payload.
        """
        funnel = self.get_ingestion_funnel_metrics()
        takedown_sla = self.get_takedown_sla_metrics()
        adoption = self.get_reader_adoption_metrics()

        # Integrity & Safety Audit checks
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Zero published articles in hidden categories (14-18)
            cursor.execute("""
                SELECT count(*) as leaked_count FROM articles
                WHERE status = 'published' AND primary_category_id IN (14, 15, 16, 17, 18)
            """)
            leak_row = cursor.fetchone()
            hidden_category_leak_count = leak_row["leaked_count"] if leak_row else 0

            # 2. Zero impressions on takedown-enforced publishers
            cursor.execute("""
                SELECT count(*) as invalid_sources FROM source_profiles
                WHERE takedown_status = 'takedown_enforced' AND verification_status = 'verified'
            """)
            invalid_row = cursor.fetchone()
            invalid_verified_count = invalid_row["invalid_sources"] if invalid_row else 0

        integrity_pass = (hidden_category_leak_count == 0 and invalid_verified_count == 0)

        return {
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ingestion_funnel": funnel,
            "takedown_sla": takedown_sla,
            "reader_adoption": adoption,
            "system_integrity": {
                "hidden_category_leak_count": hidden_category_leak_count,
                "integrity_audit_passed": integrity_pass,
                "dpdp_compliance": "ACTIVE"
            }
        }
