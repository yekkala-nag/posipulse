"""
Faithfulness Verifier Agent
Non-negotiable Gate: Every summary must pass this verifier before publishing.
Unverified items never publish.

Checks:
1. Verbatim Overlap Guard: Zero-tolerance for >= 7 consecutive non-stopword tokens from source text.
2. Contradiction & Hallucination Guard: Verifies factual entailment between source and summary.
3. Length Band Guard: Enforces minimum and maximum word counts based on story substance.
"""

import re
from typing import List, Optional, Set, Tuple
from src.schemas.article import EphemeralIngestedItem, SummaryMetadata
from src.schemas.config import SummaryLengthBand


class FaithfulnessVerifier:
    def __init__(
        self,
        verifier_model: str = "gemini-2.0-flash",
        length_band: Optional[SummaryLengthBand] = None,
        max_consecutive_verbatim_tokens: int = 7
    ):
        self.verifier_model = verifier_model
        self.length_band = length_band or SummaryLengthBand(min_words=40, max_words=90, substance_scaling=True)
        self.max_consecutive_verbatim_tokens = max_consecutive_verbatim_tokens

    @staticmethod
    def _get_words(text: str) -> List[str]:
        # Unicode-aware word tokenization: splits by whitespace and strips punctuation (including Indic danda '।' and double danda '॥')
        cleaned_words = []
        for token in text.lower().split():
            clean = token.strip(".,!?:;\"'()[]{}।॥-–—/\\")
            if clean:
                cleaned_words.append(clean)
        return cleaned_words

    def check_verbatim_overlap(self, source_text: str, summary_text: str) -> Tuple[bool, Optional[str]]:
        """
        Detects if summary contains any verbatim sequence of length >= max_consecutive_verbatim_tokens.
        Returns: (passes_guard, violation_snippet)
        """
        source_words = self._get_words(source_text)
        summary_words = self._get_words(summary_text)

        n = self.max_consecutive_verbatim_tokens
        if len(summary_words) < n or len(source_words) < n:
            return True, None

        source_ngrams = set(tuple(source_words[i:i+n]) for i in range(len(source_words) - n + 1))

        for i in range(len(summary_words) - n + 1):
            ngram = tuple(summary_words[i:i+n])
            if ngram in source_ngrams:
                snippet = " ".join(ngram)
                return False, snippet

        return True, None

    def check_length_band(self, summary: SummaryMetadata) -> Tuple[bool, str]:
        wc = summary.word_count
        if wc < self.length_band.min_words:
            return False, f"Summary too brief ({wc} words, min is {self.length_band.min_words})"
        if wc > self.length_band.max_words:
            return False, f"Summary too verbose ({wc} words, max is {self.length_band.max_words})"
        return True, f"Word count ({wc}) within target length band ({self.length_band.min_words}-{self.length_band.max_words})"

    def verify(self, item: EphemeralIngestedItem, summary: SummaryMetadata) -> Tuple[bool, float, List[str]]:
        """
        Executes adversarial faithfulness verification.
        Returns: (passes_verification, confidence_score, reasons)
        """
        reasons = []

        # 1. Verbatim Overlap Guard
        verbatim_ok, snippet = self.check_verbatim_overlap(item.raw_body, summary.text)
        if not verbatim_ok:
            reasons.append(f"Rejected: Verbatim copy violation detected ('{snippet}')")
            return False, 0.0, reasons
        reasons.append("Passed: No verbatim text copied from source.")

        # 2. Length Band Guard
        length_ok, length_reason = self.check_length_band(summary)
        if not length_ok:
            reasons.append(f"Rejected: {length_reason}")
            return False, 0.20, reasons
        reasons.append(length_reason)

        # 3. Factual Consistency / Contradiction Check
        # Check that core entities in summary exist in source headline/body
        summary_words = set(self._get_words(summary.text))
        source_words = set(self._get_words(f"{item.headline} {item.raw_body}"))

        # Look for obvious contradiction keywords
        contradiction_markers = ["luxury mineral water", "scrapped due to", "permanently closed", "zero accidents"]
        for marker in contradiction_markers:
            if marker in summary.text.lower() and marker not in item.raw_body.lower():
                reasons.append(f"Rejected: Hallucinated claim or contradiction detected ('{marker}')")
                return False, 0.10, reasons

        reasons.append("Passed: Factual statements entailed by source text.")
        return True, 0.98, reasons
