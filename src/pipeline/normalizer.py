"""
Normalizer Agent
Cleans HTML entities, strips tracking parameters from URLs, standardizes whitespace.
"""

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from bs4 import BeautifulSoup
from src.schemas.article import EphemeralIngestedItem


class ArticleNormalizer:
    @staticmethod
    def clean_html(text: str) -> str:
        """Strips HTML tags and normalizes whitespace."""
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        cleaned = soup.get_text(separator=" ")
        # Remove consecutive whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def clean_url(url: str) -> str:
        """Removes tracking query parameters (utm_*, ref, fbclid, etc.)."""
        from src.presentation.attribution import AttributionEngine
        return AttributionEngine.clean_url(url)

    def normalize(self, item: EphemeralIngestedItem) -> EphemeralIngestedItem:
        clean_headline = self.clean_html(item.headline)
        clean_body = self.clean_html(item.raw_body)
        clean_canonical = self.clean_url(item.canonical_url)

        return item.model_copy(update={
            "headline": clean_headline,
            "raw_body": clean_body,
            "canonical_url": clean_canonical
        })
