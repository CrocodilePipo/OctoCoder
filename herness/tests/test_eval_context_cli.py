from __future__ import annotations

import json
from pathlib import Path

from octocoder.evals.cli import (
    EXIT_EVALUATION_FAILED,
    EXIT_FRAMEWORK_ERROR,
    EXIT_REGRESSION,
    EXIT_SUCCESS,
    main,
)


def make_catalog(tmp_path: Path, *, stale: bool = False) -> Path:
    root = tmp_path / "evals"
    (root / "cases" / "context").mkdir(parents=True)
    (root / "suites").mkdir()
    (root / "fixtures" / "context").mkdir(parents=True)
    value = "beta" if stale else "alpha"
    (root / "cases" / "context" / "case.yaml").write_text(
        f"""schema_version: 1
id: context-cli
title: Context CLI
tags: [context-smoke]
prompt: run
fixture: context
execution: {{mode: scripted}}
context:
  stages:
    - {{id: probe, action: checkpoint, checkpoint: after}}
  facts:
    - id: name
      value: alpha
      required_at: [after]
      hard_gate: true
script:
  events:
    - type: context
      event_type: checkpoint
      stage_id: probe
      checkpoint_id: after
      checkpoint:
        id: after
        stage_id: probe
        facts: {{name: {value}}}
    - {{type: result, result: done, num_turns: 0}}
""",
        encoding="utf-8",
    )
    (root / "suites" / "context-smoke.yaml").write_text(
        "schema_version: 1\nid: context-smoke\ninclude_tags: [context-smoke]\n",
        encoding="utf-8",
    )
    return root


def test_context_cli_validates_runs_and_prints_artifacts(
    tmp_path: Path, capsys
) -> None:
    root = make_catalog(tmp_path)
    assert main(["--root", str(root), "validate", "--all"]) == EXIT_SUCCESS
    output = tmp_path / "runs"
    assert (
        main(
            [
                "--root",
                str(root),
                "run",
                "--suite",
                "context-smoke",
                "--output-root",
                str(output),
            ]
        )
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr().out
    assert "Context artifacts:" in captured
    run_dirs = list(output.glob("*/context-cli-r1-*"))
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "context-events.jsonl").exists()
    assert (run_dirs[0] / "context-metrics.json").exists()


def test_context_cli_returns_expectation_failure_for_hard_gate(tmp_path: Path) -> None:
    root = make_catalog(tmp_path, stale=True)
    assert (
        main(
            [
                "--root",
                str(root),
                "run",
                "--case",
                "context-cli",
                "--output-root",
                str(tmp_path / "runs"),
            ]
        )
        == EXIT_EVALUATION_FAILED
    )


def test_context_cli_compare_returns_regression_exit(tmp_path: Path) -> None:
    baseline_root = make_catalog(tmp_path / "baseline")
    candidate_root = make_catalog(tmp_path / "candidate", stale=True)
    baseline_runs = tmp_path / "baseline-runs"
    candidate_runs = tmp_path / "candidate-runs"
    assert main([
        "--root", str(baseline_root), "run", "--all", "--output-root", str(baseline_runs)
    ]) == EXIT_SUCCESS
    assert main([
        "--root", str(candidate_root), "run", "--all", "--output-root", str(candidate_runs)
    ]) == EXIT_EVALUATION_FAILED
    baseline = next(baseline_runs.glob("*/suite-report.json"))
    candidate = next(candidate_runs.glob("*/suite-report.json"))
    assert main(["compare", str(baseline), str(candidate)]) == EXIT_REGRESSION


def test_context_cli_framework_error_remains_exit_two(tmp_path: Path) -> None:
    root = make_catalog(tmp_path)
    case_path = root / "cases" / "context" / "case.yaml"
    case_path.write_text(
        case_path.read_text(encoding="utf-8").replace(
            "script:\n  events:",
            "script:\n  status: unsupported_instrumentation\n  events:",
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--root",
                str(root),
                "run",
                "--all",
                "--output-root",
                str(tmp_path / "runs"),
            ]
        )
        == EXIT_FRAMEWORK_ERROR
    )
