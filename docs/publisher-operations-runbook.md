# PosiPulse Publisher Operations Runbook

## Tier 1 Publisher Operations, Syndication Verification & Compliance Manual

---

### 1. Overview & Architecture Invariants

PosiPulse operates under non-negotiable architectural constraints to protect publisher copyright and reader trust across English and 15 Indian languages:
1. **Verbatim Excerpts Only:** Public interfaces show the headline plus a verbatim excerpt of the publisher's own text bounded by source ceilings (5–10 lines / 400 characters ceiling per source, never a promise). The platform never synthesises or translates publisher text in public reader views.
2. **Rights Modes per Source:** Every source has a strict rights mode:
   - `headline_only` (default: only headline and link-out; verbatim excerpt is strictly omitted)
   - `feed_provided_excerpt` (short verbatim excerpt from RSS `<description>`, capped at the publisher's ceiling; allowed where terms permit)
   - `longer_excerpt` (only with explicit publisher permission and legal contract review)
3. **Fail-Closed Constructive Filters:** 13 visible categories (Taxonomy v1); 5 hidden categories are held and never published (Option A).
4. **Direct Linking Privacy:** All outbound links navigate directly to the publisher's canonical page. Tracking parameters are stripped by default unless the publisher explicitly opts in (`utm_opt_in = True`).
5. **Immediate Takedown SLA:** Takedown requests delist all publisher stories across all surfaces immediately and lock future ingestion permanently.

---

### 2. Standard Operating Procedures (SOPs)

#### SOP 1: Publisher Onboarding & Domain Verification

When a candidate publisher applies or is enrolled:

1. **Registration:**
   Submit or receive the registration payload:
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/register \
     -H "Content-Type: application/json" \
     -d '{
       "publisher_name": "The Hindu",
       "primary_domain": "thehindu.com",
       "contact_email": "syndication@thehindu.co.in",
       "feed_urls": ["https://thehindu.com/news/national/feeder/default.rss"],
       "language": "en",
       "rights_mode": "feed_provided_excerpt",
       "requested_excerpt_chars": 400,
       "requested_excerpt_words": 60
     }'
   ```
   *Response includes `source_id` (e.g. `pub-thehindu-com-en`) and a cryptographically generated challenge.*

2. **Domain Challenge Issuance:**
   Retrieve the challenge record:
   ```bash
   curl https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/challenge
   ```
   Provide the publisher newsroom with either:
   - **DNS TXT Record:** Host `@` or `thehindu.com` with value `posipulse-site-verification=<TOKEN>`
   - **HTML `<meta>` Tag:** `<meta name="posipulse-verification" content="<TOKEN>">` on root homepage.

3. **Verification Execution:**
   Trigger verification check:
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/verify \
     -H "Content-Type: application/json" \
     -d '{"method": "dns_txt"}'
   ```
   *If successful, `verification_status` transitions to `verified`.*

4. **Manual Admin Override (Emergency / Fast-Track):**
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/verify \
     -H "Content-Type: application/json" \
     -d '{
       "method": "manual_admin",
       "admin_actor": "editorial-director@posipulse.in",
       "notes": "Verified via institutional newsroom agreement"
     }'
   ```

---

#### SOP 2: Feed Compliance Audits & Troubleshooting

All candidate feeds must satisfy the Tier 1 Syndication Guidelines (`docs/publisher-feed-guidelines.md`).

1. **CLI Feed Audit:**
   Run the CLI validator against any remote feed or local XML file:
   ```bash
   python -m src.ingestion.validator https://partner.org/rss.xml --rights-mode feed_provided_excerpt
   ```

2. **On-Demand API Audit via Dashboard:**
   Execute live audit through the API:
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/test-feed
   ```

3. **Common Validation Failures & Fixes:**
   - **Tracking Parameters in Item Links (`WARNING: TRACKING_QUERY_PARAMS`):**
     *Root Cause:* Feed items contain `utm_source`, `fbclid`, or campaign slugs.
     *Action:* PosiPulse's AttributionEngine strips these automatically; advise publisher to provide clean canonical URLs in `<guid isPermaLink="true">`.
   - **Malformed XML / Bad Entities (`ERROR: MALFORMED_XML`):**
     *Root Cause:* Unescaped `&` or invalid characters in feed body.
     *Action:* Notify publisher technical desk to wrap descriptions in `<![CDATA[ ... ]]>`.
   - **Script Injection (`ERROR: SCRIPT_INJECTION`):**
     *Root Cause:* `<script>` tag or tracking pixel detected in feed body.
     *Action:* Immediate hard blocker; alert publisher that executable scripts are forbidden under syndication safety guidelines.

---

#### SOP 3: RightsMode Adjustments & Legal Licensing Workflow

Publishers can manage their settings via the Self-Service Dashboard (`/publisher`):

1. **Requesting Extended Excerpts (`longer_excerpt`):**
   ```bash
   curl -X PATCH https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/settings \
     -H "Content-Type: application/json" \
     -d '{
       "rights_mode": "longer_excerpt",
       "excerpt_ceiling_chars": 800,
       "excerpt_ceiling_words": 120,
       "actor": "syndication@thehindu.co.in"
     }'
   ```
   *Note: Requesting `longer_excerpt` automatically moves `terms_review_status` to `pending` until formal legal agreement is executed.*

2. **Admin Terms Approval:**
   Once legal agreement is countersigned:
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/review \
     -H "Content-Type: application/json" \
     -d '{
       "review_state": "active",
       "terms_status": "reviewed_accepted",
       "actor": "legal-counsel@posipulse.in",
       "reason": "Countersigned Tier 1 Syndication License v2"
     }'
   ```

---

#### SOP 4: Immediate Takedown & Cascading Delisting Execution

In the event of a copyright notice, retraction, or legal takedown request:

1. **Trigger Immediate Takedown:**
   ```bash
   curl -X POST https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/review \
     -H "Content-Type: application/json" \
     -d '{
       "review_state": "takedown_requested",
       "actor": "compliance@posipulse.in",
       "reason": "Formal publisher copyright withdrawal notice"
     }'
   ```

2. **Cascade SLA & Verification:**
   - `source_profiles.takedown_status` immediately transitions to `takedown_enforced`.
   - Every historical article linked to `source_id` is updated to `status = 'delisted'` in a single atomic transaction.
   - All caching layers flush the source's items immediately.
   - Ingestion circuit breaker permanently trips; future fetcher cycles discard items from this source.

3. **Verify Takedown Completion:**
   Query the dashboard endpoint to confirm zero active items:
   ```bash
   curl https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/dashboard
   ```
   *Assert: `"circuit_breaker_tripped": true` and `"total_published": 0`.*

---

#### SOP 5: Privacy & DPDP Act 2023 Compliance Audits

1. **Auditing K-Anonymity Suppression:**
   Query the analytics endpoint:
   ```bash
   curl https://api.posipulse.in/v1/publishers/pub-thehindu-com-en/analytics
   ```
   *Confirm that any bucket or dimension with fewer than 5 events is suppressed or rolled into `"Other (suppressed < 5)"`.*

2. **Individual Article Delisting (Right to Erasure):**
   ```bash
   curl -X POST https://api.posipulse.in/v1/privacy/delist \
     -H "Content-Type: application/json" \
     -d '{
       "article_id": "art-12345",
       "requester_name": "Data Principal",
       "requester_email": "reader@example.com",
       "reason": "DPDP Section 12 Right to Erasure request"
     }'
   ```
