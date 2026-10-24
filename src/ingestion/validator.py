"""
Feed Validator Agent & Compliance Engine
Audits candidate publisher RSS 2.0 / Atom 1.0 feeds against Tier 1 syndication guidelines.
Generates structured compliance reports, catches tracking params/oversized excerpts,
and previews how items render under PosiPulse's verbatim excerpt model.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
import feedparser
from pydantic import BaseModel, ConfigDict, Field

from src.schemas.source import RightsMode, SourceProfile
from src.taxonomy.registry import TaxonomyRegistry


class ValidationSeverity(str, Enum):
    ERROR = "error"      # Hard blocker: malformed feed, missing title, missing link, script injection
    WARNING = "warning"  # Non-fatal issue: tracking query params, missing images, oversized descriptions
    INFO = "info"        # Informational note: category mappings, truncated excerpt notice


class FeedValidationIssue(BaseModel):
    """Specific compliance issue identified during feed validation."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Machine-readable error/warning code")
    field: str = Field(..., description="Feed or item field name")
    message: str = Field(..., description="Actionable human-readable explanation")
    severity: ValidationSeverity = Field(..., description="Issue severity level")
    item_index: Optional[int] = Field(default=None, description="0-based item index if issue is item-specific")
    item_title: Optional[str] = Field(default=None, description="Headline of affected item if available")


class FeedItemPreview(BaseModel):
    """Simulated rendering of an ingested item in PosiPulse."""
    model_config = ConfigDict(extra="forbid")

    item_index: int
    title: str
    canonical_url: str
    display_excerpt: Optional[str] = None
    rights_mode_applied: RightsMode
    thumbnail_url: Optional[str] = None
    published_at: Optional[str] = None
    categories_detected: List[str] = Field(default_factory=list)
    is_valid: bool = True
    issues: List[FeedValidationIssue] = Field(default_factory=list)


class FeedValidationResult(BaseModel):
    """Full validation audit summary for a candidate feed."""
    model_config = ConfigDict(extra="forbid")

    feed_url: Optional[str] = None
    status: str = Field(..., description="'valid', 'valid_with_warnings', or 'invalid'")
    feed_format: Optional[str] = Field(default=None, description="'rss_2.0', 'atom_1.0', or 'unknown'")
    feed_title: Optional[str] = None
    feed_link: Optional[str] = None
    feed_language: Optional[str] = None
    total_items: int = 0
    valid_items_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: List[FeedValidationIssue] = Field(default_factory=list)
    item_previews: List[FeedItemPreview] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedValidator:
    """
    Tier 1 Publisher Syndication Feed Validator.
    Validates syntax, structure, rights-mode compliance, media enclosures,
    and category mappings.
    """

    TRACKING_PARAM_NAMES = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "at_medium", "at_campaign", "ocid", "mc_cid"
    }

    def __init__(self, taxonomy_registry: Optional[TaxonomyRegistry] = None):
        try:
            self.taxonomy_registry = taxonomy_registry or TaxonomyRegistry()
        except Exception:
            self.taxonomy_registry = None

    def validate_xml(
        self,
        xml_content: str,
        source_profile: Optional[SourceProfile] = None,
        declared_language: Optional[str] = None
    ) -> FeedValidationResult:
        """Audits an XML string against Tier 1 feed guidelines."""
        issues: List[FeedValidationIssue] = []
        item_previews: List[FeedItemPreview] = []

        if not xml_content or not xml_content.strip():
            issues.append(FeedValidationIssue(
                code="EMPTY_CONTENT",
                field="body",
                message="The provided feed XML content is empty or contains only whitespace.",
                severity=ValidationSeverity.ERROR
            ))
            return FeedValidationResult(
                status="invalid",
                error_count=1,
                warning_count=0,
                issues=issues
            )

        # 1. Format Detection & Encoding Check
        feed_format = self._detect_feed_format(xml_content)
        if feed_format == "unknown":
            issues.append(FeedValidationIssue(
                code="UNRECOGNIZED_FORMAT",
                field="xml",
                message="Feed does not appear to be standard RSS 2.0 or Atom 1.0 XML.",
                severity=ValidationSeverity.WARNING
            ))

        # Check for UTF-8 declaration
        if not re.search(r'<\?xml[^>]*encoding=[\'"]utf-8[\'"]', xml_content, re.IGNORECASE):
            issues.append(FeedValidationIssue(
                code="NON_UTF8_DECLARATION",
                field="xml_prolog",
                message="XML declaration should explicitly declare encoding=\"UTF-8\".",
                severity=ValidationSeverity.WARNING
            ))

        # 2. Parse with Feedparser
        feed = feedparser.parse(xml_content)
        if feed.bozo and isinstance(feed.bozo_exception, Exception):
            exc = feed.bozo_exception
            # Ignore harmless XML entity or encoding quirks if entries were still parsed
            if not feed.entries and not getattr(feed, "feed", None):
                issues.append(FeedValidationIssue(
                    code="MALFORMED_XML",
                    field="xml",
                    message=f"XML parsing failed: {str(exc)}",
                    severity=ValidationSeverity.ERROR
                ))
                return FeedValidationResult(
                    status="invalid",
                    feed_format=feed_format,
                    error_count=1,
                    issues=issues
                )
            else:
                issues.append(FeedValidationIssue(
                    code="XML_SYNTAX_WARNING",
                    field="xml",
                    message=f"Minor XML syntax irregularity: {str(exc)}",
                    severity=ValidationSeverity.WARNING
                ))

        # 3. Feed Channel Checks
        channel = feed.get("feed", {}) or feed.get("channel", {})
        feed_title = channel.get("title", "").strip() or None
        feed_link = channel.get("link", "").strip() or None
        feed_language = channel.get("language", "").strip() or declared_language or None

        if not feed_title:
            issues.append(FeedValidationIssue(
                code="MISSING_FEED_TITLE",
                field="channel.title",
                message="Feed is missing a channel/feed title.",
                severity=ValidationSeverity.ERROR
            ))

        if not feed_link:
            issues.append(FeedValidationIssue(
                code="MISSING_FEED_LINK",
                field="channel.link",
                message="Feed is missing a channel homepage URL.",
                severity=ValidationSeverity.ERROR
            ))
        elif not feed_link.startswith("https://"):
            issues.append(FeedValidationIssue(
                code="INSECURE_FEED_LINK",
                field="channel.link",
                message=f"Feed homepage link should use secure HTTPS: '{feed_link}'",
                severity=ValidationSeverity.WARNING
            ))

        # Check language consistency
        target_lang = source_profile.language if source_profile else declared_language
        if target_lang and feed_language:
            norm_target = target_lang.lower().split("-")[0]
            norm_feed = feed_language.lower().split("-")[0]
            if norm_target != norm_feed:
                issues.append(FeedValidationIssue(
                    code="LANGUAGE_MISMATCH",
                    field="channel.language",
                    message=f"Feed declared language '{feed_language}' differs from configured '{target_lang}'.",
                    severity=ValidationSeverity.WARNING
                ))

        # 4. Item-Level Audits & Previews
        entries = feed.entries
        total_items = len(entries)
        valid_items_count = 0

        # Rights mode and excerpt ceiling bounds
        rights_mode = source_profile.rights_mode if source_profile else RightsMode.FEED_PROVIDED_EXCERPT
        ceiling_chars = source_profile.excerpt_ceiling_chars if source_profile else 400
        ceiling_words = source_profile.excerpt_ceiling_words if source_profile else 60

        for idx, entry in enumerate(entries):
            item_issues: List[FeedValidationIssue] = []
            headline = entry.get("title", "").strip()
            link = entry.get("link", "").strip()

            # Headline audit
            if not headline:
                item_issues.append(FeedValidationIssue(
                    code="MISSING_ITEM_TITLE",
                    field="item.title",
                    message="Item is missing a required headline/title.",
                    severity=ValidationSeverity.ERROR,
                    item_index=idx
                ))
            elif len(headline) > 250:
                item_issues.append(FeedValidationIssue(
                    code="HEADLINE_EXCEEDS_LENGTH",
                    field="item.title",
                    message=f"Headline exceeds 250 characters ({len(headline)} chars).",
                    severity=ValidationSeverity.WARNING,
                    item_index=idx,
                    item_title=headline[:50]
                ))

            # Canonical URL audit
            if not link:
                item_issues.append(FeedValidationIssue(
                    code="MISSING_CANONICAL_LINK",
                    field="item.link",
                    message="Item is missing a destination canonical article URL.",
                    severity=ValidationSeverity.ERROR,
                    item_index=idx,
                    item_title=headline
                ))
            else:
                parsed_link = urlparse(link)
                if parsed_link.scheme != "https":
                    item_issues.append(FeedValidationIssue(
                        code="NON_HTTPS_CANONICAL_LINK",
                        field="item.link",
                        message=f"Article link should use secure HTTPS: '{link}'",
                        severity=ValidationSeverity.WARNING,
                        item_index=idx,
                        item_title=headline
                    ))

                # Primary domain match check
                if source_profile and source_profile.primary_domain:
                    link_domain = parsed_link.netloc.lower()
                    if link_domain.startswith("www."):
                        link_domain = link_domain[4:]
                    expected_domain = source_profile.primary_domain.lower()
                    if not (link_domain == expected_domain or link_domain.endswith("." + expected_domain)):
                        item_issues.append(FeedValidationIssue(
                            code="DOMAIN_MISMATCH",
                            field="item.link",
                            message=f"Article URL domain '{parsed_link.netloc}' does not match publisher profile '{source_profile.primary_domain}'.",
                            severity=ValidationSeverity.WARNING,
                            item_index=idx,
                            item_title=headline
                        ))

                # Tracking query params check
                query_params = parse_qs(parsed_link.query)
                found_tracking = [k for k in query_params if k in self.TRACKING_PARAM_NAMES or k.startswith("utm_")]
                if found_tracking:
                    item_issues.append(FeedValidationIssue(
                        code="TRACKING_PARAMS_DETECTED",
                        field="item.link",
                        message=f"URL contains marketing tracking parameters ({', '.join(found_tracking)}). These will be stripped by default.",
                        severity=ValidationSeverity.WARNING,
                        item_index=idx,
                        item_title=headline
                    ))

            # Unique Identifier (GUID / ID)
            guid = entry.get("id", "").strip() or entry.get("guid", "").strip()
            if not guid:
                item_issues.append(FeedValidationIssue(
                    code="MISSING_GUID",
                    field="item.guid",
                    message="Item is missing a persistent unique identifier (GUID/id). Fallback hash will be used.",
                    severity=ValidationSeverity.WARNING,
                    item_index=idx,
                    item_title=headline
                ))

            # Publication Timestamp check
            pub_date_str = None
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                try:
                    pub_dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                    pub_date_str = pub_dt.isoformat()
                    now = datetime.now(timezone.utc)

                    # Future clock drift check
                    diff_seconds = (pub_dt - now).total_seconds()
                    if diff_seconds > 7200:  # > 2 hours in the future
                        item_issues.append(FeedValidationIssue(
                            code="FUTURE_TIMESTAMP_DRIFT",
                            field="item.pubDate",
                            message=f"Publication date is set > 2 hours in the future: {pub_date_str}",
                            severity=ValidationSeverity.WARNING,
                            item_index=idx,
                            item_title=headline
                        ))

                    # Age check (> 30 days)
                    if (now - pub_dt).total_seconds() > 30 * 86400:
                        item_issues.append(FeedValidationIssue(
                            code="STALE_ITEM",
                            field="item.pubDate",
                            message=f"Item is older than 30 days ({pub_date_str}) and may not be indexed in live feeds.",
                            severity=ValidationSeverity.INFO,
                            item_index=idx,
                            item_title=headline
                        ))
                except Exception:
                    item_issues.append(FeedValidationIssue(
                        code="INVALID_PUBDATE",
                        field="item.pubDate",
                        message="Publication date could not be parsed into a valid timestamp.",
                        severity=ValidationSeverity.WARNING,
                        item_index=idx,
                        item_title=headline
                    ))
            else:
                item_issues.append(FeedValidationIssue(
                    code="MISSING_PUBDATE",
                    field="item.pubDate",
                    message="Item is missing a publication date timestamp (pubDate/published).",
                    severity=ValidationSeverity.WARNING,
                    item_index=idx,
                    item_title=headline
                ))

            # Raw excerpt / description payload check
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            raw_content = ""
            if "content" in entry and entry.content:
                raw_content = entry.content[0].get("value", "")

            body_source = raw_summary or raw_content or ""

            # Check for security issues (scripts, iframe, tracking pixels) in body and raw item XML
            has_script = (
                bool(re.search(r"<\s*script[^>]*>", body_source, re.IGNORECASE))
                or bool(re.search(r"&lt;\s*script", xml_content, re.IGNORECASE))
                or bool(re.search(r"<\s*script", xml_content, re.IGNORECASE))
            )
            has_iframe = (
                bool(re.search(r"<\s*iframe[^>]*>", body_source, re.IGNORECASE))
                or bool(re.search(r"&lt;\s*iframe", xml_content, re.IGNORECASE))
                or bool(re.search(r"<\s*iframe", xml_content, re.IGNORECASE))
            )

            if has_script or has_iframe:
                item_issues.append(FeedValidationIssue(
                    code="SCRIPT_INJECTION_DETECTED",
                    field="item.description",
                    message="Feed or item contains prohibited script or iframe elements.",
                    severity=ValidationSeverity.ERROR,
                    item_index=idx,
                    item_title=headline
                ))

            has_pixel = (
                bool(re.search(r'<\s*img[^>]+width=[\'"]1[\'"][^>]+height=[\'"]1[\'"]', body_source, re.IGNORECASE))
                or bool(re.search(r'width=[\'"]1[\'"][^>]+height=[\'"]1[\'"]', xml_content, re.IGNORECASE))
            )
            if has_pixel:
                item_issues.append(FeedValidationIssue(
                    code="TRACKING_PIXEL_DETECTED",
                    field="item.description",
                    message="Description contains tracking pixel beacon (1x1 img).",
                    severity=ValidationSeverity.WARNING,
                    item_index=idx,
                    item_title=headline
                ))

            # Clean HTML to extract plain text
            soup = BeautifulSoup(body_source, "html.parser")
            plain_text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
            word_count = len(plain_text.split())

            # Check for full article dump
            if word_count > 1000:
                item_issues.append(FeedValidationIssue(
                    code="ARTICLE_DUMP_DETECTED",
                    field="item.description",
                    message=f"Description contains full-length article text ({word_count} words). Recommended excerpt ceiling is 60 words.",
                    severity=ValidationSeverity.WARNING,
                    item_index=idx,
                    item_title=headline
                ))

            # Simulate excerpt rendering
            display_excerpt = None
            if rights_mode == RightsMode.HEADLINE_ONLY:
                display_excerpt = None
            else:
                # Truncate according to profile ceiling or defaults
                if source_profile:
                    display_excerpt = source_profile.truncate_excerpt(plain_text)
                else:
                    # Generic truncation
                    if len(plain_text) > ceiling_chars or word_count > ceiling_words:
                        words = plain_text.split()[:ceiling_words]
                        truncated = " ".join(words)
                        if len(truncated) > ceiling_chars:
                            truncated = truncated[:ceiling_chars].rstrip()
                        display_excerpt = f"{truncated}..."
                    else:
                        display_excerpt = plain_text

            # Enclosures / Thumbnail
            thumbnail_url = self._extract_thumbnail(entry)
            if thumbnail_url:
                if not thumbnail_url.startswith("https://"):
                    item_issues.append(FeedValidationIssue(
                        code="NON_HTTPS_MEDIA_URL",
                        field="item.enclosure",
                        message=f"Media image URL must use HTTPS: '{thumbnail_url}'",
                        severity=ValidationSeverity.WARNING,
                        item_index=idx,
                        item_title=headline
                    ))

            # Categories check
            categories = [c.get("term", "").strip() for c in entry.get("tags", []) if c.get("term")]
            if self.taxonomy_registry and categories:
                for cat_tag in categories:
                    norm_tag = cat_tag.lower().replace("&", "and")
                    # Check hidden categories
                    for hidden_cat in self.taxonomy_registry.list_hidden():
                        h_slug = hidden_cat.slug.lower()
                        h_en = hidden_cat.name_en.lower()
                        if h_slug in norm_tag or h_en in norm_tag or any(s.slug in norm_tag for s in hidden_cat.subcategories):
                            item_issues.append(FeedValidationIssue(
                                code="HIDDEN_CATEGORY_MAPPED",
                                field="item.category",
                                message=f"Category tag '{cat_tag}' matches hidden category '{hidden_cat.slug}'. Will be held from public feed.",
                                severity=ValidationSeverity.INFO,
                                item_index=idx,
                                item_title=headline
                            ))
                            break

            has_item_error = any(issue.severity == ValidationSeverity.ERROR for issue in item_issues)
            if not has_item_error and headline and link:
                valid_items_count += 1

            issues.extend(item_issues)

            item_previews.append(FeedItemPreview(
                item_index=idx,
                title=headline or "[Untitled]",
                canonical_url=link or "",
                display_excerpt=display_excerpt,
                rights_mode_applied=rights_mode,
                thumbnail_url=thumbnail_url,
                published_at=pub_date_str,
                categories_detected=categories,
                is_valid=not has_item_error,
                issues=item_issues
            ))

        # Overall Status
        error_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == ValidationSeverity.WARNING)

        if error_count > 0 or total_items == 0 or valid_items_count == 0:
            status = "invalid"
        elif warning_count > 0:
            status = "valid_with_warnings"
        else:
            status = "valid"

        return FeedValidationResult(
            status=status,
            feed_format=feed_format,
            feed_title=feed_title,
            feed_link=feed_link,
            feed_language=feed_language,
            total_items=total_items,
            valid_items_count=valid_items_count,
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
            item_previews=item_previews
        )

    @staticmethod
    def is_safe_feed_url(url: str) -> Tuple[bool, str]:
        """
        Guards against Server-Side Request Forgery (SSRF).
        Rejects loopbacks, private RFC 1918 subnets, cloud metadata (169.254.169.254),
        and unsupported protocols.
        """
        import ipaddress
        import socket
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False, f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
            hostname = parsed.hostname
            if not hostname:
                return False, "Missing hostname in URL."
            hostname_lower = hostname.lower()
            if hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return False, "Access to localhost/loopback addresses is forbidden."
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False, f"Access to private/reserved IP address '{hostname}' is forbidden."
            except ValueError:
                try:
                    resolved_ip_str = socket.gethostbyname(hostname)
                    resolved_ip = ipaddress.ip_address(resolved_ip_str)
                    if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local or resolved_ip.is_reserved:
                        return False, f"Domain '{hostname}' resolves to private/reserved IP address '{resolved_ip_str}'."
                except Exception:
                    pass
            return True, ""
        except Exception as e:
            return False, f"Invalid URL structure: {str(e)}"

    def validate_url(
        self,
        feed_url: str,
        source_profile: Optional[SourceProfile] = None,
        timeout: int = 10
    ) -> FeedValidationResult:
        """Fetches a remote feed via HTTP and audits its contents with SSRF guards."""
        import httpx

        # Security Hardening: Anti-SSRF check
        is_safe, error_msg = self.is_safe_feed_url(feed_url)
        if not is_safe:
            issue = FeedValidationIssue(
                code="SSRF_SECURITY_VIOLATION",
                field="feed_url",
                message=f"Security violation: {error_msg}",
                severity=ValidationSeverity.ERROR
            )
            return FeedValidationResult(
                feed_url=feed_url,
                status="invalid",
                error_count=1,
                issues=[issue]
            )

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PosiPulseValidator/1.0; +https://posipulse.in/validator)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
                response = client.get(feed_url)
                response.raise_for_status()
                content = response.text
                result = self.validate_xml(content, source_profile=source_profile)
                result.feed_url = feed_url
                return result
        except Exception as e:
            issue = FeedValidationIssue(
                code="HTTP_FETCH_ERROR",
                field="network",
                message=f"Failed to fetch feed from '{feed_url}': {str(e)}",
                severity=ValidationSeverity.ERROR
            )
            return FeedValidationResult(
                feed_url=feed_url,
                status="invalid",
                error_count=1,
                issues=[issue]
            )

    @staticmethod
    def _detect_feed_format(xml_content: str) -> str:
        """Determines whether content is RSS 2.0, Atom 1.0, or unknown."""
        snippet = xml_content[:2000].lower()
        if "<rss" in snippet:
            return "rss_2.0"
        if "<feed" in snippet and "xmlns=\"http://www.w3.org/2005/atom\"" in snippet:
            return "atom_1.0"
        if "<feed" in snippet:
            return "atom_1.0"
        return "unknown"

    @staticmethod
    def _extract_thumbnail(entry: Dict[str, Any]) -> Optional[str]:
        """Extracts candidate thumbnail from enclosures, media_content, or media_thumbnail."""
        # 1. RSS 2.0 Enclosure
        enclosures = entry.get("enclosures", [])
        for enc in enclosures:
            href = enc.get("href") or enc.get("url")
            enc_type = (enc.get("type") or "").lower()
            if href and (enc_type.startswith("image/") or any(href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"])):
                return href

        # 2. Media RSS (media_content)
        media_content = entry.get("media_content", [])
        for med in media_content:
            href = med.get("url")
            med_type = (med.get("type") or "").lower()
            medium = (med.get("medium") or "").lower()
            if href and (medium == "image" or med_type.startswith("image/")):
                return href

        # 3. Media Thumbnail
        media_thumbnail = entry.get("media_thumbnail", [])
        if media_thumbnail and isinstance(media_thumbnail, list) and media_thumbnail[0].get("url"):
            return media_thumbnail[0].get("url")

        return None


# ============================================================================
# CLI Command Entrypoint
# ============================================================================

def main():
    """CLI runner for testing and inspecting candidate publisher feeds."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="PosiPulse Tier 1 Publisher Feed Compliance Validator"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Public HTTPS URL of candidate feed")
    group.add_argument("--file", help="Path to local XML file")

    parser.add_argument("--domain", help="Expected primary publisher domain (e.g., thehindu.com)")
    parser.add_argument("--language", default="en", help="Expected language code (default: en)")
    parser.add_argument("--rights-mode", choices=["headline_only", "feed_provided_excerpt", "longer_excerpt"],
                        default="headline_only", help="Rights mode to simulate (default: headline_only)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    # Construct temporary source profile for context
    source_profile = None
    if args.domain:
        source_profile = SourceProfile(
            id=f"test-{args.domain.replace('.', '-')}",
            publisher_id="test-publisher",
            publisher_name=args.domain,
            primary_domain=args.domain,
            feed_urls=[args.url or f"https://{args.domain}/rss"],
            homepage_url=f"https://{args.domain}",
            language=args.language,
            rights_mode=RightsMode(args.rights_mode)
        )

    validator = FeedValidator()

    if args.url:
        result = validator.validate_url(args.url, source_profile=source_profile)
    else:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File not found at '{args.file}'", file=sys.stderr)
            sys.exit(1)
        content = file_path.read_text(encoding="utf-8")
        result = validator.validate_xml(content, source_profile=source_profile, declared_language=args.language)

    if args.format == "json":
        print(result.model_dump_json(indent=2))
    else:
        # Human-friendly CLI report
        status_color = "\033[92m" if result.status == "valid" else ("\033[93m" if result.status == "valid_with_warnings" else "\033[91m")
        reset_color = "\033[0m"

        print("=" * 70)
        print("POSIPULSE TIER 1 PUBLISHER FEED AUDIT REPORT")
        print("=" * 70)
        print(f"Status:          {status_color}{result.status.upper()}{reset_color}")
        print(f"Format:          {result.feed_format}")
        print(f"Title:           {result.feed_title}")
        print(f"Homepage:        {result.feed_link}")
        print(f"Language:        {result.feed_language}")
        print(f"Total Items:     {result.total_items} ({result.valid_items_count} valid)")
        print(f"Errors / Warns:  {result.error_count} error(s), {result.warning_count} warning(s)")
        print("-" * 70)

        if result.issues:
            print("ISSUES IDENTIFIED:")
            for issue in result.issues:
                prefix = "[ERROR]  " if issue.severity == ValidationSeverity.ERROR else ("[WARN]   " if issue.severity == ValidationSeverity.WARNING else "[INFO]   ")
                loc = f" (Item #{issue.item_index})" if issue.item_index is not None else ""
                print(f"  {prefix}{issue.code} on {issue.field}{loc}: {issue.message}")
            print("-" * 70)

        print(f"ITEM PREVIEWS (Rendering under RightsMode: {args.rights_mode}):")
        for prev in result.item_previews[:5]:
            status_symbol = "✓" if prev.is_valid else "✗"
            print(f"  {status_symbol} [{prev.item_index + 1}] {prev.title}")
            print(f"      URL:     {prev.canonical_url}")
            if prev.display_excerpt:
                print(f"      EXCERPT: {prev.display_excerpt}")
            else:
                print(f"      EXCERPT: (Omitted - {prev.rights_mode_applied.value})")
            if prev.thumbnail_url:
                print(f"      IMAGE:   {prev.thumbnail_url}")
            print()

        if len(result.item_previews) > 5:
            print(f"  ... and {len(result.item_previews) - 5} more items.")
        print("=" * 70)

    sys.exit(0 if result.status in ("valid", "valid_with_warnings") else 1)


if __name__ == "__main__":
    main()
