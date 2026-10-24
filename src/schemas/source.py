"""
Centralized Publisher Source Profile Schemas
Defines core data contracts for publisher identities, rights modes, excerpt ceilings,
verification state, UTM opt-in, takedown enforcement, and audit trails.
"""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RightsMode(str, Enum):
    """
    Copyright and display rights granted by publisher.
    - HEADLINE_ONLY: Only the headline and canonical link are displayed. Zero excerpt text.
    - FEED_PROVIDED_EXCERPT: Verbatim excerpt extracted from feed description, subject to source ceiling.
    - LONGER_EXCERPT: Expanded verbatim excerpt permitted under explicit signed publisher agreement.
    """
    HEADLINE_ONLY = "headline_only"
    FEED_PROVIDED_EXCERPT = "feed_provided_excerpt"
    LONGER_EXCERPT = "longer_excerpt"


class VerificationStatus(str, Enum):
    """Publisher identity and domain verification status."""
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REVOKED = "revoked"


class TermsReviewStatus(str, Enum):
    """Publisher terms of service compliance review status."""
    PENDING = "pending"
    REVIEWED_ACCEPTED = "reviewed_accepted"
    CUSTOM_LICENSE = "custom_license"
    OPTED_OUT = "opted_out"


class TrustTier(str, Enum):
    """Publisher credibility and scale tier."""
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    COMMUNITY = "community"


class TakedownStatus(str, Enum):
    """Operational takedown lifecycle state."""
    ACTIVE = "active"
    TAKEDOWN_REQUESTED = "takedown_requested"
    TAKEDOWN_ENFORCED = "takedown_enforced"


class SourceProfileAuditEntry(BaseModel):
    """Audit entry documenting an administrative, verification, or takedown change."""
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = Field(..., description="Action name (e.g. created, verified, takedown_enforced)")
    actor: str = Field(..., description="Entity triggering change (system, admin_email, publisher)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metadata diff or rationale")


class SourceProfile(BaseModel):
    """
    Central publisher source profile record.
    Governs publisher attribution, excerpt ceilings, domain verification, and rights modes.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=3, max_length=100, description="Unique source slug (e.g. the-hindu-national)")
    publisher_id: str = Field(..., min_length=3, max_length=100, description="Publishing organization ID (e.g. the-hindu-group)")
    publisher_name: str = Field(..., min_length=2, max_length=200, description="Display name of publisher")
    primary_domain: str = Field(..., description="Normalized domain name (e.g. thehindu.com)")
    feed_urls: List[str] = Field(..., min_length=1, description="RSS/Atom endpoints")
    homepage_url: str = Field(..., description="Publisher homepage for attribution link-out")
    language: str = Field(..., min_length=2, max_length=5, description="ISO language code (e.g. en, hi, ta)")
    rights_mode: RightsMode = Field(default=RightsMode.HEADLINE_ONLY, description="Publisher excerpt rights mode")
    excerpt_ceiling_chars: int = Field(default=400, ge=100, le=2500, description="Max excerpt length in characters")
    excerpt_ceiling_words: int = Field(default=60, ge=15, le=400, description="Max excerpt length in words")
    utm_opt_in: bool = Field(default=False, description="Whether to append UTM attribution parameters (default OFF)")
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)
    verified_at: Optional[datetime] = Field(None, description="Timestamp of domain verification")
    terms_review_status: TermsReviewStatus = Field(default=TermsReviewStatus.PENDING)
    trust_tier: TrustTier = Field(default=TrustTier.TIER_2)
    takedown_status: TakedownStatus = Field(default=TakedownStatus.ACTIVE)
    takedown_requested_at: Optional[datetime] = None
    contact_email: Optional[EmailStr] = None
    contact_name: Optional[str] = Field(None, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_history: List[SourceProfileAuditEntry] = Field(default_factory=list)

    @field_validator("primary_domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        domain = v.strip().lower()
        if "://" in domain:
            domain = urlparse(domain).netloc
        domain = re.sub(r"^www\.", "", domain)
        if not domain or "." not in domain:
            raise ValueError(f"Invalid primary domain format: '{v}'")
        return domain

    def is_eligible_for_publishing(self) -> bool:
        """Determines if stories from this source can be actively published."""
        if self.takedown_status != TakedownStatus.ACTIVE:
            return False
        if self.terms_review_status == TermsReviewStatus.OPTED_OUT:
            return False
        return True

    def truncate_excerpt(self, raw_excerpt: Optional[str]) -> Optional[str]:
        """
        Enforces rights mode and excerpt ceilings on verbatim text.
        Returns:
            None if rights_mode is HEADLINE_ONLY.
            Bounded verbatim excerpt if rights_mode permits.
        """
        if self.rights_mode == RightsMode.HEADLINE_ONLY or not raw_excerpt:
            return None

        text = raw_excerpt.strip()
        if not text:
            return None

        # 1. Enforce character ceiling
        if len(text) > self.excerpt_ceiling_chars:
            text = text[:self.excerpt_ceiling_chars].rsplit(" ", 1)[0] + "..."

        # 2. Enforce word ceiling
        words = text.split()
        if len(words) > self.excerpt_ceiling_words:
            text = " ".join(words[:self.excerpt_ceiling_words]) + "..."

        return text
