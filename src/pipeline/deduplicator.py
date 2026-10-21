"""
Deduplicator Agent
Handles exact/fuzzy title deduplication and semantic clustering.
Prevents duplicate processing and assigns cross-lingual cluster IDs.
"""

import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple
from src.schemas.article import EphemeralIngestedItem


class ArticleDeduplicator:
    def __init__(self, intra_lang_threshold: float = 0.85):
        self.intra_lang_threshold = intra_lang_threshold
        # In-memory sliding window cache of recent items
        self._seen_hashes: Set[str] = set()
        self._clusters: Dict[str, List[str]] = {}  # cluster_id -> list of article_ids
        self._title_tokens_by_id: Dict[str, Set[str]] = {}

    def get_idempotency_hash(self, item: EphemeralIngestedItem) -> str:
        """Generates deterministic hash based on canonical URL and published date."""
        key = f"{item.canonical_url}:{item.published_at.strftime('%Y-%m-%d')}"
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        words = re.findall(r"\w+", text.lower())
        return set(words)

    def check_duplicate(self, item: EphemeralIngestedItem) -> Tuple[bool, Optional[str]]:
        """
        Checks if item is a duplicate within the sliding window.
        Returns: (is_duplicate, cluster_id)
        """
        item_hash = self.get_idempotency_hash(item)
        if item_hash in self._seen_hashes:
            return True, None

        tokens = self._tokenize(item.headline)
        if not tokens:
            return False, f"cluster_{item.id[:8]}"

        # Check Jaccard similarity against existing items
        best_sim = 0.0
        best_cluster = None

        for existing_id, existing_tokens in self._title_tokens_by_id.items():
            intersection = len(tokens.intersection(existing_tokens))
            union = len(tokens.union(existing_tokens))
            if union > 0:
                sim = intersection / union
                if sim > best_sim:
                    best_sim = sim
                    for cid, member_ids in self._clusters.items():
                        if existing_id in member_ids:
                            best_cluster = cid
                            break

        if best_sim >= self.intra_lang_threshold:
            # Intra-language duplicate: drop item
            return True, best_cluster

        # New distinct story or cross-language cluster member
        cluster_id = best_cluster if best_cluster and best_sim >= 0.50 else f"cluster_{item.id[:8]}"

        # Register in window
        self._seen_hashes.add(item_hash)
        self._title_tokens_by_id[item.id] = tokens
        if cluster_id not in self._clusters:
            self._clusters[cluster_id] = []
        self._clusters[cluster_id].append(item.id)

        return False, cluster_id
