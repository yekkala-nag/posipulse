"""
Article and Pipeline Data Contracts
Implements the non-negotiable architecture constraints:
- Article schema: id, source_id, url, canonical_url, headline, published_at, fetched_at,
  language, cluster_id, positivity {label, score, reason, rubric_version},
  summary {text, model, prompt_version, verified}, status.
- Zero raw publisher body text in display schema (raw body is ephemeral and not stored).
- Typed, schema-validated message envelopes carrying run_id, trace_id, model,
  prompt_version, and rubric_version.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ArticleStatus(str, Enum):
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    DEDUPLICATED = "deduplicated"
    HEADLINE_REJECTED = "headline_rejected"
    CLASSIFYING = "classifying"
    CLASSIFIED_NEGATIVE = "classified_negative"
    CLASSIFIED_POSITIVE = "classified_positive"
    SUMMARIZING = "summarizing"
    SUMMARIZED = "summarized"
    VERIFYING = "verifying"
    VERIFICATION_FAILED = "verification_failed"
    PUBLISHED = "published"
    DELISTED = "delisted"


class PositivityLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    TOXIC_POSITIVITY = "toxic_positivity"


class PositivityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: PositivityLabel = Field(..., description="Positivity classification label")
    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reason: str = Field(..., min_length=5, description="Constructive journalism rationale for decision")
    rubric_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer of rubric used")
    category: Optional[str] = Field(
        None, description="Constructive category: Science/Tech, Ecology, Empowerment, Resilience, Civic"
    )


class SummaryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=20, max_length=1500, description="Original-wording abstractive summary")
    model: str = Field(..., description="Model identifier that produced the summary")
    prompt_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer of summarization prompt")
    verified: bool = Field(False, description="Whether faithfulness verification passed")
    verifier_model: Optional[str] = Field(None, description="Model identifier that verified faithfulness")
    verifier_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Faithfulness confidence score")
    word_count: int = Field(..., gt=0, description="Word count of summary")


class Article(BaseModel):
    """
    Public and persistent article model.
    Note: Raw publisher body text is NEVER stored in this schema.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique deterministic UUID or hash for article")
    source_id: str = Field(..., description="Unique identifier of registered publisher feed")
    source_name: str = Field(..., description="Human-readable publisher name for display")
    url: str = Field(..., description="Fetched source URL")
    canonical_url: str = Field(..., description="Canonical publisher landing page URL")
    headline: str = Field(..., min_length=5, description="Article headline in native language")
    published_at: datetime = Field(..., description="Original publication timestamp from source feed")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="System fetch timestamp")
    language: str = Field(..., min_length=2, max_length=5, description="ISO language code (e.g. en, hi, te, ur)")
    cluster_id: Optional[str] = Field(None, description="Multilingual semantic cluster ID for deduplication")
    positivity: Optional[PositivityMetadata] = Field(None, description="Positivity classification metadata")
    summary: Optional[SummaryMetadata] = Field(None, description="Original-wording summary and verification state")
    status: ArticleStatus = Field(default=ArticleStatus.FETCHED, description="Current lifecycle state")


class EphemeralIngestedItem(BaseModel):
    """
    Ephemeral in-memory transport model used exclusively during ingestion pipeline.
    Raw body text exists strictly in-memory during processing and is destroyed before persistence.
    """
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    source_name: str
    url: str
    canonical_url: str
    headline: str
    raw_body: str = Field(..., description="Ephemeral body text used for analysis; NEVER stored in persistent DB")
    published_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    declared_language: str
    detected_language: Optional[str] = None
    language_confidence: Optional[float] = None


class PipelineMessageEnvelope(BaseModel):
    """
    Typed envelope exchanged across all pipeline agents.
    Carries run_id, trace_id, model, prompt_version, rubric_version, and timestamps.
    """
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(..., description="Unique message UUID")
    run_id: str = Field(..., description="Pipeline execution run identifier")
    trace_id: str = Field(..., description="Distributed tracing identifier for telemetry")
    stage: str = Field(..., description="Pipeline stage emitting message (e.g. fetcher, classifier, summarizer)")
    language: str = Field(..., description="Language queue code")
    payload: Dict[str, Any] = Field(..., description="Stage-specific data payload")
    model: Optional[str] = Field(None, description="LLM model used in this step if applicable")
    prompt_version: Optional[str] = Field(None, pattern=r"^\d+\.\d+\.\d+$")
    rubric_version: Optional[str] = Field(None, pattern=r"^\d+\.\d+\.\d+$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = Field(None, description="Error message if step failed")
