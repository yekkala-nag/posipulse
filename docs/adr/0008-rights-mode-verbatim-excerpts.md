# ADR 0008: Rights-Mode Enforced Verbatim Excerpt Presentation and Language-Aware Ceilings

## Status
Accepted

## Context
In digital news syndication, displaying publisher reporting without permission or proper licensing creates significant copyright liability and tension with content creators. PosiPulse operates on Tier 1 principles:
1. **Verbatim Excerpts Only:** The app displays the headline plus a verbatim excerpt of the publisher's own text (5–10 lines is a CEILING per source, not a promise). The public presentation does not summarise or translate publisher text.
2. **Three Granular Rights Modes:** Each publisher source operates under a strictly enforced rights mode:
   - `headline_only` (default): Only the original headline and direct link-out are shown. Verbatim excerpt is strictly `None`.
   - `feed_provided_excerpt`: Verbatim excerpt extracted strictly from RSS `<description>` or Atom `<summary>`, capped at the publisher's ceiling. Allowed where syndication terms permit.
   - `longer_excerpt`: Extended verbatim excerpt extracted from feed text up to the publisher's agreed ceiling, granted only with explicit contractual permission and terms review.
3. **Concrete Ceilings:** Excerpt ceilings must never be measured in arbitrary visual line counts (which depend on device resolution and font rendering). Instead, they are defined in concrete, verifiable character (`excerpt_ceiling_chars`) and word (`excerpt_ceiling_words`) limits per source profile.
4. **Direct Links with Privacy by Default:** Outbound links navigate directly to the publisher's canonical URL. All marketing and ad-tech tracking parameters (`utm_*`, `fbclid`, `gclid`, etc.) are stripped by default. Attribution UTM parameters are appended *only* if the publisher explicitly opts in (`utm_opt_in = True`).

---

## Decision

We introduce the **Attribution and Direct-Link Presentation Engine** (`src/presentation/attribution.py`), backed by database migration `004_verbatim_excerpts` (`src/storage/migrations.py`) and integrated into pipeline ingestion, API serialization, and client presentation.

### 1. Ingestion & Storage Architecture
- During pipeline normalization (`src/pipeline/normalizer.py`), `raw_body` is ephemerally sanitized. If `SourceProfile.rights_mode != RightsMode.HEADLINE_ONLY`, a verbatim excerpt is extracted from feed text (`description` or `summary`), truncated cleanly at sentence/word boundaries to the source's `excerpt_ceiling_chars` and `excerpt_ceiling_words`.
- In Migration `004_verbatim_excerpts`, the `verbatim_excerpt` column is added to the `articles` table in SQLite/PostgreSQL.
- Invariant: Full publisher article body text is **never** persisted in the database or exposed via API schemas. Only the bounded verbatim excerpt is stored.

### 2. AttributionEngine Contract (`src/presentation/attribution.py`)
- **`clean_url(url: str) -> str`**: Strips 17+ ad-tech and campaign tracking parameters (`utm_*`, `fbclid`, `gclid`, `mc_cid`, `igshid`, etc.) while preserving genuine slugs, article IDs, and path parameters.
- **`format_direct_link(canonical_url: str, profile: Optional[SourceProfile]) -> str`**:
  - If `profile.utm_opt_in is False` (default): Returns clean URL with zero marketing tracking parameters.
  - If `profile.utm_opt_in is True`: Appends canonical attribution parameters (`utm_source=posipulse`, `utm_medium=referral`, `utm_campaign=posipulse_news`).
- **`format_verbatim_excerpt(text: str, profile: SourceProfile) -> Optional[str]`**:
  - If `profile.rights_mode == RightsMode.HEADLINE_ONLY`: Strictly returns `None`.
  - For `FEED_PROVIDED_EXCERPT` or `LONGER_EXCERPT`: Strips HTML tags, trims whitespace, and bounds length to `profile.excerpt_ceiling_chars` and `profile.excerpt_ceiling_words`.
- **`resolve_attribution(source_id: str, profile: Optional[SourceProfile]) -> PublisherAttribution`**:
  Assembles canonical branding: `publisher_name`, `primary_domain`, `homepage_url`, `favicon_url`, `rights_mode`, `trust_tier`, `verification_status`, `utm_opt_in`.
- **`enrich_article_presentation(data: Dict, profile: Optional[SourceProfile]) -> Dict`**:
  Decorates every feed response payload with `direct_url`, `canonical_url`, enforced `verbatim_excerpt`, and typed `publisher_attribution`.

### 3. Reader Presentation Across Web and Mobile
- **Web Reader (`src/web/`):**
  - Displays `.card-publisher-header` containing publisher favicon, verified brand name, primary domain, and rights mode indicator.
  - Renders `.card-verbatim-box` quoting the publisher's exact words in distinct blockquote typography.
  - For `headline_only` sources, renders a clean notice directing readers to the original outlet.
  - "Read Full Story at [Publisher Name]" button routes directly to `direct_url` without intermediate redirects.
- **Mobile Reader (`src/mobile/`):**
  - React Native `ArticleCard` mirrors web presentation with bi-directional layout support (Urdu RTL).
  - Outbound link opens via native in-app browser (`SFSafariViewController` on iOS, `CustomTabsIntent` on Android).

---

## Consequences & Guarantees

1. **Copyright Safe Harbor:** Publishers retain complete control over text display. Headline-only partners never have text quoted on PosiPulse surfaces.
2. **Deterministic Attribution:** Links are always direct to the publisher's own site, eliminating aggregator trapping and preserving publisher traffic value.
3. **Privacy by Default:** Readers are protected from cross-site ad-tech tracking parameters unless the publisher explicitly requests standard web analytics UTM parameters.
4. **Zero Raw Body Retention:** Full publisher bodies remain strictly ephemeral during pipeline classification and are discarded before database insertion.
