"""
Headline Pre-Filter Agent
Deterministic, zero-cost fail-closed filter.
Rejects headlines containing disaster, homicide, violent crime, or fatal accident markers
before calling expensive LLM classification.
"""

import re
from typing import Set, Tuple
from src.schemas.article import EphemeralIngestedItem


class HeadlinePreFilter:
    # Universal fail-closed negative triggers (English and transliterations)
    NEGATIVE_KEYWORDS: Set[str] = {
        "killed", "dead", "death", "dies", "died", "murder", "murdered", "fatal",
        "accident", "crash", "collision", "blast", "explosion", "scam", "fraud",
        "arrested", "custody", "suicide", "tragedy", "tragic", "assault", "rape",
        "lynched", "collapsed", "hostage", "terror", "terrorist", "massacre"
    }

    def should_reject(self, item: EphemeralIngestedItem) -> Tuple[bool, str]:
        """
        Evaluates headline against high-precision negative markers.
        Returns: (should_reject, reason)
        """
        tokens = set(re.findall(r"\w+", item.headline.lower()))
        matched = tokens.intersection(self.NEGATIVE_KEYWORDS)

        if matched:
            return True, f"Headline matched negative disaster/crime keywords: {', '.join(sorted(matched))}"

        return False, "Headline passed preliminary filter."
