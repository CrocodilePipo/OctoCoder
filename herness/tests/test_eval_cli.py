from __future__ import annotations

from pathlib import Path

from octocoder.evals.cli import EXIT_FRAMEWORK_ERROR, EXIT_SUCCESS, main


def make_catalog(tmp_path: Path) -> Path:
    root = tmp_path / "evals"
    (root / "cases").mkdir(parents=True)
    (root / "suites").mkdir()
    fixture = root / "fixtures" / "tiny"
    fixture.mkdir(parents=True)
    (fixture / "value.txt").write_text("before\n", encoding="utf-8")
    (root / "cases" / "pass.yaml").write_text(
        """schema_version: 1
id: pass
title: Passing case
tags: [smoke]
prompt: update value
fixture: tiny
execution: {mode: scripted}
script:
  events:
    - {type: tool_use, tool_name: write_file, tool_id: call_scripted1, args: {path: value.txt}}
    - {type: tool_result, tool_name: write_file, tool_id: call_scripted1, output: ok, is_error: false}
    - {type: result, result: done, num_turns: 1}
  effects:
    - {type: write, path: value.txt, content: "after\\n"}
expected:
  outcome:
    - {id: content, type: file_contains, path: value.txt, text: after}
""",
        encoding="utf-8",
    )
    (root / "suites" / "smoke.yaml").write_text(
        "schema_version: 1\nid: smoke\ninclude_tags: [smoke]\n", encoding="utf-8"
    )
    return root


def test_cli_validates_and_runs_scripted_suite(tmp_path: Path) -> None:
    root = make_catalog(tmp_path)
    assert main(["--root", str(root), "validate", "--all"]) == EXIT_SUCCESS
    output = tmp_path / "runs"
    assert main([
        "--root", str(root), "run", "--suite", "smoke", "--output-root", str(output)
    ]) == EXIT_SUCCESS
    assert len(list(output.glob("*/suite-report.json"))) == 1
    assert not list(output.glob("*/.workspaces/*"))


def test_cli_returns_framework_exit_for_runtime_framework_error(tmp_path: Path) -> None:
    root = make_catalog(tmp_path)
    case_path = root / "cases" / "pass.yaml"
    case_path.write_text(
        case_path.read_text(encoding="utf-8").replace(
            "- {type: write, path: value.txt, content: \"after\\n\"}",
            "- {type: delete, path: .}",
        ),
        encoding="utf-8",
    )
    assert main([
        "--root", str(root), "run", "--case", "pass", "--output-root", str(tmp_path / "runs")
    ]) == EXIT_FRAMEWORK_ERROR
    verdict_files = list((tmp_path / "runs").glob("*/*/verdict.json"))
    assert len(verdict_files) == 1
    assert "framework_error" in verdict_files[0].read_text(encoding="utf-8")
