"""Bounded assignment dispatch and structured result publication."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .context import TESTED_HERDR_VERSION, TESTED_PROTOCOL, inspect_team, verify_binding
from .contracts import (ContractError, ID, MAX_RESULT_BYTES, SCHEMA_VERSION,
                        event_id, read_result_file, validate_assignment,
                        validate_result_binding)
from .state import StateStore
from .transport import HerdrClient


class AssignmentError(RuntimeError):
    def __init__(self, outcome: str, message: str):
        self.outcome = outcome
        super().__init__(message)


ACTIVE = {"prepared", "dispatching", "active", "result_received", "delivery_uncertain",
          "blocked", "protocol_error", "cancel_requested", "interrupted", "needs_reconcile"}


def _save(run: dict, store: StateStore, epoch: int) -> dict:
    generation = run["generation"]
    run["generation"] += 1
    return store.update_run(run, expected_generation=generation, owner_epoch=epoch)


def validate_dispatch_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ContractError("dispatch config: expected object")
    assignment = config.get("assignment")
    validate_assignment(assignment)
    if assignment["state"] != "prepared" or assignment["revision"] != 0 or assignment["attempt"] != 1:
        raise ContractError("assignment: new dispatch must be prepared, revision 0, attempt 1")
    for key in ("instructions", "acceptance", "entry_points", "write_scope"):
        if not isinstance(config.get(key), list) or not all(isinstance(item, str) and item.strip()
                                                           for item in config[key]):
            raise ContractError(f"dispatch.{key}: expected string list")
    if not config["instructions"] or not config["acceptance"]:
        raise ContractError("dispatch: instructions and acceptance required")
    for key in ("result_root", "result_path"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ContractError(f"dispatch.{key}: required")
    root = Path(config["result_root"])
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ContractError("result_root: expected existing absolute directory")
    path = config["result_path"]
    if Path(path).is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ContractError("result_path: expected safe relative path")
    if config.get("continuation_of") is not None:
        if not isinstance(config["continuation_of"], str) or not ID.fullmatch(config["continuation_of"]):
            raise ContractError("continuation_of: invalid")
    if assignment["repo"] is None and config["write_scope"]:
        raise ContractError("write_scope: research without repo cannot claim project writes")
    if len(json.dumps(config, ensure_ascii=False).encode()) > 32 * 1024:
        raise ContractError("dispatch: exceeds 32 KiB")
    return config


def _packet(config: dict) -> str:
    assignment = config["assignment"]
    body = {
        "assignment": {key: assignment[key] for key in (
            "run_id", "assignment_id", "member_id", "context_key", "conversation_id",
            "revision", "attempt", "return_to", "repo", "base_head", "work_snapshot")},
        "instructions": config["instructions"], "acceptance": config["acceptance"],
        "entry_points": config["entry_points"], "write_scope": config["write_scope"],
        "result": {"root": config["result_root"], "path": config["result_path"],
                   "schema_version": SCHEMA_VERSION, "max_bytes": MAX_RESULT_BYTES},
        "worker_boundary": "Work only within the assigned scope. Write the JSON result atomically; do not orchestrate other panes or change the team.",
    }
    return "Herdr assignment contract (JSON):\n" + json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def dispatch(client: HerdrClient, store: StateStore, config: dict, expected_generation: int,
             owner_epoch: int, channel=None) -> dict:
    config = validate_dispatch_config(config)
    assignment = config["assignment"]
    _, private = inspect_team(client)
    run = store.load_run(assignment["run_id"])
    if run["generation"] != expected_generation or run["owner_epoch"] != owner_epoch:
        raise AssignmentError("needs_reconcile", "run generation or owner epoch changed")
    if run["scope"] != private["scope"] or not run["team_frozen"]:
        raise AssignmentError("scope_mismatch", "owner scope or roster changed")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    if run["pause_dispatch"]:
        raise AssignmentError("busy", "dispatch paused by owner")
    if assignment["assignment_id"] in run["assignments"]:
        raise AssignmentError("busy", "assignment already exists; reconcile instead of resending")
    member = next((item for item in run["members"] if item["member_id"] == assignment["member_id"]), None)
    if member is None:
        raise ContractError("member_id: not in frozen roster")
    if member["pane_id"] == run["scope"]["owner_pane_id"]:
        raise AssignmentError("scope_mismatch", "owner cannot be own worker")
    live = next((item for item in private["agents"] if item["pane_id"] == member["pane_id"]), None)
    verify_binding(member, live, private["panes"].get(member["pane_id"]), run["scope"])
    if live.get("agent_status") not in {"idle", "done"} or live.get("interactive_ready") is False:
        raise AssignmentError("busy", "worker not ready for a new assignment")
    if assignment["conversation_id"] != member["conversation_id"] or assignment["context_key"] != member.get("context_key"):
        raise AssignmentError("identity_changed", "native conversation/context differs; reset a distinct assignment first")
    if assignment["repo"] is not None:
        raise AssignmentError("capability_blocked", "repository snapshot verification is not certified yet")
    if assignment["return_to"] != "owner":
        raise AssignmentError("capability_blocked", "direct relay is not authorized")
    active = [item for item in run["assignments"].values() if item["state"] in ACTIVE]
    if any(item["member_id"] == member["member_id"] for item in active):
        raise AssignmentError("busy", "member has an unresolved assignment")
    if active and (run["execution_mode"] != "parallel" or not run["parallel_authorized"]):
        raise AssignmentError("busy", "parallelism was not authorized")
    if assignment["repo"] and config["write_scope"] and any(
        item.get("repo") == assignment["repo"] and item.get("write_scope") for item in active
    ):
        raise AssignmentError("busy", "shared checkout already has a writer")
    if channel is None or not channel.supports(run["owner"], member):
        raise AssignmentError("capability_blocked", "same-owner return channel is not armed for this harness")

    packet = _packet(config)
    handle = channel.arm(run, assignment, member)
    saved = dict(assignment)
    saved["result_root"] = config["result_root"]
    saved["result_path"] = config["result_path"]
    saved["write_scope"] = config["write_scope"]
    saved["entry_points"] = config["entry_points"]
    saved["return_handle"] = handle
    saved["state"] = "dispatching"
    run["assignments"][saved["assignment_id"]] = saved
    _save(run, store, owner_epoch)
    try:
        channel.send(member["pane_id"], packet, handle)
    except Exception as error:
        saved["state"] = "delivery_uncertain"
        _save(run, store, owner_epoch)
        raise AssignmentError("delivery_uncertain", "task delivery uncertain; do not resend") from error
    saved["state"] = "active"
    _save(run, store, owner_epoch)
    return run


def publish_result(client: HerdrClient, store: StateStore, run_id: str, assignment_id: str,
                   result_root: Path, result_path: str) -> tuple[dict, dict]:
    if os.environ.get("HERDR_ENV") != "1":
        raise AssignmentError("capability_blocked", "result must be published from a Herdr pane")
    run = store.load_run(run_id)
    assignment = run["assignments"].get(assignment_id)
    if not assignment:
        raise ContractError("assignment_id: unknown")
    if (assignment.get("result_root"), assignment.get("result_path")) != (str(result_root), result_path):
        raise AssignmentError("protocol_error", "result path differs from registered assignment")
    current = client.current_pane()
    status = client.status()
    server, local = status.get("server", {}), status.get("client", {})
    if (server.get("running") is not True or server.get("compatible") is not True
            or (server.get("version"), local.get("version"), server.get("protocol"), local.get("protocol"))
            != (TESTED_HERDR_VERSION, TESTED_HERDR_VERSION, TESTED_PROTOCOL, TESTED_PROTOCOL)
            or server.get("session") != run["scope"]["session_id"]):
        raise AssignmentError("capability_blocked", "Herdr session/version changed")
    member = next((item for item in run["members"] if item["member_id"] == assignment["member_id"]), None)
    if not member or current.get("pane_id") != member["pane_id"] or current.get("terminal_id") != member["terminal_id"]:
        raise AssignmentError("scope_mismatch", "result publication must come from assigned worker pane")
    snapshot = client.snapshot()
    if (snapshot.get("version"), snapshot.get("protocol")) != (TESTED_HERDR_VERSION, TESTED_PROTOCOL):
        raise AssignmentError("capability_blocked", "Herdr snapshot version changed")
    live = next((item for item in snapshot.get("agents", []) if item.get("pane_id") == member["pane_id"]), None)
    pane = next((item for item in snapshot.get("panes", []) if item.get("pane_id") == member["pane_id"]), None)
    verify_binding(member, live, pane, run["scope"])
    try:
        result = read_result_file(result_root, result_path)
        validate_result_binding(result, assignment)
    except ContractError as error:
        raise AssignmentError("protocol_error", str(error)) from error
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if assignment["state"] == "result_received":
        if assignment.get("result_digest") == digest:
            return run, result
        raise AssignmentError("protocol_error", "different result already published for assignment")
    if assignment["state"] not in {"active", "dispatching"}:
        raise AssignmentError("needs_reconcile", "assignment is not accepting a result")
    assignment["result_digest"] = digest
    assignment["result_status"] = result["status"]
    assignment["state"] = "result_received"
    event = {"schema_version": SCHEMA_VERSION, "run_id": run_id,
             "assignment_id": assignment_id, "revision": assignment["revision"],
             "attempt": assignment["attempt"], "type": "result_ready", "result_digest": digest}
    key = event_id(event)
    run["outbox"][key] = {"event": event, "received": False, "action_intent": None, "applied": False}
    _save(run, store, run["owner_epoch"])
    return run, result
