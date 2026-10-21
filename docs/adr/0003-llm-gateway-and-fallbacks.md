# ADR 0003: LLM Gateway, Model Routing & Verification Strategy

## Status
Accepted

## Context
Only three pipeline stages require LLMs:
1. **Positivity Classifier**: Evaluates whether an article satisfies Constructive Journalism Rubric v1.0.0.
2. **Summarizer**: Synthesizes an original-wording abstractive summary (scaling length with substance).
3. **Faithfulness Verifier**: Evaluates candidate summary against the source text for hallucinations, contradictions, or verbatim copying.

The platform requires:
- High accuracy across 16 languages.
- Low token latency and cost.
- Resilient fallback when external AI APIs experience outages, rate limits, or degradation.

## Decision
We deploy a **Tiered LLM Gateway with Dual Verification and Indic-Optimized Fallbacks**:

```
[Candidate Article]
         |
         v
+-------------------------------+
| Positivity Classifier         |
| Primary: Gemini 1.5 Flash     |
| Fallback: Gemini 2.0 Flash    |
+---------------+---------------+
                |
          (Positive >= 0.85)
                |
                v
+-------------------------------+
| Abstractive Summarizer        |
| Primary: Gemini 1.5 Flash     |
| Indic Fallback: Sarvam-105B   |
+---------------+---------------+
                |
                v
+-------------------------------+
| Faithfulness Verifier         |
| Primary: Gemini 2.0 Flash     |
| Checks:                       |
| 1. Entailment / Factuality    |
| 2. Verbatim Overlap (< 7 n-g) |
| 3. Substantive Length Band    |
+---------------+---------------+
                |
          (Passes >= 0.95)
                |
                v
           [PUBLISHED]
```

### 1. Dual-Model Independence
The Summarizer and Verifier use distinct models or prompt variations to prevent shared cognitive bias. If Gemini 1.5 Flash generates a summary, Gemini 2.0 Flash acts as an independent adversarial judge.

### 2. Structured JSON Enforcers
All LLM prompts enforce strict Pydantic JSON schemas via native response schema parameters (`response_mime_type="application/json"`). Markdown formatting or freeform conversational preambles are rejected at the parsing boundary.

### 3. Circuit Breaker & Fallback Chain
- **Primary:** Google Gemini 1.5 Flash ($0.075/1M input, $0.30/1M output).
- **Secondary (High Severity / Verification):** Google Gemini 2.0 Flash ($0.10/1M input, $0.40/1M output).
- **Indic Specialized Fallback:** Sarvam-105B for scripts with high token fertility (Odia, Gujarati, Punjabi) if Gemini encounters quota throttling.
- If all LLM calls fail, the item is pushed to the language's retry queue with exponential backoff (up to 3 retries), then sent to the Dead-Letter Queue (DLQ). The pipeline fails closed: **no item is published unverified**.

## Consequences
- **Positive:** Maximum faithfulness; zero hallucinated stories reach users; robust handling of external provider outages.
- **Negative:** Dual-model invocation increases processing cost by ~30% compared to single-pass generation (yet total cost remains $< ₹0.06$ per published item).
