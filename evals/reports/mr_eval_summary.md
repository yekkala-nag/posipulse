# Golden Evaluation Report: MR

**Evaluated At:** 2026-10-21T09:05:53.916225+00:00  
**Total Items:** 30  

## Classification Performance
- **Positive-Class Precision:** **1.0000** (Threshold: $\ge 0.9$) -> **PASS**
- **Recall:** 0.8333 *(Precision prioritized over recall)*
- **F1 Score:** 0.9091
- **Toxic Positivity Rejection Rate:** 100.0%

## Confusion Matrix
| Metric | Positive (Actual) | Non-Positive (Actual) |
| :--- | :---: | :---: |
| **Predicted Positive** | TP = 10 | FP = 0 |
| **Predicted Non-Positive** | FN = 2 | TN = 18 |

## Summarization & Faithfulness Performance
- **Faithfulness Pass Rate:** **100.0%** (Threshold: $\ge 95.0%$) -> **PASS**
- **Verbatim Overlap Violations:** **0** -> **PASS**
- **Length Band Compliance:** 100.0%
