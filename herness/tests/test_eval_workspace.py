from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from octocoder.evals.workspace import (
    PreparedWorkspace,
    WorkspaceError,
    capture_workspace,
    cleanup_workspace,
    prepare_workspace,
)


def test_workspace_isolated_patch_and_cleanup(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "README.md").write_text("before\n", encoding="utf-8")
    workspace = prepare_workspace(fixture, tmp_path / "workspaces", "run-1")
    (workspace.path / "README.md").write_text("after\n", encoding="utf-8")
    (workspace.path / "new.txt").write_text("new\n", encoding="utf-8")

    snapshot = capture_workspace(workspace)

    assert fixture.joinpath("README.md").read_text(encoding="utf-8") == "before\n"
    assert snapshot.changed_files == ["README.md", "new.txt"]
    assert "+after" in snapshot.patch
    cleanup_workspace(workspace)
    assert not workspace.path.exists()


def test_workspace_patch_tracks_deleted_and_binary_files(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "delete.txt").write_text("remove me", encoding="utf-8")
    workspace = prepare_workspace(fixture, tmp_path / "workspaces", "run-binary")
    (workspace.path / "delete.txt").unlink()
    (workspace.path / "binary.bin").write_bytes(b"\x00\x01\x02")
    snapshot = capture_workspace(workspace)
    assert snapshot.changed_files == ["binary.bin", "delete.txt"]
    assert "delete.txt" in snapshot.patch
    assert "binary.bin" in snapshot.patch
    cleanup_workspace(workspace)


def test_cleanup_rejects_mismatched_marker(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    workspace = prepare_workspace(fixture, tmp_path / "workspaces", "run-1")
    (workspace.path / ".octocoder-eval-workspace.json").write_text(
        '{"run_id":"someone-else"}', encoding="utf-8"
    )
    with pytest.raises(WorkspaceError, match="does not match"):
        cleanup_workspace(workspace)


def test_workspace_rejects_fixture_symlink(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    try:
        (fixture / "link.txt").symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(WorkspaceError, match="symlink"):
        prepare_workspace(fixture, tmp_path / "workspaces", "run-1")


def test_cleanup_rejects_path_outside_run_root(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    (sentinel / "keep.txt").write_text("keep", encoding="utf-8")
    fake = PreparedWorkspace("run", tmp_path / "owned", sentinel, {})
    with pytest.raises(WorkspaceError, match="outside"):
        cleanup_workspace(fake)
    assert (sentinel / "keep.txt").exists()


def test_cleanup_retries_transient_windows_file_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    workspace = prepare_workspace(fixture, tmp_path / "workspaces", "run-retry")
    real_rmtree = shutil.rmtree
    attempts = 0

    def flaky_rmtree(path, *, onerror):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            error = OSError("file is in use")
            error.winerror = 32
            raise error
        real_rmtree(path, onerror=onerror)

    monkeypatch.setattr(
        "octocoder.evals.workspace._is_transient_cleanup_error",
        lambda _error: True,
    )
    monkeypatch.setattr("octocoder.evals.workspace.shutil.rmtree", flaky_rmtree)
    monkeypatch.setattr("octocoder.evals.workspace.time.sleep", lambda _seconds: None)

    cleanup_workspace(workspace)

    assert attempts == 2
    assert not workspace.path.exists()
