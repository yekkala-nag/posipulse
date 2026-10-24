"""
Category Taxonomy Data Models and Contracts (Taxonomy v1)

Defines versioned models for categories, subcategories, special rules,
and IPTC Media Topics 2024.1 crosswalk mappings.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryVisibility(str, Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class PositiveFitRating(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SpecialRuleFlags(BaseModel):
    """
    Domain-specific gatekeeper rules applied during classification.
    - Economy: promotional content and PR puffery check
    - Health: corroboration required for medical/efficacy claims
    - Entertainment: gossip, scandals, and paparazzi excluded
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    promotional_content_check: bool = Field(
        default=False,
        description="Enforces strict PR/commercial puffery filter on business news"
    )
    corroboration_required: bool = Field(
        default=False,
        description="Requires verified institutional or peer-reviewed corroboration for medical claims"
    )
    gossip_excluded: bool = Field(
        default=False,
        description="Excludes tabloid gossip, celebrity feuds, divorces, and paparazzi reports"
    )


class IPTCReference(BaseModel):
    """
    Crosswalk mapping to IPTC Media Topics standard (Release 2024.1).
    Standard URI: http://cv.iptc.org/newscodes/mediatopic/
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    qcode: str = Field(..., description="IPTC concept QCode, e.g., medtop:20000210")
    uri: str = Field(..., description="Canonical IPTC URI")
    name_en: str = Field(..., description="Official IPTC English concept name")
    standard_version: str = Field(default="2024.1", description="IPTC Media Topics release version")


class Subcategory(BaseModel):
    """
    Subcategory (field) within a category.
    IDs are permanent and globally unique across the taxonomy.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., pattern=r"^[a-z0-9_]+$", description="Globally unique permanent subcategory ID")
    slug: str = Field(..., pattern=r"^[a-z0-9\-]+$", description="URL-safe slug")
    name_en: str = Field(..., min_length=2, description="English display name")
    description: str = Field(..., description="Scope of coverage")
    iptc_reference: Optional[IPTCReference] = None


class Category(BaseModel):
    """
    Top-level Category model.
    Permanent integer ID (1-18) reserved and never reused.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(..., ge=1, le=100, description="Permanent stable integer ID, never reused")
    slug: str = Field(..., pattern=r"^[a-z0-9\-]+$", description="URL-safe slug")
    visibility: CategoryVisibility = Field(..., description="'visible' at launch or 'hidden'")
    positive_fit: PositiveFitRating = Field(..., description="Constructive journalism alignment: high, medium, low")
    special_rules: SpecialRuleFlags = Field(default_factory=SpecialRuleFlags)
    iptc_reference: IPTCReference
    display_names: Dict[str, str] = Field(
        ...,
        description="Localized display names per ISO language code (placeholders until native review)"
    )
    subcategories: List[Subcategory] = Field(..., min_length=1, description="List of subcategories")

    @field_validator("display_names")
    @classmethod
    def validate_english_name(cls, v: Dict[str, str]) -> Dict[str, str]:
        if "en" not in v or not v["en"].strip():
            raise ValueError("Category must have a non-empty English ('en') display name.")
        return v

    def get_display_name(self, language: str = "en") -> str:
        return self.display_names.get(language, self.display_names.get("en", self.slug))

    @property
    def name_en(self) -> str:
        return self.display_names.get("en", self.slug)

    @property
    def is_visible(self) -> bool:
        return self.visibility == CategoryVisibility.VISIBLE


class TaxonomyVersion(BaseModel):
    """
    Immutable versioned taxonomy manifest.
    Any alteration to categories or subcategories requires a SemVer bump.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer version of taxonomy")
    effective_date: str = Field(..., description="ISO 8601 date when version became effective")
    description: str = Field(..., description="Release notes for this taxonomy version")
    checksum: str = Field(..., description="SHA-256 fingerprint of category definitions for tamper detection")
    categories: List[Category] = Field(..., min_length=18, description="All registered categories (visible and hidden)")
