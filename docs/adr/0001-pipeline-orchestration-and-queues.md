# ADR 0001: Pipeline Orchestration & Per-Language Queue Isolation

## Status
Accepted

## Context
The platform ingests news from hundreds of publisher feeds across English and 15 Indian languages. The pipeline must scale reliably under the following operational realities:
1. Different languages have vastly differing publication frequencies (English and Hindi publish hundreds of stories an hour; Tier 2/3 languages publish dozens a day).
2. Feed failures, network timeouts, malformed XML, and publisher rate limits are frequent and unpredictable.
3. If processing for one language (e.g. Odia or Tamil) crashes or exhausts its LLM cost cap, it must **never** block or delay ingestion for any other language.
4. Duplicate feed entries must be handled idempotently without re-triggering expensive LLM inference.

## Decision
We adopt a **Decoupled Asynchronous Fan-Out Architecture with Per-Language Isolated Queues**:

```
                       +-------------------+
                       | Cron Scheduler    |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       | Orchestrator      |
                       +---------+---------+
                                 |
           +---------------------+---------------------+
           |                     |                     |
           v                     v                     v
+--------------------+ +--------------------+ +--------------------+
| Queue: lang=en     | | Queue: lang=hi     | | Queue: lang=te     |
+----------+---------+ +----------+---------+ +----------+---------+
           |                     |                     |
           v                     v                     v
     [Worker Pool]         [Worker Pool]         [Worker Pool]
           |                     |                     |
   - Fetchers (Per-Source)
   - Normalizer
   - Language Detector & Script Validator
   - Embedding Deduplicator (bge-m3)
   - Headline Pre-Filter (Fail-closed)
   - Positivity Classifier (Gemini 1.5 Flash)
   - Abstractive Summarizer (Original Wording)
   - Faithfulness Verifier (Gemini 2.0 Flash)
           |
           v
   +---------------------------------------------------+
   | Storage (Zero Raw Publisher Body Stored)          |
   +---------------------------------------------------+
```

### Key Architectural Tenets:
1. **Isolated Worker Queues Per Language:** Each language has its own independent message queue (backed by Redis / Celery or Postgres-backed async jobs). A poison pill or cost exhaustion in Urdu never impacts Marathi.
2. **Deterministic Pre-Filtering:** Only the Classifier, Summarizer, and Verifier invoke LLMs. Fetching, normalizing, language-ID, deduplication, and headline keyword filtering are 100% deterministic code executing locally on CPU.
3. **Idempotency Keys:** Every item generates an idempotency hash `item_hash = sha256(canonical_url + published_date)`. The orchestrator checks the hash index before enqueuing to prevent redundant downstream LLM spend.
4. **Resilience & Circuit Breaking:**
   - Per-source exponential backoff with jitter on HTTP 429/5xx.
   - If a source fails 5 consecutive times, its circuit breaker trips to `DEGRADED`, backing off checks to 4 hours while alerting operators.
   - Malformed items move to a **Dead-Letter Queue (DLQ)** with full message context (`trace_id`, `run_id`, `payload`, `error`) for post-mortem inspection.
5. **Per-Run & Per-Language Cost Caps:** Each worker maintains an in-memory budget tracker. If a language queue reaches 80% of its daily budget, warnings fire; at 100%, LLM inference halts and logs are emitted, failing closed.

## Consequences
- **Positive:** Complete fault isolation, predictable cloud expenditures, zero cross-language starvation, and 100% idempotent execution.
- **Negative:** Requires managing separate worker queue metrics and language configurations.
