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
    return process.stdout.strip()


def clean_snapshot(repo: Path) -> dict:
    repo = Path(repo).expanduser()
    if not repo.is_absolute() or repo.is_symlink() or not repo.is_dir():
        raise SnapshotError("repo must be an existing absolute non-symlink directory")
    canonical = repo.resolve()
    root = Path(_git(repo, "rev-parse", "--show-toplevel").decode("utf-8", "replace"))
    if root.resolve() != canonical:
        raise SnapshotError("repo must be the exact Git checkout root")
    head = _git(repo, "rev-parse", "HEAD").decode("ascii", "replace")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
        raise SnapshotError("Git HEAD unavailable")
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8", "replace")
    if not branch:
        raise SnapshotError("detached HEAD needs an explicit owner decision")
    dirty = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if dirty:
        raise SnapshotError("checkout has existing tracked or untracked changes")
    if (_git(repo, "rev-parse", "HEAD").decode("ascii", "replace") != head
            or _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8", "replace") != branch):
        raise SnapshotError("checkout changed during inspection")
    payload = json.dumps([str(canonical), branch, head, "clean"], separators=(",", ":"))
    return {"repo": str(canonical), "branch": branch, "base_head": head,
            "work_snapshot": "clean-sha256:" + hashlib.sha256(payload.encode()).hexdigest()}
