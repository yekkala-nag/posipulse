"""
Regression tests for Language Identification & Script Validation.
Verifies:
1. Multiline descriptions with newlines ('\\n') do not crash fastText with ValueError.
2. Real sampled Maithili items with embedded HTML and newlines pass detection.
3. Robustness against whitespace, carriage returns ('\\r'), and multiline feeds.
"""

from datetime import datetime, timezone
import pytest
from src.pipeline.language_detector import LanguageDetector
from src.schemas.article import EphemeralIngestedItem


def test_language_detector_multiline_newline_does_not_crash():
    """
    Regression Test:
    FastText model.predict() raises:
    ValueError: predict processes one line at a time (remove '\n')
    when input contains newlines.
    The detector must sanitize text so multiline feed items do not crash.
    """
    detector = LanguageDetector()

    # Raw item from Maithili feed containing newlines
    multiline_item = EphemeralIngestedItem(
        id="test-mai-multiline",
        source_id="mithila-mirror",
        source_name="Mithila Mirror",
        url="https://mithilamirror.com/article-multiline",
        canonical_url="https://mithilamirror.com/article-multiline",
        headline="प्रो. अशोक कुमार मेहता सम्हारलनि पदभार",
        raw_body="<p>दरभंगा, मिथिला मिरर : ललित नारायण मिथिला विश्वविद्यालय\n\n<p>डॉ. मेहता कहलनि जे मैथिली विभागक विकास लेल प्रतिबद्ध छी।</p>\n",
        published_at=datetime.now(timezone.utc),
        declared_language="mai"
    )

    # This MUST NOT raise ValueError: predict processes one line at a time
    is_match, pred_lang, confidence = detector.detect_and_validate(multiline_item)
    assert is_match is True
    assert pred_lang == "mai"
    assert confidence >= 0.70


def test_language_detector_handles_carriage_returns_and_tabs():
    """Verify tabs, carriage returns and odd whitespace are safely sanitized."""
    detector = LanguageDetector()

    item = EphemeralIngestedItem(
        id="test-hi-whitespace",
        source_id="amar-ujala",
        source_name="Amar Ujala",
        url="https://amarujala.com/test",
        canonical_url="https://amarujala.com/test",
        headline="सौर ऊर्जा संयंत्र से\r\nगाँव को मिली\tबिजली",
        raw_body="राजस्थान के बाड़मेर जिले में\r\nग्रामीणों ने मिलकर\nसोलर पैनल स्थापित किए।\r\n",
        published_at=datetime.now(timezone.utc),
        declared_language="hi"
    )

    is_match, pred_lang, confidence = detector.detect_and_validate(item)
    assert is_match is True
    assert pred_lang == "hi"
