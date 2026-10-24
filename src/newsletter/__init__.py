"""
PosiPulse Per-Language Newsletters Package.
"""

from src.newsletter.builder import NewsletterDigestBuilder
from src.newsletter.esp import (
    EmailMessage,
    EmailServiceProvider,
    MockEmailProvider,
    SESEmailProvider,
)
from src.newsletter.models import (
    DigestItem,
    NewsletterIssue,
    NewsletterSubscription,
    SubscribeRequest,
    SubscriptionStatus,
)
from src.newsletter.service import NewsletterService

__all__ = [
    "DigestItem",
    "EmailMessage",
    "EmailServiceProvider",
    "MockEmailProvider",
    "NewsletterDigestBuilder",
    "NewsletterIssue",
    "NewsletterService",
    "NewsletterSubscription",
    "SESEmailProvider",
    "SubscribeRequest",
    "SubscriptionStatus",
]
