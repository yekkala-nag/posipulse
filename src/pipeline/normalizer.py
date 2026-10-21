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
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        # Strip marketing/tracking parameters
        filtered_params = {
            k: v for k, v in query_params.items()
            if not k.startswith("utm_") and k not in {"fbclid", "gclid", "ref", "at_medium", "at_campaign"}
        }
        clean_query = urlencode(filtered_params, doseq=True)
        clean_parsed = parsed._replace(query=clean_query, fragment="")
        return urlunparse(clean_parsed)

    def normalize(self, item: EphemeralIngestedItem) -> EphemeralIngestedItem:
        clean_headline = self.clean_html(item.headline)
        clean_body = self.clean_html(item.raw_body)
        clean_canonical = self.clean_url(item.canonical_url)

        return item.model_copy(update={
            "headline": clean_headline,
            "raw_body": clean_body,
            "canonical_url": clean_canonical
        })
