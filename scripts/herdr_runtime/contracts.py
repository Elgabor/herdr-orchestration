"""Versioned data contracts. Inputs from workers and terminals are untrusted."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat

SCHEMA_VERSION = 1
MAX_RESULT_BYTES = 12 * 1024
MAX_ENVELOPE_BYTES = 4 * 1024
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
HERDR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
AGENT_ALIAS = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
HARNESSES = {"codex", "claude", "pi", "opencode"}
ASSIGNMENT_STATES = {
    "prepared", "dispatching", "active", "result_received", "collected",
    "delivery_uncertain", "blocked", "protocol_error", "cancel_requested",
    "cancelled", "interrupted", "needs_reconcile",
}
RESULT_STATES = {"done", "blocked", "needs_info", "failed"}


class ContractError(ValueError):
    pass


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{field}: expected object")
    return value


def _required(obj: dict, key: str, kind: type, field: str = "") -> object:
    path = f"{field}.{key}" if field else key
    if key not in obj:
        raise ContractError(f"{path}: required")
    value = obj[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ContractError(f"{path}: expected {kind.__name__}")
    if kind is str and not value.strip():
        raise ContractError(f"{path}: empty")
    return value


def _id(obj: dict, key: str, field: str = "") -> str:
    value = _required(obj, key, str, field)
    path = f"{field}.{key}" if field else key
    if not ID.fullmatch(value):
        raise ContractError(f"{path}: invalid identifier")
    return value


def _herdr_id(obj: dict, key: str, field: str = "") -> str:
    value = _required(obj, key, str, field)
    path = f"{field}.{key}" if field else key
    if not HERDR_ID.fullmatch(value):
        raise ContractError(f"{path}: invalid Herdr identifier")
    return value


def _version(obj: dict) -> None:
    value = _required(obj, "schema_version", int)
    if value != SCHEMA_VERSION:
        raise ContractError(f"schema_version: unsupported {value}")


def _enum(obj: dict, key: str, values: set[str], field: str = "") -> str:
    value = _required(obj, key, str, field)
    if value not in values:
        raise ContractError(f"{field + '.' if field else ''}{key}: invalid value {value}")
    return value


def _nonnegative(obj: dict, key: str, field: str = "") -> int:
    value = _required(obj, key, int, field)
    if value < 0:
        raise ContractError(f"{field + '.' if field else ''}{key}: must be nonnegative")
    return value


def _nullable_string(obj: dict, key: str, field: str = "") -> None:
    path = f"{field}.{key}" if field else key
    if key not in obj or (obj[key] is not None and not isinstance(obj[key], str)):
        raise ContractError(f"{path}: expected string or null")


def _relative_path(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ContractError(f"{field}: invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", "."} for part in value.split("/")):
        raise ContractError(f"{field}: path traversal or absolute path")


def validate_member(value: object) -> dict:
    obj = _object(value, "member")
    _id(obj, "member_id")
    _required(obj, "label", str)
    _enum(obj, "harness", HARNESSES)
    for key in ("session_id", "workspace_id", "tab_id", "pane_id"):
        _herdr_id(obj, key)
    _herdr_id(obj, "terminal_id")
    _nonnegative(obj, "occupant_revision")
    _enum(obj, "identity_status", {"verified", "unknown"})
    _nullable_string(obj, "agent_alias")
    if obj["agent_alias"] is not None and not AGENT_ALIAS.fullmatch(obj["agent_alias"]):
        raise ContractError("agent_alias: invalid Herdr alias")
    _nullable_string(obj, "conversation_id")
    if obj["identity_status"] == "verified" and obj["conversation_id"] is None:
        raise ContractError("conversation_id: required for verified identity")
    if type(obj.get("created_by_run")) is not bool:
        raise ContractError("created_by_run: expected bool")
    return obj


def validate_run(value: object) -> dict:
    obj = _object(value, "run")
    _version(obj)
    _id(obj, "run_id")
    _required(obj, "mission", str)
    mode = _enum(obj, "mode", {"adopt_existing", "bootstrap_team"})
    _nonnegative(obj, "generation")
    _nonnegative(obj, "owner_epoch")
    scope = _object(_required(obj, "scope", dict), "scope")
    for key in ("session_id", "workspace_id", "tab_id", "owner_pane_id"):
        _herdr_id(scope, key, "scope")
    owner = validate_member(_required(obj, "owner", dict))
    if owner["pane_id"] != scope["owner_pane_id"]:
        raise ContractError("owner.pane_id: outside owner scope")
    for key in ("session_id", "workspace_id", "tab_id"):
        if owner[key] != scope[key]:
            raise ContractError(f"owner.{key}: outside owner scope")
    _enum(obj, "execution_mode", {"sequential", "parallel"})
    for key in ("parallel_authorized", "bootstrap_authorized", "team_frozen", "pause_dispatch"):
        if type(obj.get(key)) is not bool:
            raise ContractError(f"{key}: expected bool")
    members = _required(obj, "members", list)
    ids = {owner["member_id"]}
    panes = {owner["pane_id"]}
    for index, member in enumerate(members):
        validate_member(member)
        if member["member_id"] in ids:
            raise ContractError(f"members[{index}].member_id: duplicate")
        if member["pane_id"] in panes:
            raise ContractError(f"members[{index}].pane_id: duplicate")
        ids.add(member["member_id"])
        panes.add(member["pane_id"])
        for key in ("session_id", "workspace_id", "tab_id"):
            if member[key] != scope[key]:
                raise ContractError(f"members[{index}].{key}: outside run scope")
    if obj["execution_mode"] == "parallel" and not obj["parallel_authorized"]:
        raise ContractError("execution_mode: parallel not authorized")
    assignments = _required(obj, "assignments", dict)
    for key, assignment in assignments.items():
        validate_assignment(assignment)
        if key != assignment["assignment_id"] or assignment["run_id"] != obj["run_id"]:
            raise ContractError(f"assignments.{key}: identity mismatch")
    _required(obj, "outbox", dict)
    if "resets" in obj and not isinstance(obj["resets"], dict):
        raise ContractError("resets: expected object")
    for key in ("setup_plan", "setup_journal", "created_resources"):
        _required(obj, key, list)
    if mode == "adopt_existing":
        if not obj["team_frozen"] or any(obj[key] for key in ("setup_plan", "setup_journal", "created_resources")):
            raise ContractError("adopt_existing: frozen roster and empty setup journal required")
    if mode == "bootstrap_team" and (not obj["bootstrap_authorized"] or not obj["setup_plan"]):
        raise ContractError("setup_plan: authorized bootstrap requires a plan")
    if mode == "bootstrap_team":
        if len(obj["setup_plan"]) != len(obj["setup_journal"]):
            raise ContractError("setup_journal: length differs from plan")
        for index, item in enumerate(obj["setup_journal"]):
            item = _object(item, f"setup_journal[{index}]")
            if item.get("state") not in {"planned", "split_pending", "pane_created", "launch_pending", "active"}:
                raise ContractError(f"setup_journal[{index}].state: invalid")
            if item.get("pane_id") is not None:
                _herdr_id(item, "pane_id", f"setup_journal[{index}]")
        resource_panes = set()
        for index, item in enumerate(obj["created_resources"]):
            item = _object(item, f"created_resources[{index}]")
            if item.get("type") != "pane":
                raise ContractError(f"created_resources[{index}].type: invalid")
            pane_id = _herdr_id(item, "pane_id", f"created_resources[{index}]")
            if pane_id in resource_panes:
                raise ContractError(f"created_resources[{index}].pane_id: duplicate")
            resource_panes.add(pane_id)
    return obj


def validate_assignment(value: object) -> dict:
    obj = _object(value, "assignment")
    _version(obj)
    for key in ("run_id", "assignment_id", "member_id", "context_key"):
        _id(obj, key)
    _nullable_string(obj, "conversation_id")
    _nonnegative(obj, "revision")
    if _nonnegative(obj, "attempt") == 0:
        raise ContractError("attempt: must be positive")
    _enum(obj, "state", ASSIGNMENT_STATES)
    _enum(obj, "return_to", {"owner"})
    for key in ("repo", "base_head", "work_snapshot"):
        _nullable_string(obj, key)
    if obj["repo"] is None and obj["base_head"] is not None:
        raise ContractError("base_head: requires repo")
    return obj


def validate_result(value: object) -> dict:
    obj = _object(value, "result")
    _version(obj)
    for key in ("run_id", "assignment_id", "member_id"):
        _id(obj, key)
    _nonnegative(obj, "revision")
    if _nonnegative(obj, "attempt") == 0:
        raise ContractError("attempt: must be positive")
    _nullable_string(obj, "conversation_id")
    _enum(obj, "status", RESULT_STATES)
    _required(obj, "summary", str)
    for key in ("repo", "base_head", "work_snapshot"):
        _nullable_string(obj, key)
    for key in ("files_changed", "verification", "open_points", "artifacts"):
        _required(obj, key, list)
    for i, path in enumerate(obj["files_changed"]):
        _relative_path(path, f"files_changed[{i}]")
    for i, item in enumerate(obj["verification"]):
        check = _object(item, f"verification[{i}]")
        _required(check, "check", str, f"verification[{i}]")
        _required(check, "cwd", str, f"verification[{i}]")
        _enum(check, "result", {"PASS", "FAIL", "NOT_RUN"}, f"verification[{i}]")
        _nullable_string(check, "evidence", f"verification[{i}]")
    for i, item in enumerate(obj["artifacts"]):
        artifact = _object(item, f"artifacts[{i}]")
        _relative_path(_required(artifact, "path", str, f"artifacts[{i}]"), f"artifacts[{i}].path")
        _required(artifact, "type", str, f"artifacts[{i}]")
        _nullable_string(artifact, "sha256", f"artifacts[{i}]")
    for i, point in enumerate(obj["open_points"]):
        if not isinstance(point, str):
            raise ContractError(f"open_points[{i}]: expected string")
    if not obj["verification"]:
        _required(obj, "verification_note", str)
    return obj


def validate_result_binding(result: dict, assignment: dict) -> None:
    validate_result(result)
    validate_assignment(assignment)
    for key in ("run_id", "assignment_id", "member_id", "revision", "attempt", "conversation_id", "repo", "base_head", "work_snapshot"):
        if result[key] != assignment[key]:
            raise ContractError(f"{key}: expected assignment binding")


def read_result_file(root: Path, relative_path: str) -> dict:
    """Read a bounded worker file through no-follow directory descriptors."""
    _relative_path(relative_path, "result_path")
    root = Path(root)
    if root.is_symlink():
        raise ContractError("result_root: symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(root, flags | os.O_DIRECTORY)
    try:
        parts = relative_path.split("/")
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], flags, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RESULT_BYTES:
                raise ContractError("result_path: not a bounded regular file")
            data = os.read(fd, MAX_RESULT_BYTES + 1)
            if len(data) > MAX_RESULT_BYTES:
                raise ContractError("result_path: too large")
        finally:
            os.close(fd)
    except OSError as error:
        raise ContractError(f"result_path: unsafe or unreadable: {error.strerror}") from error
    finally:
        os.close(directory)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"result_path: invalid UTF-8 JSON: {error}") from error
    return validate_result(value)


def validate_metric(value: object) -> dict:
    obj = _object(value, "metric")
    state = _enum(obj, "state", {"known", "unknown", "unavailable", "stale"})
    for key in ("unit", "scope", "observed_at", "source"):
        _required(obj, key, str)
    if "value" not in obj:
        raise ContractError("value: required")
    if state != "known" and obj["value"] is not None:
        raise ContractError("value: must be null unless state is known")
    if state == "known" and obj["value"] is None:
        raise ContractError("value: required when known")
    return obj


def validate_capability(value: object) -> dict:
    obj = _object(value, "capability")
    _enum(obj, "status", {"verified", "unknown", "unsupported"})
    for key in ("method", "version", "observation"):
        _required(obj, key, str)
    return obj


def validate_event(value: object) -> dict:
    obj = _object(value, "event")
    _version(obj)
    for key in ("run_id", "assignment_id", "type"):
        _id(obj, key)
    _nonnegative(obj, "revision")
    if _nonnegative(obj, "attempt") == 0:
        raise ContractError("attempt: must be positive")
    digest = _required(obj, "result_digest", str)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("result_digest: expected SHA-256 hex")
    return obj


def event_id(event: dict) -> str:
    validate_event(event)
    fields = ("run_id", "assignment_id", "revision", "attempt", "type", "result_digest")
    body = json.dumps([event[key] for key in fields], separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
