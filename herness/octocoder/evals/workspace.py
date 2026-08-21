from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from octocoder.evals.models import WorkspaceSnapshot


MARKER = ".octocoder-eval-workspace.json"


class WorkspaceError(RuntimeError):
    """Raised when workspace ownership or containment cannot be proven."""


def _is_transient_cleanup_error(exc: OSError) -> bool:
    return os.name == "nt" and exc.winerror in {5, 32}


@dataclass(frozen=True)
class PreparedWorkspace:
    run_id: str
    run_root: Path
    path: Path
    before_manifest: dict[str, str]


def _assert_beneath(path: Path, root: Path, *, allow_root: bool = False) -> Path:
    resolved = path.resolve()
    root = root.resolve()
    if not resolved.is_relative_to(root) or (resolved == root and not allow_root):
        raise WorkspaceError(f"Path is outside owned root: {resolved}")
    return resolved


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise WorkspaceError(f"Fixture symlinks are not supported: {path}")


def manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.name == MARKER:
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _run_git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def prepare_workspace(fixture: Path, run_root: Path, run_id: str) -> PreparedWorkspace:
    fixture = fixture.resolve()
    if not fixture.is_dir():
        raise WorkspaceError(f"Fixture does not exist: {fixture}")
    _reject_symlinks(fixture)
    run_root.mkdir(parents=True, exist_ok=True)
    path = _assert_beneath(run_root / run_id, run_root)
    if path.exists():
        raise WorkspaceError(f"Workspace already exists: {path}")
    shutil.copytree(fixture, path, ignore=shutil.ignore_patterns(".git"))
    before = manifest(path)
    (path / MARKER).write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    commands = (
        ("init", "-q"),
        ("config", "user.email", "eval@octocoder.local"),
        ("config", "user.name", "OctoCoder Eval"),
        ("add", "-A"),
        ("commit", "-q", "--allow-empty", "-m", "evaluation baseline"),
    )
    for args in commands:
        completed = _run_git(path, *args)
        if completed.returncode != 0:
            raise WorkspaceError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return PreparedWorkspace(run_id, run_root.resolve(), path, before)


def capture_workspace(workspace: PreparedWorkspace) -> WorkspaceSnapshot:
    completed = _run_git(workspace.path, "add", "-N", ".")
    if completed.returncode not in (0, 1):
        raise WorkspaceError(completed.stderr.strip())
    diff = _run_git(workspace.path, "diff", "--binary", "--no-ext-diff", "HEAD", "--", ".")
    if diff.returncode != 0:
        raise WorkspaceError(diff.stderr.strip())
    after = manifest(workspace.path)
    changed = sorted(
        path
        for path in set(workspace.before_manifest).union(after)
        if workspace.before_manifest.get(path) != after.get(path)
    )
    return WorkspaceSnapshot(
        patch=diff.stdout,
        changed_files=changed,
        before_manifest=workspace.before_manifest,
        after_manifest=after,
    )


def resolve_workspace_path(workspace: Path, relative: str) -> Path:
    candidate = workspace / relative
    parent = candidate.parent.resolve()
    _assert_beneath(parent, workspace, allow_root=True)
    if candidate.exists() and candidate.is_symlink():
        raise WorkspaceError(f"Refusing symlink path: {relative}")
    return candidate


def cleanup_workspace(workspace: PreparedWorkspace) -> None:
    path = _assert_beneath(workspace.path, workspace.run_root)
    marker = path / MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkspaceError(f"Missing or invalid workspace marker: {marker}") from exc
    if data.get("run_id") != workspace.run_id:
        raise WorkspaceError("Workspace ownership marker does not match run ID")

    def remove_readonly(function, target, _error) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    # Antivirus and Git can briefly retain handles after a subprocess exits on Windows.
    # Ownership and containment have already been verified above, so retry only the
    # transient sharing/access errors against this exact path.
    for attempt in range(6):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
            return
        except OSError as exc:
            if not _is_transient_cleanup_error(exc) or attempt == 5:
                raise WorkspaceError(f"Failed to clean evaluation workspace: {path}") from exc
            time.sleep(0.05 * (2**attempt))
