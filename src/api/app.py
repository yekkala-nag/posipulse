"""
FastAPI Client API Gateway
Implements OpenAPI 3.1 specification serving mobile and web clients.
Enforces prominent original publisher attribution, language-aware directionality (RTL),
feed pagination, and DPDP Act delisting.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from src.config.loader import LanguageConfigRegistry
from src.ingestion.validator import FeedValidationResult, FeedValidator
from src.observability.metrics import metrics_collector
from src.pipeline.orchestrator import PipelineOrchestrator
from src.presentation.attribution import AttributionEngine
from src.publisher.onboarding import PublisherOnboardingService
from src.schemas.article import Article
from src.schemas.source import (
    PublisherRegistrationRequest,
    PublisherReviewState,
    RightsMode,
    SourceProfile,
    TermsReviewStatus,
    VerificationChallenge,
    VerificationMethod,
    VerificationResult,
)
from src.storage.db import StorageEngine


FIXTURE_MAP: Dict[str, tuple[str, str]] = {
    "en": ("the_hindu_sample.xml", "the-hindu-national"),
    "hi": ("bbc_hindi_sample.xml", "bbc-hindi"),
    "bn": ("anandabazar_sample.xml", "anandabazar-patrika"),
    "mr": ("loksatta_marathi_sample.xml", "loksatta-national"),
    "te": ("eenadu_telugu_sample.xml", "eenadu-national"),
    "ta": ("dinamalar_tamil_sample.xml", "dinamalar-national"),
    "ur": ("inquilab_urdu_sample.xml", "inquilab-mumbai"),
    "gu": ("gujaratsamachar_sample.xml", "gujarat-samachar"),
    "kn": ("prajavani_kannada_sample.xml", "prajavani-kannada"),
    "or": ("sambad_odia_sample.xml", "sambad-odia"),
    "ml": ("mathrubhumi_malayalam_sample.xml", "mathrubhumi-malayalam"),
    "pa": ("jagbani_punjabi_sample.xml", "jagbani-punjabi"),
    "as": ("asomiya_pratidin_sample.xml", "asomiya-pratidin"),
    "ne": ("kantipur_nepali_sample.xml", "kantipur-daily"),
    "mai": ("mithila_mirror_sample.xml", "mithila-mirror"),
    "gom": ("bhashabhas_konkani_sample.xml", "bhashabhas-konkani"),
}


def create_app(storage: Optional[StorageEngine] = None, registry: Optional[LanguageConfigRegistry] = None) -> FastAPI:
    app = FastAPI(
        title="Positive News App API Gateway",
        version="1.0.0",
        description="Public client API for verified constructive news in English and 15 Indian languages."
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # In-memory or shared instances
    storage_engine = storage or StorageEngine(":memory:")
    config_registry = registry or LanguageConfigRegistry()

    # Mount static assets for web reader client
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/")
    @app.get("/app")
    def get_web_app():
        index_file = web_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "PosiPulse Web Reader Client"}

    @app.get("/publisher")
    def get_publisher_portal():
        pub_file = web_dir / "publisher.html"
        if pub_file.exists():
            return FileResponse(pub_file)
        return {"message": "PosiPulse Publisher Portal"}

    class FeedbackPayload(BaseModel):
        article_id: str
        feedback_type: str = Field(..., description="not_positive, toxic_positivity, inaccurate_summary, broken_link, other")
        comments: str = Field(..., max_length=1000)

    class DelistPayload(BaseModel):
        article_id: str
        requester_name: str
        requester_email: EmailStr
        reason: str = Field(..., max_length=2000)

    @app.get("/health")
    def get_health() -> Dict[str, Any]:
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/metrics")
    def get_metrics(
        format: Optional[str] = Query(None, description="json or prometheus"),
        accept: Optional[str] = Header(None)
    ):
        if format == "prometheus" or (accept and "text/plain" in accept):
            return Response(
                content=metrics_collector.export_prometheus_text(),
                media_type="text/plain; version=0.0.4"
            )

        db_metrics = storage_engine.get_metrics()
        telemetry = metrics_collector.get_summary()
        combined = dict(db_metrics)
        combined["telemetry"] = telemetry
        return combined

    @app.get("/v1/languages")
    def list_languages() -> Dict[str, Any]:
        configs = config_registry.list_all()
        return {
            "languages": [
                {
                    "code": c.language_code,
                    "english_name": c.language_name_english,
                    "native_name": c.language_name_native,
                    "script": c.script,
                    "is_rtl": c.is_rtl,
                    "tier": c.tier.value,
                    "status": c.status.value,
                    "healthy_sources_count": len([s for s in c.sources if s.health_status == "healthy"])
                }
                for c in configs
            ]
        }

    @app.get("/v1/categories")
    def list_categories(
        language: str = Query("en", min_length=2, max_length=5, description="ISO language code for localized display names")
    ) -> Dict[str, Any]:
        """
        Returns all 13 visible news categories according to Taxonomy v1,
        with localized display names, standard IPTC Media Topics codes, and icons.
        """
        from src.taxonomy import default_taxonomy_registry

        CATEGORY_ICONS = {
            1: "🌾",   # Agriculture & Rural
            2: "🔬",   # Science & Technology
            3: "📚",   # Education & Skills
            4: "🌱",   # Environment & Climate
            5: "🏆",   # Sports
            6: "🤝",   # Society & Community
            7: "🎨",   # Arts, Culture & Heritage
            8: "✈️",   # Lifestyle & Travel
            9: "📈",   # Economy & Business
            10: "🩺",  # Health & Wellness
            11: "🚆",  # Infrastructure & Transport
            12: "🎭",  # Entertainment & Media
            13: "🌐",  # World & Diplomacy
        }

        visible_categories = default_taxonomy_registry.list_visible()
        result = []
        for cat in visible_categories:
            display_name = cat.get_display_name(language)
            icon = CATEGORY_ICONS.get(cat.id, "📰")
            result.append({
                "id": cat.id,
                "slug": cat.slug,
                "name_en": cat.name_en,
                "display_name": display_name,
                "icon": icon,
                "iptc_qcode": cat.iptc_reference.qcode if cat.iptc_reference else None,
                "subcategories_count": len(cat.subcategories)
            })

        return {
            "taxonomy_version": default_taxonomy_registry.version,
            "total_visible": len(result),
            "language": language,
            "categories": result
        }

    @app.get("/v1/feed")
    def get_feed(
        language: str = Query(..., min_length=2, max_length=5, description="ISO language code (e.g. en, hi, ur)"),
        category: Optional[str] = Query(None, description="Constructive category filter"),
        since: Optional[datetime] = Query(None, description="Incremental timestamp filter"),
        limit: int = Query(20, ge=1, le=100),
        cursor: Optional[str] = Query(None, description="Pagination cursor")
    ) -> Dict[str, Any]:
        lang_config = config_registry.get(language)
        if not lang_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The requested language code '{language}' is not supported."
            )

        articles, next_cursor = storage_engine.get_feed(
            language=language,
            category=category,
            since=since,
            limit=limit,
            cursor=cursor
        )

        # Enrich articles with prominent publisher attribution, direct links, and excerpts
        profiles_cache: Dict[str, Optional[SourceProfile]] = {}

        def _get_profile(source_id: str) -> Optional[SourceProfile]:
            if source_id not in profiles_cache:
                profiles_cache[source_id] = storage_engine.get_source_profile(source_id)
            return profiles_cache[source_id]

        enriched = []
        for a in articles:
            raw_data = a.model_dump()
            profile = _get_profile(a.source_id)
            enriched_item = AttributionEngine.enrich_article_presentation(
                raw_data,
                profile=profile,
                is_rtl=lang_config.is_rtl
            )
            enriched.append(enriched_item)

        # Batch record anonymous impressions for served feed articles (DPDP Act 2023)
        if articles:
            storage_engine.record_impressions_batch([
                {
                    "source_id": a.source_id,
                    "article_id": a.id,
                    "language": a.language,
                    "category_id": a.category.primary_id if a.category else None
                }
                for a in articles
            ])

        return {
            "articles": enriched,
            "next_cursor": next_cursor,
            "total_returned": len(enriched)
        }

    # ========================================================================
    # Reader Following & Topic Preferences (Categories & Sources)
    # ========================================================================

    class FollowRequest(BaseModel):
        following_type: str = Field(..., description="'category' or 'source'")
        target_id: Union[str, int] = Field(..., description="Category ID (e.g. 1-13) or Source ID slug")

    @app.get("/v1/feed/following")
    def get_following_feed(
        device_id: str = Query(..., min_length=4, max_length=128, description="Anonymous device identifier"),
        language: str = Query(..., min_length=2, max_length=5, description="ISO language code"),
        limit: int = Query(20, ge=1, le=100),
        cursor: Optional[str] = Query(None, description="Pagination cursor")
    ) -> Dict[str, Any]:
        """
        Following Feed.
        Delivers verified constructive news matching topics (categories) and publisher sources
        followed by an anonymous device ID. No user account required.
        """
        lang_config = config_registry.get(language)
        if not lang_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The requested language code '{language}' is not supported."
            )

        articles, next_cursor = storage_engine.get_following_feed(
            device_id=device_id,
            language=language,
            limit=limit,
            cursor=cursor
        )

        profiles_cache: Dict[str, Optional[SourceProfile]] = {}

        def _get_profile(source_id: str) -> Optional[SourceProfile]:
            if source_id not in profiles_cache:
                profiles_cache[source_id] = storage_engine.get_source_profile(source_id)
            return profiles_cache[source_id]

        enriched = []
        for a in articles:
            raw_data = a.model_dump()
            profile = _get_profile(a.source_id)
            enriched_item = AttributionEngine.enrich_article_presentation(
                raw_data,
                profile=profile,
                is_rtl=lang_config.is_rtl
            )
            enriched.append(enriched_item)

        # Batch record anonymous impressions
        if articles:
            storage_engine.record_impressions_batch([
                {
                    "source_id": a.source_id,
                    "article_id": a.id,
                    "language": a.language,
                    "category_id": a.category.primary_id if a.category else None
                }
                for a in articles
            ])

        return {
            "articles": enriched,
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
            "total_returned": len(enriched),
            "following": storage_engine.get_reader_following(device_id)
        }

    @app.get("/v1/reader/{device_id}/following")
    def get_reader_following(device_id: str) -> Dict[str, Any]:
        """
        Retrieve all categories and sources followed by an anonymous device ID.
        DPDP Act 2023: Full transparency on stored preferences.
        """
        following = storage_engine.get_reader_following(device_id)
        from src.taxonomy import default_taxonomy_registry

        # Enrich categories with display metadata
        enriched_categories = []
        for cat_item in following["categories"]:
            cat_id_int = int(cat_item) if isinstance(cat_item, int) or (isinstance(cat_item, str) and cat_item.isdigit()) else None
            if cat_id_int:
                cat = default_taxonomy_registry.get_by_id(cat_id_int)
                if cat:
                    enriched_categories.append({
                        "id": cat.id,
                        "slug": cat.slug,
                        "name_en": cat.name_en,
                        "display_name": cat.get_display_name("en")
                    })

        # Enrich sources with publisher metadata
        enriched_sources = []
        for src_id in following["sources"]:
            prof = storage_engine.get_source_profile(src_id)
            if prof:
                enriched_sources.append({
                    "id": prof.id,
                    "publisher_name": prof.publisher_name,
                    "primary_domain": prof.primary_domain,
                    "verification_status": prof.verification_status.value
                })

        return {
            "device_id": device_id,
            "categories": following["categories"],
            "sources": following["sources"],
            "enriched_categories": enriched_categories,
            "enriched_sources": enriched_sources
        }

    @app.post("/v1/reader/{device_id}/follow")
    def follow_topic_or_source(device_id: str, request: FollowRequest) -> Dict[str, Any]:
        """
        Follow a visible news category or active publisher source.
        Fail-closed invariant: Hidden categories (14-18) are never followable.
        """
        from src.taxonomy import default_taxonomy_registry

        target_str = str(request.target_id)
        if request.following_type == "category":
            target_cat = None
            if target_str.isdigit():
                target_cat = default_taxonomy_registry.get_by_id(int(target_str))
            else:
                target_cat = default_taxonomy_registry.get_by_slug(target_str)

            if not target_cat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Category '{request.target_id}' not found."
                )
            if not target_cat.is_visible:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Hidden news categories cannot be followed under constructive journalism guidelines."
                )
            storage_engine.follow_target(device_id, "category", str(target_cat.id))

        elif request.following_type == "source":
            prof = storage_engine.get_source_profile(target_str)
            if not prof:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Publisher source '{request.target_id}' not found."
                )
            if prof.takedown_status.value == "takedown_enforced":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Delisted publisher sources cannot be followed."
                )
            storage_engine.follow_target(device_id, "source", prof.id)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid following_type. Must be 'category' or 'source'."
            )

        return {
            "success": True,
            "status": "followed",
            "device_id": device_id,
            "following_type": request.following_type,
            "target_id": request.target_id,
            "following": storage_engine.get_reader_following(device_id)
        }

    @app.delete("/v1/reader/{device_id}/follow")
    def unfollow_topic_or_source(
        device_id: str,
        request: Optional[FollowRequest] = None,
        following_type: Optional[str] = Query(None, description="'category' or 'source'"),
        target_id: Optional[Union[str, int]] = Query(None, description="Category ID or source slug")
    ) -> Dict[str, Any]:
        """Unfollow a category or publisher source."""
        f_type = request.following_type if request else following_type
        t_id = str(request.target_id) if request else (str(target_id) if target_id is not None else None)
        if not f_type or not t_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide following_type and target_id."
            )
        unfollowed = storage_engine.unfollow_target(device_id, f_type, t_id)
        return {
            "success": True,
            "status": "unfollowed" if unfollowed else "not_found",
            "device_id": device_id,
            "following": storage_engine.get_reader_following(device_id)
        }

    @app.delete("/v1/reader/{device_id}/following")
    def clear_all_reader_following(device_id: str) -> Dict[str, Any]:
        """
        DPDP Section 12 Right to Erasure.
        Permanently wipes all followed topic and source preferences for the device.
        """
        cleared_count = storage_engine.clear_reader_following(device_id)
        return {
            "success": True,
            "status": "erased",
            "device_id": device_id,
            "records_cleared": cleared_count,
            "deleted_count": cleared_count
        }

    @app.get("/v1/articles/{article_id}")
    def get_article(article_id: str) -> Dict[str, Any]:
        art = storage_engine.get_article(article_id)
        if not art:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article '{article_id}' not found or has been delisted."
            )

        lang_config = config_registry.get(art.language)
        profile = storage_engine.get_source_profile(art.source_id)
        return AttributionEngine.enrich_article_presentation(
            art.model_dump(),
            profile=profile,
            is_rtl=lang_config.is_rtl if lang_config else False
        )

    @app.get("/v1/clusters/{cluster_id}")
    def get_cluster(cluster_id: str) -> Dict[str, Any]:
        cluster_articles = storage_engine.get_cluster_articles(cluster_id)
        if not cluster_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Semantic cluster '{cluster_id}' not found."
            )

        profiles_cache: Dict[str, Optional[SourceProfile]] = {}
        enriched = []
        for a in cluster_articles:
            lang_config = config_registry.get(a.language)
            if a.source_id not in profiles_cache:
                profiles_cache[a.source_id] = storage_engine.get_source_profile(a.source_id)
            profile = profiles_cache[a.source_id]
            enriched_item = AttributionEngine.enrich_article_presentation(
                a.model_dump(),
                profile=profile,
                is_rtl=lang_config.is_rtl if lang_config else False
            )
            enriched.append(enriched_item)

        return {
            "cluster_id": cluster_id,
            "articles": enriched
        }

    @app.post("/v1/feedback", status_code=status.HTTP_202_ACCEPTED)
    def submit_feedback(payload: FeedbackPayload) -> Dict[str, Any]:
        feedback_id = storage_engine.record_feedback(
            article_id=payload.article_id,
            feedback_type=payload.feedback_type,
            comments=payload.comments
        )
        return {
            "success": True,
            "feedback_id": feedback_id,
            "message": "Feedback received and queued for evaluation."
        }

    @app.post("/v1/privacy/delist", status_code=status.HTTP_202_ACCEPTED)
    def submit_delist(payload: DelistPayload) -> Dict[str, Any]:
        success = storage_engine.delist_article(
            article_id=payload.article_id,
            requester_name=payload.requester_name,
            requester_email=str(payload.requester_email),
            reason=payload.reason
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article '{payload.article_id}' not found."
            )

        return {
            "success": True,
            "message": "Article has been delisted and removed from feed distribution under DPDP Act obligations."
        }

    @app.post("/v1/demo/seed")
    def seed_demo_articles(
        language: str = Query(..., description="Language code to seed demo articles for")
    ) -> Dict[str, Any]:
        lang_config = config_registry.get(language)
        if not lang_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The requested language code '{language}' is not supported."
            )

        fixture_info = FIXTURE_MAP.get(language)
        if not fixture_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No demo fixture registered for language '{language}'."
            )

        fixture_file, source_id = fixture_info
        fixture_path = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / fixture_file
        if not fixture_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fixture file '{fixture_file}' not found."
            )

        xml_content = fixture_path.read_text(encoding="utf-8")
        orchestrator = PipelineOrchestrator(language_config=lang_config, storage=storage_engine)
        stats = orchestrator.process_raw_xml(xml_content, source_id=source_id)

        return {
            "success": True,
            "language": language,
            "published_count": stats["published_count"],
            "stats": stats
        }

    @app.post("/v1/ingest/live")
    def trigger_live_ingest(
        language: str = Query(..., description="Language code to fetch live news for"),
        source_id: Optional[str] = Query(None, description="Optional specific publisher source ID"),
        force: bool = Query(False, description="Bypass publisher cooldown interval"),
        background: bool = Query(False, description="Run ingestion asynchronously in background"),
        background_tasks: BackgroundTasks = None
    ) -> Dict[str, Any]:
        """
        Dynamically fetches and ingests live RSS news feeds for the requested language.
        Respects cooldown rate limits unless force=True.
        """
        lang_config = config_registry.get(language)
        if not lang_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The requested language code '{language}' is not supported."
            )

        orchestrator = PipelineOrchestrator(language_config=lang_config, storage=storage_engine)

        def _run_fetch():
            if source_id:
                return orchestrator.process_live_source(source_id=source_id, force=force)
            return orchestrator.process_live_language(force=force)

        if background and background_tasks:
            background_tasks.add_task(_run_fetch)
            return {
                "success": True,
                "message": f"Dynamic live ingest queued in background for {language}.",
                "language": language,
                "background": True
            }

        result = _run_fetch()
        return {
            "success": True,
            "language": language,
            "result": result
        }

    @app.get("/api/cron")
    def run_cron_scheduled_fetch(
        authorization: Optional[str] = Header(None)
    ) -> Dict[str, Any]:
        """
        Vercel Cron Trigger Endpoint
        Executes incremental polling across active languages respecting cooldowns.
        """
        import os
        cron_secret = os.environ.get("CRON_SECRET")
        if cron_secret and authorization != f"Bearer {cron_secret}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron authorization token.")

        processed = []
        for lang_code in ["en", "hi", "ur", "bn", "mr", "te", "ta", "gu"]:
            lang_cfg = config_registry.get(lang_code)
            if not lang_cfg:
                continue
            orchestrator = PipelineOrchestrator(language_config=lang_cfg, storage=storage_engine)
            res = orchestrator.process_live_language(force=False)
            processed.append({
                "language": lang_code,
                "published_count": res.get("total_published", 0),
                "ingested_count": res.get("total_ingested", 0)
            })

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": processed
        }

    class FeedValidationRequest(BaseModel):
        feed_url: Optional[str] = None
        xml_content: Optional[str] = None
        primary_domain: Optional[str] = None
        language: Optional[str] = "en"
        rights_mode: Optional[RightsMode] = RightsMode.HEADLINE_ONLY

    @app.post("/v1/publishers/validate-feed", response_model=FeedValidationResult)
    def validate_publisher_feed(request: FeedValidationRequest) -> FeedValidationResult:
        """
        Tier 1 Publisher Feed Compliance Auditor.
        Validates candidate RSS 2.0 / Atom 1.0 feeds, checks for tracking params,
        enforces excerpt ceilings, and generates item previews under the specified rights mode.
        """
        if not request.feed_url and not request.xml_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'feed_url' or 'xml_content' must be provided."
            )

        source_profile = None
        if request.primary_domain:
            source_profile = SourceProfile(
                id=f"validate-{request.primary_domain.replace('.', '-')}",
                publisher_id="temp-validator",
                publisher_name=request.primary_domain,
                primary_domain=request.primary_domain,
                feed_urls=[request.feed_url or f"https://{request.primary_domain}/rss"],
                homepage_url=f"https://{request.primary_domain}",
                language=request.language or "en",
                rights_mode=request.rights_mode or RightsMode.HEADLINE_ONLY,
            )

        validator = FeedValidator()
        if request.feed_url:
            return validator.validate_url(request.feed_url, source_profile=source_profile)
        else:
            return validator.validate_xml(
                request.xml_content or "",
                source_profile=source_profile,
                declared_language=request.language or "en"
            )

    @app.post("/v1/publishers/register", response_model=SourceProfile, status_code=status.HTTP_201_CREATED)
    def register_publisher_source(request: PublisherRegistrationRequest) -> SourceProfile:
        """Self-service registration for candidate publishers."""
        onboarding_service = PublisherOnboardingService(storage_engine)
        try:
            return onboarding_service.register_publisher(request)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @app.get("/v1/publishers/{source_id}/challenge", response_model=VerificationChallenge)
    def get_publisher_verification_challenge(source_id: str) -> VerificationChallenge:
        """Fetches active verification tokens and instructions for DNS and HTML meta tag verification."""
        onboarding_service = PublisherOnboardingService(storage_engine)
        try:
            return onboarding_service.get_or_create_challenge(source_id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    class VerifyDomainRequest(BaseModel):
        method: VerificationMethod = VerificationMethod.DNS_TXT
        admin_actor: Optional[str] = None

    @app.post("/v1/publishers/{source_id}/verify", response_model=VerificationResult)
    def trigger_domain_verification(source_id: str, request: VerifyDomainRequest) -> VerificationResult:
        """Triggers automated DNS TXT, HTML meta tag, or admin manual verification."""
        onboarding_service = PublisherOnboardingService(storage_engine)
        try:
            return onboarding_service.verify_domain(
                source_id=source_id,
                method=request.method,
                actor=request.admin_actor or "system"
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    class ReviewTermsRequest(BaseModel):
        terms_review_status: TermsReviewStatus
        admin_actor: str
        notes: Optional[str] = None

    @app.post("/v1/publishers/{source_id}/review", response_model=SourceProfile)
    def review_publisher_terms(source_id: str, request: ReviewTermsRequest) -> SourceProfile:
        """Admin review of publisher terms of service and syndication agreement."""
        onboarding_service = PublisherOnboardingService(storage_engine)
        try:
            return onboarding_service.review_terms(
                source_id=source_id,
                new_terms_status=request.terms_review_status,
                actor=request.admin_actor,
                notes=request.notes
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    class LifecycleStateRequest(BaseModel):
        new_state: PublisherReviewState
        actor: str
        reason: str

    @app.post("/v1/publishers/{source_id}/state", response_model=SourceProfile)
    def transition_publisher_lifecycle_state(source_id: str, request: LifecycleStateRequest) -> SourceProfile:
        """Transitions publisher review/scheduling state (active, suspended, takedown)."""
        onboarding_service = PublisherOnboardingService(storage_engine)
        try:
            return onboarding_service.update_lifecycle_state(
                source_id=source_id,
                new_state=request.new_state,
                actor=request.actor,
                reason=request.reason
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    class OutboundClickPayload(BaseModel):
        article_id: str

    @app.post("/v1/analytics/click", status_code=status.HTTP_204_NO_CONTENT)
    def record_outbound_click(payload: OutboundClickPayload):
        """
        Privacy-Preserving Outbound Click Beacon (DPDP Act 2023 Compliant).
        Records an anonymous aggregate outbound click for publisher reporting.
        Zero personal data collected (all IPs, user agents, cookies, and identifiers discarded).
        """
        art = storage_engine.get_article(payload.article_id)
        if not art:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found or delisted.")

        cat_id = art.category.primary_id if art.category else None
        storage_engine.record_click(
            source_id=art.source_id,
            article_id=art.id,
            language=art.language,
            category_id=cat_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/v1/publishers/{source_id}/analytics")
    def get_publisher_analytics(
        source_id: str,
        period: str = Query("7d", pattern=r"^(24h|7d|30d)$", description="Aggregation window (24h, 7d, 30d)"),
        min_threshold: int = Query(5, ge=1, le=50, description="K-anonymity suppression threshold (default 5)")
    ) -> Dict[str, Any]:
        """
        Publisher Analytics Dashboard (DPDP Act 2023 Compliant).
        Returns aggregate-only referral performance metrics:
        impressions, outbound clicks, CTR, and language/category breakdowns.
        Enforces minimum threshold k-anonymity (suppresses buckets with fewer than min_threshold events).
        """
        profile = storage_engine.get_source_profile(source_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Publisher source '{source_id}' not found."
            )

        from datetime import timedelta
        now = datetime.now(timezone.utc)
        if period == "24h":
            since = now - timedelta(hours=24)
        elif period == "30d":
            since = now - timedelta(days=30)
        else:
            since = now - timedelta(days=7)

        analytics_data = storage_engine.get_publisher_analytics(
            source_id=source_id,
            since=since,
            min_threshold=min_threshold
        )
        analytics_data["publisher_name"] = profile.publisher_name
        analytics_data["primary_domain"] = profile.primary_domain
        analytics_data["period"] = period
        return analytics_data

    @app.get("/v1/publishers/{source_id}/dashboard")
    def get_publisher_dashboard(source_id: str) -> Dict[str, Any]:
        """
        Publisher Self-Service Management Dashboard.
        Assembles profile metadata, ingestion health, historical article counts,
        recent ingested items, and audit history.
        """
        profile = storage_engine.get_source_profile(source_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Publisher source '{source_id}' not found."
            )

        fetch_log = storage_engine.get_source_fetch_log(source_id)
        counts = storage_engine.get_source_article_counts(source_id)
        recent_articles = storage_engine.get_source_recent_articles(source_id, limit=20)

        # Enrich recent articles with direct links and excerpts
        enriched_articles = []
        for art in recent_articles:
            raw = art.model_dump()
            enriched_articles.append(
                AttributionEngine.enrich_article_presentation(raw, profile=profile)
            )

        # Check circuit breaker and health status
        circuit_breaker_tripped = (
            profile.takedown_status.value != "active"
            or profile.review_state.value in ("suspended", "takedown_requested", "takedown_enforced")
        )
        last_status = fetch_log["status"] if fetch_log else ("healthy" if profile.review_state.value == "active" else "idle")

        ingestion_health = {
            "status": last_status,
            "last_fetched_at": fetch_log["last_fetched_at"] if fetch_log else None,
            "items_last_fetched": fetch_log["items_count"] if fetch_log else 0,
            "circuit_breaker_tripped": circuit_breaker_tripped,
            "metrics": counts
        }

        # Sanitized audit trail (last 10 entries)
        recent_audit = [
            {
                "timestamp": entry.timestamp.isoformat(),
                "action": entry.action,
                "actor": entry.actor,
                "details": entry.details
            }
            for entry in profile.audit_history[-10:]
        ]

        return {
            "source_profile": profile.model_dump(),
            "ingestion_health": ingestion_health,
            "recent_articles": enriched_articles,
            "recent_audit": recent_audit
        }

    class PublisherSettingsUpdateRequest(BaseModel):
        contact_email: Optional[EmailStr] = None
        contact_name: Optional[str] = None
        utm_opt_in: Optional[bool] = None
        rights_mode: Optional[RightsMode] = None
        excerpt_ceiling_chars: Optional[int] = Field(None, ge=100, le=2500)
        excerpt_ceiling_words: Optional[int] = Field(None, ge=15, le=400)
        actor: str = "publisher"

    @app.patch("/v1/publishers/{source_id}/settings", response_model=SourceProfile)
    def update_publisher_settings(
        source_id: str,
        request: PublisherSettingsUpdateRequest
    ) -> SourceProfile:
        """
        Publisher Self-Service Settings Management.
        Allows partner publishers to toggle UTM opt-in, update contact info,
        and request RightsMode or excerpt ceiling adjustments.
        """
        profile = storage_engine.get_source_profile(source_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Publisher source '{source_id}' not found."
            )

        changes = {}
        if request.contact_email is not None:
            profile.contact_email = request.contact_email
            changes["contact_email"] = str(request.contact_email)
        if request.contact_name is not None:
            profile.contact_name = request.contact_name
            changes["contact_name"] = request.contact_name
        if request.utm_opt_in is not None:
            profile.utm_opt_in = request.utm_opt_in
            changes["utm_opt_in"] = request.utm_opt_in
        if request.excerpt_ceiling_chars is not None:
            profile.excerpt_ceiling_chars = request.excerpt_ceiling_chars
            changes["excerpt_ceiling_chars"] = request.excerpt_ceiling_chars
        if request.excerpt_ceiling_words is not None:
            profile.excerpt_ceiling_words = request.excerpt_ceiling_words
            changes["excerpt_ceiling_words"] = request.excerpt_ceiling_words

        if request.rights_mode is not None and request.rights_mode != profile.rights_mode:
            old_mode = profile.rights_mode
            profile.rights_mode = request.rights_mode
            changes["rights_mode"] = {"from": old_mode.value, "to": request.rights_mode.value}
            # If requesting LONGER_EXCERPT, require terms review confirmation
            if request.rights_mode == RightsMode.LONGER_EXCERPT:
                profile.terms_review_status = TermsReviewStatus.PENDING
                changes["terms_review_status"] = "pending_agreement"

        storage_engine.save_source_profile(
            profile,
            actor=request.actor,
            action="publisher_settings_updated"
        )
        return profile

    class TestFeedRequest(BaseModel):
        feed_url: Optional[str] = None

    @app.post("/v1/publishers/{source_id}/test-feed", response_model=FeedValidationResult)
    def test_publisher_feed(
        source_id: str,
        request: TestFeedRequest = TestFeedRequest()
    ) -> FeedValidationResult:
        """
        On-Demand Feed Validator Integration.
        Runs the Tier 1 feed compliance audit against the publisher's registered feed URL,
        reporting actionable warnings and item preview renderings under their active RightsMode.
        """
        profile = storage_engine.get_source_profile(source_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Publisher source '{source_id}' not found."
            )

        target_url = request.feed_url or (profile.feed_urls[0] if profile.feed_urls else None)
        if not target_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No feed URL registered or provided for validation."
            )

        validator = FeedValidator()
        return validator.validate_url(target_url, source_profile=profile)

    return app


app = create_app()
