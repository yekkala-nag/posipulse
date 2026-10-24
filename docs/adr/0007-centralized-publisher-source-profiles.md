# ADR 0007: Centralized Publisher Source Profiles, Rights Modes, and Immediate Takedown Architecture

## Status
Accepted

## Context
PosiPulse aggregates news across English and 15 Indian languages under strict positive-only, fail-closed principles. Previously, publisher sources were modeled as static YAML items under `config/languages/*.yaml` with minimal metadata (`id`, `name`, `feed_url`, `homepage_url`, `language`, `health_status`).

To support Tier 1 publisher onboarding, domain verification, granular copyright management, and India DPDP Act 2023 compliance, the system requires a centralized, database-backed `SourceProfile` record satisfying the following non-negotiable requirements:
1. **Verbatim Excerpt & Rights Mode:** The app presents the headline plus a verbatim excerpt of the publisher's own text bounded by a strict ceiling (5-10 lines / 400 characters ceiling per source, never a promise; no AI summarisation or translation). Each source operates in one of three rights modes:
   - `headline_only` (default: only headline and link-out displayed; zero excerpt text)
   - `feed_provided_excerpt` (only short verbatim excerpt from RSS `<description>`, capped at the publisher's ceiling; allowed where terms permit)
   - `longer_excerpt` (only with explicit publisher permission and contract review)
2. **Excerpt Ceiling Metric:** Excerpt limits must be stored in concrete character and word counts (`excerpt_ceiling_chars`, `excerpt_ceiling_words`), never arbitrary line counts.
3. **UTM Attribution Opt-In:** Links go directly to the publisher's canonical page. Inbound links never append UTM parameters unless the publisher explicitly opts in (`utm_opt_in = True`, default: `False`).
4. **Immediate Takedown Enforcement:** A takedown request removes the publisher's items from every surface immediately and prevents re-ingestion.
5. **Reversible Schema Evolution:** All database schema changes must be versioned, idempotent, and reversible.

---

## Decision

We introduce the **Source Profile Foundation** governed by `src/schemas/source.py`, backed by SQLite/PostgreSQL storage in `src/storage/migrations.py` (Migration `003_source_profiles`), and managed via `StorageEngine` in `src/storage/db.py`.

### 1. Data Contract (`SourceProfile`)

Each source profile records:
- **`id`** (`str`): Unique source slug (e.g., `the-hindu-national`).
- **`publisher_id`** (`str`): Unique identifier for publisher entity (e.g., `the-hindu-group`).
- **`publisher_name`** (`str`): Canonical organization display name.
- **`primary_domain`** (`str`): Cleaned canonical domain for ownership verification (e.g., `thehindu.com`).
- **`feed_urls`** (`List[str]`): Monitored RSS/Atom endpoints.
- **`homepage_url`** (`str`): Publisher homepage URL for reader attribution.
- **`language`** (`str`): Primary ISO language code (e.g., `en`, `hi`, `ta`).
- **`rights_mode`** (`RightsMode`): `headline_only` (default), `feed_provided_excerpt`, or `longer_excerpt`.
- **`excerpt_ceiling_chars`** (`int`): Strict upper bound on excerpt length in characters (default: 400).
- **`excerpt_ceiling_words`** (`int`): Word count boundary (default: 60).
- **`utm_opt_in`** (`bool`): Default `False`. Only `True` if publisher explicitly requests UTM tracking.
- **`verification_status`** (`VerificationStatus`): `unverified` (default), `pending`, `verified`, `revoked`.
- **`verified_at`** (`Optional[datetime]`): Timestamp when domain ownership and reviewer checks passed.
- **`terms_review_status`** (`TermsReviewStatus`): `pending`, `reviewed_accepted`, `custom_license`, `opted_out`.
- **`trust_tier`** (`TrustTier`): `tier_1`, `tier_2`, `community`.
- **`takedown_status`** (`TakedownStatus`): `active`, `takedown_requested`, `takedown_enforced`.
- **`contact_email`** / **`contact_name`**: Operational contact for legal/compliance notices.
- **`audit_history`** (`List[SourceProfileAuditEntry]`): Immutable record of every administrative or automated status change.

### 2. Database Schema (Migration `003_source_profiles`)

```sql
CREATE TABLE source_profiles (
    id TEXT PRIMARY KEY,
    publisher_id TEXT NOT NULL,
    publisher_name TEXT NOT NULL,
    primary_domain TEXT NOT NULL,
    feed_urls_json TEXT NOT NULL,
    homepage_url TEXT NOT NULL,
    language TEXT NOT NULL,
    rights_mode TEXT NOT NULL DEFAULT 'headline_only',
    excerpt_ceiling_chars INTEGER NOT NULL DEFAULT 400,
    excerpt_ceiling_words INTEGER NOT NULL DEFAULT 60,
    utm_opt_in INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    verified_at TEXT,
    terms_review_status TEXT NOT NULL DEFAULT 'pending',
    trust_tier TEXT NOT NULL DEFAULT 'tier_2',
    takedown_status TEXT NOT NULL DEFAULT 'active',
    takedown_requested_at TEXT,
    contact_email TEXT,
    contact_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_metadata_json TEXT
);

CREATE INDEX idx_source_profiles_domain ON source_profiles(primary_domain);
CREATE INDEX idx_source_profiles_lang_ver ON source_profiles(language, verification_status);
CREATE INDEX idx_source_profiles_takedown ON source_profiles(takedown_status);

CREATE TABLE source_profile_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    details_json TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX idx_source_audit_source_id ON source_profile_audit_log(source_id);
```

### 3. Immediate Takedown Cascade
When `enforce_source_takedown(source_id)` is invoked:
1. `source_profiles.takedown_status` transitions to `'takedown_enforced'`.
2. All articles in `articles` matching `source_id` are instantly updated: `status = 'delisted'`, `publish_hold_reason = 'Publisher takedown enforced'`.
3. Ingestion fetch checks (`can_fetch_source` and `process_live_source`) fail-closed and reject any future items from that source.
4. An immutable audit record is appended to `source_profile_audit_log`.

---

## Consequences

- **Positive:** Centralized governance for all 56+ publisher feeds; copyright clarity with per-source rights modes and enforceable ceilings; instantaneous compliance with publisher opt-outs and takedowns.
- **Negative:** Schema migration required; feeds without reviewed terms default to `headline_only` to prevent copyright exposure.
