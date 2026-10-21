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
    # Universal fail-closed negative triggers (English, Hindi, and common variants)
    NEGATIVE_KEYWORDS: Set[str] = {
        # English
        "killed", "dead", "death", "dies", "died", "murder", "murdered", "fatal",
        "accident", "crash", "collision", "blast", "explosion", "scam", "fraud",
        "arrested", "custody", "suicide", "tragedy", "tragic", "assault", "rape",
        "lynched", "collapsed", "hostage", "terror", "terrorist", "massacre",
        # Hindi (Devanagari)
        "मौत", "हादसा", "दुर्घटना", "विस्फोट", "धमाका", "फटा", "हत्या", "गिरफ्तार",
        "धोखाधड़ी", "आत्महत्या", "त्रासदी", "झुलसे", "टक्कर", "तबाही", "लूट",
        # Bengali (Eastern Nagri)
        "মৃত্যু", "দুর্ঘটনা", "অগ্নিকাণ্ড", "বিস্ফোরণ", "খুন", "হত্যা", "লুট", "ডাকাতি",
        "ধস", "নিহত", "গ্রেপ্তার", "প্রতারণা", "বিষাক্ত",
        # Marathi (Devanagari)
        "मृत्यू", "अपघात", "स्फोट", "आग", "दरोडा", "फसवणूक", "अटकेत", "कोसळली",
        "उध्वस्त", "धडक", "बळी",
        # Telugu
        "మృతి", "దుర్మరణం", "ప్రమాదం", "పేలుడు", "దోపిడీ", "మోసం", "అరెస్ట్",
        "కూలి", "హత్య", "విషాదం", "ఢీకొని", "ఢీకొన్న",
        # Tamil
        "உயிரிழப்பு", "பலி", "விபத்து", "வெடிவிபத்து", "தீவிபத்து", "கொலை", "கொள்ளை",
        "மோசடி", "கைது", "இடிந்து", "மோதி"
    }

    def should_reject(self, item: EphemeralIngestedItem) -> Tuple[bool, str]:
        """
        Evaluates headline against high-precision negative markers.
        Returns: (should_reject, reason)
        """
        # Unicode-aware tokenization: split on whitespace and strip punctuation
        tokens = {w.strip(".,!?:;\"'()[]{}।॥-–—/\\") for w in item.headline.lower().split()}
        matched = tokens.intersection(self.NEGATIVE_KEYWORDS)

        if matched:
            return True, f"Headline matched negative disaster/crime keywords: {', '.join(sorted(matched))}"

        return False, "Headline passed preliminary filter."
