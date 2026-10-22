# Architectural & Legal Decision Log (ADR-0)

**Project:** Multi-Agent Multilingual Positive News App  
**Phase:** Phase 0 (Research & Foundation)  
**Status:** Approved for Checkpoint Review  

This decision log documents all architectural choices, legal interpretations flagged for counsel, source conflicts, trade-offs, and confidence levels established during Phase 0.

---

## Decision 1: News Summarization & Copyright Fair Dealing

* **Claim:** Does generating and displaying an AI summary of third-party news constitute fair dealing or copyright infringement under Indian law?
* **Sources:**
  1. Indian Copyright Act, 1957 — Section 52(1)(a)(i) (Fair dealing for private use/research) and Section 52(1)(b)(i) (Reporting of current events).
  2. *ANI Media Pvt. Ltd. v. OpenAI OpCo LLC* (Delhi High Court, July 2026, interim injunction denial).
  3. *Eastern Book Company v. D.B. Modak* (Supreme Court of India, 2008 — factual non-copyrightability).
  4. Industry operational precedent (*Inshorts* / *Way2News* decade-long operational record in India).
* **Legal Ambiguity (Flagged for Counsel):**
  Whether commercial AI-generated summarization without direct publisher licensing is protected under Section 52 fair dealing if challenged by publishers asserting commercial market substitution.
* **Conservative Reversible Choice:**
  1. **Strict Abstractive Rewriting:** Summaries must be written entirely in original wording; never reproduce publisher sentences.
  2. **Verbatim N-Gram Guard:** Deterministic verifier rejects any candidate summary with $\ge 7$ consecutive overlapping non-stopword tokens with the source.
  3. **Zero Storage for Display:** Raw publisher article bodies are held in ephemeral memory only during processing and permanently purged post-summarization. Only `[headline, original_summary, canonical_url, publisher_name, timestamp]` are stored in client databases.
  4. **Prominent Universal Link-Out:** Every article card renders an unmissable call-to-action linking directly to the publisher's original URL.
  5. **Respect Robots.txt & Paywalls:** Zero paywall or subscription bypass; honor `robots.txt` disallow and crawl-delay rules.
  6. **Publisher Takedown Protocol:** Implement an immediate administrative delisting mechanism if any publisher requests exclusion.
* **Reason:** Eliminates risk of substantial literary reproduction; respects publisher traffic flow by directing users to the primary source.
* **Confidence:** **High (Legal counsel review requested for commercial licensing agreements as scale expands).**

---

## Decision 2: DPDP Act 2023 Compliance & Personal Data

* **Claim:** Does Section 3(c)(ii) of the Digital Personal Data Protection Act, 2023 exempt news aggregation from data principal consent and processing constraints?
* **Sources:**
  1. Digital Personal Data Protection Act, 2023 — Section 3(c)(ii) (Publicly available personal data exclusions) and Section 9 (Children's data).
  2. Nasscom & DSCI Compliance Analysis (2024–2026).
  3. Supreme Court RTI / Privacy jurisprudence (*Puttaswamy v. Union of India*).
* **Legal Ambiguity (Flagged for Counsel):**
  Section 3(c)(ii) only exempts personal data made public *by the Data Principal themselves* or under a statutory legal obligation. Ordinary private citizens named in third-party news reports did not make their own data public.
* **Conservative Reversible Choice:**
  1. **Constructive Filter as Privacy Shield:** The positivity classifier fails-closed on crimes, arrests, domestic disputes, personal bankruptcies, and controversial scandals. By filtering for institutional science, ecology, public infrastructure, and verified sports/cultural wins, exposure of vulnerable private citizens is minimized.
  2. **Data Principal Grievance Redressal:** Build a dedicated privacy endpoint allowing any individual named in an item to request delisting, with automated SLA $\le 72$ hours.
  3. **No Minor Profiling:** Strict compliance with Section 9; no user tracking, profiling, or targeted ad tech.
* **Reason:** Maximizes privacy safeguards and avoids reliance on tenuous blanket interpretations of "public data."
* **Confidence:** **High.**

---

## Decision 3: Tier 3 Language Composition & Swappability

* **Claim:** Can Tier 3 languages (Odia, Assamese, Maithili, Nepali, Konkani) be supported immediately with healthy automated feeds and high-quality generation?
* **Sources:**
  1. Regional digital publishing audit across Indian news portals.
  2. Prasar Bharati / Akashvani News On Air language directories.
  3. Empirical Language-ID test (fastText `lid.176` and Lingua).
  4. Token fertility pilot benchmarks.
* **Source Conflict / Reality:**
  - **Odia:** Has robust, high-volume regional dailies (*Sambad*, *Dharitri*, *Prameya*, *News18 Odia*). Feed availability is strong, but token fertility is very high (7.36 tokens/word in global BPE).
  - **Assamese & Nepali:** Have viable, verified RSS feeds (*Asomiya Pratidin*, *Pratidin Time*, *Kantipur*, *Setopati*).
  - **Maithili & Konkani:** Suffer from an extreme shortage of active, automated RSS 2.0 / Atom syndication feeds. Publications exist largely as static PDF e-papers or social media video desks. Moreover, fastText misclassifies Maithili as Hindi (conf=0.88) and Konkani as Marathi (conf=0.78).
* **Choice:**
  1. **Promote Odia to Tier 2** (sufficient healthy sources; handle token fertility with optimized subword tokenizers).
  2. **Retain Assamese and Nepali in Tier 3** as viable languages.
  3. **Propose Swapping / Deferring Maithili and Konkani** until Phase 4 publisher partnerships are established. Propose launching Tier 1 (6 languages), Tier 2 (6 languages: Gujarati, Urdu, Kannada, Odia, Malayalam, Punjabi), and Tier 3 (2 languages: Assamese, Nepali).
* **Reason:** Fulfills the strict quality gate: *"At least 3 healthy sources per language"* and avoids launching broken feeds.
* **Confidence:** **Very High (Pending owner approval at Checkpoint).**

---

## Decision 4: Multi-Stage Language Identification & Script Disambiguation

* **Claim:** FastText `lid.176` or Lingua is sufficient for identifying languages in the ingestion pipeline.
* **Sources:**
  1. FastText `lid.176` benchmark (accuracy: 88.0% on 16 languages; 100% on distinct scripts; failed on Devanagari shared scripts: Maithili, Nepali, Konkani).
  2. Lingua detector (fails completely on Kannada, Malayalam, Odia, Assamese, Maithili, Nepali, Konkani due to absence from library enum).
  3. AI4Bharat `IndicLID` (IIT Madras benchmark).
* **Choice:** Implement a **Three-Stage Hierarchical Discriminator**:
  - **Stage 1 (Channel Prior):** Ingestion fetchers tag items with expected language from feed registry metadata (`feed_lang`).
  - **Stage 2 (Unicode Block Verification):** Deterministic check verifying text matches the expected script block (e.g. Devanagari `\u0900-\u097F`, Bengali `\u0980-\u09FF`, Dravidian scripts, Perso-Arabic `\u0600-\u06FF`).
  - **Stage 3 (Subword & Morphological Disambiguation):**
    - For Eastern Nagri script: Detect Assamese characters **'ৰ' (U+09F0)** or **'ৱ' (U+09F1)** vs Bengali **'র' (U+09B0)**.
    - For Devanagari shared script: Run fastText verified with language-specific stopword markers (e.g., Nepali *छ, छन्, को*; Marathi *आहे, नाही, च्या*; Hindi *है, हैं, का*).
* **Reason:** Eliminates script-sharing confusion while maintaining sub-millisecond deterministic CPU performance.
* **Confidence:** **Very High.**

---

## Decision 5: Core Model Architecture (Gemini 1.5 Flash + Sarvam AI Fallback)

* **Claim:** Which model provides the required precision, multilingual reasoning, and economic feasibility?
* **Sources:**
  1. Official API pricing: Google Gemini 1.5 Flash ($0.075/1M input, $0.30/1M output), OpenAI GPT-4o-mini ($0.15/1M in, $0.60/1M out), Sarvam AI Sarvam-105B (₹15/1M in, ₹60/1M out).
  2. Empirical Token Fertility Test (`o200k_base` vs Gemini 256k SentencePiece vs Sarvam custom Indic tokenizer).
  3. Instruction-following & structured output support (JSON Schema enforcement).
* **Choice:**
  - **Primary Engine:** **Google Gemini 1.5 Flash** for classification, original summarization, and faithfulness verification. It offers 50% lower cost than GPT-4o-mini, large context caching, and native 256k multilingual vocabulary.
  - **High-Fertility Script Specialist / Fallback:** **Sarvam AI (Sarvam-105B)** for scripts like Odia, Gujarati, and Punjabi where subword fragmentation on global models is high.
  - **Deterministic Code:** All scheduling, fetching, parsing, language detection, deduplication, and database operations remain strictly deterministic Python code.
* **Reason:** Minimizes cost to < ₹0.06 per published item while maintaining high faithfulness.
* **Confidence:** **High.**

---

## Decision 6: Multilingual Deduplication Strategy

* **Claim:** How should cross-source and cross-lingual story duplication be handled?
* **Sources:**
  1. BAAI/bge-m3 embedding architecture (569M parameters, 1024-dim, dense + sparse + ColBERT multi-vector).
  2. Sentence-Transformers v6.1.0 and PyTorch.
* **Choice:**
  - Use **BAAI/bge-m3** embeddings for story clustering.
  - **Intra-Language Deduplication:** Dense cosine similarity $\ge 0.94$ merges duplicate wire stories within the same language.
  - **Cross-Lingual Deduplication:** Dense cosine similarity $\ge 0.88$ assigns cross-lingual stories on the same event to a shared `cluster_id`.
* **Reason:** Allows readers to see when the same constructive milestone is reported across multiple languages and prevents feed clutter.
* **Confidence:** **High.**

---

## Decision 7: Constructive Journalism Definition & Positivity Rubric

* **Claim:** Can positive news be accurately separated from marketing PR, political propaganda, and toxic positivity?
* **Sources:**
  1. Solutions Journalism Network (SJN) 4 Pillars (Response, Insight, Evidence, Limitations).
  2. Constructive Institute (Aarhus University) Framework.
* **Choice:**
  - Codify **Constructive Journalism Rubric v1.0.0** with explicit positive outcome criteria (Science/Tech, Ecological Restoration, Socio-Economic Empowerment, Disaster Resilience, Civic Triumphs, Sports, Entertainment).
  - Codify constructive sports achievements (Olympic triumphs, national/world records, youth academies, sportsmanship) and constructive entertainment/culture (heritage film restoration, classical music & arts preservation, national arts awards).
  - Explicit **Fail-Closed Exclusion** on toxic positivity (e.g., child labor framed as heartwarming), corporate PR puffery, violent crime stories containing minor incidental kindness, and sports/celebrity scandals (doping, match-fixing, paparazzi gossip, divorce feuds).
  - Require the classifier to output `{is_positive: bool, confidence: float, reason: str, rubric_version: "1.0.0", category: str}`.
* **Reason:** Ensures strict adherence to "Precision over recall: if unsure, exclude."
* **Confidence:** **Very High.**

---

## Decision 8: App Store Compliance Architecture

* **Claim:** How to satisfy Apple Guidelines 4.3 / 5.2.2 and Google Play News Policy?
* **Sources:**
  1. Apple App Store Review Guidelines (4.3 Spam, 5.2.2 Third-Party IP, 1.2 UGC).
  2. Google Play News Policy & Play Console News Declaration.
* **Choice:**
  - Every card features high-contrast publisher branding and a universal deep link to the original article.
  - Full Unicode font rendering with Google Fonts (Noto Sans Indic) and proper right-to-left (RTL) styling for Urdu.
  - App includes an in-app "Report story" feedback loop and verified developer editorial disclosure.
* **Reason:** Eliminates risk of store rejections for "unauthorized scraping" or "low-utility RSS wrappers."
* **Confidence:** **Very High.**
