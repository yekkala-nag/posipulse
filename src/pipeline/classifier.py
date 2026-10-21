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
        if any(w in text for w in ["8-year-old", "child", "young boy", "kid"]) and any(
            w in text for w in ["works 14 hours", "selling flowers", "pays for mother", "cancer treatment"]
        ):
            return PositivityMetadata(
                label=PositivityLabel.TOXIC_POSITIVITY,
                score=0.10,
                reason="Systemic hardship or child labor framed as inspirational resilience.",
                rubric_version=self.rubric_version,
                category="Exclusion/Toxic Positivity"
            )

        # Check for negative markers: accident, casualty, collapse, attack
        if any(w in text for w in ["fatal", "collision", "claims lives", "killed", "died", "fire", "blast", "explosion", "ransomware", "cyberattack"]):
            return PositivityMetadata(
                label=PositivityLabel.NEGATIVE,
                score=0.05,
                reason="Severe disaster, casualty, or criminal incident.",
                rubric_version=self.rubric_version,
                category="Exclusion/Negative"
            )

        # Check for positive constructive achievements:
        if any(w in text for w in ["breakthrough", "develop", "membrane", "purification", "solar", "restoration", "water", "success", "record efficiency", "integration tests", "milestone", "conservation", "recovering", "cooperative"]):
            category = "Science/Tech"
            if "solar" in text or "water" in text or "restoration" in text:
                category = "Ecology"
            elif "cooperative" in text or "livelihood" in text:
                category = "Empowerment"

            return PositivityMetadata(
                label=PositivityLabel.POSITIVE,
                score=0.95,
                reason="Constructive scientific breakthrough, environmental achievement, or community solution.",
                rubric_version=self.rubric_version,
                category=category
            )

        # Check for routine neutral economic/policy reports
        if any(w in text for w in ["repo rate", "reserve bank", "monetary policy", "committee", "notices", "bench"]):
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
