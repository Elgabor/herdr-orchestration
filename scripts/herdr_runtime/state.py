"""Private, atomic JSON state with short locks and explicit owner epochs."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from .contracts import ContractError, ID, event_id, validate_event, validate_run

MAX_STATE_BYTES = 1024 * 1024


class StateConflict(RuntimeError):
    pass


class UnsafePath(RuntimeError):
    pass


def _static_member(member: dict) -> dict:
    return {key: value for key, value in member.items()
            if key not in {"conversation_id", "context_key", "identity_status"}}


def _read_json(path: Path) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise StateConflict(f"{path.name}: absent") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STATE_BYTES:
            raise UnsafePath(f"{path.name}: not a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_STATE_BYTES + 1)
        if len(data) > MAX_STATE_BYTES:
            raise UnsafePath(f"{path.name}: too large")
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict):
            raise ContractError(f"{path.name}: expected object")
        return value
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"{path.name}: invalid UTF-8 JSON: {error}") from error
    finally:
        os.close(fd)


def _atomic_json(path: Path, value: dict) -> None:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > MAX_STATE_BYTES:
        raise ContractError(f"{path.name}: state exceeds {MAX_STATE_BYTES} bytes")
    fd, temp = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise UnsafePath(f"{path.name}: symlink")
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class StateStore:
    def __init__(self, root: Path):
        root = Path(root).expanduser()
        if root.is_symlink():
            raise UnsafePath("state root: symlink")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = root.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise UnsafePath("state root: require owner-only directory")
        self.root = root.resolve()

    @contextmanager
    def _locked(self):
        lock = self.root / ".lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not ID.fullmatch(run_id):
            raise ContractError("run_id: invalid identifier")
        return self.root / f"run-{run_id}.json"

    def create_run(self, run: dict) -> dict:
        validate_run(run)
        if run["generation"] != 0 or run["owner_epoch"] != 1:
            raise ContractError("generation/owner_epoch: expected 0/1 for new run")
        path = self._path(run["run_id"])
        with self._locked():
            if path.exists() or path.is_symlink():
                raise StateConflict("run_id: already exists")
            _atomic_json(path, run)
        return run

    def create_run_claimed(self, run: dict, claim_keys: list[str]) -> dict:
        """Reserve owner and worker panes before publishing a new run.

        A crash after the claim write can leave an orphan claim, which blocks
        reuse until reconciled. It cannot silently give the pane to two runs.
        """
        validate_run(run)
        if run["generation"] != 0 or run["owner_epoch"] != 1:
            raise ContractError("generation/owner_epoch: expected 0/1 for new run")
        if not claim_keys or len(set(claim_keys)) != len(claim_keys):
            raise ContractError("claim_keys: expected unique nonempty list")
        if any(not isinstance(key, str) or not ID.fullmatch(key) for key in claim_keys):
            raise ContractError("claim_keys: invalid identifier")
        path = self._path(run["run_id"])
        with self._locked():
            if path.exists() or path.is_symlink():
                raise StateConflict("run_id: already exists")
            claims = self._load_claims()
            for key in claim_keys:
                if key in claims:
                    raise StateConflict(f"claim_keys: pane already claimed ({key})")
            for key in claim_keys:
                claims[key] = {"run_id": run["run_id"], "owner_epoch": 1}
            _atomic_json(self.root / "claims.json", claims)
            _atomic_json(path, run)
        return run

    def load_run(self, run_id: str) -> dict:
        run = _read_json(self._path(run_id))
        validate_run(run)
        return run

    def update_run(self, run: dict, *, expected_generation: int, owner_epoch: int) -> dict:
        validate_run(run)
        path = self._path(run["run_id"])
        with self._locked():
            current = _read_json(path)
            validate_run(current)
            if current["generation"] != expected_generation or current["owner_epoch"] != owner_epoch:
                raise StateConflict("generation or owner_epoch changed")
            if run["owner_epoch"] != owner_epoch or run["generation"] != expected_generation + 1:
                raise StateConflict("new generation or owner_epoch invalid")
            if run["run_id"] != current["run_id"] or run["scope"] != current["scope"]:
                raise StateConflict("run identity or scope changed")
            if run["owner"] != current["owner"]:
                raise StateConflict("owner binding changed")
            for key in ("mode", "setup_plan", "bootstrap_authorized", "execution_mode", "parallel_authorized"):
                if run[key] != current[key]:
                    raise StateConflict(f"{key} changed after run initialization")
            if current["team_frozen"]:
                if not run["team_frozen"] or len(run["members"]) != len(current["members"]):
                    raise StateConflict("frozen team changed")
                for old, new in zip(current["members"], run["members"]):
                    if _static_member(old) != _static_member(new):
                        raise StateConflict("frozen team changed")
                    if new["conversation_id"] != old["conversation_id"]:
                        reset = run.get("resets", {}).get(old["member_id"], {})
                        if (reset.get("state") != "complete"
                                or reset.get("old_conversation_id") != old["conversation_id"]
                                or reset.get("new_conversation_id") != new["conversation_id"]):
                            raise StateConflict("conversation changed without completed native reset")
            if current["team_frozen"] and (run["setup_journal"] != current["setup_journal"]
                                           or run["created_resources"] != current["created_resources"]):
                raise StateConflict("frozen setup changed")
            _atomic_json(path, run)
        return run

    def resume_owner(self, run_id: str, *, expected_epoch: int) -> dict:
        path = self._path(run_id)
        with self._locked():
            run = _read_json(path)
            validate_run(run)
            if run["owner_epoch"] != expected_epoch:
                raise StateConflict("owner_epoch changed")
            run["owner_epoch"] += 1
            run["generation"] += 1
            run["awaiting_user_resume"] = True
            claims = self._load_claims()
            for claim in claims.values():
                if claim["run_id"] == run_id:
                    claim["owner_epoch"] = run["owner_epoch"]
            _atomic_json(path, run)
            _atomic_json(self.root / "claims.json", claims)
            return run

    def _load_claims(self) -> dict:
        path = self.root / "claims.json"
        if not path.exists() and not path.is_symlink():
            return {}
        return _read_json(path)

    def claim_member(self, key: str, *, run_id: str, owner_epoch: int) -> dict:
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ContractError("member claim key: invalid")
        with self._locked():
            run = _read_json(self._path(run_id))
            validate_run(run)
            if run["owner_epoch"] != owner_epoch:
                raise StateConflict("owner_epoch changed")
            claims = self._load_claims()
            existing = claims.get(key)
            if existing and existing["run_id"] != run_id:
                raise StateConflict("member already claimed")
            # A crash between updating the run and claims during resume leaves
            # a claim with the previous epoch. The run is authoritative.
            claims[key] = {"run_id": run_id, "owner_epoch": owner_epoch}
            _atomic_json(self.root / "claims.json", claims)
            return claims[key]

    def release_member(self, key: str, *, run_id: str, owner_epoch: int) -> None:
        with self._locked():
            run = _read_json(self._path(run_id))
            if run["owner_epoch"] != owner_epoch:
                raise StateConflict("owner_epoch changed")
            claims = self._load_claims()
            if not claims.get(key) or claims[key]["run_id"] != run_id:
                raise StateConflict("member claim changed")
            del claims[key]
            _atomic_json(self.root / "claims.json", claims)

    def _event_change(self, run_id: str, owner_epoch: int, change) -> dict:
        path = self._path(run_id)
        with self._locked():
            run = _read_json(path)
            validate_run(run)
            if run["owner_epoch"] != owner_epoch:
                raise StateConflict("owner_epoch changed")
            change(run)
            run["generation"] += 1
            validate_run(run)
            _atomic_json(path, run)
            return run

    def record_event(self, event: dict, *, owner_epoch: int) -> str:
        validate_event(event)
        key = event_id(event)

        def change(run):
            if event["assignment_id"] not in run["assignments"]:
                raise ContractError("assignment_id: unknown")
            if key not in run["outbox"]:
                run["outbox"][key] = {"event": event, "received": False, "action_intent": None, "applied": False}

        self._event_change(event["run_id"], owner_epoch, change)
        return key

    def receive_event(self, run_id: str, key: str, *, owner_epoch: int) -> dict:
        def change(run):
            if key not in run["outbox"]:
                raise ContractError("event_id: unknown")
            run["outbox"][key]["received"] = True

        return self._event_change(run_id, owner_epoch, change)

    def plan_action(self, run_id: str, key: str, action_key: str, *, owner_epoch: int) -> dict:
        if not ID.fullmatch(action_key):
            raise ContractError("action_key: invalid")

        def change(run):
            item = run["outbox"].get(key)
            if not item or not item["received"]:
                raise StateConflict("event not received")
            if item["action_intent"] not in (None, action_key):
                raise StateConflict("action intent changed")
            item["action_intent"] = action_key

        return self._event_change(run_id, owner_epoch, change)

    def mark_applied(self, run_id: str, key: str, action_key: str, *, owner_epoch: int) -> dict:
        def change(run):
            item = run["outbox"].get(key)
            if not item or item["action_intent"] != action_key:
                raise StateConflict("action intent missing or changed")
            item["applied"] = True

        return self._event_change(run_id, owner_epoch, change)
