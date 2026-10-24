# ADR 0010: Per-Language Newsletters, Double Opt-In & ESP Recommendation

## Status
Accepted

## Context
PosiPulse curates constructive, verified news in English and 15 Indian languages. While real-time feed consumption on web and mobile provides immediate access to positive news, reader retention and habit formation require scheduled weekly summaries. However, email distribution in multilingual India presents unique regulatory, technical, and syndication challenges:

1. **Digital Personal Data Protection (DPDP) Act 2023 Compliance:**
   - Explicit consent requirement: Subscribers must explicitly opt-in with a double confirmation step before receiving recurring digests.
   - Right to withdraw consent (Section 6(4)): Unsubscribing must be as easy as subscribing, supporting one-click unsubscribe links and RFC 8058 email client headers (`List-Unsubscribe`, `List-Unsubscribe-Post`).
   - Right to erasure (Section 12): Subscribers can permanently purge their email address and subscription history.
   - Data localization: Indian personal data (subscriber email addresses and reading preferences) should preferably be processed in-country.

2. **Publisher Rights & Syndication Ceilings:**
   - Newsletters must never republish complete reporting, create derivative translations, or run abstractive generative summaries of publisher content.
   - For `headline_only` sources, digests render only the headline, publisher name, and direct canonical link-out.
   - For `feed_provided_excerpt` and `longer_excerpt` sources, verbatim excerpts are strictly bounded by character/word ceilings configured per publisher profile.
   - Direct links must point directly to the original publisher article without intermediate tracking wrappers.

3. **Multilingual Typography & RTL Directionality:**
   - 16 distinct language editions (English, Hindi, Bengali, Marathi, Telugu, Tamil, Urdu, Gujarati, Kannada, Odia, Malayalam, Punjabi, Assamese, Nepali, Maithili, Konkani).
   - Urdu (`ur`) requires right-to-left layout (`dir="rtl"`), right-aligned text, and appropriate Nastaliq/Naskh font stacks, while other languages use LTR.

4. **Email Service Provider (ESP) Deliverability & Scale:**
   - Indian ISP deliverability (Gmail, Yahoo, Rediffmail, Netcore/Jio) requires DKIM, SPF, DMARC, and Indian IP reputation.
   - Cost efficiency when distributing millions of weekly digests.

---

## ESP Evaluation & Comparison

| Criterion | AWS SES (Simple Email Service) | Postmark | SendGrid | Self-Hosted Postfix |
| :--- | :--- | :--- | :--- | :--- |
| **Data Residency** | **Native Mumbai (`ap-south-1`)** | US / EU only | US only | On-premise Indian VPS |
| **Pricing** | **$0.10 / 1,000 emails** ($0.0001/email) | $1.50 / 1,000 emails | $0.80 / 1,000 emails | Server cost only (~$50/mo) |
| **Unicode & Indian Script** | Full UTF-8 support; native headers | Full UTF-8 support | Full UTF-8 support | Configuration overhead |
| **RFC 8058 One-Click** | Native header injection | Native header injection | Native header injection | Manual config |
| **Deliverability Reputation** | High (shared or dedicated IP) | Very high | Moderate to high | Low (IP warmup challenge) |
| **DPDP Compliance** | **Full compliance in `ap-south-1`** | Requires cross-border safeguards | Requires cross-border safeguards | Full control |

### Recommendation: AWS SES (Mumbai `ap-south-1`)
AWS SES in Mumbai (`ap-south-1`) is selected as the primary production ESP:
1. **In-Country Data Processing:** Complies directly with Indian DPDP Act data sovereignty expectations.
2. **Cost Advantage:** At 100,000 subscribers receiving weekly digests (400,000 emails/month), SES costs ~$40/month, compared to $600/month on Postmark.
3. **DKIM / SPF / DMARC:** Easily automated via AWS Route53 DNS for `posipulse.in`.

---

## Architectural Decision

1. **Pluggable ESP Interface:**
   - Implemented `EmailServiceProvider` abstract interface in [src/newsletter/esp.py](file:///Users/nyakkala/Documents/GitHub/posipulse/src/newsletter/esp.py).
   - `MockEmailProvider`: In-memory provider capturing all outgoing emails for automated unit tests and CI/CD pipelines.
   - `SESEmailProvider`: Production AWS SES implementation with Mumbai region default and custom RFC 8058 header injection.

2. **Double Opt-In Subscription Workflow:**
   - `POST /v1/newsletter/subscribe`: Records subscription with status `pending_confirmation`, generates cryptographic confirmation token (`secrets.token_urlsafe(32)`), and dispatches confirmation email.
   - `GET /v1/newsletter/confirm?token=...`: Verifies token and transitions subscriber to `confirmed`, recording `confirmed_at` timestamp.

3. **Single-Click Unsubscribe (RFC 8058):**
   - Every outgoing email contains a unique unsubscribe link with a secure token: `GET /v1/newsletter/unsubscribe?token=...` and `POST /v1/newsletter/unsubscribe`.
   - Headers: `List-Unsubscribe: <https://posipulse.in/v1/newsletter/unsubscribe?token=...>`, `List-Unsubscribe-Post: List-Unsubscribe=One-Click`.

4. **Right to Erasure (DPDP Section 12):**
   - `DELETE /v1/newsletter/subscription?email=...`: Permanently wipes all email records and tokens from the database.

5. **Digest Assembly Engine:**
   - Implemented `NewsletterDigestBuilder` in [src/newsletter/builder.py](file:///Users/nyakkala/Documents/GitHub/posipulse/src/newsletter/builder.py).
   - Compiles weekly issues per language, selecting published constructive stories, enforcing category visibility rules (hidden categories 14–18 held and excluded), formatting verbatim excerpts under publisher ceilings, and rendering responsive HTML and plain-text templates with RTL support for Urdu.

---

## Consequences

- **Positive:**
  - Zero unsolicited spam; 100% verified subscriber base.
  - Fully compliant with the Indian DPDP Act 2023.
  - Publishers receive high-intent, qualified outbound traffic directly to their canonical domains.
  - Fast, responsive email rendering across all 16 supported languages.

- **Trade-offs:**
  - Double opt-in introduces drop-off during signup (~15–25%), but guarantees high inbox placement and zero spam complaints.
  - Multi-language template maintenance requires regular testing across Indian email clients.
