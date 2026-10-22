"""
FastAPI Client API Gateway
Implements OpenAPI 3.1 specification serving mobile and web clients.
Enforces prominent original publisher attribution, language-aware directionality (RTL),
feed pagination, and DPDP Act delisting.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from src.config.loader import LanguageConfigRegistry
from src.observability.metrics import metrics_collector
from src.pipeline.orchestrator import PipelineOrchestrator
from src.schemas.article import Article
from src.storage.db import StorageEngine


FIXTURE_MAP: Dict[str, tuple[str, str]] = {
    "en": ("the_hindu_sample.xml", "the-hindu-national"),
    "hi": ("bbc_hindi_sample.xml", "bbc-hindi"),
    "bn": ("anandabazar_sample.xml", "anandabazar-patrika"),
    "mr": ("loksatta_marathi_sample.xml", "loksatta-maharashtra"),
    "te": ("eenadu_telugu_sample.xml", "eenadu-andhra-pradesh"),
    "ta": ("dinamalar_tamil_sample.xml", "dinamalar-tamil-nadu"),
    "ur": ("inquilab_urdu_sample.xml", "inquilab-mumbai"),
    "gu": ("gujaratsamachar_sample.xml", "gujarat-samachar"),
    "kn": ("prajavani_kannada_sample.xml", "prajavani-kannada"),
    "or": ("sambad_odia_sample.xml", "sambad-odia"),
    "ml": ("mathrubhumi_malayalam_sample.xml", "mathrubhumi-malayalam"),
    "pa": ("jagbani_punjabi_sample.xml", "jagbani-punjabi"),
    "as": ("asomiya_pratidin_sample.xml", "asomiya-pratidin"),
    "ne": ("kantipur_nepali_sample.xml", "kantipur-nepal"),
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

        # Enrich articles with RTL directionality flag for client UI layout
        enriched = []
        for a in articles:
            data = a.model_dump()
            data["is_rtl"] = lang_config.is_rtl
            enriched.append(data)

        return {
            "articles": enriched,
            "next_cursor": next_cursor,
            "total_returned": len(enriched)
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
        data = art.model_dump()
        data["is_rtl"] = lang_config.is_rtl if lang_config else False
        return data

    @app.get("/v1/clusters/{cluster_id}")
    def get_cluster(cluster_id: str) -> Dict[str, Any]:
        cluster_articles = storage_engine.get_cluster_articles(cluster_id)
        if not cluster_articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Semantic cluster '{cluster_id}' not found."
            )

        enriched = []
        for a in cluster_articles:
            lang_config = config_registry.get(a.language)
            data = a.model_dump()
            data["is_rtl"] = lang_config.is_rtl if lang_config else False
            enriched.append(data)

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

    return app


app = create_app()
