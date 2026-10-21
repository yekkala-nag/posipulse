"""
FastAPI Client API Gateway
Implements OpenAPI 3.1 specification serving mobile and web clients.
Enforces prominent original publisher attribution, language-aware directionality (RTL),
feed pagination, and DPDP Act delisting.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from src.config.loader import LanguageConfigRegistry
from src.schemas.article import Article
from src.storage.db import StorageEngine


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
    def get_metrics() -> Dict[str, Any]:
        return storage_engine.get_metrics()

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

    return app
