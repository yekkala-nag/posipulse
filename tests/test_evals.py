"""
Unit Tests for Golden Evaluation Tooling and Gate Checker (Phase 3)
Verifies:
1. GoldenEvaluator correctly computes precision, recall, F1, and toxic positivity rejection.
2. QualityGateChecker enforces all 4 gates before certifying a language.
3. English and Hindi both pass the 0.90 precision and 0.95 faithfulness gates.
"""

from pathlib import Path
import pytest
from src.config.loader import LanguageConfigRegistry
from src.evals.evaluator import GoldenEvaluator
from src.evals.gate_checker import QualityGateChecker


@pytest.fixture
def base_dir():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def registry(base_dir):
    return LanguageConfigRegistry(str(base_dir / "config" / "languages"))


def test_english_golden_evaluation(registry, base_dir):
    en_config = registry.get_strict("en")
    evaluator = GoldenEvaluator(en_config)
    golden_path = base_dir / "evals" / "golden" / "en_golden.json"

    report = evaluator.evaluate_golden_file(str(golden_path))

    assert report["total_items"] == 30
    metrics = report["metrics"]
    assert metrics["precision"] >= 0.90, "Positive-class precision must be >= 0.90"
    assert metrics["recall"] >= 0.70, "Recall must be >= 0.70"
    assert metrics["toxic_positivity_rejection_rate"] == 1.0, "All toxic positivity traps must be rejected"
    assert metrics["faithfulness_pass_rate"] >= 0.95, "Faithfulness pass rate must be >= 0.95"
    assert metrics["verbatim_violations_count"] == 0, "Zero verbatim copy violations permitted"


def test_hindi_golden_evaluation(registry, base_dir):
    hi_config = registry.get_strict("hi")
    evaluator = GoldenEvaluator(hi_config)
    golden_path = base_dir / "evals" / "golden" / "hi_golden.json"

    report = evaluator.evaluate_golden_file(str(golden_path))

    assert report["total_items"] == 30
    metrics = report["metrics"]
    assert metrics["precision"] >= 0.90, "Hindi precision must be >= 0.90"
    assert metrics["faithfulness_pass_rate"] >= 0.95, "Hindi faithfulness must be >= 0.95"
    assert metrics["verbatim_violations_count"] == 0


def test_quality_gate_certification(registry, base_dir):
    en_config = registry.get_strict("en")
    checker = QualityGateChecker(en_config)
    golden_path = base_dir / "evals" / "golden" / "en_golden.json"

    passed, cert = checker.evaluate_gates(str(golden_path))
    assert passed is True
    assert cert["all_gates_passed"] is True
    assert cert["gate_details"]["positive_precision"]["passed"] is True
    assert cert["gate_details"]["faithfulness_pass_rate"]["passed"] is True
    assert cert["gate_details"]["healthy_sources"]["passed"] is True
