from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from octocoder.config import ConfigError, load_config
from octocoder.evals.compare import compare_reports, load_report, render_comparison_markdown
from octocoder.evals.loader import EvaluationLoadError, load_catalog, select_cases
from octocoder.evals.models import ComparisonThresholds, ExecutionMode
from octocoder.evals.orchestration import EvaluationOrchestrator
from octocoder.evals.redaction import SecretRedactor, discover_secrets


EXIT_SUCCESS = 0
EXIT_EVALUATION_FAILED = 1
EXIT_FRAMEWORK_ERROR = 2
EXIT_REGRESSION = 3
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "evals"


def _selection(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case")
    group.add_argument("--suite")
    group.add_argument("--all", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="octocoder-eval", description="OctoCoder agent evaluation")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Evaluation catalog root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate evaluation cases and suites")
    _selection(validate)

    run = subparsers.add_parser("run", help="Run evaluation cases or a suite")
    _selection(run)
    run.add_argument("--repeat", type=int, default=None)
    run.add_argument("--execution", choices=[mode.value for mode in ExecutionMode])
    run.add_argument("--output-root", type=Path, default=None)
    run.add_argument("--keep-workspace", action="store_true")

    compare = subparsers.add_parser("compare", help="Compare candidate and baseline suite reports")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)
    return parser


def _load_selected(args) -> tuple:
    catalog = load_catalog(args.root)
    return catalog, select_cases(
        catalog,
        case_id=getattr(args, "case", None),
        suite_id=getattr(args, "suite", None),
        all_cases=getattr(args, "all", False),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            comparison = compare_reports(load_report(args.baseline), load_report(args.candidate))
            text = render_comparison_markdown(comparison)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8")
            print(text, end="")
            return EXIT_REGRESSION if comparison.regression else EXIT_SUCCESS

        catalog, (cases, suite) = _load_selected(args)
        if args.command == "validate":
            print(f"Validated {len(catalog.cases)} case(s) and {len(catalog.suites)} suite(s) in {catalog.root}")
            print(f"Selection contains {len(cases)} case(s)")
            return EXIT_SUCCESS

        repeat = args.repeat if args.repeat is not None else (suite.repeat if suite else 1)
        if repeat < 1:
            raise EvaluationLoadError("repeat must be at least 1")
        suite_id = suite.id if suite else (cases[0].id if len(cases) == 1 else "all")
        output_root = args.output_root or (catalog.root / "runs")
        try:
            config = load_config()
        except ConfigError:
            config = None
        redactor = SecretRedactor(discover_secrets(config))
        evaluation = asyncio.run(
            EvaluationOrchestrator(catalog, output_root, redactor).run(
                cases,
                suite_id=suite_id,
                repeat=repeat,
                thresholds=suite.thresholds if suite else None,
                execution_override=ExecutionMode(args.execution) if args.execution else None,
                keep_workspace=args.keep_workspace,
            )
        )
        print(f"Report: {evaluation.report_markdown}")
        print(f"JSON: {evaluation.report_json}")
        for result in evaluation.report.results:
            if result.execution.context_metrics is not None:
                print(
                    f"Context artifacts: {evaluation.output_directory / result.artifact_path}"
                )
        if any(
            result.status.value in {"framework_failed", "unsupported_instrumentation"}
            for result in evaluation.report.results
        ):
            return EXIT_FRAMEWORK_ERROR
        return EXIT_SUCCESS if evaluation.report.passed else EXIT_EVALUATION_FAILED
    except (EvaluationLoadError, ValidationError, OSError, ValueError) as exc:
        print(f"Evaluation framework error: {exc}", file=sys.stderr)
        return EXIT_FRAMEWORK_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
