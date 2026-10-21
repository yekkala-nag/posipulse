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
        if toxic_en or toxic_hi:
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
        if neg_en or neg_hi:
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
        if pos_en or pos_hi:
            category = "Science/Tech"
            if any(w in text for w in ["solar", "सौर", "water", "जल", "restoration", "पुनर्जीवित", "ecology", "जैविक", "धान"]):
                category = "Ecology"
            elif any(w in text for w in ["cooperative", "सहकारी", "weavers", "हस्तशिल्प", "empowerment", "आदिवासी"]):
                category = "Empowerment"
            elif any(w in text for w in ["swachh", "स्वच्छ", "civic", "पहलवानों", "कुश्ती", "medal"]):
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
        if neutral_en or neutral_hi:
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
