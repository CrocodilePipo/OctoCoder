from __future__ import annotations

from pathlib import Path

import pytest

from octocoder.evals.loader import EvaluationLoadError, load_catalog, resolve_suite


CASE = """\
schema_version: 1
id: edit-readme
title: Edit README
tags: [smoke, edit]
prompt: Add a heading
fixture: tiny-project
execution: {mode: scripted}
script: {events: [], effects: []}
"""


def make_catalog(tmp_path: Path) -> Path:
    root = tmp_path / "evals"
    (root / "cases").mkdir(parents=True)
    (root / "suites").mkdir()
    (root / "fixtures" / "tiny-project").mkdir(parents=True)
    (root / "cases" / "case.yaml").write_text(CASE, encoding="utf-8")
    (root / "suites" / "smoke.yaml").write_text(
        "schema_version: 1\nid: smoke\ninclude_tags: [smoke]\n",
        encoding="utf-8",
    )
    return root


def test_catalog_discovers_and_resolves_tags(tmp_path: Path) -> None:
    catalog = load_catalog(make_catalog(tmp_path))
    assert list(catalog.cases) == ["edit-readme"]
    assert [case.id for case in resolve_suite(catalog, catalog.suites["smoke"])] == ["edit-readme"]


def test_catalog_rejects_duplicate_ids(tmp_path: Path) -> None:
    root = make_catalog(tmp_path)
    (root / "cases" / "duplicate.yaml").write_text(CASE, encoding="utf-8")
    with pytest.raises(EvaluationLoadError, match="Duplicate case ID"):
        load_catalog(root)


def test_catalog_rejects_unknown_case_reference(tmp_path: Path) -> None:
    root = make_catalog(tmp_path)
    (root / "suites" / "smoke.yaml").write_text(
        "schema_version: 1\nid: smoke\ncases: [missing]\n",
        encoding="utf-8",
    )
    with pytest.raises(EvaluationLoadError, match="unknown cases"):
        load_catalog(root)
