"""
Feed Fetcher Agent
Pulls RSS 2.0 / Atom syndication feeds.
Supports live network fetching with exponential backoff, circuit breaking,
and robust character encoding / malformed XML tolerance.
"""

from datetime import datetime, timezone
import hashlib
import time
from typing import List, Optional
import feedparser
from src.observability.logger import logger
from src.observability.metrics import metrics_collector
from src.schemas.article import EphemeralIngestedItem
from src.schemas.config import PublisherSource


class FeedFetcher:
    def __init__(self, source: PublisherSource, timeout_seconds: int = 10, max_retries: int = 3):
        self.source = source
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.consecutive_failures = 0

    def parse_raw_content(self, xml_content: str) -> List[EphemeralIngestedItem]:
        """Parses raw XML string with tolerance for malformed feeds and dirty encodings."""
        if not xml_content or not xml_content.strip():
            return []

        # Strip any UTF-8 BOM if present
        if xml_content.startswith("\ufeff"):
            xml_content = xml_content[1:]

        feed = feedparser.parse(xml_content)
        items = []

        for entry in feed.entries:
            headline = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not headline or not link:
                continue

            # Deterministic unique ID
            item_id = hashlib.sha256(f"{self.source.id}:{link}".encode()).hexdigest()[:16]

            # Raw description/summary as ephemeral body text
            raw_body = entry.get("description", "") or entry.get("summary", "") or headline

            # Published timestamp
            published_parsed = entry.get("published_parsed")
            if published_parsed:
                try:
                    published_at = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    published_at = datetime.now(timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)

            item = EphemeralIngestedItem(
                id=item_id,
                source_id=self.source.id,
                source_name=self.source.name,
                url=link,
                canonical_url=link,
                headline=headline,
                raw_body=raw_body,
                published_at=published_at,
                declared_language=self.source.language
            )
            items.append(item)

        return items

    def fetch_live(self) -> List[EphemeralIngestedItem]:
        """
        Fetches live feed with exponential backoff on 429/5xx,
        circuit breaker tracking, and source health status updates.
        """
        import httpx

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (compatible; PosiPulseBot/1.0; +https://posipulse.in/bot)",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start_time = time.time()
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                    resp = client.get(self.source.feed_url)
                    resp.raise_for_status()

                    content_text = resp.text
                    duration = time.time() - start_time
                    metrics_collector.record_stage_execution("fetch_live", duration, "success")
                    self.consecutive_failures = 0
                    self.source.health_status = "healthy"
                    return self.parse_raw_content(content_text)

            except Exception as e:
                last_error = e
                self.consecutive_failures += 1
                logger.warning(
                    f"Fetch attempt {attempt}/{self.max_retries} failed for {self.source.id}: {str(e)}",
                    extra={"source_id": self.source.id, "attempt": attempt, "error": str(e)}
                )
                metrics_collector.increment_counter("posipulse_fetch_errors_total", source_id=self.source.id)

                if attempt < self.max_retries:
                    backoff = 0.2 * (2 ** (attempt - 1))
                    time.sleep(backoff)

        # Mark source degraded or failing
        if self.consecutive_failures >= self.source.circuit_breaker_fail_threshold:
            self.source.health_status = "failing"
        else:
            self.source.health_status = "degraded"

        metrics_collector.set_gauge("posipulse_publisher_healthy", 0.0, source_id=self.source.id)
        raise RuntimeError(f"All {self.max_retries} fetch attempts failed for {self.source.id}: {last_error}")

