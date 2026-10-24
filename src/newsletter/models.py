"""
Data Models and Enums for Per-Language Newsletters (Taxonomy v1 & DPDP Act 2023).
Defines subscription lifecycle, double opt-in confirmation contracts,
and compiled weekly digest issue models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.schemas.source import RightsMode


class SubscriptionStatus(str, Enum):
    """Lifecycle state of an email newsletter subscriber."""
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"


class NewsletterSubscription(BaseModel):
    """
    Reader newsletter subscription record.
    Complies with DPDP Act 2023 with cryptographic double opt-in tokens,
    per-language isolation, and explicit consent timestamps.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique subscription ID, e.g. sub-...")
    email: EmailStr = Field(..., description="Subscriber email address")
    language: str = Field(..., description="ISO 639-1/3 language code")
    status: SubscriptionStatus = Field(
        default=SubscriptionStatus.PENDING_CONFIRMATION,
        description="Current subscription status"
    )
    confirmation_token: str = Field(..., description="Cryptographically random token for double opt-in")
    unsubscribe_token: str = Field(..., description="Permanent random token for one-click unsubscribe")
    requested_at: datetime = Field(..., description="Timestamp of initial signup request")
    confirmed_at: Optional[datetime] = Field(None, description="Timestamp of double opt-in confirmation")
    unsubscribed_at: Optional[datetime] = Field(None, description="Timestamp of unsubscription")
    created_at: datetime = Field(..., description="Row creation timestamp")
    updated_at: datetime = Field(..., description="Row update timestamp")


class SubscribeRequest(BaseModel):
    """User-submitted signup request for a language-specific constructive newsletter."""
    email: EmailStr = Field(..., description="Valid subscriber email address")
    language: str = Field(default="en", min_length=2, max_length=5, description="ISO language code")


class DigestItem(BaseModel):
    """
    An individual constructive story item rendered in a newsletter digest issue.
    Strictly preserves publisher attribution and syndication rights modes:
    - Never summarizes or translates publisher text in public views.
    - Honors verbatim excerpt ceilings where terms allow.
    - Prominent direct link to the publisher's original article.
    """
    model_config = ConfigDict(extra="forbid")

    article_id: str
    headline: str
    publisher_name: str
    primary_domain: Optional[str] = None
    direct_url: str
    category_id: Optional[int] = None
    category_name: str
    category_icon: str
    rights_mode: RightsMode
    verbatim_excerpt: Optional[str] = None
    published_at: datetime
    is_rtl: bool = False


class NewsletterIssue(BaseModel):
    """Compiled weekly constructive digest issue for a specific language."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique issue identifier, e.g. issue-en-2026-w43")
    language: str = Field(..., description="ISO language code")
    subject: str = Field(..., description="Newsletter email subject line")
    issue_date: str = Field(..., description="Publication date or ISO week (e.g. 2026-W43)")
    article_ids: List[str] = Field(default_factory=list, description="IDs of articles in digest")
    html_content: str = Field(..., description="Full responsive HTML email content")
    text_content: str = Field(..., description="Full accessible plain-text email content")
    sent_at: Optional[datetime] = Field(None, description="Timestamp when issue was dispatched")
    recipient_count: int = Field(default=0, ge=0, description="Number of recipients dispatched to")
    created_at: datetime = Field(..., description="Creation timestamp")
