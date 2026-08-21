from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from octocoder.evals.models import CaseRunResult, EvalCase, SuiteReport
from octocoder.evals.redaction import SecretRedactor
from octocoder.evals.report import render_case_markdown, render_suite_markdown


class ArtifactError(RuntimeError):
    """Raised when run artifacts cannot be written safely."""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


class ArtifactWriter:
    def __init__(self, root: Path, redactor: SecretRedactor | None = None) -> None:
        self.root = root.resolve()
        self.redactor = redactor or SecretRedactor()

    def _serialize_json(self, value) -> str:
        data = self.redactor.redact(value)
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if self.redactor.contains_secret(text):
            raise ArtifactError("Secret remained after artifact redaction")
        return text

    def write_case(self, case: EvalCase, result: CaseRunResult) -> Path:
        directory = self.root / result.execution.run_id
        if directory.exists():
            raise ArtifactError(f"Run artifact already exists: {directory}")
        directory.mkdir(parents=True)
        files = {
            "case.yaml": yaml.safe_dump(
                self.redactor.redact(case), allow_unicode=True, sort_keys=False
            ),
            "raw-events.jsonl": "".join(
                json.dumps(self.redactor.redact(event), ensure_ascii=False, sort_keys=True) + "\n"
                for event in result.execution.raw_events
            ),
            "events.jsonl": "".join(
                json.dumps(self.redactor.redact(event), ensure_ascii=False, sort_keys=True) + "\n"
                for event in result.execution.events
            ),
            "trajectory.json": self._serialize_json(result.execution.trajectory),
            "workspace.patch": self.redactor.redact_text(result.execution.workspace_diff.patch),
            "stderr.txt": self.redactor.redact_text(result.execution.stderr),
            "verdict.json": self._serialize_json(result),
            "report.md": self.redactor.redact_text(render_case_markdown(result)),
        }
        if case.context is not None:
            files.update(
                {
                    "context-events.jsonl": "".join(
                        json.dumps(
                            self.redactor.redact(event),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                        for event in result.execution.context_events
                    ),
                    "context-checkpoints.json": self._serialize_json(
                        result.execution.context_checkpoints
                    ),
                    "context-metrics.json": self._serialize_json(
                        result.execution.context_metrics or {}
                    ),
                }
            )
        for name, content in files.items():
            if self.redactor.contains_secret(content):
                raise ArtifactError(f"Secret remained in {name}")
            _atomic_write(directory / name, content)
        return directory

    def write_suite(self, directory: Path, report: SuiteReport) -> tuple[Path, Path]:
        directory = directory.resolve()
        if not directory.is_relative_to(self.root):
            raise ArtifactError("Suite report directory is outside artifact root")
        json_path = directory / "suite-report.json"
        markdown_path = directory / "suite-report.md"
        _atomic_write(json_path, self._serialize_json(report))
        markdown = self.redactor.redact_text(render_suite_markdown(report))
        if self.redactor.contains_secret(markdown):
            raise ArtifactError("Secret remained in suite Markdown")
        _atomic_write(markdown_path, markdown)
        return json_path, markdown_path
