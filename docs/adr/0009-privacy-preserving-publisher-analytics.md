# ADR 0009: Privacy-Preserving Pre-Aggregated Hourly Analytics and DPDP 2023 Safe Harbor

## Status
Accepted

## Context
Tier 1 news publishers require actionable traffic analytics (impressions, outbound clicks, click-through rates across languages and constructive news categories) to evaluate syndication value and audience reach. However, user privacy is non-negotiable under the **India Digital Personal Data Protection (DPDP) Act 2023** and global data privacy standards.

Existing analytics patterns frequently rely on raw event-level audit tables storing IP addresses, User-Agent strings, cookie UUIDs, and granular millisecond timestamps. Such architectures create severe legal liability:
- Storing IP addresses and client identifiers constitutes collection of digital personal data requiring explicit consent notices and data principal rights workflows.
- Granular event streams allow deanonymization of reading habits through statistical fingerprinting.

To reconcile publisher observability with strict privacy invariants, PosiPulse requires an analytics architecture providing:
1. **Zero Personal Data Collection:** No IP addresses, device identifiers, User-Agents, or session tokens are collected or stored.
2. **Pre-Aggregated Hourly Bucketing:** Raw events are never written to disk; counts are directly aggregated into 1-hour time buckets.
3. **K-Anonymity Enforcement:** Any metric bucket or dimension breakdown with fewer than 5 events is suppressed to prevent audience re-identification.
4. **Immediate Delisting Compliance:** If a story is delisted under DPDP Section 12 (Right to Erasure), analytics records must not expose residual story-level traces.

---

## Decision

We introduce the **Privacy-Preserving Publisher Analytics Engine** backed by Migration `005_publisher_analytics` (`src/storage/migrations.py`) and integrated into `src/storage/db.py` and `src/api/app.py`.

### 1. Database Schema (`publisher_analytics_hourly`)
```sql
CREATE TABLE publisher_analytics_hourly (
    source_id TEXT NOT NULL,
    article_id TEXT NOT NULL,
    language TEXT NOT NULL,
    category_id INTEGER,
    time_bucket TEXT NOT NULL, -- Format: YYYY-MM-DDTHH:00:00Z (strictly 1-hour resolution)
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, article_id, time_bucket)
);

CREATE INDEX idx_publisher_analytics_source_time
ON publisher_analytics_hourly (source_id, time_bucket);
```

### 2. Zero-Retention Direct Counter Increment
Neither impressions nor outbound clicks generate event log rows. Instead, events execute atomic SQL upserts against the current hourly bucket:
```sql
INSERT INTO publisher_analytics_hourly (
    source_id, article_id, language, category_id, time_bucket, impressions, clicks
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source_id, article_id, time_bucket)
DO UPDATE SET
    impressions = impressions + excluded.impressions,
    clicks = clicks + excluded.clicks;
```
- **Impression Logging:** When `/v1/feed` serves verified articles, an anonymous batch impression increment is queued via `record_impressions_batch`.
- **Outbound Click Logging:** When a reader clicks "Read Full Story at [Publisher]", the client asynchronously fires `POST /v1/analytics/click`, incrementing the `clicks` counter.

### 3. K-Anonymity Query Layer (`StorageEngine.get_publisher_analytics`)
When aggregating analytics for publisher dashboards (`GET /v1/publishers/{source_id}/analytics` or `GET /v1/publishers/{source_id}/dashboard`), the query engine enforces $k$-anonymity ($k = 5$ by default):
- If the total volume for a source or article is less than $k$, individual counts are suppressed and flagged as `k_anonymity_suppressed: true`.
- Breakdown slices (languages, categories) below $k$ are suppressed and rolled into an aggregated `"Other (suppressed < 5)"` category.

---

## Consequences & Guarantees

1. **Complete Immunity from Data Breaches:** Because the database contains only aggregate counters bucketed by hour without any client identifiers, a database dump reveals zero personal data.
2. **DPDP Act 2023 Compliance:** Satisfies India DPDP Section 7 (Legitimate Uses) and eliminates the need for consent banners or cookie popups.
3. **High Write Throughput:** Atomic upserts on `(source_id, article_id, time_bucket)` scale efficiently with minimal storage footprint compared to unbounded event logs.
4. **Publisher Transparency:** Newsrooms gain accurate referral verification without compromising the privacy of their readers.
