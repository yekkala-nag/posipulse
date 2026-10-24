# PosiPulse Pilot Rollout & Hardening Runbook

## Tier 1 Production Deployment, Security Guardrails & Operational SLA Runbook

---

### 1. Executive Summary & Pilot Scope

The PosiPulse Tier 1 Pilot deploys the constructive news syndication platform with a controlled cohort of 5 Tier 1 publishers spanning English and primary regional Indian languages (Hindi, Tamil, Telugu, Bengali).

#### Pilot Invariants
1. **Verbatim Excerpts Only:** Only publisher-authored headlines and verbatim excerpts clipped to source-specific ceilings (≤400 characters, ≤60 words). No public AI synthesis or machine translation of third-party copyright.
2. **Fail-Closed Positivity & Hidden Categories:** Articles classified into categories 14–18 (e.g., crime, political polemics, disasters) are held and never published or followed.
3. **Direct Canonical Links:** Readers navigate directly to publisher URLs without intermediary redirects or trampolines. Outbound UTM tracking is enabled only upon explicit publisher opt-in (`utm_opt_in = true`).
4. **Zero-PII Reader Preferences:** Reader following is anchored strictly to anonymous, rotated device UUIDs stored locally on device. No IP logging or device fingerprints.
5. **DPDP Act 2023 Compliant Newsletters:** Double opt-in verification tokens, RFC 8058 single-click unsubscription, and complete right to erasure (Section 12).
6. **Takedown SLA Guarantee:** Legal takedown requests must be fully enforced across public feeds and storage within 24 hours (operational target < 15 minutes).

---

### 2. Pre-Flight Checklist & Hardening Gates

Before admitting live traffic and scheduling feed ingestion jobs, verify each hardening gate:

| Gate | Requirement | Verification Command / Metric | Pass Criteria |
| :--- | :--- | :--- | :--- |
| **G1: Anti-SSRF** | Feed validator blocks private/loopback/cloud metadata IPs | `pytest tests/test_pilot_readiness.py -k test_ssrf` | Loopbacks (`127.0.0.1`), RFC 1918, `169.254.169.254` blocked |
| **G2: Takedown SLA** | Takedown processing latency under 24 hours | `GET /v1/admin/dashboard` -> `takedown_sla.sla_compliance_rate_percent` | 100.0% compliant |
| **G3: Hidden Categories** | Zero articles in categories 14–18 in published feeds | `GET /v1/admin/dashboard` -> `system_integrity.hidden_category_leak_count` | 0 leaked stories |
| **G4: Direct Attribution** | Links omit tracking parameters by default | `GET /v1/feed` inspection on standard partner stories | Zero tracking trampolines |
| **G5: Newsletter Opt-In** | Double opt-in confirmation required before dispatch | `pytest tests/test_newsletter.py` | Unconfirmed tokens receive 0 emails |

---

### 3. Pilot Publisher Onboarding Pipeline

#### Step 1: Self-Service Registration & Challenge Issuance
1. Candidate publisher submits details via `/v1/publishers/register`.
2. Generate time-bounded verification challenge (validity: 7 days):
   ```bash
   curl -X GET https://api.posipulse.in/v1/publishers/pub-partner-en/challenge
   ```
3. Publisher installs DNS TXT record or root HTML `<meta>` tag:
   - DNS: `_posipulse-challenge.partner.com` -> `posipulse-site-verification=<TOKEN>`
   - HTML: `<meta name="posipulse-verification" content="<TOKEN>">`

#### Step 2: Automated Verification with SSRF Guard
Execute automated verification:
```bash
curl -X POST https://api.posipulse.in/v1/publishers/pub-partner-en/verify \
  -H "Content-Type: application/json" \
  -d '{"method": "dns_txt", "admin_actor": "ops-lead"}'
```
*Note: Any attempt to point primary domains to internal subnets or cloud metadata will be rejected with `SSRF_SECURITY_VIOLATION`.*

#### Step 3: Rights Mode & Ceilings Sign-Off
Assign agreed rights mode:
- `feed_provided_excerpt`: Standard RSS `<description>` clipping (default 400 chars).
- `longer_excerpt`: Requires explicit counter-signed syndication agreement reviewed via `/v1/publishers/{id}/review`.

---

### 4. Operational Monitoring & Dashboards

The administrative control center exposes real-time telemetry via `GET /v1/admin/dashboard`:

#### Ingestion Funnel Analytics
Monitors content conversion across pipeline stages:
```json
"ingestion_funnel": {
  "total_articles_ingested": 1420,
  "stage_counts": {
    "headline_rejected": 110,
    "classified_negative": 840,
    "verification_failed": 35,
    "held_hidden_category": 45,
    "published": 390,
    "delisted": 0
  },
  "positivity_pass_rate": 0.331,
  "final_publication_rate": 0.2746,
  "fail_closed_held_count": 45
}
```

#### Takedown SLA Compliance (<24h Target)
Tracks speed and completeness of publisher copyright or privacy requests:
```json
"takedown_sla": {
  "total_requested": 4,
  "total_enforced": 4,
  "pending_requests": 0,
  "average_enforcement_time_hours": 0.12,
  "sla_compliant_count": 4,
  "sla_breached_count": 0,
  "sla_compliance_rate_percent": 100.0,
  "sla_status": "COMPLIANT"
}
```
*Alert Threshold: Any pending takedown exceeding 6 hours triggers an urgent PagerDuty alert; >24 hours is a critical compliance incident.*

#### Reader Adoption & Newsletter Telemetry (Zero-PII)
Aggregates device count trends and newsletter list health:
```json
"reader_adoption": {
  "reader_following": {
    "total_anonymous_devices": 1250,
    "top_followed_categories": [{"category_id": 1, "followers": 480}],
    "top_followed_sources": [{"source_id": "pub-partner-en", "followers": 310}]
  },
  "newsletters": {
    "total_confirmed_subscribers": 840,
    "total_pending_confirmations": 95,
    "subscribers_by_language": {
      "en": {"confirmed": 420, "pending": 40, "unsubscribed": 12},
      "hi": {"confirmed": 210, "pending": 25, "unsubscribed": 5}
    }
  }
}
```

---

### 5. Security & SSRF Guardrails

All outbound HTTP calls initiated by the platform (RSS feed polling, HTML meta tag verification, favicon retrieval) pass through `FeedValidator.is_safe_feed_url()`:

1. **Rejected Schemes:** Only `http://` and `https://` are permitted (`file://`, `ftp://`, `gopher://` rejected).
2. **Loopback Block:** `localhost`, `127.0.0.1`, `::1`, `0.0.0.0` rejected.
3. **Private IP Ranges Block:** RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) rejected.
4. **Cloud Metadata Block:** AWS/GCP/Azure instance metadata service (`169.254.169.254`) blocked.
5. **DNS Rebinding Prevention:** Hostnames are resolved to IP before connection; if the resolved IP falls in private subnets, the request is aborted.

---

### 6. Incident Response & Emergency Procedures

#### SOP-IR-1: Emergency Publisher Takedown (< 15 Minutes)
If a publisher demands immediate removal:
1. Trigger enforcement via API:
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/{source_id}/takedown \
     -H "Content-Type: application/json" \
     -d '{"action": "enforce", "reason": "Publisher copyright withdrawal request", "actor": "incident-commander"}'
   ```
2. Verify enforcement:
   - Articles delisted in `delisted_articles` table.
   - Circuit breaker tripped (`takedown_enforced`).
   - `GET /v1/sources/{source_id}` displays takedown notice.
   - Public feed omits all articles from this source.

#### SOP-IR-2: Publisher Feed Quarantining (Poisoned / Spam Feed)
If a partner feed begins publishing low-quality or policy-violating items:
```bash
curl -X POST https://api.posipulse.in/v1/publishers/{source_id}/lifecycle \
  -H "Content-Type: application/json" \
  -d '{"new_state": "quarantined", "reason": "High false positive rate / malformed feed XML", "actor": "qa-lead"}'
```

---

### 7. Post-Pilot Evaluation & Rollout Sign-Off

The pilot moves to General Availability (GA) when:
- 100% of takedowns enforced in < 24 hours over 30 consecutive days.
- Zero leaks of hidden category content (categories 14–18).
- Positive news precision > 92% validated by editorial sampling.
- Zero SSRF or unauthorized private network penetration attempts successful.
