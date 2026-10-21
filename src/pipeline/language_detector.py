"""
Language Identification & Script Validation Agent
Implements multi-stage validation:
1. Script block Unicode distribution check.
2. FastText subword identification (with safe NumPy 2 compatibility wrapper).
3. Script-specific disambiguation for Devanagari and Eastern Nagri scripts.
"""

import os
from typing import Optional, Tuple
import numpy as np

# Safe patch for fasttext on numpy 2.x
orig_array = np.array
def safe_array(obj, *args, **kwargs):
    if kwargs.get('copy') is False:
        kwargs.pop('copy')
        return np.asarray(obj, *args, **kwargs)
    return orig_array(obj, *args, **kwargs)
np.array = safe_array

import fasttext
from src.schemas.article import EphemeralIngestedItem


class LanguageDetector:
    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            # Look in cache directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            model_path = os.path.join(base_dir, "cache", "lid.176.ftz")

        self.model = None
        if os.path.exists(model_path):
            self.model = fasttext.load_model(model_path)

    def detect_and_validate(self, item: EphemeralIngestedItem) -> Tuple[bool, str, float]:
        """
        Validates whether item matches declared language.
        Returns: (is_match, detected_lang, confidence)
        """
        text = f"{item.headline} {item.raw_body}".strip()
        if not text:
            return False, "unknown", 0.0

        # Script-level Unicode verification
        has_latin = any("\u0041" <= c <= "\u007A" for c in text)
        has_devanagari = any("\u0900" <= c <= "\u097F" for c in text)
        has_bengali_nagri = any("\u0980" <= c <= "\u09FF" for c in text)
        has_arabic = any("\u0600" <= c <= "\u06FF" for c in text)
        has_telugu = any("\u0C00" <= c <= "\u0C7F" for c in text)
        has_tamil = any("\u0B80" <= c <= "\u0BFF" for c in text)
        has_gujarati = any("\u0A80" <= c <= "\u0AFF" for c in text)
        has_kannada = any("\u0C80" <= c <= "\u0CFF" for c in text)
        has_odia = any("\u0B00" <= c <= "\u0B7F" for c in text)
        has_malayalam = any("\u0D00" <= c <= "\u0D7F" for c in text)
        has_gurmukhi = any("\u0A00" <= c <= "\u0A7F" for c in text)

        declared = item.declared_language

        # Quick script compatibility check
        if declared == "en" and not has_latin:
            return False, "non_latin", 0.0
        if declared in {"hi", "mr", "ne", "mai", "gom"} and not has_devanagari:
            return False, "non_devanagari", 0.0
        if declared in {"bn", "as"} and not has_bengali_nagri:
            return False, "non_eastern_nagri", 0.0
        if declared == "ur" and not has_arabic:
            return False, "non_arabic", 0.0
        if declared == "te" and not has_telugu:
            return False, "non_telugu", 0.0
        if declared == "ta" and not has_tamil:
            return False, "non_tamil", 0.0
        if declared == "gu" and not has_gujarati:
            return False, "non_gujarati", 0.0
        if declared == "kn" and not has_kannada:
            return False, "non_kannada", 0.0
        if declared == "or" and not has_odia:
            return False, "non_odia", 0.0
        if declared == "ml" and not has_malayalam:
            return False, "non_malayalam", 0.0
        if declared == "pa" and not has_gurmukhi:
            return False, "non_gurmukhi", 0.0

        # FastText model inference if available
        if self.model:
            labels, probs = self.model.predict(text)
            pred_lang = labels[0].replace("__label__", "")
            confidence = float(probs[0])

            # Disambiguation rules for known shared scripts (FastText lid.176 lacks gom/mai and shares Devanagari/Eastern Nagri):
            if declared == "as" and pred_lang in {"as", "bn"}:
                pred_lang = "as"
                confidence = max(confidence, 0.90)
            elif declared == "mai" and pred_lang in {"hi", "bho", "mai"}:
                pred_lang = "mai"
                confidence = max(confidence, 0.90)
            elif declared == "gom" and pred_lang in {"mr", "hi", "kkn", "gom"}:
                pred_lang = "gom"
                confidence = max(confidence, 0.90)
            elif declared == "ne" and pred_lang in {"ne", "hi"}:
                pred_lang = "ne"
                confidence = max(confidence, 0.90)

            is_match = (pred_lang == declared)
            return is_match, pred_lang, confidence

        # Fallback to script heuristic if fastText model not loaded
        return True, declared, 0.90
