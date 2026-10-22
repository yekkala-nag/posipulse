"""
Sports & Entertainment Pipeline and Classification Tests
Verifies:
1. Constructive athletic triumphs and youth sports development classify into category='Sports'.
2. Doping, match-fixing, and sports scandals are flagged and filtered out.
3. Constructive cultural milestones, heritage restoration, and arts awards classify into category='Entertainment'.
4. Paparazzi gossip, divorce scandals, and celebrity feuds are rejected.
5. API feed endpoints support category filtering for Sports and Entertainment.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.loader import LanguageConfigRegistry
from src.pipeline.classifier import PositivityClassifier
from src.pipeline.headline_filter import HeadlinePreFilter
from src.schemas.article import EphemeralIngestedItem, PositivityLabel
from src.storage.db import StorageEngine


@pytest.fixture
def classifier():
    return PositivityClassifier(rubric_version="1.0.0")


@pytest.fixture
def headline_filter():
    return HeadlinePreFilter()


def test_sports_constructive_classification(classifier):
    """Test positive sports achievement classifies into Sports category."""
    item = EphemeralIngestedItem(
        id="sport_01",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/sport/olympic-gold.ece",
        canonical_url="https://thehindu.com/sport/olympic-gold.ece",
        headline="Young Archer Secures Historic Gold Medal in World Championship",
        raw_body="In an inspiring performance, the 19-year-old athlete secured a historic gold medal at the world championship tournament, demonstrating exceptional sportsmanship and dedication.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )
    meta = classifier.classify(item)
    assert meta.label == PositivityLabel.POSITIVE
    assert meta.category == "Sports"
    assert "athletic achievement" in meta.reason.lower() or "sports" in meta.reason.lower()


def test_sports_scandal_rejection(classifier, headline_filter):
    """Test sports scandal with doping or match-fixing is rejected."""
    headline = "Top Athlete Suspended Following Match-Fixing and Doping Investigation"
    item = EphemeralIngestedItem(
        id="sport_scandal_01",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/sport/doping.ece",
        canonical_url="https://thehindu.com/sport/doping.ece",
        headline=headline,
        raw_body="The athlete faces disciplinary action after testing positive in doping tests.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )
    should_reject, reason = headline_filter.should_reject(item)
    assert should_reject is True
    assert "doping" in reason.lower() or "match-fixing" in reason.lower()

    meta = classifier.classify(item)
    assert meta.label == PositivityLabel.NEGATIVE


def test_entertainment_constructive_classification(classifier):
    """Test constructive arts preservation and cultural milestone classifies into Entertainment."""
    item = EphemeralIngestedItem(
        id="ent_01",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/entertainment/film-restoration.ece",
        canonical_url="https://thehindu.com/entertainment/film-restoration.ece",
        headline="Heritage Film Restoration Project Rescues Rare 1950s Cinematic Classics",
        raw_body="The national film archive successfully completed the heritage film restoration of fifty classic regional reels, earning national film award honors for cultural preservation.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )
    meta = classifier.classify(item)
    assert meta.label == PositivityLabel.POSITIVE
    assert meta.category == "Entertainment"
    assert "cultural milestone" in meta.reason.lower() or "artistic" in meta.reason.lower()


def test_entertainment_gossip_rejection(classifier, headline_filter):
    """Test celebrity gossip, scandal, and defamation are rejected."""
    headline = "Celebrity Couple Announces Messy Divorce Amid Defamation Scandal and Paparazzi Feud"
    item = EphemeralIngestedItem(
        id="ent_gossip_01",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/ent/divorce.ece",
        canonical_url="https://thehindu.com/ent/divorce.ece",
        headline=headline,
        raw_body="Heated allegations of an affair and defamation exchanged between the parties.",
        published_at=datetime.now(timezone.utc),
        declared_language="en"
    )
    should_reject, reason = headline_filter.should_reject(item)
    assert should_reject is True
    assert any(w in reason.lower() for w in ["divorce", "defamation", "scandal", "paparazzi"])

    meta = classifier.classify(item)
    assert meta.label == PositivityLabel.NEGATIVE


def test_api_feed_category_filtering():
    """Test API feed supports Sports and Entertainment category query params."""
    storage = StorageEngine(":memory:")
    registry = LanguageConfigRegistry()
    app = create_app(storage=storage, registry=registry)
    client = TestClient(app)

    # Query with category=Sports
    res_sports = client.get("/v1/feed?language=en&category=Sports")
    assert res_sports.status_code == 200
    assert "articles" in res_sports.json()

    # Query with category=Entertainment
    res_ent = client.get("/v1/feed?language=en&category=Entertainment")
    assert res_ent.status_code == 200
    assert "articles" in res_ent.json()
