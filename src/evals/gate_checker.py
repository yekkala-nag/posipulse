"""
Language Quality Gate Checker
Evaluates whether a language satisfies all 4 mandatory gates before it can be enabled:
1. Positive-class precision >= min_positive_precision on golden set.
2. Verifier faithfulness pass rate >= min_faithfulness_pass_rate.
3. At least min_healthy_sources healthy sources.
4. Native-speaker spot check passed.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from src.evals.evaluator import GoldenEvaluator
from src.schemas.config import LanguageConfig, LanguageStatus


class QualityGateChecker:
    def __init__(self, language_config: LanguageConfig):
        self.config = language_config
        self.evaluator = GoldenEvaluator(language_config)

    def evaluate_gates(self, golden_filepath: str) -> Tuple[bool, Dict[str, Any]]:
        eval_report = self.evaluator.evaluate_golden_file(golden_filepath)
        metrics = eval_report["metrics"]

        precision_ok = metrics["precision"] >= self.config.quality_gate.min_positive_precision
        faithfulness_ok = metrics["faithfulness_pass_rate"] >= self.config.quality_gate.min_faithfulness_pass_rate
        verbatim_ok = metrics["verbatim_violations_count"] == 0

        healthy_sources = [s for s in self.config.sources if s.is_active and s.health_status == "healthy"]
        sources_ok = len(healthy_sources) >= self.config.quality_gate.min_healthy_sources

        spot_check_ok = self.config.quality_gate.native_speaker_spot_check_passed

        all_passed = bool(
            precision_ok
            and faithfulness_ok
            and verbatim_ok
            and sources_ok
            and spot_check_ok
        )

        certificate = {
            "language": self.config.language_code,
            "all_gates_passed": all_passed,
            "certified_at": datetime.now(timezone.utc).isoformat() if all_passed else None,
            "gate_details": {
                "positive_precision": {
                    "value": metrics["precision"],
                    "required": self.config.quality_gate.min_positive_precision,
                    "passed": precision_ok
                },
                "faithfulness_pass_rate": {
                    "value": metrics["faithfulness_pass_rate"],
                    "required": self.config.quality_gate.min_faithfulness_pass_rate,
                    "passed": faithfulness_ok
                },
                "zero_verbatim_copying": {
                    "violations": metrics["verbatim_violations_count"],
                    "passed": verbatim_ok
                },
                "healthy_sources": {
                    "count": len(healthy_sources),
                    "required": self.config.quality_gate.min_healthy_sources,
                    "passed": sources_ok
                },
                "native_speaker_spot_check": {
                    "passed": spot_check_ok
                }
            },
            "eval_report": eval_report
        }
        return all_passed, certificate
