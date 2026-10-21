# ADR 0002: Storage Engine, State Transitions & Ephemeral Memory Isolation

## Status
Accepted

## Context
Under Indian copyright law (Section 52 of the Copyright Act, 1957) and DPDP Act 2023 compliance, our platform must:
1. Never store, mirror, or serve full publisher article text.
2. Maintain end-to-end auditability and traceability for every published item (tracking `model`, `prompt_version`, `rubric_version`, and verifier scores).
3. Provide fast, sub-50ms paginated queries for mobile and web clients across languages and categories.
4. Support immediate administrative delisting (within 72 hours) upon receipt of Data Principal privacy requests.

## Decision
We enforce a strict **Ephemeral Memory Boundary** and adopt **PostgreSQL with JSONB and pgvector (or SQLite with json1 for local testing)**.

### 1. Ephemeral Ingestion vs. Persistent Storage Schema

```
[In-Memory / Queue Message]
 ephemeral_ingested_item:
   raw_body: "Full scraped article text..."   <--- Exists ONLY in RAM / Redis payload
         |
         | (Classification, Original Abstractive Summarization, Faithfulness Verification)
         v
[Persistent Database Record]
 articles:
   id: "uuid"
   headline: "Native headline"
   summary: {
     text: "Original abstractive synthesis...",   <--- Our original words
     model: "gemini-1.5-flash",
     prompt_version: "1.0.0",
     verified: true,
     verifier_model: "gemini-2.0-flash",
     verifier_score: 0.98
   }
   positivity: {
     label: "positive",
     score: 0.94,
     reason: "Constructive scientific achievement...",
     rubric_version: "1.0.0",
     category: "Science/Tech"
   }
   canonical_url: "https://thehindu.com/..."      <--- Prominent link-out
   source_name: "The Hindu"
   language: "en"
   cluster_id: "cluster_xyz"
   status: "published"

   *** RAW BODY TEXT IS NEVER PERSISTED ***
```

### 2. State Machine Transitions

```
[FETCHED] 
   --> [NORMALIZED] 
   --> [DEDUPLICATED] 
   --> [HEADLINE_REJECTED] (Fail-closed)
   --> [CLASSIFYING] 
          |--> [CLASSIFIED_NEGATIVE] (Terminated)
          +--> [CLASSIFIED_POSITIVE]
                  --> [SUMMARIZING]
                         --> [SUMMARIZED]
                                --> [VERIFYING]
                                       |--> [VERIFICATION_FAILED] (Terminated)
                                       +--> [PUBLISHED]
                                               |--> [DELISTED] (Privacy takedown)
```

### 3. Database Schema
- **Table `articles`**: Primary indexed columns on `(language, status, published_at DESC)` and `(cluster_id)`.
- **Table `clusters`**: Groups cross-lingual stories with shared `cluster_id` and centroid embedding.
- **Table `audit_log`**: Records execution runs, token expenditures, verifier scores, and privacy delisting timestamps.

## Consequences
- **Positive:** Complete elimination of copyright liability for full-text reproduction; lean database storage footprint; sub-millisecond index lookups.
- **Negative:** If a summary needs re-generation with a newer prompt version, the original article body must be re-fetched from the publisher feed.
