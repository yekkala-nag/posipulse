# ADR 0006: Controlled News Category Taxonomy & Option A Hidden-Category Policy

## Status
Proposed (Approved for Checkpoint Review)

## Context
Posipulse aggregates and delivers constructive news in English and 15 Indian languages under strict precision-first, positive-only criteria. Prior to this design, items carried an unversioned, ad-hoc string label (e.g., `"Science/Tech"`, `"Sports"`, `"Civic"`) that lacked hierarchical subcategories, multilingual localized naming, or standardized interoperability with international news exchange standards.

To scale navigation, feeds, and client experiences across languages without diluting the core positive-only mandate, the system requires a controlled, immutable category taxonomy satisfying the following non-negotiable requirements:
1. **Precision-First Fail-Closed:** Category classification must never cause an item to be published that the positivity rubric or integrity check would have excluded.
2. **Crime Remains Excluded:** No "Crime" category may exist; crime reporting is strictly excluded by the positivity rubric.
3. **Verbatim Excerpt Invariant:** Publisher text remains an unedited, verbatim excerpt with canonical link-out attribution; taxonomy logic must not introduce summarization or rewriting.
4. **Stable Permanent Identifiers:** Category IDs ($1$–$18$) and subcategory IDs are permanently allocated and never reused or re-assigned.
5. **Option A Hidden-Category Policy:** Categories sensitive to positive news framing or requiring future editorial gates (IDs 14–18: Governance, Law/Justice, Religion, Defence, Disaster) are classified and stored, but **never** published or served on any public surface (feeds, clusters, notifications, search, caches). Ambiguity between visible and hidden categories must hold the item.
6. **Feature Flagging & Rollback:** The taxonomy sits behind a runtime feature flag with a documented rollback path.

---

## Decision

We establish **Taxonomy Version 1 (v1.0.0)** as versioned configuration data in [`config/taxonomy/v1.json`](file:///Users/nyakkala/Documents/GitHub/posipulse/config/taxonomy/v1.json) governed by [`src/taxonomy/models.py`](file:///Users/nyakkala/Documents/GitHub/posipulse/src/taxonomy/models.py) and [`src/taxonomy/registry.py`](file:///Users/nyakkala/Documents/GitHub/posipulse/src/taxonomy/registry.py).

### 1. Controlled Taxonomy Architecture (18 Categories)

#### Visible at Launch (13 Categories):
1. **Agriculture & Rural (ID 1):** Farming practices, crops & yields, irrigation, dairy & fisheries, rural enterprise, cooperatives.
2. **Science & Technology (ID 2):** Research & discovery, space, AI & software, electronics & telecom, innovation, digital public infrastructure.
3. **Education & Skills (ID 3):** Results & admissions, scholarships, research institutions, skilling, edtech, schools.
4. **Environment & Climate (ID 4):** Wildlife & conservation, renewable energy, water & rivers, waste & cleanup, forests.
5. **Sports (ID 5):** Cricket, hockey, football, kabaddi, athletics, Olympic & Paralympic, badminton/tennis/chess, grassroots.
6. **Society & Community (ID 6):** Inspiring individuals, social enterprise, volunteering, women & child welfare, inclusion & accessibility, senior citizens, youth.
7. **Arts, Culture & Heritage (ID 7):** Festivals, crafts, heritage sites, languages & literature, museums, folk traditions.
8. **Lifestyle & Travel (ID 8):** Tourism, food & cuisine, fashion, home, hobbies.
9. **Economy & Business (ID 9):** Startups, jobs, MSMEs & trade, banking, consumer, corporate.
10. **Health & Wellness (ID 10):** Medical research, public health programs, hospitals & care, nutrition & fitness.
11. **Infrastructure & Transport (ID 11):** Roads, rail & metro, ports, aviation, housing, urban development, power.
12. **Entertainment & Media (ID 12):** Cinema, music, TV & OTT, theatre, books, awards.
13. **World & Diplomacy (ID 13):** Bilateral cooperation, agreements, diaspora achievements, global collaboration.

#### Hidden at Launch (5 Reserved Categories):
14. **Governance & Public Services (ID 14)**
15. **Law, Justice & Safety (ID 15)**
16. **Religion & Spirituality (ID 16)**
17. **Defence & Security (ID 17)**
18. **Disaster & Emergency (ID 18)**

---

### 2. Special Gatekeeper Rule Flags
Domain-specific safeguards are codified directly in category metadata:
* **Economy & Business (ID 9) — `promotional_content_check = True`:** Mandatory filter for corporate PR puffery, promotional sponsored material, and unsubstantiated market claims.
* **Health & Wellness (ID 10) — `corroboration_required = True`:** Mandatory requirement for peer-reviewed journal publication or public health authority validation for medical or nutritional breakthroughs.
* **Entertainment & Media (ID 12) — `gossip_excluded = True`:** Strict exclusion of celebrity gossip, divorces, scandals, and paparazzi coverage.

---

### 3. IPTC Media Topics 2024.1 Crosswalk
The taxonomy aligns directly with the **IPTC Media Topics NewsCodes standard (Version 2024.1)** maintained by the International Press Telecommunications Council (`http://cv.iptc.org/newscodes/mediatopic/`):
* Agriculture & Rural $\rightarrow$ `medtop:20000210` (`agriculture`)
* Science & Technology $\rightarrow$ `medtop:14000000` (`science and technology`)
* Education & Skills $\rightarrow$ `medtop:06000000` (`education`)
* Environment & Climate $\rightarrow$ `medtop:07000000` (`environment`)
* Sports $\rightarrow$ `medtop:16000000` (`sport`)
* Society & Community $\rightarrow$ `medtop:15000000` (`society`)
* Arts, Culture & Heritage $\rightarrow$ `medtop:01000000` (`arts, culture, entertainment and media`)
* Lifestyle & Travel $\rightarrow$ `medtop:11000000` (`lifestyle and leisure`)
* Economy & Business $\rightarrow$ `medtop:05000000` (`economy, business and finance`)
* Health & Wellness $\rightarrow$ `medtop:08000000` (`health`)
* Infrastructure & Transport $\rightarrow$ `medtop:20000337` (`transport`)
* Entertainment & Media $\rightarrow$ `medtop:01000000` (`arts, culture, entertainment and media`)
* World & Diplomacy $\rightarrow$ `medtop:20000638` (`international relations`)
* Governance & Public Services $\rightarrow$ `medtop:12000000` (`politics and government`)
* Law, Justice & Safety $\rightarrow$ `medtop:03000000` (`crime, law and justice`)
* Religion & Spirituality $\rightarrow$ `medtop:13000000` (`religion`)
* Defence & Security $\rightarrow$ `medtop:02000000` (`conflict, war and peace`)
* Disaster & Emergency $\rightarrow$ `medtop:04000000` (`disaster, accident and emergency incident`)

---

### 4. Option A Hidden-Category Policy Implementation
* Any story whose **primary category** resolves to IDs $14$ through $18$ is persisted with a held status (`status = 'held_hidden_category'`).
* **Zero Leakage:** Held articles are excluded from public feed queries, cluster article joins, notifications, and client caches.
* Enabling a hidden category in the future requires only a configuration change (updating `visibility: "visible"` in `config/taxonomy/v1.json` with a version bump), requiring no database schema migrations.

---

### 5. Integrity & Versioning Enforcement
* `TaxonomyVersion` carries a canonical SHA-256 checksum over the serialized category list.
* If any category property is modified without recomputing the checksum and updating the version number, `TaxonomyRegistry` raises a fatal startup error.
* All 13 visible categories must have localized display names in all 16 supported languages (`en`, `hi`, `bn`, `mr`, `te`, `ta`, `ur`, `gu`, `kn`, `or`, `ml`, `pa`, `as`, `ne`, `mai`, `gom`).

---

### 6. Feature Flagging and Rollback Protocol
* **Flag:** Environment variable `POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1` (default: `"true"`).
* **Rollback Mechanism:** Setting `POSIPULSE_ENABLE_CATEGORY_TAXONOMY_V1="false"` instantly disables category filtering in feed endpoints and reverts ingestion to unversioned legacy tags, requiring zero deployment downtime.

---

## Consequences

* **Positive:**
  * Clean, standardized, multilingual category taxonomy aligned with the international IPTC standard.
  * Guaranteed containment of sensitive categories via Option A holding policy.
  * Tamper-proof configuration with deterministic checksums and automated validation tests.
* **Negative:**
  * Adding or editing categories or subcategories requires a formal SemVer bump and checksum recalculation.
