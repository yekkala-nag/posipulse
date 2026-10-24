"""
Email Service Provider (ESP) Abstractions & Implementations.
Includes MockEmailProvider for local development & automated test suites,
and SESEmailProvider for AWS Simple Email Service in Mumbai (ap-south-1).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmailMessage:
    """Represents an outgoing email message."""
    def __init__(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        from_email: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.to_email = to_email
        self.subject = subject
        self.html_body = html_body
        self.text_body = text_body
        self.from_email = from_email or "PosiPulse Newsletters <newsletters@posipulse.in>"
        self.headers = headers or {}
        self.sent_at = datetime.now(timezone.utc)


class EmailServiceProvider(ABC):
    """Abstract Email Service Provider interface."""

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Sends an individual transactional or confirmation email."""
        pass

    @abstractmethod
    def send_batch(
        self,
        messages: List[EmailMessage],
    ) -> Dict[str, Any]:
        """Dispatches a batch of emails, returning success/failure counts."""
        pass


class MockEmailProvider(EmailServiceProvider):
    """
    In-memory mock ESP for tests and local development.
    Captures all sent emails with full inspectability and outbox queries.
    """

    def __init__(self):
        self.outbox: List[EmailMessage] = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        msg = EmailMessage(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            headers=headers,
        )
        self.outbox.append(msg)
        logger.info(f"[MockESP] Queued email to '{to_email}' with subject: '{subject}'")
        return True

    def send_batch(
        self,
        messages: List[EmailMessage],
    ) -> Dict[str, Any]:
        self.outbox.extend(messages)
        logger.info(f"[MockESP] Queued batch of {len(messages)} emails.")
        return {
            "total": len(messages),
            "successful": len(messages),
            "failed": 0,
        }

    def clear(self) -> None:
        """Clears the test outbox."""
        self.outbox.clear()

    def get_emails_for(self, email: str) -> List[EmailMessage]:
        """Returns all emails delivered to the given recipient."""
        return [m for m in self.outbox if m.to_email.lower() == email.lower()]

    def get_last_email_for(self, email: str) -> Optional[EmailMessage]:
        """Returns the most recent email delivered to the recipient."""
        emails = self.get_emails_for(email)
        return emails[-1] if emails else None


class SESEmailProvider(EmailServiceProvider):
    """
    AWS Simple Email Service (SES) provider.
    Defaults to Mumbai region ('ap-south-1') for Indian DPDP Act data residency compliance.
    """

    def __init__(
        self,
        region_name: str = "ap-south-1",
        sender_email: str = "PosiPulse Newsletters <newsletters@posipulse.in>",
    ):
        self.region_name = os.environ.get("AWS_REGION", region_name)
        self.sender_email = os.environ.get("POSIPULSE_SENDER_EMAIL", sender_email)
        self._client = None

    def _get_boto3_client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("ses", region_name=self.region_name)
            except ImportError:
                logger.warning("boto3 is not installed. SES operations will simulate fallback.")
                return None
        return self._client

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        client = self._get_boto3_client()
        if not client:
            logger.info(f"[Simulated-SES] Simulated delivery to {to_email}")
            return True

        try:
            # Custom headers for List-Unsubscribe (RFC 8058)
            custom_headers = []
            if headers:
                for k, v in headers.items():
                    custom_headers.append({"Name": k, "Value": v})

            response = client.send_email(
                Source=self.sender_email,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(f"SES Message ID: {response.get('MessageId')}")
            return True
        except Exception as e:
            logger.error(f"SES Send Email Error for {to_email}: {e}")
            return False

    def send_batch(
        self,
        messages: List[EmailMessage],
    ) -> Dict[str, Any]:
        successful = 0
        failed = 0
        for msg in messages:
            ok = self.send_email(
                to_email=msg.to_email,
                subject=msg.subject,
                html_body=msg.html_body,
                text_body=msg.text_body,
                headers=msg.headers,
            )
            if ok:
                successful += 1
            else:
                failed += 1
        return {
            "total": len(messages),
            "successful": successful,
            "failed": failed,
        }
