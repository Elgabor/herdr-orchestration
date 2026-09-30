"""Read-only checkout identity for a clean, single-writer assignment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


class SnapshotError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> bytes:
    try:
        process = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                 check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SnapshotError("git checkout inspection unavailable") from error
    if process.returncode:
        raise SnapshotError("git checkout inspection failed")
    return process.stdout


def clean_snapshot(repo: Path) -> dict:
    repo = Path(repo).expanduser()
    if not repo.is_absolute() or repo.is_symlink() or not repo.is_dir():
        raise SnapshotError("repo must be an existing absolute non-symlink directory")
    canonical = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip())
    if root.resolve() != canonical:
        raise SnapshotError("repo must be the exact Git checkout root")
    head = _git(repo, "rev-parse", "HEAD").decode("ascii", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise SnapshotError("Git HEAD unavailable")
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8", "replace").strip()
    if not branch:
        raise SnapshotError("detached HEAD needs an explicit owner decision")
    dirty = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if dirty:
        raise SnapshotError("checkout has existing tracked or untracked changes")
    if (_git(repo, "rev-parse", "HEAD").decode("ascii", "replace").strip() != head
            or _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8", "replace").strip() != branch):
        raise SnapshotError("checkout changed during inspection")
    payload = json.dumps([str(canonical), branch, head, "clean"], separators=(",", ":"))
    return {"repo": str(canonical), "branch": branch, "base_head": head,
            "work_snapshot": "clean-sha256:" + hashlib.sha256(payload.encode()).hexdigest()}


def changed_paths(repo: Path, base_head: str) -> set[str]:
    """List tracked and untracked path names since the assigned base; no file contents."""
    repo = Path(repo)
    if not repo.is_absolute() or repo.is_symlink() or not repo.is_dir():
        raise SnapshotError("repo checkout path changed")
    root = Path(_git(repo, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip())
    if root.resolve() != repo.resolve() or str(repo.resolve()) != str(repo):
        raise SnapshotError("repo is no longer the assigned canonical checkout")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base_head):
        raise SnapshotError("assigned base_head invalid")
    # A rename must expose both its old and new paths to write_scope checks.
    tracked = _git(repo, "diff", "--no-renames", "--name-only", "-z", base_head, "--")
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    try:
        return {item.decode("utf-8") for item in (tracked + untracked).split(b"\0") if item}
    except UnicodeError as error:
        raise SnapshotError("changed path is not UTF-8") from error
