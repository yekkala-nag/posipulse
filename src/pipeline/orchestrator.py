"""
Pipeline Orchestrator Agent
Coordinates end-to-end execution across agents:
Scheduler -> Orchestrator -> Fetcher -> Normalizer -> Language Detector -> Deduplicator ->
Headline Pre-Filter -> Positivity Classifier -> Summarizer -> Verifier -> Storage.

Guarantees:
- Typed schema-validated message envelopes carrying run_id, trace_id, rubric_version, prompt_version.
- Zero raw publisher body text persisted to database.
- Fail-closed execution and Dead-Letter Queue (DLQ) error tracking.
- Per-run cost caps with circuit breaking.
"""

from datetime import datetime, timezone
import time
import uuid
from typing import Any, Dict, List, Optional
from src.observability.logger import logger
from src.observability.metrics import metrics_collector
from src.pipeline.classifier import PositivityClassifier
from src.pipeline.deduplicator import ArticleDeduplicator
from src.pipeline.fetcher import FeedFetcher
from src.pipeline.headline_filter import HeadlinePreFilter
from src.pipeline.language_detector import LanguageDetector
from src.pipeline.normalizer import ArticleNormalizer
from src.pipeline.summarizer import AbstractiveSummarizer
from src.pipeline.verifier import FaithfulnessVerifier
from src.schemas.article import (
    Article,
    ArticleStatus,
    EphemeralIngestedItem,
    PipelineMessageEnvelope,
    PositivityLabel,
)
from src.schemas.config import LanguageConfig
from src.storage.db import StorageEngine


class PipelineOrchestrator:
    def __init__(
        self,
        language_config: LanguageConfig,
        storage: StorageEngine,
        deduplicator: Optional[ArticleDeduplicator] = None,
        language_detector: Optional[LanguageDetector] = None
    ):
        self.config = language_config
        self.storage = storage
        self.deduplicator = deduplicator or ArticleDeduplicator()
        self.language_detector = language_detector or LanguageDetector()
        self.normalizer = ArticleNormalizer()
        self.headline_filter = HeadlinePreFilter()
        self.classifier = PositivityClassifier(
            model_name=self.config.model_routing.classifier_primary_model,
            rubric_version=self.config.rubric_version
        )
        self.summarizer = AbstractiveSummarizer(
            model_name=self.config.model_routing.summarizer_primary_model,
            prompt_version=self.config.prompt_version,
            length_band=self.config.length_band
        )
        self.verifier = FaithfulnessVerifier(
            verifier_model=self.config.model_routing.verifier_model,
            length_band=self.config.length_band
        )

        self.dead_letter_queue: List[PipelineMessageEnvelope] = []
        self.current_run_cost_usd: float = 0.0

    def process_items(
        self,
        raw_items: List[EphemeralIngestedItem],
        source_id: str,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion pipeline from an ephemeral list of ingested items.
        Enforces idempotency, circuit breakers, verification gates, and zero raw body retention.
        """
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"

        stats = {
            "run_id": run_id,
            "trace_id": trace_id,
            "language": self.config.language_code,
            "source_id": source_id,
            "ingested_count": len(raw_items),
            "normalized_count": 0,
            "language_matched_count": 0,
            "duplicate_dropped_count": 0,
            "headline_rejected_count": 0,
            "classified_positive_count": 0,
            "classified_negative_count": 0,
            "verification_passed_count": 0,
            "published_count": 0,
            "run_cost_usd": 0.0
        }

        for item in raw_items:
            metrics_collector.increment_counter("posipulse_articles_ingested_total", language=self.config.language_code)

            # 1. Cost Cap Circuit Breaker Check
            if self.current_run_cost_usd >= self.config.cost_caps.max_cost_per_run_usd:
                metrics_collector.increment_counter("posipulse_circuit_breaker_trips_total", language=self.config.language_code)
                self.dead_letter_queue.append(
                    PipelineMessageEnvelope(
                        message_id=uuid.uuid4().hex,
                        run_id=run_id,
                        trace_id=trace_id,
                        stage="cost_guard",
                        language=self.config.language_code,
                        payload={"item_id": item.id},
                        error="Run cost cap reached. Circuit breaker engaged."
                    )
                )
                break

            # 2. Normalization
            norm_item = self.normalizer.normalize(item)
            stats["normalized_count"] += 1

            # 3. Language Detection & Script Gate
            lang_ok, detected_lang, conf = self.language_detector.detect_and_validate(norm_item)
            if not lang_ok:
                continue
            stats["language_matched_count"] += 1

            # 4. Idempotency & Deduplication
            is_dupe, cluster_id = self.deduplicator.check_duplicate(norm_item)
            if is_dupe or self.storage.is_hash_processed(self.deduplicator.get_idempotency_hash(norm_item)):
                stats["duplicate_dropped_count"] += 1
                continue

            # Record hash to prevent reprocessing
            self.storage.record_processed_hash(self.deduplicator.get_idempotency_hash(norm_item), norm_item.id)

            # 5. Deterministic Headline Pre-Filter (Fail-Closed)
            should_reject, reject_reason = self.headline_filter.should_reject(norm_item)
            if should_reject:
                stats["headline_rejected_count"] += 1
                continue

            # 6. Positivity Classification (Constructive Journalism Rubric)
            positivity = self.classifier.classify(norm_item)
            self.current_run_cost_usd += 0.00005  # incremental token cost tracking

            if positivity.label != PositivityLabel.POSITIVE or positivity.score < self.config.positivity_threshold:
                stats["classified_negative_count"] += 1
                continue
            stats["classified_positive_count"] += 1

            # 7. Abstractive Summarization (Original Wording)
            candidate_summary = self.summarizer.summarize(norm_item)
            self.current_run_cost_usd += 0.00008

            # 8. Adversarial Faithfulness Verification
            verified_ok, verifier_score, reasons = self.verifier.verify(norm_item, candidate_summary)
            self.current_run_cost_usd += 0.00007

            if not verified_ok:
                metrics_collector.increment_counter(
                    "posipulse_dlq_total",
                    stage="verifier",
                    language=self.config.language_code
                )
                self.dead_letter_queue.append(
                    PipelineMessageEnvelope(
                        message_id=uuid.uuid4().hex,
                        run_id=run_id,
                        trace_id=trace_id,
                        stage="verifier",
                        language=self.config.language_code,
                        payload={"item_id": norm_item.id, "headline": norm_item.headline},
                        model=self.config.model_routing.verifier_model,
                        error=f"Faithfulness verification failed: {'; '.join(reasons)}"
                    )
                )
                continue

            stats["verification_passed_count"] += 1

            # Finalize summary with verification status
            final_summary = candidate_summary.model_copy(update={
                "verified": True,
                "verifier_model": self.config.model_routing.verifier_model,
                "verifier_score": verifier_score
            })

            # 9. Persistent Storage
            # Strict non-negotiable rule: norm_item.raw_body is NEVER passed to Article model.
            published_article = Article(
                id=norm_item.id,
                source_id=norm_item.source_id,
                source_name=norm_item.source_name,
                url=norm_item.url,
                canonical_url=norm_item.canonical_url,
                headline=norm_item.headline,
                published_at=norm_item.published_at,
                fetched_at=datetime.now(timezone.utc),
                language=self.config.language_code,
                cluster_id=cluster_id,
                positivity=positivity,
                summary=final_summary,
                status=ArticleStatus.PUBLISHED
            )

            self.storage.insert_article(published_article)
            stats["published_count"] += 1
            metrics_collector.increment_counter(
                "posipulse_articles_published_total",
                language=self.config.language_code
            )

        stats["run_cost_usd"] = round(self.current_run_cost_usd, 6)
        return stats

    def process_raw_xml(
        self,
        xml_content: str,
        source_id: str,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion pipeline from an XML feed string.
        Enforces idempotency, circuit breakers, and verification gates.
        """
        source = next((s for s in self.config.sources if s.id == source_id), None)
        if not source:
            raise ValueError(f"Source ID '{source_id}' not found in language configuration for {self.config.language_code}")

        fetcher = FeedFetcher(source)
        raw_items = fetcher.parse_raw_content(xml_content)
        return self.process_items(raw_items, source_id=source_id, run_id=run_id)

    def process_live_source(
        self,
        source_id: str,
        force: bool = False,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamically fetches from live publisher RSS/API endpoint.
        Respects cooldown rate limits unless force=True.
        """
        source = next((s for s in self.config.sources if s.id == source_id), None)
        if not source:
            raise ValueError(f"Source ID '{source_id}' not found in language configuration for {self.config.language_code}")

        if not force and not self.storage.can_fetch_source(source.id, source.fetch_interval_minutes):
            logger.info(f"Skipping live fetch for {source.id}: cooldown active.", extra={"source_id": source.id})
            return {
                "source_id": source.id,
                "status": "skipped_cooldown",
                "published_count": 0,
                "ingested_count": 0
            }

        fetcher = FeedFetcher(source)
        try:
            raw_items = fetcher.fetch_live()
            self.storage.record_source_fetch(source.id, status="success", items_count=len(raw_items))
        except Exception as e:
            logger.error(f"Live fetch failed for {source.id}: {e}", extra={"source_id": source.id, "error": str(e)})
            self.storage.record_source_fetch(source.id, status="error", items_count=0)
            return {
                "source_id": source.id,
                "status": "fetch_error",
                "error": str(e),
                "published_count": 0,
                "ingested_count": 0
            }

        return self.process_items(raw_items, source_id=source_id, run_id=run_id)

    def process_live_language(
        self,
        force: bool = False,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamically fetches all active registered publisher sources for this language.
        """
        aggregated = {
            "language": self.config.language_code,
            "sources_attempted": 0,
            "sources_succeeded": 0,
            "total_ingested": 0,
            "total_published": 0,
            "details": []
        }

        for source in self.config.sources:
            if not source.is_active:
                continue
            aggregated["sources_attempted"] += 1
            res = self.process_live_source(source.id, force=force, run_id=run_id)
            aggregated["details"].append(res)
            if res.get("status") not in ["fetch_error", "skipped_cooldown"]:
                aggregated["sources_succeeded"] += 1
            aggregated["total_ingested"] += res.get("ingested_count", 0)
            aggregated["total_published"] += res.get("published_count", 0)

        return aggregated
