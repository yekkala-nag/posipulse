"""
Publisher Onboarding and Rights Negotiation Service
Coordinates publisher registration, domain ownership verification,
editorial terms reviews, and review state machine transitions.
"""

from datetime import datetime, timezone
import re
from typing import Any, Optional
from urllib.parse import urlparse

from src.publisher.verification import DomainVerifier
from src.schemas.source import (
    PublisherRegistrationRequest,
    PublisherReviewState,
    RightsMode,
    SourceProfile,
    TermsReviewStatus,
    TrustTier,
    VerificationChallenge,
    VerificationMethod,
    VerificationResult,
    VerificationStatus,
)
from src.storage.db import StorageEngine


class PublisherOnboardingService:
    """
    Manages Tier 1 publisher lifecycle from self-service registration
    through automated domain verification to active feed scheduling.
    """

    def __init__(self, storage: StorageEngine):
        self.storage = storage

    def register_publisher(
        self,
        request: PublisherRegistrationRequest,
        actor: str = "publisher"
    ) -> SourceProfile:
        """
        Registers a new candidate publisher in 'pending_review' state,
        generates an initial domain verification challenge, and persists to DB.
        """
        # 1. Normalize domain
        raw_domain = request.primary_domain.strip().lower()
        if "://" in raw_domain:
            raw_domain = urlparse(raw_domain).netloc
        normalized_domain = re.sub(r"^www\.", "", raw_domain)

        # 2. Derive stable source ID (e.g. pub-thehindu-com-en)
        domain_slug = re.sub(r"[^a-z0-9]+", "-", normalized_domain).strip("-")
        source_id = f"pub-{domain_slug}-{request.language}"

        # 3. Check for existing profile
        existing = self.storage.get_source_profile(source_id)
        if existing:
            raise ValueError(f"Publisher source with ID '{source_id}' is already registered.")

        # 4. Generate domain verification challenge
        challenge = DomainVerifier.create_challenge(source_id, normalized_domain)

        homepage_url = request.homepage_url or f"https://{normalized_domain}"

        profile = SourceProfile(
            id=source_id,
            publisher_id=f"org-{domain_slug}",
            publisher_name=request.publisher_name,
            primary_domain=normalized_domain,
            feed_urls=request.feed_urls,
            homepage_url=homepage_url,
            language=request.language,
            rights_mode=request.rights_mode,
            excerpt_ceiling_chars=request.requested_excerpt_chars,
            excerpt_ceiling_words=request.requested_excerpt_words,
            utm_opt_in=request.utm_opt_in,
            verification_status=VerificationStatus.PENDING,
            terms_review_status=TermsReviewStatus.PENDING,
            trust_tier=TrustTier.TIER_2,
            review_state=PublisherReviewState.PENDING_REVIEW,
            contact_email=request.contact_email,
            contact_name=request.contact_name,
            extra_metadata={
                "verification_challenge": challenge.model_dump(mode="json"),
                "registration_notes": f"Registered via onboarding API by {actor}"
            }
        )

        self.storage.save_source_profile(profile, actor=actor, action="publisher_registered")
        return profile

    def get_or_create_challenge(self, source_id: str) -> VerificationChallenge:
        """Retrieves an active challenge for a source, or generates a fresh one if expired."""
        profile = self.storage.get_source_profile(source_id)
        if not profile:
            raise ValueError(f"Source profile '{source_id}' not found.")

        raw_ch = profile.extra_metadata.get("verification_challenge")
        if raw_ch:
            challenge = VerificationChallenge.model_validate(raw_ch)
            # Check expiration
            if challenge.expires_at > datetime.now(timezone.utc):
                return challenge

        # Regenerate expired challenge
        fresh_challenge = DomainVerifier.create_challenge(source_id, profile.primary_domain)
        profile.extra_metadata["verification_challenge"] = fresh_challenge.model_dump(mode="json")
        self.storage.save_source_profile(profile, actor="system", action="verification_challenge_renewed")
        return fresh_challenge

    def verify_domain(
        self,
        source_id: str,
        method: VerificationMethod,
        actor: str = "system",
        custom_resolver: Optional[Any] = None,
        custom_client: Optional[Any] = None
    ) -> VerificationResult:
        """
        Executes automated verification via DNS TXT, HTML meta tag, or manual admin override.
        Transitions source profile to 'verified' upon success.
        """
        profile = self.storage.get_source_profile(source_id)
        if not profile:
            raise ValueError(f"Source profile '{source_id}' not found.")

        challenge = self.get_or_create_challenge(source_id)

        verified = False
        message = ""
        record_found = None

        if method == VerificationMethod.DNS_TXT:
            verified, message, record_found = DomainVerifier.verify_dns_txt(
                profile.primary_domain,
                challenge.token,
                custom_resolver=custom_resolver
            )
        elif method == VerificationMethod.HTML_META:
            verified, message, record_found = DomainVerifier.verify_html_meta(
                profile.primary_domain,
                challenge.token,
                client=custom_client
            )
        elif method == VerificationMethod.MANUAL_ADMIN:
            if not actor or actor == "system" or "@" not in actor:
                verified = False
                message = "Manual verification requires a verified administrator email actor."
            else:
                verified = True
                message = f"Manually verified by admin: {actor}"
                record_found = f"admin_override:{actor}"

        # Update profile state upon verification
        if verified:
            profile.verification_status = VerificationStatus.VERIFIED
            profile.verified_at = datetime.now(timezone.utc)

            # Check if terms were already approved
            if profile.terms_review_status in (
                TermsReviewStatus.REVIEWED_ACCEPTED,
                TermsReviewStatus.CUSTOM_LICENSE
            ):
                profile.review_state = PublisherReviewState.ACTIVE
            else:
                profile.review_state = PublisherReviewState.VERIFIED

            self.storage.save_source_profile(
                profile,
                actor=actor,
                action=f"domain_verified_via_{method.value}"
            )

        return VerificationResult(
            source_id=source_id,
            primary_domain=profile.primary_domain,
            method=method,
            verified=verified,
            message=message,
            record_found=record_found
        )

    def review_terms(
        self,
        source_id: str,
        new_terms_status: TermsReviewStatus,
        actor: str,
        notes: Optional[str] = None
    ) -> SourceProfile:
        """
        Updates terms of service review status (pending -> accepted/custom/opted_out).
        Transitions profile to 'active' if already domain-verified.
        """
        profile = self.storage.get_source_profile(source_id)
        if not profile:
            raise ValueError(f"Source profile '{source_id}' not found.")

        profile.terms_review_status = new_terms_status

        # Review state machine transitions
        if new_terms_status in (TermsReviewStatus.REVIEWED_ACCEPTED, TermsReviewStatus.CUSTOM_LICENSE):
            if profile.verification_status == VerificationStatus.VERIFIED:
                profile.review_state = PublisherReviewState.ACTIVE
        elif new_terms_status == TermsReviewStatus.OPTED_OUT:
            profile.review_state = PublisherReviewState.SUSPENDED

        if notes:
            profile.extra_metadata["terms_review_notes"] = notes

        self.storage.save_source_profile(
            profile,
            actor=actor,
            action=f"terms_reviewed_{new_terms_status.value}"
        )
        return profile

    def update_lifecycle_state(
        self,
        source_id: str,
        new_state: PublisherReviewState,
        actor: str,
        reason: str
    ) -> SourceProfile:
        """
        Explicitly transitions a publisher profile through operational lifecycle states.
        Enforces cascade if takedown is requested or enforced.
        """
        profile = self.storage.get_source_profile(source_id)
        if not profile:
            raise ValueError(f"Source profile '{source_id}' not found.")

        if new_state in (PublisherReviewState.TAKEDOWN_REQUESTED, PublisherReviewState.TAKEDOWN_ENFORCED):
            # Cascade delisting via DB storage takedown engine
            self.storage.enforce_source_takedown(source_id, reason=reason, actor=actor)
            return self.storage.get_source_profile(source_id)  # type: ignore

        profile.review_state = new_state
        profile.extra_metadata["state_transition_reason"] = reason

        self.storage.save_source_profile(
            profile,
            actor=actor,
            action=f"lifecycle_transition_to_{new_state.value}"
        )
        return profile
