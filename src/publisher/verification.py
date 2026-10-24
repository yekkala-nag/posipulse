"""
Publisher Domain Ownership Verification Engine
Supports DNS TXT record challenge, HTML meta tag verification,
and cryptographic token lifecycle management.
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, List, Optional, Tuple
from bs4 import BeautifulSoup
import httpx

from src.schemas.source import (
    SourceProfile,
    VerificationChallenge,
    VerificationMethod,
    VerificationResult,
)


class DomainVerifier:
    """
    Automated domain verification service.
    Verifies that a candidate publisher controls their primary domain.
    """

    TOKEN_PREFIX = "posipulse_verify_"
    DNS_PREFIX = "_posipulse-challenge."
    META_TAG_NAME = "posipulse-verification"

    @classmethod
    def generate_token(cls) -> str:
        """Generates a cryptographically secure 32-character hex verification token."""
        return f"{cls.TOKEN_PREFIX}{secrets.token_hex(16)}"

    @classmethod
    def create_challenge(
        cls,
        source_id: str,
        primary_domain: str,
        validity_days: int = 7
    ) -> VerificationChallenge:
        """Creates a time-bounded challenge for DNS and HTML meta tag verification."""
        token = cls.generate_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=validity_days)

        dns_record_name = f"{cls.DNS_PREFIX}{primary_domain}"
        dns_txt_expected = f"posipulse-site-verification={token}"
        meta_tag_expected = f'<meta name="{cls.META_TAG_NAME}" content="{token}">'

        return VerificationChallenge(
            source_id=source_id,
            primary_domain=primary_domain,
            token=token,
            dns_record_name=dns_record_name,
            dns_txt_expected=dns_txt_expected,
            meta_tag_expected=meta_tag_expected,
            expires_at=expires_at
        )

    @classmethod
    def verify_dns_txt(
        cls,
        primary_domain: str,
        expected_token: str,
        custom_resolver: Optional[Any] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Queries DNS TXT records for posipulse-site-verification=<token>.
        Checks both _posipulse-challenge.<domain> and apex <domain>.
        """
        try:
            import dns.resolver

            resolver = custom_resolver or dns.resolver.Resolver()
            resolver.timeout = 5.0
            resolver.lifetime = 5.0

            expected_txt = f"posipulse-site-verification={expected_token}"
            domains_to_check = [
                f"{cls.DNS_PREFIX}{primary_domain}",
                primary_domain
            ]

            found_records: List[str] = []
            for query_domain in domains_to_check:
                try:
                    answers = resolver.resolve(query_domain, "TXT")
                    for rdata in answers:
                        # DNS TXT strings can be chunked or quoted
                        for chunk in rdata.strings:
                            val = chunk.decode("utf-8", errors="ignore").strip().strip('"')
                            found_records.append(val)
                            if val == expected_txt or val == expected_token:
                                return True, f"Valid DNS TXT record found on {query_domain}", val
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
                    continue
                except dns.resolver.Timeout:
                    return False, f"DNS query timed out resolving {query_domain}", None
                except Exception as e:
                    return False, f"DNS resolution error for {query_domain}: {str(e)}", None

            return (
                False,
                f"No matching DNS TXT record '{expected_txt}' found on {primary_domain} or {cls.DNS_PREFIX}{primary_domain}.",
                "; ".join(found_records) if found_records else None
            )

        except ImportError:
            return False, "dnspython library not available for DNS verification", None
        except Exception as e:
            return False, f"Unexpected DNS verification failure: {str(e)}", None

    @classmethod
    def verify_html_meta(
        cls,
        primary_domain: str,
        expected_token: str,
        client: Optional[httpx.Client] = None,
        timeout: int = 10
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Fetches the publisher's root HTML page and checks for:
        <meta name="posipulse-verification" content="<expected_token>">
        """
        urls_to_try = [
            f"https://{primary_domain}",
            f"https://www.{primary_domain}",
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PosiPulseVerifier/1.0; +https://posipulse.in/verify)",
            "Accept": "text/html,application/xhtml+xml",
        }

        last_error = None
        for target_url in urls_to_try:
            try:
                if client:
                    resp = client.get(target_url)
                else:
                    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as http_client:
                        resp = http_client.get(target_url)

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code} received from {target_url}"
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                meta_tag = soup.find("meta", attrs={"name": cls.META_TAG_NAME})
                if meta_tag and meta_tag.get("content"):
                    content_val = str(meta_tag.get("content")).strip()
                    if content_val == expected_token:
                        return True, f"Verified via HTML meta tag on {target_url}", content_val
                    else:
                        return False, f"Meta tag found with mismatched token: '{content_val}'", content_val

            except Exception as e:
                last_error = f"Connection failure on {target_url}: {str(e)}"
                continue

        return False, f"HTML meta tag verification failed: {last_error or 'No tag found in <head>'}", None
