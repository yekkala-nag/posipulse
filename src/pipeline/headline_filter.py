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
        "doping", "match-fixing", "divorce", "affair", "scandal", "defamation", "paparazzi",
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
        "மோசடி", "கைது", "இடிந்து", "மோதி",
        # Urdu (Perso-Arabic)
        "جاں بحق", "ہلاکت", "حادثہ", "دھماکہ", "لوٹ", "گرفتار", "ڈکیتی", "زمین بوس", "موت", "تصادم", "پھٹنے",
        # Gujarati
        "મોત", "અકસ્માત", "આગ", "લૂંટ", "ધરાશાયી", "ઝડપાઈ", "ભડથું", "ચોરી", "છેતરપિંડી", "ગમખ્વાર",
        # Kannada
        "ಸಾವು", "ಅಪಘಾತ", "ಸ್ಫೋಟ", "ದರೋಡೆ", "ಕುಸಿತ", "ಬಂಧನ", "ದುರ್ಮರಣ", "ಬೆಂಕಿ", "ವಂಚಿಸಿದ", "ಡಿಕ್ಕಿ",
        # Odia
        "ମୃତ", "ମୃତ୍ୟୁ", "ଦୁର୍ଘଟଣା", "ବିସ୍ଫୋରଣ", "ଲୁଟ", "ଭୁଶୁଡ଼ି", "ଗିରଫ", "ଅଗ୍ନିକାଣ୍ଡ", "ଓଲଟି", "ଠକେଇ",
        # Malayalam
        "മരിച്ചു", "അപകടം", "തീപിടുത്തം", "കവർന്നു", "തകർന്നു", "അറസ്റ്റിൽ", "കൂട്ടിയിടിച്ച്", "ദുരന്തം", "തട്ടിപ്പ്", "മരണം",
        # Punjabi (Gurmukhi)
        "ਮੌਤ", "ਹਾਦਸਾ", "ਧਮਾਕਾ", "ਲੁੱਟੇ", "ਡਿੱਗੀ", "ਗ੍ਰਿਫ਼ਤਾਰ", "ਅੱਗ", "ਟੱਕਰ", "ਠੱਗੀ", "ਦੱਬਣ",
        # Assamese (Eastern Nagri)
        "মৃত্যু", "দুৰ্ঘটনা", "বিস্ফোৰণ", "হত্যা", "লুট", "ডকাইতি", "গ্ৰেপ্তাৰ", "অগ্নিকাণ্ড", "খহনীয়া", "ধ্বংস",
        # Nepali (Devanagari)
        "मृत्यु", "दुर्घटना", "विस्फोट", "हत्या", "लुटपाट", "पहिरो", "पक्राउ", "आगलागी", "ठगी", "डुबान",
        # Maithili (Devanagari)
        "मृत्यु", "दुर्घटना", "विस्फोट", "हत्या", "लूटपाट", "गिरफ्तार", "आगि", "ठगी", "धसि", "विनाश",
        # Konkani (Devanagari)
        "मरण", "अपघात", "स्फोट", "खून", "लूट", "अटक", "लागिल्ली", "फटोवणी", "कोसळप", "उडप"
    }

    def should_reject(self, item: EphemeralIngestedItem) -> Tuple[bool, str]:
        """
        Evaluates headline against high-precision negative markers.
        Returns: (should_reject, reason)
        """
        headline_lower = item.headline.lower()

        # Check multi-word phrase keywords
        for kw in self.NEGATIVE_KEYWORDS:
            if " " in kw and kw in headline_lower:
                return True, f"Headline matched negative disaster/crime keywords: {kw}"

        # Unicode-aware tokenization: split on whitespace and strip Indic & Perso-Arabic punctuation
        punctuation_chars = ".,!?:;\"'()[]{}।॥،؛؟۔-–—/\\"
        tokens = {w.strip(punctuation_chars) for w in headline_lower.split()}
        matched = tokens.intersection(self.NEGATIVE_KEYWORDS)

        if matched:
            return True, f"Headline matched negative disaster/crime keywords: {', '.join(sorted(matched))}"

        return False, "Headline passed preliminary filter."
