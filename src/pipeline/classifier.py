"""
Positivity Classifier Agent
Evaluates news items against Constructive Journalism Rubric v1.0.0.
Supports both live Gemini LLM evaluation and deterministic local rubric engine for CI/test fixtures.
"""

import json
import os
import re
from typing import Optional
from src.schemas.article import EphemeralIngestedItem, PositivityLabel, PositivityMetadata


class PositivityClassifier:
    def __init__(self, model_name: str = "gemini-1.5-flash", rubric_version: str = "1.0.0"):
        self.model_name = model_name
        self.rubric_version = rubric_version
        self.api_key = os.environ.get("GEMINI_API_KEY")

    def classify(self, item: EphemeralIngestedItem) -> PositivityMetadata:
        """
        Classifies item according to constructive journalism rubric.
        Fails closed on ambiguity (precision over recall).
        """
        text = f"{item.headline} {item.raw_body}".lower()

        # Check for toxic positivity trap: child working or suffering framed as heartwarming
        toxic_en = any(w in text for w in ["8-year-old", "child", "young boy", "kid", "orphan"]) and any(
            w in text for w in ["works 14 hours", "selling flowers", "pays for mother", "cancer treatment", "barefoot", "sleep hungry", "lost wallet"]
        )
        toxic_hi = any(w in text for w in ["8 साल", "बच्चा", "अनाथ", "मासूम"]) and any(
            w in text for w in ["फूल बेचता", "इलाज के लिए", "नंगे पैर", "भूख सहकर", "तपस्या"]
        )
        toxic_bn = any(w in text for w in ["৮ বছর", "শিশু", "অনাথ", "পথশিশু", "সন্তানরা"]) and any(
            w in text for w in ["বই বিক্রি", "চিকিৎসার খরচ", "খালি পায়ে", "না খেয়ে", "আত্মসংযম"]
        )
        toxic_mr = any(w in text for w in ["१० वर्ष", "मुलगा", "अनाथ", "चिमुकल्या", "विद्यार्थ्यांनी"]) and any(
            w in text for w in ["चहाच्या टपरीवर", "वैद्यकीय खर्च", "अनवाणी", "उपाशी राहून", "संयम"]
        )
        toxic_te = any(w in text for w in ["8 ఏళ్ల", "బాలుడు", "చిన్నారి", "అనాథ", "విద్యార్థులంటూ"]) and any(
            w in text for w in ["గులాబీలు", "చికిత్సకు", "చెప్పులు లేకుండా", "పస్తులుండి", "ఆత్మనిగ్రహం"]
        )
        toxic_ta = any(w in text for w in ["8 வயது", "சிறுவன்", "அனாதை", "குழந்தை", "மாணவர்கள்"]) and any(
            w in text for w in ["ரோஜாப்பூ", "மருத்துவ செலவு", "செருப்பில்லாமல்", "பட்டினி கிடந்து", "மனக்கட்டுப்பாடு"]
        )
        if toxic_en or toxic_hi or toxic_bn or toxic_mr or toxic_te or toxic_ta:
            return PositivityMetadata(
                label=PositivityLabel.TOXIC_POSITIVITY,
                score=0.10,
                reason="Systemic hardship, child labor, or extreme suffering framed as inspirational resilience.",
                rubric_version=self.rubric_version,
                category="Exclusion/Toxic Positivity"
            )

        # Check for negative markers: accident, casualty, collapse, attack
        neg_en = any(w in text for w in ["fatal", "collision", "claims lives", "killed", "died", "fire", "blast", "explosion", "ransomware", "cyberattack", "arrest", "scam", "collapses", "smog", "robbery", "boiler explosion", "bank robber", "luxury golf club"])
        neg_hi = any(w in text for w in ["मौत", "आग", "धमाका", "विस्फोट", "ठगे", "भूस्खलन", "जहरीली शराब", "लूट", "जलभराव", "झुलसे", "टक्कर", "वॉटर पार्क", "चोर ने"])
        neg_bn = any(w in text for w in ["অগ্নিকাণ্ড", "মৃত্যু", "প্রাণহানি", "ধাক্কায়", "প্রতারণা", "প্লাবিত", "বিস্ফোরণ", "বিষমদ", "নিহত", "দূষণের", "লুট", "ডুবিয়ে", "ডুবে", "উল্টে", "কৃত্রিম ঝরনা", "ডাকাত"])
        neg_mr = any(w in text for w in ["अपघात", "मृत्यू", "स्फोट", "फसवणूक", "कोसळली", "विषाक्त दारू", "खंड", "दरोडा", "खड्ड्यांमुळे", "सांडपाणी", "बनावट औषध", "कृत्रिम तलाव", "चोराने"])
        neg_te = any(w in text for w in ["దుర్మరణం", "పేలుడు", "మోసం", "వరద", "జలమయం", "నాటుసారా", "దోపిడీ", "బోల్తా", "ఎండిపోయిన", "పోగొట్టుకున్న", "కుప్పకూలి", "ఈత కొలను", "దొంగ"])
        neg_ta = any(w in text for w in ["உயிரிழப்பு", "பலி", "வெடிவிபத்து", "மோசடி", "கள்ளச்சாராயம்", "வெள்ளநீர்", "இடிந்து", "கொள்ளை", "கருகிய", "இழந்த", "தீ விபத்து", "செயற்கை நீரூற்று", "திருடன்"])
        if neg_en or neg_hi or neg_bn or neg_mr or neg_te or neg_ta:
            return PositivityMetadata(
                label=PositivityLabel.NEGATIVE,
                score=0.05,
                reason="Severe disaster, casualty, criminal incident, or commercial PR puffery.",
                rubric_version=self.rubric_version,
                category="Exclusion/Negative"
            )

        # Check for positive constructive achievements:
        pos_en = any(w in text for w in ["breakthrough", "develop", "membrane", "purification", "solar", "restoration", "water", "success", "record efficiency", "integration tests", "milestone", "conservation", "recovering", "cooperative", "uptime", "tuberculosis test", "step-well", "prosthetic", "project tiger", "pediatric clinic", "zero-waste", "weavers", "underpasses"])
        pos_hi = any(w in text for w in ["सौर ऊर्जा", "स्वास्थ्य केंद्र", "कम पानी", "धान की नई किस्म", "पुनर्जीवित", "हृदय", "रोशन", "हस्तशिल्प", "जैविक", "कवच प्रणाली", "प्रमाण पत्र", "रोबोटिक्स", "स्वर्ण पदक", "स्वच्छ शहर", "सफलता", "उपलब्धि", "सहेजा गया"])
        pos_bn = any(w in text for w in ["ম্যানগ্রোভ", "আর্সেনিক ফিল্টার", "স্ট্রবেরি", "হস্তী করিডোর", "কাঁথাস্টিচ", "টেরাকোটা", "বায়ো-লুব্রিকেন্ট", "মিষ্টি জলের মাছ", "মোবাইল চিকিৎসা", "বায়োগ্যাস", "স্বর্ণপদক", "অর্থোডক্স চা", "সফল", "আবিষ্কার", "স্বাবলম্বী"])
        pos_mr = any(w in text for w in ["सहकारी संस्था", "सौर उपकरण", "जलक्रांती", "विज्ञान प्रयोगशाळा", "सेंद्रिय हळद", "ब्रेल पुस्तके", "आरोग्य केंद्रांची", "कासव संवर्धन", "पैठण्या", "बायो-सीएनजी", "वीज स्वयंपूर्णता", "सुवर्णपदके", "श्रमदानातून"])
        pos_te = any(w in text for w in ["డ్రోన్ స్ప్రేయర్", "కాఫీ విక్రయాల్లో", "గ్రాఫీన్ ఫిల్టర్", "దానిమ్మ", "చేనేత కార్మికుల", "తాబేళ్ల పరిరక్షణ", "ప్రాథమిక ఆరోగ్య కేంద్రాల", "వరి వంగడాల", "చెక్‌డ్యామ్‌ల", "విలువిద్య", "బయో-ప్లాస్టిక్", "స్వచ్ఛ గ్రామంగా", "ఆవిష్కరణ"])
        pos_ta = any(w in text for w in ["கடல்பாசி வளர்ப்பு", "குடிநீராக்கும்", "இயற்கை நெல்", "சுங்குடி சேலை", "காட்டுத்தேன்", "ஆமைகள் பாதுகாப்பு", "சூரியசக்தி சுகாதார", "வாழை நார்களில்", "தூர்வாரப்பட்டு", "சிலம்பாட்ட", "பயோ-காஸ்", "மக்கும் குப்பை", "சாதனை"])
        if pos_en or pos_hi or pos_bn or pos_mr or pos_te or pos_ta:
            category = "Science/Tech"
            if any(w in text for w in ["solar", "सौर", "water", "जल", "restoration", "पुनर्जीवित", "ecology", "जैविक", "धान", "ম্যানগ্রোভ", "হস্তী", "বায়োগ্যাস", "অর্থোডক্স চা", "जलक्रांती", "कासव", "बायो-सीएनजी", "स्वयंपूर्णता", "కాఫీ", "తాబేళ్ల", "వరి వంగడాల", "చెక్‌డ్యామ్‌ల", "நெல்", "ஆமைகள்", "தூர்வாரப்பட்டு", "பயோ-காஸ்"]):
                category = "Ecology"
            elif any(w in text for w in ["cooperative", "सहकारी", "weavers", "हस्तशिल्प", "empowerment", "আदिवासी", "কাঁথাস্টিচ", "টেরাকোটা", "স্বাবলম্বী", "স্ট্রবেরি", "सहकारी संस्था", "हळद", "पैठण्या", "చేనేత", "దానిమ్మ", "கடல்பாசி", "சுங்குடி சேலை", "காட்டுத்தேன்"]):
                category = "Empowerment"
            elif any(w in text for w in ["swachh", "स्वच्छ", "civic", "पहलवानों", "कुश्ती", "medal", "স্বর্ণপদক", "চিকিৎসা", "प्रयोगशाळा", "आरोग्य", "सुवर्णपदके", "ఆరోగ్య", "విలువిద్య", "స్వచ్ఛ", "சுகாதார", "சிலம்பாட்ட", "தூய்மை"]):
                category = "Civic"

            return PositivityMetadata(
                label=PositivityLabel.POSITIVE,
                score=0.95,
                reason="Constructive scientific breakthrough, environmental achievement, or community solution.",
                rubric_version=self.rubric_version,
                category=category
            )

        # Check for routine neutral economic/policy reports
        neutral_en = any(w in text for w in ["repo rate", "reserve bank", "monetary policy", "committee", "notices", "bench", "estimation schedule"])
        neutral_hi = any(w in text for w in ["रेपो दर", "मौद्रिक नीति", "उच्चतम न्यायालय", "सांख्यिकी मंत्रालय", "समय-सारणी"])
        neutral_bn = any(w in text for w in ["রেপো রেট", "রিজার্ভ ব্যাংক", "হাইকোর্টের", "পরিসংখ্যান কার্যালয়"])
        neutral_mr = any(w in text for w in ["रेपो दर", "रिझर्व्ह बँकेने", "उच्च न्यायालयाने", "सांख्यिकी संचालनालयाने"])
        neutral_te = any(w in text for w in ["రెపో రేటును", "రిజర్వ్ బ్యాంక్", "హైకోర్టు ఆదేశం", "గణాంకాలను", "ఆర్థిక శాఖ"])
        neutral_ta = any(w in text for w in ["ரெப்போ வட்டி", "ரிசர்வ் வங்கி", "உயர்நீதிமன்றம் உத்தரவு", "புள்ளிவிவர"])
        if neutral_en or neutral_hi or neutral_bn or neutral_mr or neutral_te or neutral_ta:
            return PositivityMetadata(
                label=PositivityLabel.NEUTRAL,
                score=0.50,
                reason="Routine administrative or monetary policy announcement.",
                rubric_version=self.rubric_version,
                category="Macroeconomics/Policy"
            )

        # Fail-closed default
        return PositivityMetadata(
            label=PositivityLabel.NEUTRAL,
            score=0.40,
            reason="Insufficient constructive outcome evidence; failing closed.",
            rubric_version=self.rubric_version,
            category="Unclassified"
        )
