# Comprehensive Engineering Test Plan

**Project:** Multi-Agent Multilingual Positive News App  
**Phase:** Phase 1 Design Specification  
**Status:** Active Quality Standard  

---

## 1. Testing Philosophy & Non-Negotiables
Quality and reliability in this platform cannot be verified purely through manual inspection. In accordance with the project constraints:
1. **Precision Over Recall:** Our classifier and verifier must fail closed. If unsure about positivity or faithfulness, the item is excluded.
2. **Deterministic CI (No Live Network):** Ingestion fetcher tests must run entirely against recorded local fixtures (saved XML/RSS payloads), guaranteeing reproducible, zero-flakiness CI builds.
3. **Continuous Golden Evals:** Every enabled language maintains a dedicated golden test set evaluated on every prompt or rubric version bump.
4. **Verbatim Copying Zero-Tolerance:** Automated tests enforce $< 7$ overlapping non-stopword tokens between summary and source.
5. **Faithfulness Gate:** Unverified stories never publish.

---

## 2. Test Pyramid & Execution Matrix

```
                +----------------------------+
                | Native Speaker Spot Checks |  (Manual Sampling)
                +--------------+-------------+
                               |
                +--------------+-------------+
                |   End-to-End Mock Scenarios |  (Mocked Sources -> API)
                +--------------+-------------+
                               |
                +--------------+-------------+
                | Failure Injection & Chaos   |  (Timeouts, 429s, Malformed)
                +--------------+-------------+
                               |
                +--------------+-------------+
                | Golden Evals & Faithfulness |  (Classifier & Verifier)
                +--------------+-------------+
                               |
                +--------------+-------------+
                | Unit & Contract Tests      |  (Schemas, Routers, FastText)
                +----------------------------+
```

| Layer | Target Components | Tools & Frameworks | Coverage Target | CI Execution |
| :--- | :--- | :--- | :---: | :---: |
| **Unit Tests** | Pydantic schemas, language config loader, language-ID, text normalizers, verbatim overlap detector | `pytest`, `pydantic` | $>90\%$ | Every PR |
| **Contract Tests** | Inter-agent message envelopes (`run_id`, `trace_id`, `rubric_version`), OpenAPI spec validation | `pytest`, `schemathesis` | $100\%$ | Every PR |
| **Fixture Fetcher Tests** | RSS/Atom parsers, character encoding sanitization (Devanagari, RTL Urdu, Dravidian) | `pytest`, recorded `.xml` fixtures | $100\%$ feeds | Every PR |
| **Golden Evals** | Positivity classifier precision & recall per language | Python eval harness, golden set | $\ge 0.90$ precision | Scheduled / Version bump |
| **Faithfulness Checks** | Hallucination detection, length-band adherence, contradiction traps | LLM verifier test suite | $\ge 0.95$ pass rate | Scheduled / Version bump |
| **Failure Injection** | Circuit breakers, dead-letter queue, retry backoff with jitter, cost cap alarms | Custom chaos mocks | All failure modes | Nightly |
| **Native Spot Checks** | Editorial review of 20 published stories per language | Native speaker sampling matrix | Pass/Fail | Prior to Tier Gate sign-off |

---

## 3. Specific Test Suites

### 3.1 Unit & Contract Test Suite
- **Schema Invariant Tests:**
  - Verify `Article` rejects raw publisher body text if inadvertently populated.
  - Verify `SummaryMetadata` enforces word count and prompt version formatting.
  - Verify `PipelineMessageEnvelope` requires non-empty `run_id`, `trace_id`, and `stage`.
- **Config Loader Tests:**
  - Load all YAML configurations in `config/languages/` and assert zero validation errors.
  - Validate that Urdu has `is_rtl: true` and Latin languages have `is_rtl: false`.
  - Validate that all declared sources have valid feed URLs and positive fetch intervals.
- **OpenAPI Schema Conformance:**
  - Validate `docs/openapi.yaml` against OpenAPI 3.1 specification.

### 3.2 Recorded-Fixture Ingestion Tests
- Create offline XML fixtures in `tests/fixtures/`:
  - `the_hindu_sample.xml` (English RSS 2.0)
  - `bbc_hindi_sample.xml` (Hindi RSS 2.0 with Devanagari entities)
  - `bbc_tamil_sample.xml` (Tamil RSS 2.0)
  - `news18_urdu_sample.xml` (Urdu RSS 2.0 with RTL Nastaliq text)
- Assert that fetchers extract title, canonical link, published timestamp, and summary cleanly without making any outbound network calls.

### 3.3 Golden Classifier & Verifier Evals
For each target language, a golden evaluation file `evals/golden/{lang}_golden.json` contains:
- 10 Clearly Positive stories (Breakthroughs, environmental restoration, civic wins).
- 10 Clearly Negative stories (Disasters, homicides, accidents, war).
- 5 Toxic Positivity traps (Child labor framed as heartwarming, poverty exploitation).
- 5 Neutral / Policy stories (Market close, administrative committee appointments).

**Pass Criteria:**
- **Positive Precision:** $\ge 0.90$. A negative or toxic-positivity story being classified as positive is a fatal test failure.
- **Recall Target:** $\ge 0.70$ (precision strictly prioritized over recall).

### 3.4 Summary Faithfulness & Verbatim Overlap Guard
- **Verbatim Overlap Test:**
  - Generate test summary containing 8 verbatim consecutive words from the source text.
  - Assert that the verifier flags a `VERBATIM_COPY_VIOLATION` and rejects publication.
- **Contradiction / Hallucination Test:**
  - Inject fabricated facts (e.g., claiming a satellite exploded when the source states it launched successfully).
  - Assert that the verifier returns `verified: false` and confidence $< 0.20$.
- **Substantive Length Band Test:**
  - Verify that a 150-word story generates a concise 40-word summary, while an extensive 1,000-word investigative report generates a comprehensive 80-word summary, both respecting the language's defined length band.

### 3.5 Failure Injection & Chaos Tests
- **Timeout Injection:** Inject a 10-second hang on fetcher HTTP requests; assert that timeout triggers within 5 seconds and initiates exponential backoff.
- **Feed Corruption:** Pass malformed binary data instead of XML; assert graceful capture into the Dead-Letter Queue (DLQ).
- **LLM Rate-Limit / 429 Injection:** Mock primary LLM returning HTTP 429; assert that the worker transparently reroutes to the secondary fallback model without dropping the item.
- **Cost Cap Circuit Breaker:** Mock token spend exceeding `max_cost_per_run_usd`; assert that the worker cleanly halts further LLM calls, preserves queue state, and emits an operator alert.

### 3.6 Native-Speaker Review Protocol
Prior to promoting any language from `beta` to `active` (see GATES in Phase 4):
1. A random sample of 25 published stories and their source links is reviewed by a native speaker.
2. The reviewer scores:
   - Constructiveness (Is this genuinely positive/beneficial?).
   - Faithfulness (Does the summary accurately reflect the source?).
   - Linguistic Fluency (Is the summary natural, grammatically correct Indic prose, free of machine-translation stiffness?).
3. A language passes only if $\ge 92\%$ of sampled items receive approval.
