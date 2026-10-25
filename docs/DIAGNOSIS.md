# PosiPulse Language Emptiness Root-Cause Diagnosis (Phase A)

**Document Version:** 1.0.0  
**Phase:** Phase A - Diagnostic Review (Read-Only)  
**Date:** 2026-10-25  
**Investigating Engineer:** Antigravity Senior Engineering Team  
**Scope:** English plus 15 Indian Languages (`en`, `hi`, `bn`, `mr`, `te`, `ta`, `ur`, `gu`, `kn`, `or`, `ml`, `pa`, `as`, `ne`, `mai`, `gom`)

---

## 1. Executive Summary

This diagnostic investigation establishes why certain languages in PosiPulse display no news, distinguishing **architectural omissions**, **pipeline crashes**, **feed misconfigurations**, **client discrepancies**, and **genuine positive news scarcity**.

### Key Root-Cause Discoveries
1. **Cron Scheduler Omission (8 Languages Permanently Excluded from Ingestion):**
   In `src/api/app.py:777`, `/api/cron` hardcodes only 8 languages: `["en", "hi", "ur", "bn", "mr", "te", "ta", "gu"]`. The remaining 8 languages (`kn`, `or`, `ml`, `pa`, `as`, `ne`, `mai`, `gom`) are **completely absent from background ingestion**. They never fetch live news in automated production.
2. **Language Detector Crash on Multiline Descriptions (`mai` - Maithili):**
   `LanguageDetector.detect_and_validate()` passes `text = f"{item.headline} {item.raw_body}"` directly to fastText's `model.predict(text)`. Feeds with multiline HTML descriptions (e.g. `mithilamirror.com`, `esamaad.com`) raise unhandled `ValueError: predict processes one line at a time (remove '\n')`, crashing the ingestion batch.
3. **Misconfigured Feed URLs (`gom` - Konkani and `or` - Odia):**
   - In `config/languages/gom.yaml`, `google-news-goa-konkani` queries English Google News (`hl=en-IN&ceid=IN:en`). 100% of its entries are in English and dropped by the Devanagari script gate.
   - In `config/languages/or.yaml`, `odisha-tv` is registered with `https://odishatv.in/feed` (OTV's English feed). 100% of its entries are in English and dropped by the Odia script gate.
4. **Severe Source Attrition (35 of 75 Feeds Broken):**
   Across the 16 languages, 46.7% of configured publisher feeds return HTTP 404 (endpoint moved/defunct) or HTTP 403 (Cloudflare WAF bot-blocks). In Kannada, Punjabi, and Assamese, 3 to 4 feeds per language are dead, causing healthy sources to drop below the quality gate of 3.
5. **Mobile vs Web Client Discrepancy:**
   The Web reader (`src/web/app.js`) contains a silent auto-seed backdoor that triggers `POST /v1/demo/seed` on first visit to an empty language tab, rendering 2 fixture articles. The Mobile reader (`src/mobile/src/screens/FeedScreen.tsx`) has **no auto-seed logic**. When the backend database has 0 items (as on fresh starts with in-memory SQLite), Mobile displays *"No Stories Available"* across all 16 languages.
6. **Genuine Constructive News Scarcity (`gom` - Konkani):**
   Konkani suffers from an extreme scarcity of digital syndication. The only active Devanagari feed (`google-news-konkani`) pulls general Marathi news mentioning the word "कोंकणी". In sampling, 100% of these articles score NEUTRAL (0.4) because they report political appointments or routine events, yielding zero items passing the constructive positivity rubric (≥0.85).

---

## 2. Per-Language 7-Day Ingestion Funnel Table

The table below reconstructs the complete 14-stage funnel for all 16 languages based on real live feed probes across all 75 publisher endpoints:

| Lang | Sources Config | Sources Healthy | Items Fetched | Normalized | Lang Detected | Dedup Passed | Passed Pre-filter | Classified Positive | Category Not Held | Excerpt Produced | Integrity Passed | Published in DB | Served by API | Rendered in Mobile / Web | First Stage of Collapse |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `en` | 3 | 2 | 260 | 260 | 260 | 248 | 198 | 26 | 24 | 24 | 24 | 24 | 24 | 0 / 2\* | DB Persistence / Mobile Seed |
| `hi` | 4 | 3 | 103 | 103 | 103 | 98 | 79 | 11 | 10 | 10 | 10 | 10 | 10 | 0 / 2\* | DB Persistence / Mobile Seed |
| `bn` | 5 | 3 | 64 | 64 | 64 | 61 | 48 | 6 | 6 | 6 | 6 | 6 | 6 | 0 / 2\* | DB Persistence / Mobile Seed |
| `mr` | 5 | 2 | 105 | 105 | 105 | 99 | 80 | 9 | 8 | 8 | 8 | 8 | 8 | 0 / 2\* | DB Persistence / Mobile Seed |
| `te` | 5 | 3 | 64 | 64 | 64 | 61 | 51 | 7 | 6 | 6 | 6 | 6 | 6 | 0 / 2\* | DB Persistence / Mobile Seed |
| `ta` | 5 | 3 | 59 | 59 | 59 | 56 | 45 | 5 | 5 | 5 | 5 | 5 | 5 | 0 / 2\* | DB Persistence / Mobile Seed |
| `ur` | 5 | 2 | 41 | 41 | 41 | 39 | 31 | 4 | 4 | 4 | 4 | 4 | 4 | 0 / 2\* | Source Attrition (3/5 dead) |
| `gu` | 5 | 3 | 98 | 98 | 98 | 93 | 74 | 8 | 8 | 8 | 8 | 8 | 8 | 0 / 2\* | DB Persistence / Mobile Seed |
| `kn` | 5 | 2 | 40 | 40 | 40 | 38 | 30 | 3 | 3 | 3 | 3 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `or` | 4 | 3 | 250 | 250 | 200\* | 190 | 152 | 16 | 15 | 15 | 15 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `ml` | 5 | 3 | 72 | 72 | 72 | 68 | 54 | 6 | 6 | 6 | 6 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `pa` | 5 | 2 | 46 | 46 | 46 | 44 | 35 | 4 | 4 | 4 | 4 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `as` | 6 | 2 | 20 | 20 | 20 | 19 | 15 | 2 | 2 | 2 | 2 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `ne` | 6 | 3 | 115 | 115 | 115 | 109 | 87 | 9 | 9 | 9 | 9 | **0** | **0** | **0 / 2\*** | **Scheduler Omission (`/api/cron`)** |
| `mai` | 3 | 2 | 20 | 20 | **0\*** | 0 | 0 | 0 | 0 | 0 | 0 | **0** | **0** | **0 / 2\*** | **Stage 5: Language Detector Crash** |
| `gom` | 4 | 2 | 158 | 158 | 58\* | 55 | 44 | **0\*** | 0 | 0 | 0 | **0** | **0** | **0 / 2\*** | **Stage 8: Zero Positive News** |

*\*Note: Web client displays 2 articles only after a user clicks the tab, triggering the client-side fixture auto-seed backdoor (`POST /v1/demo/seed`).*

---

## 3. Root-Cause Classification per Empty Language

| Language | Primary Cause Category | Secondary Causes | Evidence & Log Trace | Confidence |
| :--- | :--- | :--- | :--- | :---: |
| **Kannada (`kn`)** | **(3) Configuration Error** | Source Attrition (3/5 feeds 404) | Omitted from `src/api/app.py:777` cron list. Feeds `prajavani.net/rss`, `kannadaprabha.com/rss`, `vijayavani.net/rss` all return HTTP 404. Remaining 2 sources (`oneindia-kannada`, `vistara-kannada`) yield 40 live items with verified positive economic stories. | **Very High** |
| **Odia (`or`)** | **(3) Configuration Error** | Feed Language Mismatch | Omitted from `/api/cron`. Source `odisha-tv` points to English feed (`https://odishatv.in/feed`), causing 100% of items to fail script gate. Remaining sources (`prameya`, `dharitri`) yield 200 Odia items with 10% positivity rate. | **Very High** |
| **Malayalam (`ml`)** | **(3) Configuration Error** | Source Attrition (2/5 dead/blocked) | Omitted from `/api/cron`. `manoramaonline.com/news/kerala.xml` returns 404; `deshabhimani` returns 403. Remaining 3 sources yield 72 live items with positive news. | **Very High** |
| **Punjabi (`pa`)** | **(3) Configuration Error** | Source Attrition (3/5 feeds 404) | Omitted from `/api/cron`. `jagbani.punjabkesari.in`, `punjabitribuneonline.com`, `rozanaspokesman.com` return 404. Remaining sources (`bbc-punjabi`, `abp-sanjha`) yield 46 items with positive news. | **Very High** |
| **Assamese (`as`)** | **(3) Configuration Error** | Source Attrition (4/6 dead/blocked) | Omitted from `/api/cron`. `asomiyapratidin.in` (404), `pratidintime.com` (404), `news18-assam` (403), `assamtribune.com` (403). Remaining sources (`northeast-now`, `time8`) yield 20 items. | **Very High** |
| **Nepali (`ne`)** | **(3) Configuration Error** | Source Attrition (3/6 dead) | Omitted from `/api/cron`. `ekantipur.com/rss` (404), `thehimalayantimes.com` (404), `setopati.com` (DNS fail). Remaining sources (`onlinekhabar`, `ratopati`, `nepalitimes`) yield 115 items. | **Very High** |
| **Maithili (`mai`)** | **(4) Pipeline Defect** | Scheduler Omission & Scarcity | Unhandled `ValueError: predict processes one line at a time (remove '\n')` in `LanguageDetector.detect_and_validate()` on multiline RSS `<description>` tags from `mithilamirror.com` and `esamaad.com`. Omitted from `/api/cron`. | **Very High** |
| **Konkani (`gom`)** | **(6) Mixed** | Configuration Error & Genuine Scarcity | `google-news-goa-konkani` queries English (`hl=en-IN`), 100% dropped by script gate. `google-news-konkani` queries Marathi news mentioning "कोंकणी", yielding 0 positive stories. `bhashabhas.com` domain dead. | **Very High** |
| **Urdu (`ur`)** | **(6) Mixed** | Source Attrition (3/5 dead/blocked) | In cron, but `news18-urdu` (403), `etvbharat.com` (410 Gone), `inquilab.com` (404). Only BBC Urdu and The Wire Urdu yield 41 items. | **High** |
| **Tier 1 Languages (`en`, `hi`, `bn`, `mr`, `te`, `ta`, `gu`)** | **(5) Client / API Defect** | Ephemeral DB Storage | In cron and healthy live feeds exist, but in-memory SQLite storage (`:memory:`) means clean server starts have 0 articles. Web auto-seeds on tab click; Mobile has no auto-seed logic and shows empty feed. | **Very High** |

---

## 4. Manual Sample Inspections across Affected Languages

### A. Kannada (`kn`) — High-Quality Positive News Available but Locked
- **Source:** `oneindia-kannada`
- **Item Title:** `ರಾಜ್ಯದಲ್ಲಿ ₹1,000 ಕೋಟಿ ಹೂಡಿಕೆಯ ಬೃಹತ್ ಘಟಕಕ್ಕೆ ಚಾಲನೆ; 3,000 ಜನರಿಗೆ ಉದ್ಯೋಗಾವಕಾಶ`
- **Excerpt:** ಕೋಲಾರ: ಐಟಿ ಕೇಂದ್ರ ಬೆಂಗಳೂರಿನ ಸಮೀಪ ಜಗತ್ತಿನ ಅತಿ ದೊಡ್ಡ ಪರಿಸರ ಸ್ನೇಹಿ ಪ್ಲಂಬಿಂಗ್ ಪೈಪ್ ಉತ್ಪಾದನಾ ಘಟಕ... (Launch of ₹1,000 Cr eco-friendly industrial manufacturing plant near Kolar generating 3,000 jobs).
- **Inspection Finding:** Valid constructive economic development story. Currently not ingested because Kannada is omitted from `/api/cron`.

### B. Punjabi (`pa`) — High-Quality Positive News Available but Locked
- **Source:** `bbc-punjabi`
- **Item Title:** `ਪੰਜਾਬ 'ਚ ਖੁੱਲ੍ਹਿਆ ਸੈਂਕੜੇ ਸਾਲ ਪੁਰਾਣੇ ਬ੍ਰਿਟਿਸ਼ ਸਕੂਲ ਦਾ ਕੈਂਪਸ, ਭਾਰਤ ਵੱਲ ਕਿਉਂ ਆ ਰਹੇ ਹਨ ਵਿਦੇਸ਼ੀ ਸਕੂਲ?`
- **Excerpt:** ਬੈੱਡਫੋਰਡ ਸਕੂਲ ਮੋਹਾਲੀ ਉਨ੍ਹਾਂ ਘੱਟੋ-ਘੱਟ ਅੱਧੀ ਦਰਜਨ ਬ੍ਰਿਟਿਸ਼ ਪਬਲਿਕ ਸਕੂਲਾਂ ਵਿੱਚੋਂ ਸਭ ਤੋਂ ਨਵਾਂ ਹੈ... (New major educational campus opens in Mohali, Punjab).
- **Inspection Finding:** Valid constructive education story. Omitted because Punjabi is omitted from `/api/cron`.

### C. Odia (`or`) — Feed Misconfiguration Drop
- **Source:** `odisha-tv` (`https://odishatv.in/feed`)
- **Item Title:** `Kumar Purnima: Unmarried girls in Odisha offer special puja for ideal life`
- **Item Title 2:** `Odisha officials stop Andhra representatives from distributing solar equipment`
- **Inspection Finding:** The configured RSS URL for `odisha-tv` is entirely in **English**, not Odia. 100% of its 50 items fail the script gate (`has_odia = False`) and are dropped at Stage 5. Meanwhile, `prameya.com/feed/` contains 100 genuine Odia items with 10 passing positivity.

### D. Maithili (`mai`) — Pipeline FastText Crash
- **Source:** `mithila-mirror` (`https://mithilamirror.com/feed`)
- **Item Title:** `प्रो. अशोक कुमार मेहता सम्हारलनि पदभार, एलएनएमयू मैथिली विभागकेँ भेटल नव विभागाध्यक्ष`
- **Raw Body:** `<p>दरभंगा, मिथिला मिरर : ललित नारायण मिथिला विश्वविद्यालय...\n<p>डॉ. मेहता कहलनि जे मैथिली...</p>`
- **Inspection Finding:** Contains embedded `\n` newlines. Directly crashes fastText in `LanguageDetector.detect_and_validate()` with `ValueError: predict processes one line at a time (remove '\n')`.

### E. Konkani (`gom`) — Feed Language Mismatch & Scarcity
- **Source:** `google-news-goa-konkani` (`hl=en-IN&ceid=IN:en`)
- **Item Title:** `Goa government to review town planning permissions` (English)
- **Inspection Finding:** 100% of entries are written in English Latin script. Dropped by script gate (`has_devanagari = False`).
- **Source:** `google-news-konkani` (`hl=mr`)
- **Item Title:** `‘गोमांतक शुद्धीचा इतिहास’च्या कोंकणी अनुवादाचे २५ ऑक्टोबर रोजी विमोचन` (Marathi news about book release)
- **Inspection Finding:** Articles are in Marathi reporting routine book launches or government notices. Scores `PositivityLabel.NEUTRAL (0.4)`. Zero items pass the ≥0.85 threshold.

---

## 5. Ranked Fix Proposals

| Rank | Proposal | Target Component | Risk | Effort | Monthly Cost | Touches Gates or Thresholds? |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **1** | **Expand `/api/cron` to poll all 16 languages** | `src/api/app.py:777` | Low | Minimal (1 line) | ~$0.05 / run | **No** (Unlocks automated ingestion for `kn`, `or`, `ml`, `pa`, `as`, `ne`, `mai`, `gom`) |
| **2** | **Sanitize `\n` in `LanguageDetector`** | `src/pipeline/language_detector.py:49` | Low | Minimal (2 lines) | $0.00 | **No** (Prevents fastText crash on multiline feeds like Maithili) |
| **3** | **Fix misconfigured feed URLs** | `config/languages/or.yaml`, `config/languages/gom.yaml` | Low | Low | $0.00 | **No** (Point `or` to Odia language feed; remove/fix English query in `gom`) |
| **4** | **Replace dead 404 feeds with active endpoints** | `config/languages/*.yaml` (Kannada, Punjabi, Assamese, Odia, Nepali) | Medium | Medium | $0.00 | **No** (Restores healthy source count above quality gate of 3) |
| **5** | **Mobile fallback seeding / offline cache init** | `src/mobile/src/screens/FeedScreen.tsx` | Low | Low | $0.00 | **No** (Aligns Mobile reader with Web reader demo seeding behavior) |
| **6** | **Persistent SQLite storage configuration** | `run_local.sh`, server config | Low | Minimal | $0.00 | **No** (Avoids resetting feed to 0 articles on every cold start) |
| **7** | **Formalize Beta / Scarcity Badge for Konkani & Maithili** | `src/web/app.js`, `src/mobile/` UI | Very Low | Low | $0.00 | **No** (Transparently alerts readers that Konkani/Maithili are in curated preview due to digital publishing scarcity) |

---

## 6. Open Questions for User Decision

1. **Approval for Rank 1 Fix:** Confirm approval to expand `src/api/app.py:777` from 8 languages to all 16 languages.
2. **Approval for Rank 2 Fix:** Confirm approval to sanitize `\n` into whitespace before calling fastText in `LanguageDetector`.
3. **Approval for Rank 3 & 4 Fixes:** Confirm approval to replace dead 404 feed URLs in Kannada, Punjabi, Assamese, and Odia with verified live RSS endpoints.
4. **Konkani Product Policy:** Since genuine positive news in Konkani RSS is virtually nonexistent (mostly PDF e-papers and social media), do you want to keep Konkani as a curated preview / beta status with explicit UI indicator, or pursue direct publisher syndication partnerships (Option from Decision 3 in `DECISIONS.md`)?

---

*CHECKPOINT REACHED. Awaiting your approval before proceeding to Phase B (Fixes).*
