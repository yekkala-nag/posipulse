"""
Newsletter Subscription & Dispatch Service.
Orchestrates double opt-in confirmations, single-click unsubscriptions (RFC 8058),
DPDP Section 12 erasure rights, and digest broadcasts via configured ESP.
"""

from datetime import datetime, timezone
import logging
import secrets
from typing import Any, Dict, List, Optional, Tuple

from src.config.loader import LanguageConfigRegistry
from src.newsletter.builder import NewsletterDigestBuilder
from src.newsletter.esp import EmailMessage, EmailServiceProvider, MockEmailProvider
from src.newsletter.models import NewsletterIssue, NewsletterSubscription, SubscriptionStatus
from src.storage.db import StorageEngine

logger = logging.getLogger(__name__)


class NewsletterService:
    """
    High-level service managing reader newsletter subscriptions and weekly dispatch.
    """

    def __init__(
        self,
        storage: StorageEngine,
        esp_provider: Optional[EmailServiceProvider] = None,
        config_registry: Optional[LanguageConfigRegistry] = None,
        base_url: str = "https://posipulse.in",
    ):
        self.storage = storage
        self.esp = esp_provider or MockEmailProvider()
        self.config_registry = config_registry or LanguageConfigRegistry()
        self.base_url = base_url.rstrip("/")
        self.builder = NewsletterDigestBuilder(
            storage=storage,
            config_registry=self.config_registry,
            base_url=self.base_url
        )

    def subscribe(
        self,
        email: str,
        language: str = "en",
        send_confirmation_email: bool = True,
    ) -> Tuple[NewsletterSubscription, bool, str]:
        """
        Initiates a newsletter subscription with double opt-in.
        Returns (subscription, is_new_or_reactivated, confirmation_link).
        """
        norm_email = email.strip().lower()
        lang_config = self.config_registry.get(language)
        if not lang_config:
            raise ValueError(f"Language '{language}' is not supported for newsletters.")

        now = datetime.now(timezone.utc)
        existing = self.storage.get_newsletter_subscription(norm_email, language)

        if existing:
            sub = NewsletterSubscription(
                id=existing["id"],
                email=existing["email"],
                language=existing["language"],
                status=SubscriptionStatus(existing["status"]),
                confirmation_token=existing["confirmation_token"],
                unsubscribe_token=existing["unsubscribe_token"],
                requested_at=datetime.fromisoformat(existing["requested_at"]),
                confirmed_at=datetime.fromisoformat(existing["confirmed_at"]) if existing["confirmed_at"] else None,
                unsubscribed_at=datetime.fromisoformat(existing["unsubscribed_at"]) if existing["unsubscribed_at"] else None,
                created_at=datetime.fromisoformat(existing["created_at"]),
                updated_at=datetime.fromisoformat(existing["updated_at"]),
            )

            if sub.status == SubscriptionStatus.CONFIRMED:
                # Already active subscriber
                confirmation_link = f"{self.base_url}/v1/newsletter/confirm?token={sub.confirmation_token}"
                return sub, False, confirmation_link

            # Reactivate or regenerate pending token
            sub.confirmation_token = secrets.token_urlsafe(32)
            sub.status = SubscriptionStatus.PENDING_CONFIRMATION
            sub.updated_at = now
        else:
            sub_id = f"sub-{secrets.token_hex(8)}"
            sub = NewsletterSubscription(
                id=sub_id,
                email=norm_email,
                language=language,
                status=SubscriptionStatus.PENDING_CONFIRMATION,
                confirmation_token=secrets.token_urlsafe(32),
                unsubscribe_token=secrets.token_urlsafe(32),
                requested_at=now,
                confirmed_at=None,
                unsubscribed_at=None,
                created_at=now,
                updated_at=now,
            )

        self.storage.save_newsletter_subscription(sub)
        confirmation_link = f"{self.base_url}/v1/newsletter/confirm?token={sub.confirmation_token}"

        if send_confirmation_email:
            self._send_confirmation_email(sub, confirmation_link)

        return sub, True, confirmation_link

    def confirm(self, token: str) -> NewsletterSubscription:
        """
        Confirms a subscription via double opt-in token.
        Transitions status from 'pending_confirmation' to 'confirmed'.
        """
        raw = self.storage.get_newsletter_subscription_by_token("confirmation", token)
        if not raw:
            raise KeyError("Invalid or expired confirmation token.")

        now = datetime.now(timezone.utc)
        sub = NewsletterSubscription(
            id=raw["id"],
            email=raw["email"],
            language=raw["language"],
            status=SubscriptionStatus.CONFIRMED,
            confirmation_token=raw["confirmation_token"],
            unsubscribe_token=raw["unsubscribe_token"],
            requested_at=datetime.fromisoformat(raw["requested_at"]),
            confirmed_at=now,
            unsubscribed_at=None,
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=now,
        )
        self.storage.save_newsletter_subscription(sub)
        logger.info(f"Confirmed newsletter subscription for {sub.email} ({sub.language})")
        return sub

    def unsubscribe(self, token: str) -> NewsletterSubscription:
        """
        Single-click unsubscription (RFC 8058 compliant).
        Transitions status to 'unsubscribed'.
        """
        raw = self.storage.get_newsletter_subscription_by_token("unsubscribe", token)
        if not raw:
            raise KeyError("Invalid unsubscribe token.")

        now = datetime.now(timezone.utc)
        sub = NewsletterSubscription(
            id=raw["id"],
            email=raw["email"],
            language=raw["language"],
            status=SubscriptionStatus.UNSUBSCRIBED,
            confirmation_token=raw["confirmation_token"],
            unsubscribe_token=raw["unsubscribe_token"],
            requested_at=datetime.fromisoformat(raw["requested_at"]),
            confirmed_at=datetime.fromisoformat(raw["confirmed_at"]) if raw["confirmed_at"] else None,
            unsubscribed_at=now,
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=now,
        )
        self.storage.save_newsletter_subscription(sub)
        logger.info(f"Unsubscribed reader {sub.email} from {sub.language} newsletter")
        return sub

    def erase(self, email: str) -> int:
        """
        DPDP Act Section 12 Right to Erasure.
        Permanently wipes all subscriber records matching the email address.
        """
        count = self.storage.erase_newsletter_subscription(email)
        logger.info(f"DPDP Erasure: permanently deleted {count} subscription records for {email}")
        return count

    def dispatch_weekly_digest(
        self,
        language: str,
        issue: Optional[NewsletterIssue] = None,
        days: int = 7,
        limit: int = 10,
    ) -> Tuple[NewsletterIssue, int]:
        """
        Compiles and broadcasts the weekly constructive digest to all confirmed subscribers.
        Returns (compiled_issue, recipient_count).
        """
        if not issue:
            issue = self.builder.build_digest(language=language, days=days, limit=limit)

        subscribers = self.storage.get_confirmed_subscribers(language)
        if not subscribers:
            logger.info(f"No confirmed subscribers for '{language}' newsletter. Archiving issue without broadcast.")
            now = datetime.now(timezone.utc)
            issue.sent_at = now
            issue.recipient_count = 0
            self.storage.save_newsletter_issue(issue)
            return issue, 0

        messages: List[EmailMessage] = []
        for s in subscribers:
            unsub_token = s["unsubscribe_token"]
            unsub_url = f"{self.base_url}/v1/newsletter/unsubscribe?token={unsub_token}"

            # Replace placeholder token in HTML and text with user's unique token
            user_html = issue.html_content.replace("SAMPLE_TOKEN", unsub_token)
            user_text = issue.text_content.replace("SAMPLE_TOKEN", unsub_token)

            headers = {
                "List-Unsubscribe": f"<{unsub_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }

            msg = EmailMessage(
                to_email=s["email"],
                subject=issue.subject,
                html_body=user_html,
                text_body=user_text,
                headers=headers,
            )
            messages.append(msg)

        batch_result = self.esp.send_batch(messages)
        now = datetime.now(timezone.utc)
        issue.sent_at = now
        issue.recipient_count = batch_result.get("successful", len(messages))
        self.storage.save_newsletter_issue(issue)

        logger.info(
            f"Dispatched {issue.id} to {issue.recipient_count} subscribers in '{language}' via {type(self.esp).__name__}"
        )
        return issue, issue.recipient_count

    def _send_confirmation_email(self, sub: NewsletterSubscription, confirmation_link: str) -> None:
        """Sends the double opt-in confirmation email."""
        lang_config = self.config_registry.get(sub.language)
        lang_name = lang_config.language_name_english if lang_config else sub.language.upper()

        subject = f"Please confirm your PosiPulse {lang_name} Constructive Weekly subscription"
        html_body = f"""
        <div style="font-family: system-ui, sans-serif; max-width: 580px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #2b6cb0;">✨ Confirm Your Constructive News Subscription</h2>
            <p>Thank you for subscribing to <strong>PosiPulse {lang_name} Constructive Weekly</strong>.</p>
            <p>Under our zero-spam policy and the DPDP Act 2023, please verify your email address to begin receiving weekly digests:</p>
            <div style="margin: 24px 0;">
                <a href="{confirmation_link}" style="background-color: #2b6cb0; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    Confirm Subscription ↗
                </a>
            </div>
            <p style="font-size: 12px; color: #718096;">
                Or copy and paste this URL into your browser:<br>
                <a href="{confirmation_link}" style="color: #2b6cb0;">{confirmation_link}</a>
            </p>
            <p style="font-size: 11px; color: #a0aec0; margin-top: 32px; border-top: 1px solid #edf2f7; padding-top: 12px;">
                If you did not request this subscription, you can safely ignore this email. No further emails will be sent.
            </p>
        </div>
        """
        text_body = f"""
Confirm Your PosiPulse {lang_name} Subscription

Please confirm your subscription to the PosiPulse {lang_name} Constructive Weekly edition by visiting the link below:

{confirmation_link}

If you did not request this, please ignore this email.
        """.strip()

        self.esp.send_email(
            to_email=sub.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )
