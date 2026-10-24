# PosiPulse Tier 1 Publisher Feed Guidelines

**Version:** 1.0.0  
**Effective Date:** 2026-10-24  
**Audience:** Partner News Organizations, Editors, Technical Syndication Teams

---

## 1. Executive Summary & Core Principles

PosiPulse is a positive, constructive journalism platform serving readers across India in English and 15 scheduled languages. Our partnership model is built on transparency, copyright compliance, and maximum publisher attribution:

1. **Direct Publisher Traffic**: Every item featured on PosiPulse links directly to the publisher's original article page. PosiPulse never wraps article pages in frames, intermediate proxies, or AMP caches.
2. **Verbatim Publisher Text Only**: PosiPulse never generates AI summaries or automated rewrites of publisher stories in public feeds. Readers see the publisher's exact headline and a verbatim excerpt.
3. **Strict Rights Modes**: Publishers retain control over how their content is excerpted:
   - **`headline_only` (Default)**: PosiPulse displays only the headline, publication date, source byline, and direct link. Excerpts are omitted.
   - **`feed_provided_excerpt`**: PosiPulse displays the headline plus a bounded verbatim excerpt provided directly in the feed (capped at 100–400 characters / 15–60 words).
   - **`longer_excerpt`**: Available exclusively with written syndication agreements.
4. **Zero-Tracking by Default**: Direct links contain clean URLs. Marketing parameters (`utm_*`) are appended **only** if the publisher explicitly opts in via their verified source profile (`utm_opt_in = true`).
5. **Immediate Takedown Guarantee**: If an article or source is flagged for delisting or copyright withdrawal, PosiPulse cascades immediate removal across all feeds and blocks re-ingestion.

---

## 2. Supported Syndication Formats

PosiPulse ingests syndication feeds conforming to either of the following standard formats:

| Format | Specification | MIME Type | Recommended Encoding |
| :--- | :--- | :--- | :--- |
| **RSS 2.0** | RSS 2.0 Specification (W3C / Harvard) | `application/rss+xml`, `application/xml`, `text/xml` | UTF-8 |
| **Atom 1.0** | IETF RFC 4287 | `application/atom+xml`, `application/xml` | UTF-8 |

Feeds must start with a standard XML prolog:
```xml
<?xml version="1.0" encoding="UTF-8"?>
```

---

## 3. Feed-Level (Channel) Requirements

The top-level feed channel must provide clear publication metadata:

| Element (RSS 2.0) | Element (Atom 1.0) | Requirement | Description / Rule |
| :--- | :--- | :--- | :--- |
| `<title>` | `<title>` | **Required** | Publication or section title (e.g., *The Hindu - Science & Tech*). |
| `<link>` | `<link rel="alternate">` | **Required** | Canonical website homepage or section landing page. Must use HTTPS. |
| `<description>` | `<subtitle>` | **Required** | Concise summary of the channel's editorial scope. |
| `<language>` | `xml:lang` or `<feed xml:lang="...">` | **Required** | ISO 639-1 language code (e.g., `en`, `hi`, `ta`, `bn`, `te`, `mr`). |
| `<lastBuildDate>` | `<updated>` | **Recommended** | RFC 822 or ISO 8601 timestamp of feed generation. |
| `<image>` | `<logo>` / `<icon>` | **Recommended** | High-resolution publication logo on transparent or clean background. |

---

## 4. Item-Level Field Specifications

Each `<item>` (RSS 2.0) or `<entry>` (Atom 1.0) must represent a single, standalone news story.

### 4.1 Required Fields

1. **Headline (`<title>`)**:
   - Clean, descriptive headline reflecting the constructive news story.
   - Maximum length: 250 characters.
   - Plain text only; HTML markup, clickbait phrasing, or ALL-CAPS text should be avoided.

2. **Canonical Article URL (`<link>` / `<link rel="alternate">`)**:
   - Direct HTTPS URL to the full story on the publisher's primary domain.
   - **No Redirect Chains**: URLs must point directly to the destination story page.
   - **No Tracking Wrappers**: Do not wrap links in third-party click redirectors (e.g., Bitly, Outbrain, campaign click trackers). Clean URLs ensure reader privacy.

3. **Unique Identifier (`<guid>` / `<id>`)**:
   - Persistent unique identifier (e.g., permanent URL or UUID).
   - In RSS 2.0, if using `<guid>`, set `isPermaLink="true"` when the GUID is the permanent canonical URL.
   - Identifiers must never be recycled for different stories.

4. **Publication Timestamp (`<pubDate>` / `<published>` / `<updated>`)**:
   - Valid RFC 822 / RFC 1123 date (e.g., `Sat, 24 Oct 2026 10:30:00 +0530`) or ISO 8601 date (e.g., `2026-10-24T10:30:00+05:30`).
   - Timestamps must include an explicit timezone offset (`+05:30`, `GMT`, or `Z`).
   - **Clock Drift**: Future timestamps exceeding 2 hours are rejected as invalid.
   - **Freshness**: Stories published more than 30 days prior will not be served in active news feeds.

---

### 4.2 Content Payload & Excerpt Rules

Depending on your publisher profile's `rights_mode`, PosiPulse extracts editorial excerpts according to the following strict boundaries:

1. **Verbatim Text**: Excerpts are extracted from `<description>`, `<summary>`, or the beginning of `<content:encoded>`.
2. **Ceiling Capping**:
   - Default ceiling: **400 characters** or **60 words**, whichever is shorter.
   - PosiPulse enforces a hard ceiling at ingestion. If the feed provides 80 words, PosiPulse cleanly truncates the text at sentence or word boundaries with an ellipsis (`...`).
3. **No Article Dumping**:
   - Do **not** dump entire unedited full-text articles (> 1,200 words) into the `<description>` field unless your syndication contract specifies `RightsMode.LONGER_EXCERPT`. Feeds dumping full raw HTML bodies will trigger a validation warning.
4. **Clean Editorial Text**:
   - Injected promotional snippets, subscription banners (*"Subscribe now for Rs. 99"*), sponsored content plugs, and reader comment sections must not be included inside excerpt elements.
   - Embedded tracking pixels (e.g., `<img src="..." width="1" height="1">`) and `<script>`/`<iframe>` tags are stripped automatically by the normalizer and flagged as warnings in the validator.

---

### 4.3 Images & Multimedia Enclosures

Featured images enhance story presentation on mobile and web readers. PosiPulse supports standard enclosure and Media RSS namespaces:

```xml
<!-- Option A: Standard RSS Enclosure -->
<enclosure url="https://example.com/images/solar-breakthrough.jpg"
           length="148920"
           type="image/jpeg" />

<!-- Option B: Yahoo Media RSS (Recommended) -->
<media:content url="https://example.com/images/solar-breakthrough.jpg"
               medium="image"
               type="image/jpeg"
               width="1200"
               height="675">
    <media:title>Engineers inspect solar array at Pavagada park</media:title>
    <media:credit>Staff Photographer / Press Trust</media:credit>
</media:content>
```

#### Specifications:
- **Protocol**: HTTPS is strictly required. Non-secure `http://` image URLs are rejected.
- **Formats**: JPEG (`image/jpeg`), PNG (`image/png`), WebP (`image/webp`).
- **Minimum Dimensions**: 400 × 300 pixels.
- **Recommended Aspect Ratio**: 16:9 (e.g., 1200 × 675 px) or 4:3 (e.g., 1200 × 900 px).
- **Licensing & Credits**: Images must be original publisher photography or licensed wire imagery cleared for syndication previews.

---

### 4.4 Category Tagging & Taxonomy Mapping

Publishers may provide editorial category tags via `<category>` tags:
```xml
<category>Science &amp; Technology</category>
<category>Solar Energy</category>
```

PosiPulse automatically cross-references publisher categories with our constructive taxonomy (Taxonomy v1):

#### 13 Public Visible Categories:
1. `agriculture-rural` (Agriculture & Rural Milestones)
2. `science-technology` (Scientific Discoveries & Tech Innovation)
3. `education-skills` (Education, Literacy & Skill Development)
4. `environment-climate` (Conservation, Renewable Energy & Climate Action)
5. `sports` (Sportsmanship, Athletic Achievements & Grassroots Sports)
6. `society-community` (Grassroots Community Initiatives & Volunteering)
7. `arts-culture-heritage` (Cultural Preservation, Literature & Fine Arts)
8. `lifestyle-travel` (Constructive Living, Wellness Travel & Architecture)
9. `economy-business` (Job Creation, Ethical Business & Micro-Enterprises)
10. `health-wellness` (Medical Breakthroughs & Preventive Public Health)
11. `infrastructure-transport` (Clean Public Transit, Bridges & Water Supply)
12. `entertainment-media` (Constructive Cinema, Music & Storytelling)
13. `world-diplomacy` (Peace Treaties, Cross-Border Cooperation & Relief)

#### 5 Held / Hidden Categories (Option A - Fail-Closed):
The following categories are classified and stored for archival analysis, but are **never published** in public feeds:
- `governance-public-services`
- `law-justice-safety`
- `religion-spirituality`
- `defence-security`
- `disaster-emergency`

---

## 5. Technical & Operational Requirements

1. **HTTP Caching Headers**:
   - Feeds should send valid `ETag` and `Last-Modified` headers to support conditional HTTP GET (`If-None-Match`, `If-Modified-Since`). This reduces bandwidth and server load.
2. **Response Times**:
   - Feed servers must respond within **10 seconds**. Requests exceeding this threshold trigger retry backoffs.
3. **Polling Frequency & Rate Limits**:
   - PosiPulse polls feeds every 30 to 60 minutes.
   - PosiPulse includes an identification User-Agent:
     `Mozilla/5.0 (compatible; PosiPulseBot/1.0; +https://posipulse.in/bot)`
4. **Reliability & Uptime**:
   - Feeds experiencing 5 consecutive HTTP 5xx or connection failures enter a `degraded` circuit-breaker state.

---

## 6. Feed Pre-Flight Checklist

Before submitting a feed for onboarding:
- [ ] Valid XML syntax (checked with `python -m src.ingestion.validator --url <URL>`).
- [ ] UTF-8 encoding declared in XML prolog.
- [ ] Direct canonical URLs using HTTPS on the publisher's primary domain.
- [ ] No intermediate click-tracking redirects.
- [ ] Publication dates formatted with explicit timezone offsets.
- [ ] Clean text excerpts with no injected ads or tracking pixels.
- [ ] High-resolution HTTPS featured images provided via `<enclosure>` or `<media:content>`.
- [ ] Feed responds in under 5 seconds with valid HTTP 200 and caching headers.
