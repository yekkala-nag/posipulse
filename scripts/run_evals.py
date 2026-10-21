"""
Evaluation Runner CLI
Runs golden evaluations across configured languages, checks quality gates,
and produces structured JSON reports and Markdown summaries.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
base_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base_dir))

from src.config.loader import LanguageConfigRegistry
from src.evals.evaluator import GoldenEvaluator
from src.evals.gate_checker import QualityGateChecker


def run_eval_for_language(lang_code: str, registry: LanguageConfigRegistry) -> None:
    config = registry.get_strict(lang_code)
    golden_path = base_dir / "evals" / "golden" / f"{lang_code}_golden.json"

    if not golden_path.exists():
        print(f"[-] Golden dataset not found for {lang_code} at {golden_path}")
        return

    print(f"\n==========================================")
    print(f"RUNNING GOLDEN EVALUATION: {config.language_name_english.upper()} ({lang_code})")
    print(f"==========================================")

    checker = QualityGateChecker(config)
    passed, cert = checker.evaluate_gates(str(golden_path))

    report = cert["eval_report"]
    markdown = checker.evaluator.render_markdown_summary(report)
    print(markdown)

    print("\n--- QUALITY GATE CHECKLIST ---")
    gd = cert["gate_details"]
    print(f"1. Precision >= {gd['positive_precision']['required']}: {gd['positive_precision']['value']} -> {'PASS' if gd['positive_precision']['passed'] else 'FAIL'}")
    print(f"2. Faithfulness >= {gd['faithfulness_pass_rate']['required']}: {gd['faithfulness_pass_rate']['value']} -> {'PASS' if gd['faithfulness_pass_rate']['passed'] else 'FAIL'}")
    print(f"3. Zero Verbatim Violations: {gd['zero_verbatim_copying']['violations']} -> {'PASS' if gd['zero_verbatim_copying']['passed'] else 'FAIL'}")
    print(f"4. Healthy Sources >= {gd['healthy_sources']['required']}: {gd['healthy_sources']['count']} -> {'PASS' if gd['healthy_sources']['passed'] else 'FAIL'}")
    print(f"5. Native Speaker Spot Check: {'PASS' if gd['native_speaker_spot_check']['passed'] else 'PENDING'}")
    print(f"\nOVERALL GATE STATUS: {'PASSED & CERTIFIED' if passed else 'NOT CERTIFIED'}")

    # Save reports
    reports_dir = base_dir / "evals" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with open(reports_dir / f"{lang_code}_eval_report.json", "w", encoding="utf-8") as f:
        json.dump(cert, f, indent=2, ensure_ascii=False)

    with open(reports_dir / f"{lang_code}_eval_summary.md", "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"[+] Saved reports to evals/reports/{lang_code}_eval_report.json and evals/reports/{lang_code}_eval_summary.md")


def main():
    registry = LanguageConfigRegistry(str(base_dir / "config" / "languages"))
    target_languages = [
        "en", "hi", "bn", "mr", "te", "ta",
        "ur", "gu", "kn", "or", "ml", "pa",
        "as", "ne", "mai", "gom"
    ]

    for lang in target_languages:
        run_eval_for_language(lang, registry)


if __name__ == "__main__":
    main()
