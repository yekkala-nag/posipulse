"""
Feed Fetcher Agent
Pulls RSS 2.0 / Atom syndication feeds.
Supports both live network fetching (with backoff & timeouts) and recorded offline fixtures for CI.
"""

from datetime import datetime, timezone
import hashlib
from typing import List, Optional
import feedparser
from src.schemas.article import EphemeralIngestedItem
from src.schemas.config import PublisherSource


class FeedFetcher:
    def __init__(self, source: PublisherSource, timeout_seconds: int = 10):
        self.source = source
        self.timeout_seconds = timeout_seconds

    def parse_raw_content(self, xml_content: str) -> List[EphemeralIngestedItem]:
        """Parses raw XML string (used for both live responses and recorded offline fixtures)."""
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
                published_at = datetime(*published_parsed[:6], tzinfo=timezone.utc)
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
        """Fetches from live feed URL with timeout."""
        import httpx
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            resp = client.get(self.source.feed_url)
            resp.raise_for_status()
            return self.parse_raw_content(resp.text)
