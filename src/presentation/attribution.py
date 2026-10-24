"""
Attribution and Direct-Link Engine
Enforces:
1. Prominent original publisher attribution (name, verified domain, favicon, rights mode).
2. Clean direct links with strict privacy by default (all tracking params stripped).
3. Opt-in attribution UTM parameters when SourceProfile.utm_opt_in == True.
4. Verbatim excerpt enforcement conforming to SourceProfile.rights_mode and ceilings.
"""

from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from src.schemas.article import PublisherAttribution
from src.schemas.source import RightsMode, SourceProfile


class AttributionEngine:
    """
    Central engine for reader presentation, direct linking,
    and verbatim excerpt rights enforcement.
    """

    STRIPPED_TRACKING_KEYS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "at_medium", "at_campaign", "ocid", "mc_cid",
        "_hsenc", "_hsmi", "igshid", "msclkid", "twclid", "mkt_tok"
    }

    @classmethod
    def clean_url(cls, url: str) -> str:
        """
        Strips all marketing, social, and campaign tracking query parameters.
        Preserves genuine article IDs, slugs, and path structure.
        """
        if not url:
            return ""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        clean_params = {
            k: v for k, v in query_params.items()
            if not k.startswith("utm_") and k.lower() not in cls.STRIPPED_TRACKING_KEYS
        }

        clean_query = urlencode(clean_params, doseq=True)
        clean_parsed = parsed._replace(query=clean_query, fragment="")
        return urlunparse(clean_parsed)

    @classmethod
    def format_direct_link(
        cls,
        canonical_url: str,
        profile: Optional[SourceProfile] = None,
        utm_opt_in: Optional[bool] = None,
        campaign: str = "posipulse_news"
    ) -> str:
        """
        Generates direct link to publisher's original article page.
        - Privacy by default: If utm_opt_in is False, all tracking params are stripped.
        - Opt-in only: If utm_opt_in is True, standard attribution parameters are appended.
        """
        base_clean_url = cls.clean_url(canonical_url)
        if not base_clean_url:
            return ""

        # Determine opt-in preference
        should_append_utm = False
        if utm_opt_in is not None:
            should_append_utm = utm_opt_in
        elif profile is not None:
            should_append_utm = profile.utm_opt_in

        if not should_append_utm:
            return base_clean_url

        # Append standard PosiPulse publisher attribution UTM parameters
        campaign_name = campaign
        if profile and profile.extra_metadata.get("utm_campaign"):
            campaign_name = profile.extra_metadata["utm_campaign"]

        parsed = urlparse(base_clean_url)
        existing_params = parse_qs(parsed.query, keep_blank_values=True)
        existing_params["utm_source"] = ["posipulse"]
        existing_params["utm_medium"] = ["referral"]
        existing_params["utm_campaign"] = [campaign_name]

        new_query = urlencode(existing_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    @classmethod
    def format_verbatim_excerpt(
        cls,
        raw_text: Optional[str],
        profile: Optional[SourceProfile] = None
    ) -> Optional[str]:
        """
        Enforces rights mode and excerpt ceilings on verbatim text.
        - headline_only: strictly None (no excerpt displayed)
        - feed_provided_excerpt: bounded by source ceiling (chars & words)
        - longer_excerpt: bounded by source ceiling
        """
        if not raw_text or not raw_text.strip():
            return None

        # Fail closed: If no source profile is provided, default to headline-only
        if profile is None or profile.rights_mode == RightsMode.HEADLINE_ONLY:
            return None

        return profile.truncate_excerpt(raw_text)

    @classmethod
    def resolve_attribution(
        cls,
        source_id: str,
        profile: Optional[SourceProfile] = None,
        fallback_name: Optional[str] = None
    ) -> PublisherAttribution:
        """Constructs complete publisher attribution metadata for card display."""
        if profile:
            favicon = (
                profile.extra_metadata.get("favicon_url")
                or f"https://{profile.primary_domain}/favicon.ico"
            )
            return PublisherAttribution(
                publisher_name=profile.publisher_name,
                primary_domain=profile.primary_domain,
                homepage_url=profile.homepage_url,
                logo_url=profile.extra_metadata.get("logo_url"),
                favicon_url=favicon,
                rights_mode=profile.rights_mode.value,
                trust_tier=profile.trust_tier.value,
                verification_status=profile.verification_status.value,
                utm_opt_in=profile.utm_opt_in
            )

        # Fallback for legacy or unregistered sources
        domain = "posipulse.in"
        return PublisherAttribution(
            publisher_name=fallback_name or source_id,
            primary_domain=domain,
            homepage_url=f"https://{domain}",
            logo_url=None,
            favicon_url=f"https://{domain}/favicon.ico",
            rights_mode=RightsMode.HEADLINE_ONLY.value,
            trust_tier="tier_2",
            verification_status="unverified",
            utm_opt_in=False
        )

    @classmethod
    def enrich_article_presentation(
        cls,
        article_data: Dict[str, Any],
        profile: Optional[SourceProfile] = None,
        is_rtl: bool = False
    ) -> Dict[str, Any]:
        """
        Enriches raw serialized article dict with direct link, verbatim excerpt,
        publisher attribution, and text directionality.
        """
        data = dict(article_data)
        canonical = data.get("canonical_url") or data.get("url") or ""

        # 1. Direct link computation
        direct_url = cls.format_direct_link(canonical, profile=profile)
        data["direct_url"] = direct_url
        data["canonical_url"] = cls.clean_url(canonical)

        # 2. Verbatim excerpt enforcement
        # If verbatim_excerpt was already stored, ensure it obeys rights_mode
        stored_excerpt = data.get("verbatim_excerpt")
        if profile and profile.rights_mode == RightsMode.HEADLINE_ONLY:
            data["verbatim_excerpt"] = None
        elif stored_excerpt and profile:
            data["verbatim_excerpt"] = cls.format_verbatim_excerpt(stored_excerpt, profile)
        elif not stored_excerpt and profile and profile.rights_mode != RightsMode.HEADLINE_ONLY:
            # Fallback to summary text if verbatim excerpt wasn't separately cached
            summary_obj = data.get("summary")
            summary_text = summary_obj.get("text") if isinstance(summary_obj, dict) else None
            data["verbatim_excerpt"] = cls.format_verbatim_excerpt(summary_text, profile)

        # 3. Publisher attribution
        source_id = data.get("source_id", "unknown")
        fallback_name = data.get("source_name", source_id)
        attribution = cls.resolve_attribution(source_id, profile=profile, fallback_name=fallback_name)
        data["publisher_attribution"] = attribution.model_dump()

        # 4. RTL flag
        data["is_rtl"] = is_rtl
        return data
