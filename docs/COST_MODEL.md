# Operational Cost Model & Token Economics

**Project:** Multi-Agent Multilingual Positive News App  
**Phase:** Phase 1 Design Specification  
**Status:** Approved Economic Baseline  

---

## 1. Unit Economics & Pricing Foundation

The cost model is built entirely on empirical fertility metrics obtained during our Phase 0 pilot evaluation and verified published model pricing:

### Model Pricing (as of October 2026):
| Model | Role | Input Cost / 1M Tokens | Output Cost / 1M Tokens |
| :--- | :--- | :---: | :---: |
| **Google Gemini 1.5 Flash** | Primary Classifier & Summarizer | **$0.075** (~₹6.56) | **$0.30** (~₹26.25) |
| **Google Gemini 2.0 Flash** | Primary Faithfulness Verifier | **$0.100** (~₹8.75) | **$0.40** (~₹35.00) |
| **Sarvam AI (Sarvam-105B)** | Specialized Indic Fallback | **₹15.00** (~$0.17) | **₹60.00** (~$0.68) |

*Conversion Rate Used:* 1 USD = 87.50 INR.

---

## 2. Pipeline Stage Cost Breakdown (Per 1,000 Ingested Articles)

For a typical language queue ingesting 1,000 raw news articles from healthy RSS feeds:

```
[1,000 Raw Articles Ingested]
        |
        v
[Stage 1: Fetch, Normalize, Language-ID, Deduplicate]
Cost: $0.00 (100% Deterministic Python / CPU execution)
        |
        v
[Stage 2: Headline Pre-Filter]
- 70% of negative/routine stories rejected cheaply.
- 1,000 headlines evaluated (~20 words/headline).
- Input: ~25,000 tokens | Output: ~1,000 tokens
Cost: ~$0.0022
        |
        v
[Stage 3: Full-Text Positivity Classifier]
- 300 passing candidate articles evaluated (~400 words body).
- Input: ~150,000 tokens | Output: ~9,000 tokens
Cost: ~$0.0140
        |
        v
[Stage 4: Original-Wording Summarizer]
- ~12% acceptance rate = 120 positive articles summarized.
- Input: ~60,000 tokens | Output: ~18,000 tokens (~70 words/summary)
Cost: ~$0.0099
        |
        v
[Stage 5: Dual Faithfulness Verifier]
- 120 candidate summaries verified against source text.
- Input: ~70,000 tokens | Output: ~3,600 tokens
Cost: ~$0.0084
        |
        v
[120 Verified Positive Articles Published]
Total Batch LLM Cost (1,000 raw -> 120 published): ~$0.0345 (₹3.02)
```

---

## 3. Cost Per Published Story by Language Tier

Because token fertility varies by Indic script (from 1.23 tokens/word in English to 7.36 in Odia on global BPE tokenizers), actual costs per published story reflect this distribution:

| Tier | Language | Script | Fertility (Tokens/Word) | Cost / Raw Ingested ($) | Cost / Published Story ($) | Cost / Published Story (INR) |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **Tier 1** | **English** | Latin | 1.23 | $0.000030 | **$0.00025** | **₹0.022** |
| **Tier 1** | **Hindi** | Devanagari | 1.75 | $0.000042 | **$0.00035** | **₹0.030** |
| **Tier 1** | **Marathi** | Devanagari | 2.85 | $0.000066 | **$0.00055** | **₹0.048** |
| **Tier 1** | **Bengali** | Eastern Nagri | 2.91 | $0.000067 | **$0.00056** | **₹0.049** |
| **Tier 1** | **Telugu** | Telugu | 3.18 | $0.000073 | **$0.00061** | **₹0.053** |
| **Tier 1** | **Tamil** | Tamil | 3.46 | $0.000080 | **$0.00066** | **₹0.058** |
| **Tier 2** | **Gujarati** | Gujarati | 2.70 | $0.000063 | **$0.00052** | **₹0.046** |
| **Tier 2** | **Urdu** | Perso-Arabic (RTL) | 1.59 | $0.000038 | **$0.00032** | **₹0.028** |
| **Tier 2** | **Kannada** | Kannada | 2.78 | $0.000065 | **$0.00054** | **₹0.047** |
| **Tier 2** | **Malayalam** | Malayalam | 3.71 | $0.000085 | **$0.00071** | **₹0.062** |
| **Tier 2** | **Punjabi** | Gurmukhi | 2.73 | $0.000063 | **$0.00053** | **₹0.046** |
| **Tier 2** | **Odia** (Gemini) | Odia | 7.36 | $0.000166 | **$0.00138** | **₹0.121** |
| **Tier 2** | *Odia (Sarvam)* | Odia | *2.10* | *$0.000052* | ***$0.00043*** | ***₹0.038*** |
| **Tier 3** | **Assamese** | Eastern Nagri | 2.67 | $0.000062 | **$0.00052** | **₹0.045** |
| **Tier 3** | **Nepali** | Devanagari | 2.38 | $0.000056 | **$0.00046** | **₹0.041** |

---

## 4. Projected Monthly Operating Expenditures

Estimated monthly model expenditure scaling across languages:

| Monthly Published Articles | Active Languages | Estimated Monthly Ingestion | Monthly LLM Expenditure (USD) | Monthly LLM Expenditure (INR) |
| :---: | :---: | :---: | :---: | :---: |
| **1,000 stories / month** | 1 (English Skeleton) | ~8,300 raw articles | **$0.25** | **₹22** |
| **6,000 stories / month** | 6 (Tier 1 Core) | ~50,000 raw articles | **$2.88** | **₹252** |
| **14,000 stories / month** | 14 (Tier 1 + Tier 2 + Tier 3) | ~116,000 raw articles | **$7.56** | **₹661** |
| **100,000 stories / month** | 14 (High-Frequency Scale) | ~830,000 raw articles | **$54.00** | **₹4,725** |

*Note:* Cloud hosting (small VPS or serverless container + Redis + Postgres) adds approximately $15–$25/month. Total technical infrastructure to operate 14 Indian languages at high quality is under **$80/month (~₹7,000/month)**.

---

## 5. Cost Guardrails & Circuit Breakers

To prevent unexpected billing spikes or infinite crawling loops:
1. **Per-Run Cost Cap:** Configured at **$1.50 per language run**. If token expenditure during a single pipeline execution crosses $1.50, the worker gracefully finishes current items, rejects new incoming feed items, and emits an alert.
2. **Daily Budget Cap:** Configured at **$15.00/day per language**. If total daily token consumption hits 80% ($12.00), a warning alert is sent; at 100%, the language queue pauses until the next UTC day.
3. **Idempotency Hash Guard:** The database index on `sha256(canonical_url + published_date)` prevents duplicate LLM invocations for stories that have already been classified within the last 30 days.
