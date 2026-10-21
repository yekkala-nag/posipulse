"""
Per-Language Configuration and Source Registry Schemas
Ensures each language operates independently with strict per-language isolation,
quality gates, rubric few-shot exemplars, length bands, models, and cost caps.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LanguageTier(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class LanguageStatus(str, Enum):
    ACTIVE = "active"
    BETA = "beta"
    DISABLED = "disabled"


class SummaryLengthBand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_words: int = Field(..., gt=15, description="Minimum words for a concise story")
    max_words: int = Field(..., le=250, description="Maximum words for a substantive story")
    substance_scaling: bool = Field(
        True, description="Whether length dynamically scales with source informational density"
    )


class QualityGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_positive_precision: float = Field(0.90, ge=0.80, le=1.0)
    min_faithfulness_pass_rate: float = Field(0.95, ge=0.85, le=1.0)
    min_healthy_sources: int = Field(3, ge=1)
    native_speaker_spot_check_passed: bool = Field(False)
    gate_passed_at: Optional[str] = None


class CostCapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cost_per_run_usd: float = Field(..., gt=0.0)
    max_daily_budget_usd: float = Field(..., gt=0.0)
    cost_per_published_item_target_usd: float = Field(..., gt=0.0)
    alert_threshold_percentage: float = Field(80.0, ge=50.0, le=100.0)


class RubricExemplar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    body_snippet: str
    label: str = Field(..., description="positive, negative, toxic_positivity, neutral")
    reason: str
    substance_category: str


class ModelRoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classifier_primary_model: str
    classifier_fallback_model: str
    summarizer_primary_model: str
    summarizer_fallback_model: str
    verifier_model: str
    temperature: float = Field(0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(500, gt=50, le=4096)


class PublisherSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique source slug (e.g. the-hindu-national)")
    name: str = Field(..., description="Display name of publisher")
    feed_url: str = Field(..., description="Public RSS 2.0 or Atom feed URL")
    homepage_url: str = Field(..., description="Publisher homepage for attribution")
    language: str = Field(..., description="ISO language code")
    is_active: bool = Field(True)
    health_status: str = Field("healthy", description="healthy, degraded, failing")
    fetch_interval_minutes: int = Field(30, ge=5, le=1440)
    circuit_breaker_fail_threshold: int = Field(5, ge=1)
    respect_robots_txt: bool = Field(True)


class LanguageConfig(BaseModel):
    """
    Complete configuration profile for a single language queue.
    """
    model_config = ConfigDict(extra="forbid")

    language_code: str = Field(..., min_length=2, max_length=5, description="ISO code (en, hi, mr, te, ur, etc.)")
    language_name_english: str
    language_name_native: str
    script: str = Field(..., description="Script identifier (Devanagari, Eastern Nagri, Telugu, Arabic, etc.)")
    is_rtl: bool = Field(False, description="True for Right-to-Left scripts (Urdu)")
    tier: LanguageTier
    status: LanguageStatus
    quality_gate: QualityGateConfig
    length_band: SummaryLengthBand
    cost_caps: CostCapConfig
    model_routing: ModelRoutingConfig
    positivity_threshold: float = Field(0.85, ge=0.5, le=1.0)
    rubric_version: str = Field("1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    prompt_version: str = Field("1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    exemplars: List[RubricExemplar] = Field(default_factory=list)
    sources: List[PublisherSource] = Field(default_factory=list)
