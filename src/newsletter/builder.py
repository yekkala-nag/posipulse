"""
Newsletter Digest Builder Engine.
Assembles responsive HTML and plain-text weekly digests for any supported language.
Strictly enforces publisher attribution, syndication rights modes (verbatim excerpts
under ceilings, no unauthorized summarization/translation), directionality (RTL for Urdu),
and prominent direct link-outs without tracking redirects.
"""

from datetime import datetime, timedelta, timezone
import html
from typing import Any, Dict, List, Optional, Tuple

from src.config.loader import LanguageConfigRegistry
from src.newsletter.models import DigestItem, NewsletterIssue
from src.presentation.attribution import AttributionEngine
from src.schemas.article import Article, ArticleStatus
from src.schemas.source import RightsMode, SourceProfile
from src.storage.db import StorageEngine
from src.taxonomy import default_taxonomy_registry


class NewsletterDigestBuilder:
    """
    Constructs per-language weekly constructive digests from verified published stories.
    """

    def __init__(
        self,
        storage: StorageEngine,
        config_registry: Optional[LanguageConfigRegistry] = None,
        base_url: str = "https://posipulse.in",
    ):
        self.storage = storage
        self.config_registry = config_registry or LanguageConfigRegistry()
        self.base_url = base_url.rstrip("/")

    def select_top_stories_for_digest(
        self,
        language: str,
        days: int = 7,
        limit: int = 10,
    ) -> List[DigestItem]:
        """
        Retrieves the top constructive stories published within the last N days.
        Ensures fail-closed exclusion of delisted items and hidden categories.
        """
        since_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Query published articles in this language
        with self.storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.* FROM articles a
                LEFT JOIN delisted_articles d ON a.id = d.article_id
                LEFT JOIN source_profiles sp ON a.source_id = sp.id
                WHERE a.language = ?
                  AND a.status = ?
                  AND d.article_id IS NULL
                  AND (sp.takedown_status IS NULL OR sp.takedown_status = 'active')
                  AND a.published_at >= ?
                ORDER BY a.published_at DESC
                LIMIT ?
            """, (language, ArticleStatus.PUBLISHED.value, since_time, limit * 2))
            rows = cursor.fetchall()

        articles = [self.storage._row_to_article(r) for r in rows]

        # Filter out any hidden categories (Option A: held, never published in digest)
        digest_items: List[DigestItem] = []
        lang_config = self.config_registry.get(language)
        is_rtl = lang_config.is_rtl if lang_config else False

        for art in articles:
            # Check category visibility
            cat_id = art.category.primary_id if art.category else None
            cat_obj = default_taxonomy_registry.get_by_id(cat_id) if cat_id else None

            if cat_obj and not cat_obj.is_visible:
                continue

            category_name = cat_obj.get_display_name(language) if cat_obj else "Constructive"
            cat_slug = cat_obj.slug if cat_obj else "constructive"
            cat_icon = self._get_category_icon(cat_slug)

            # Retrieve publisher source profile
            profile = self.storage.get_source_profile(art.source_id)
            rights_mode = profile.rights_mode if profile else RightsMode.HEADLINE_ONLY

            # Direct URL with opt-in UTM parameters only
            direct_url = AttributionEngine.format_direct_link(
                art.canonical_url or art.url,
                profile=profile
            )

            # Verbatim excerpt clipped to ceiling
            raw_text = art.verbatim_excerpt
            verbatim_text = AttributionEngine.format_verbatim_excerpt(raw_text, profile=profile)

            item = DigestItem(
                article_id=art.id,
                headline=art.headline,
                publisher_name=profile.publisher_name if profile else (art.source_name or "Publisher"),
                primary_domain=profile.primary_domain if profile else None,
                direct_url=direct_url,
                category_id=cat_id,
                category_name=category_name,
                category_icon=cat_icon,
                rights_mode=rights_mode,
                verbatim_excerpt=verbatim_text,
                published_at=art.published_at,
                is_rtl=is_rtl,
            )
            digest_items.append(item)
            if len(digest_items) >= limit:
                break

        return digest_items

    def build_digest(
        self,
        language: str,
        issue_date: Optional[str] = None,
        days: int = 7,
        limit: int = 10,
        sample_unsubscribe_token: str = "SAMPLE_TOKEN",
    ) -> NewsletterIssue:
        """
        Compiles a weekly constructive digest issue for the given language.
        Generates both responsive HTML and plain-text email representations.
        """
        lang_config = self.config_registry.get(language)
        lang_name = lang_config.language_name_english if lang_config else language.upper()
        native_name = lang_config.language_name_native if lang_config else lang_name
        is_rtl = lang_config.is_rtl if lang_config else False

        now = datetime.now(timezone.utc)
        issue_date_str = issue_date or now.strftime("%Y-W%W")
        issue_id = f"issue-{language}-{issue_date_str.lower()}"

        items = self.select_top_stories_for_digest(language=language, days=days, limit=limit)
        article_ids = [item.article_id for item in items]

        # Subject line in appropriate language / English fallback
        subject = f"PosiPulse {native_name} Constructive Weekly ({issue_date_str}) — Verified Solutions & Progress"

        html_content = self._render_html_digest(
            items=items,
            language=language,
            lang_name=lang_name,
            native_name=native_name,
            is_rtl=is_rtl,
            issue_date=issue_date_str,
            sample_unsubscribe_token=sample_unsubscribe_token,
        )

        text_content = self._render_text_digest(
            items=items,
            language=language,
            lang_name=lang_name,
            native_name=native_name,
            issue_date=issue_date_str,
            sample_unsubscribe_token=sample_unsubscribe_token,
        )

        return NewsletterIssue(
            id=issue_id,
            language=language,
            subject=subject,
            issue_date=issue_date_str,
            article_ids=article_ids,
            html_content=html_content,
            text_content=text_content,
            sent_at=None,
            recipient_count=0,
            created_at=now,
        )

    def _render_html_digest(
        self,
        items: List[DigestItem],
        language: str,
        lang_name: str,
        native_name: str,
        is_rtl: bool,
        issue_date: str,
        sample_unsubscribe_token: str,
    ) -> str:
        """Generates clean, responsive HTML email markup with RTL support."""
        direction = "rtl" if is_rtl else "ltr"
        align = "right" if is_rtl else "left"
        font_stack = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
        if language == "ur":
            font_stack = "'Noto Nastaliq Urdu', 'Jameel Noori Nastaleeq', " + font_stack

        articles_html = ""
        for it in items:
            excerpt_html = ""
            if it.verbatim_excerpt:
                excerpt_html = f"""
                <div style="background-color: #f7fafc; border-{align}: 3px solid #38a169; padding: 10px 14px; margin: 10px 0; border-radius: 4px;">
                    <div style="font-size: 11px; text-transform: uppercase; color: #718096; font-weight: 600; margin-bottom: 4px;">
                        “ Publisher's Verbatim Excerpt
                    </div>
                    <blockquote style="margin: 0; font-size: 13px; line-height: 1.5; color: #2d3748; font-style: italic;">
                        {html.escape(it.verbatim_excerpt)}
                    </blockquote>
                </div>
                """
            elif it.rights_mode == RightsMode.HEADLINE_ONLY:
                excerpt_html = f"""
                <div style="font-size: 11px; color: #718096; margin: 6px 0;">
                    📰 Headline-only rights agreement. Read complete reporting directly on {html.escape(it.publisher_name)}.
                </div>
                """

            articles_html += f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: {align};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="display: inline-block; background-color: #ebf8ff; color: #2b6cb0; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 9999px;">
                        {it.category_icon} {html.escape(it.category_name)}
                    </span>
                    <span style="font-size: 11px; color: #718096; font-weight: 600;">
                        {html.escape(it.publisher_name)}
                    </span>
                </div>
                <h2 style="font-size: 17px; line-height: 1.35; margin: 8px 0; color: #1a202c; font-weight: 700;">
                    {html.escape(it.headline)}
                </h2>
                {excerpt_html}
                <div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid #edf2f7;">
                    <a href="{html.escape(it.direct_url)}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background-color: #2b6cb0; color: #ffffff; text-decoration: none; font-size: 12px; font-weight: 600; padding: 8px 16px; border-radius: 6px;">
                        Read Full Story on {html.escape(it.publisher_name)} ↗
                    </a>
                </div>
            </div>
            """

        if not items:
            articles_html = f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; text-align: center; color: #718096;">
                <p>No new published stories met our strict constructive verification threshold for this edition.</p>
            </div>
            """

        unsubscribe_url = f"{self.base_url}/v1/newsletter/unsubscribe?token={sample_unsubscribe_token}"
        privacy_url = f"{self.base_url}/#privacy"

        return f"""<!DOCTYPE html>
<html lang="{html.escape(language)}" dir="{direction}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PosiPulse Constructive Weekly — {html.escape(lang_name)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f7fafc; font-family: {font_stack}; -webkit-font-smoothing: antialiased; text-align: {align};">
    <div style="max-width: 640px; margin: 0 auto; padding: 24px 16px;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1a365d, #2b6cb0); border-radius: 12px; padding: 24px; color: #ffffff; margin-bottom: 20px; text-align: center;">
            <div style="font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">✨ PosiPulse</div>
            <div style="font-size: 14px; color: #bee3f8; margin-top: 4px; font-weight: 500;">
                {html.escape(native_name)} • {html.escape(lang_name)} Constructive Weekly Edition
            </div>
            <div style="display: inline-block; background: rgba(255,255,255,0.15); font-size: 11px; padding: 3px 10px; border-radius: 9999px; margin-top: 8px;">
                Week {html.escape(issue_date)} • Verified Solutions & Constructive Journalism
            </div>
        </div>

        <!-- Stories List -->
        {articles_html}

        <!-- Footer (DPDP Act & Rights Compliance) -->
        <div style="margin-top: 28px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 11px; color: #718096; line-height: 1.6;">
            <p style="margin: 4px 0;">
                <strong>Attribution & Rights Guarantee:</strong> PosiPulse does not rewrite, summarize, or translate publisher reporting in public newsletters. Excerpts are verbatim and bounded by strict publisher agreements.
            </p>
            <p style="margin: 8px 0;">
                You are receiving this digest because you confirmed subscription for {html.escape(lang_name)}.
            </p>
            <p style="margin: 8px 0;">
                <a href="{unsubscribe_url}" style="color: #e53e3e; text-decoration: underline; font-weight: 600;">One-Click Unsubscribe</a>
                &nbsp;•&nbsp;
                <a href="{privacy_url}" style="color: #4a5568; text-decoration: underline;">DPDP Act Privacy Rights</a>
            </p>
            <p style="margin: 8px 0; color: #a0aec0; font-size: 10px;">
                PosiPulse India • Non-commercial constructive journalism research project
            </p>
        </div>
    </div>
</body>
</html>"""

    def _render_text_digest(
        self,
        items: List[DigestItem],
        language: str,
        lang_name: str,
        native_name: str,
        issue_date: str,
        sample_unsubscribe_token: str,
    ) -> str:
        """Generates accessible plain-text digest representation."""
        lines = [
            f"=== POSIPULSE CONSTRUCTIVE WEEKLY ({native_name} / {lang_name}) ===",
            f"Edition: {issue_date}",
            "Verified Solutions, Progress & Constructive News",
            "----------------------------------------------------------------------",
            "",
        ]

        if not items:
            lines.append("No new published stories met our strict constructive verification threshold this week.")
            lines.append("")

        for idx, it in enumerate(items, 1):
            lines.append(f"{idx}. [{it.category_name}] {it.headline}")
            lines.append(f"   Publisher: {it.publisher_name}")
            if it.verbatim_excerpt:
                lines.append(f"   Excerpt: \"{it.verbatim_excerpt}\"")
            lines.append(f"   Read Full Story: {it.direct_url}")
            lines.append("")

        unsubscribe_url = f"{self.base_url}/v1/newsletter/unsubscribe?token={sample_unsubscribe_token}"
        lines.extend([
            "----------------------------------------------------------------------",
            "Attribution & Rights: Stories belong to original publishers. No unauthorized summaries.",
            f"One-Click Unsubscribe: {unsubscribe_url}",
            f"DPDP Act Privacy Center: {self.base_url}/#privacy",
        ])

        return "\n".join(lines)

    @staticmethod
    def _get_category_icon(slug: str) -> str:
        icons = {
            "agriculture-rural": "🌾",
            "science-tech": "🔬",
            "education-skills": "🎓",
            "environment-climate": "🌱",
            "sports-fitness": "🏆",
            "society-community": "🤝",
            "arts-culture": "🎨",
            "lifestyle-wellness": "🧘",
            "economy-business": "📈",
            "health-medicine": "🩺",
            "infrastructure-cities": "🏗️",
            "entertainment-media": "🎭",
            "world-diplomacy": "🌐",
        }
        return icons.get(slug, "📰")
