"""
Unit Tests for Article and Pipeline Message Schemas
Verifies:
1. Pydantic validation rejects extra fields (extra='forbid').
2. Raw publisher body text cannot be accidentally stored in Article schema.
3. Positivity metadata strictly enforces score boundaries and SemVer versioning.
4. Summary metadata enforces minimum word counts and prompt versions.
5. Pipeline message envelopes enforce run_id, trace_id, stage, and language.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from src.schemas.article import (
    Article,
    ArticleStatus,
    EphemeralIngestedItem,
    PipelineMessageEnvelope,
    PositivityLabel,
    PositivityMetadata,
    SummaryMetadata,
)


def test_article_schema_valid():
    positivity = PositivityMetadata(
        label=PositivityLabel.POSITIVE,
        score=0.95,
        reason="Breakthrough solar desalination plant completed.",
        rubric_version="1.0.0",
        category="Science/Tech"
    )
    summary = SummaryMetadata(
        text="Scientists built a novel solar-powered desalination membrane providing clean water to 500 households.",
        model="gemini-1.5-flash",
        prompt_version="1.0.0",
        verified=True,
        verifier_model="gemini-2.0-flash",
        verifier_score=0.98,
        word_count=15
    )
    article = Article(
        id="art_12345",
        source_id="the-hindu-national",
        source_name="The Hindu",
        url="https://thehindu.com/sci-tech/article123.ece",
        canonical_url="https://thehindu.com/sci-tech/article123.ece",
        headline="Breakthrough Solar Desalination Plant Opens",
        published_at=datetime.now(timezone.utc),
        language="en",
        positivity=positivity,
        summary=summary,
        status=ArticleStatus.PUBLISHED
    )
    assert article.id == "art_12345"
    assert article.status == ArticleStatus.PUBLISHED
    assert article.summary.verified is True


def test_article_schema_forbids_raw_body():
    """Verifies that raw publisher body text cannot be attached to persistent Article model."""
    positivity = PositivityMetadata(
        label=PositivityLabel.POSITIVE,
        score=0.95,
        reason="Breakthrough outcome.",
        rubric_version="1.0.0"
    )
    with pytest.raises(ValidationError) as exc_info:
        Article(
            id="art_123",
            source_id="the-hindu",
            source_name="The Hindu",
            url="https://thehindu.com/a.html",
            canonical_url="https://thehindu.com/a.html",
            headline="Headline Test",
            published_at=datetime.now(timezone.utc),
            language="en",
            positivity=positivity,
            raw_body="This publisher text should be rejected by schema."  # forbidden
        )
    assert "extra_forbidden" in str(exc_info.value) or "Extra inputs are not permitted" in str(exc_info.value)


def test_positivity_metadata_validation():
    # Test valid
    pos = PositivityMetadata(
        label=PositivityLabel.POSITIVE,
        score=0.90,
        reason="Constructive achievement in clean energy.",
        rubric_version="1.0.0"
    )
    assert pos.score == 0.90

    # Test invalid score > 1.0
    with pytest.raises(ValidationError):
        PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=1.5,
            reason="Invalid score.",
            rubric_version="1.0.0"
        )

    # Test invalid rubric semver
    with pytest.raises(ValidationError):
        PositivityMetadata(
            label=PositivityLabel.POSITIVE,
            score=0.9,
            reason="Invalid version.",
            rubric_version="v1"  # not X.Y.Z
        )


def test_ephemeral_item_lifecycle():
    item = EphemeralIngestedItem(
        id="item_99",
        source_id="bbc-hindi",
        source_name="BBC Hindi",
        url="https://bbc.com/hindi/art.html",
        canonical_url="https://bbc.com/hindi/art.html",
        headline="सौर ऊर्जा परियोजना पूरी हुई",
        raw_body="राजस्थान के मरुस्थलीय जिले में सौर ऊर्जा से संचालित स्वास्थ्य केंद्र...",
        published_at=datetime.now(timezone.utc),
        declared_language="hi"
    )
    assert item.raw_body is not None
    assert item.declared_language == "hi"


def test_pipeline_message_envelope():
    msg = PipelineMessageEnvelope(
        message_id="msg_001",
        run_id="run_20261021_01",
        trace_id="trace_abc123",
        stage="summarizer",
        language="hi",
        payload={"article_id": "art_123", "raw_length": 450},
        model="gemini-1.5-flash",
        prompt_version="1.0.0",
        rubric_version="1.0.0"
    )
    assert msg.run_id == "run_20261021_01"
    assert msg.stage == "summarizer"


def test_category_assignment_validation():
    from src.schemas.article import CategoryAssignment

    # Valid assignment
    cat = CategoryAssignment(
        primary_id=2,
        secondary_ids=[9, 11],
        subcategory_id="scitech_ai_software",
        confidence=0.96,
        taxonomy_version="1.0.0"
    )
    assert cat.primary_id == 2
    assert cat.secondary_ids == [9, 11]
    assert cat.subcategory_id == "scitech_ai_software"

    # Reject more than 2 secondary IDs
    with pytest.raises(ValidationError):
        CategoryAssignment(
            primary_id=2,
            secondary_ids=[1, 3, 5],  # 3 items > max 2
            taxonomy_version="1.0.0"
        )

    # Reject duplicate secondary IDs
    with pytest.raises(ValidationError):
        CategoryAssignment(
            primary_id=2,
            secondary_ids=[9, 9],  # duplicate
            taxonomy_version="1.0.0"
        )

    # Reject invalid ID range
    with pytest.raises(ValidationError):
        CategoryAssignment(
            primary_id=150,  # > 100
            taxonomy_version="1.0.0"
        )


def test_article_with_category_assignment_and_hold_reason():
    from src.schemas.article import CategoryAssignment

    cat = CategoryAssignment(
        primary_id=14,  # Hidden category
        secondary_ids=[],
        confidence=0.95,
        taxonomy_version="1.0.0"
    )
    positivity = PositivityMetadata(
        label=PositivityLabel.POSITIVE,
        score=0.92,
        reason="Administrative digital public service milestone.",
        rubric_version="1.0.0"
    )
    article = Article(
        id="art_held_01",
        source_id="the-hindu",
        source_name="The Hindu",
        url="https://thehindu.com/gov.html",
        canonical_url="https://thehindu.com/gov.html",
        headline="Citizen Services Digital Portal Launched",
        published_at=datetime.now(timezone.utc),
        language="en",
        category=cat,
        positivity=positivity,
        status=ArticleStatus.HELD_HIDDEN_CATEGORY,
        publish_hold_reason="Primary category 14 (Governance & Public Services) is hidden at launch"
    )
    assert article.status == ArticleStatus.HELD_HIDDEN_CATEGORY
    assert article.category.primary_id == 14
    assert "hidden at launch" in article.publish_hold_reason

