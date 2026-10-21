"""
Golden Dataset Evaluation Tooling
Computes precision, recall, F1, toxic positivity rejection rate,
faithfulness verification pass rate, and length band compliance.
Generates structured JSON and Markdown eval reports per language.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.pipeline.classifier import PositivityClassifier
from src.pipeline.summarizer import AbstractiveSummarizer
from src.pipeline.verifier import FaithfulnessVerifier
from src.schemas.article import EphemeralIngestedItem, PositivityLabel
from src.schemas.config import LanguageConfig


class GoldenEvaluator:
    def __init__(self, language_config: LanguageConfig):
        self.config = language_config
        self.classifier = PositivityClassifier(
            model_name=self.config.model_routing.classifier_primary_model,
            rubric_version=self.config.rubric_version
        )
        self.summarizer = AbstractiveSummarizer(
            model_name=self.config.model_routing.summarizer_primary_model,
            prompt_version=self.config.prompt_version,
            length_band=self.config.length_band
        )
        self.verifier = FaithfulnessVerifier(
            verifier_model=self.config.model_routing.verifier_model,
            length_band=self.config.length_band
        )

    def evaluate_golden_file(self, golden_filepath: str) -> Dict[str, Any]:
        with open(golden_filepath, "r", encoding="utf-8") as f:
            items = json.load(f)

        tp = 0
        fp = 0
        fn = 0
        tn = 0
        toxic_pos_total = 0
        toxic_pos_rejected = 0

        verified_passed = 0
        verbatim_violations = 0
        length_compliant = 0

        detailed_results = []

        for item_data in items:
            item = EphemeralIngestedItem(
                id=item_data["id"],
                source_id="golden-source",
                source_name="Golden Benchmark",
                url="https://example.com/gold",
                canonical_url="https://example.com/gold",
                headline=item_data["headline"],
                raw_body=item_data["body"],
                published_at=datetime.now(timezone.utc),
                declared_language=item_data["language"]
            )

            expected = item_data["ground_truth"]
            positivity = self.classifier.classify(item)
            predicted_positive = (
                positivity.label == PositivityLabel.POSITIVE
                and positivity.score >= self.config.positivity_threshold
            )

            # Confusion matrix metrics
            if expected == "positive":
                if predicted_positive:
                    tp += 1
                else:
                    fn += 1
            else:
                if predicted_positive:
                    fp += 1
                else:
                    tn += 1

            # Toxic positivity specific audit
            if expected == "toxic_positivity":
                toxic_pos_total += 1
                if not predicted_positive:
                    toxic_pos_rejected += 1

            # Summarizer & Verifier evaluation on positive items
            item_eval: Dict[str, Any] = {
                "id": item.id,
                "headline": item.headline,
                "expected": expected,
                "predicted": positivity.label.value,
                "score": positivity.score,
                "reason": positivity.reason,
            }

            if predicted_positive:
                summary = self.summarizer.summarize(item)
                v_ok, v_score, v_reasons = self.verifier.verify(item, summary)
                if v_ok:
                    verified_passed += 1
                verbatim_ok, _ = self.verifier.check_verbatim_overlap(item.raw_body, summary.text)
                if not verbatim_ok:
                    verbatim_violations += 1
                length_ok, _ = self.verifier.check_length_band(summary)
                if length_ok:
                    length_compliant += 1

                item_eval["summary_verified"] = v_ok
                item_eval["verbatim_ok"] = verbatim_ok
                item_eval["length_ok"] = length_ok

            detailed_results.append(item_eval)

        # Compute aggregate scores
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        toxic_rejection_rate = (toxic_pos_rejected / toxic_pos_total) if toxic_pos_total > 0 else 1.0

        faithfulness_pass_rate = (verified_passed / tp) if tp > 0 else 0.0
        length_compliance_rate = (length_compliant / tp) if tp > 0 else 0.0

        report = {
            "language": self.config.language_code,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "total_items": len(items),
            "confusion_matrix": {
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn
            },
            "metrics": {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "toxic_positivity_rejection_rate": round(toxic_rejection_rate, 4),
                "faithfulness_pass_rate": round(faithfulness_pass_rate, 4),
                "verbatim_violations_count": verbatim_violations,
                "length_compliance_rate": round(length_compliance_rate, 4)
            },
            "gate_assessment": {
                "precision_gate_passed": precision >= self.config.quality_gate.min_positive_precision,
                "faithfulness_gate_passed": faithfulness_pass_rate >= self.config.quality_gate.min_faithfulness_pass_rate,
                "zero_verbatim_copying": verbatim_violations == 0
            },
            "detailed_items": detailed_results
        }
        return report

    def render_markdown_summary(self, report: Dict[str, Any]) -> str:
        m = report["metrics"]
        g = report["gate_assessment"]
        c = report["confusion_matrix"]
        return rf"""# Golden Evaluation Report: {report['language'].upper()}

**Evaluated At:** {report['evaluated_at']}  
**Total Items:** {report['total_items']}  

## Classification Performance
- **Positive-Class Precision:** **{m['precision']:.4f}** (Threshold: $\ge {self.config.quality_gate.min_positive_precision}$) -> **{'PASS' if g['precision_gate_passed'] else 'FAIL'}**
- **Recall:** {m['recall']:.4f} *(Precision prioritized over recall)*
- **F1 Score:** {m['f1_score']:.4f}
- **Toxic Positivity Rejection Rate:** {m['toxic_positivity_rejection_rate'] * 100:.1f}%

## Confusion Matrix
| Metric | Positive (Actual) | Non-Positive (Actual) |
| :--- | :---: | :---: |
| **Predicted Positive** | TP = {c['true_positives']} | FP = {c['false_positives']} |
| **Predicted Non-Positive** | FN = {c['false_negatives']} | TN = {c['true_negatives']} |

## Summarization & Faithfulness Performance
- **Faithfulness Pass Rate:** **{m['faithfulness_pass_rate'] * 100:.1f}%** (Threshold: $\ge {self.config.quality_gate.min_faithfulness_pass_rate * 100:.1f}%$) -> **{'PASS' if g['faithfulness_gate_passed'] else 'FAIL'}**
- **Verbatim Overlap Violations:** **{m['verbatim_violations_count']}** -> **{'PASS' if g['zero_verbatim_copying'] else 'FAIL'}**
- **Length Band Compliance:** {m['length_compliance_rate'] * 100:.1f}%
"""
