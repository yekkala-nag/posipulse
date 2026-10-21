# ADR 0004: Multilingual Deduplication & Cross-Lingual Semantic Clustering

## Status
Accepted

## Context
Major constructive news occurrences (e.g. an ISRO satellite launch, a clean energy milestone, a wildlife recovery) are simultaneously reported by multiple news outlets across English and several regional languages. Without deduplication:
1. Readers would see repetitive coverage of the same event.
2. Computational budget would be wasted summarizing and verifying duplicate stories.
3. The platform would fail to provide cross-lingual exploration (letting readers see how Tamil, Hindi, and English outlets cover the same achievement).

## Decision
We implement a **Two-Tier Deduplication Pipeline using Multilingual Embeddings (BAAI/bge-m3)**:

```
[Incoming Item Headline + First 2 Sentences]
                     |
                     v
+---------------------------------------------------+
| Stage 1: Exact & Fuzzy Lexical Deduplication      |
| - Normalized URL match & Canonical check          |
| - MinHash / LSH on Title tokens                   |
+--------------------+------------------------------+
                     | (New or Distinct)
                     v
+---------------------------------------------------+
| Stage 2: Cross-Lingual Semantic Clustering        |
| - Compute BAAI/bge-m3 dense vector (1024-dim)     |
| - Query Vector Index (sliding 72-hour window)     |
+--------------------+------------------------------+
                     |
       +-------------+-------------+
       |                           |
(Cosine >= 0.94)            (Cosine >= 0.88)
(Same Language)             (Different Language)
       |                           |
       v                           v
[Drop as Intra-Lang Dupe]   [Assign shared cluster_id]
```

### 1. Sliding Window Indexing
Because news deduplication is time-bounded, vector indexing is partitioned into a sliding **72-hour rolling window**. Matches outside the 72-hour window are considered distinct historical developments.

### 2. Representative Selection
When multiple articles from the same language cover the identical story (e.g. PTI syndicate published across 4 Hindi portals), the system selects the earliest published item from the highest-ranked healthy source as the primary story, preventing feed clutter.

## Consequences
- **Positive:** Feeds remain diverse and fresh; enables the mobile/web client `GET /v1/clusters/{cluster_id}` feature for multi-perspective reading.
- **Negative:** Requires local CPU/GPU memory to hold the 569M parameter `bge-m3` embedding model (~1.5GB RAM).
