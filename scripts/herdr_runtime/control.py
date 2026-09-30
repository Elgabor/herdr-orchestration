"""Versioned owner controls; amendment delivery never implies worker acceptance."""

from __future__ import annotations

import json

from .assignment import AssignmentError, _save
from .context import inspect_team, verify_binding
from .contracts import ContractError, ID
from .state import StateConflict, StateStore
from .transport import HerdrClient, HerdrError

MAX_INSTRUCTION = 4096


def validate_control(config: dict) -> dict:
    if not isinstance(config, dict) or config.get("type") not in {
        "future_instruction", "pause_dispatch", "amend_assignment", "cancel_assignment", "change_goal"
    }:
        raise ContractError("control.type: unsupported")
    if not isinstance(config.get("run_id"), str) or not ID.fullmatch(config["run_id"]):
        raise ContractError("control.run_id: invalid")
    if config["type"] in {"future_instruction", "amend_assignment"}:
        value = config.get("instruction")
        if not isinstance(value, str) or not value.strip() or len(value.encode()) > MAX_INSTRUCTION:
            raise ContractError("control.instruction: expected nonempty text under 4 KiB")
    if config["type"] == "future_instruction":
        if not isinstance(config.get("instruction_id"), str) or not ID.fullmatch(config["instruction_id"]):
            raise ContractError("control.instruction_id: invalid")
    if config["type"] in {"amend_assignment", "cancel_assignment"}:
        if not isinstance(config.get("assignment_id"), str) or not ID.fullmatch(config["assignment_id"]):
            raise ContractError("control.assignment_id: invalid")
    if config["type"] == "amend_assignment":
        if not isinstance(config.get("amendment_id"), str) or not ID.fullmatch(config["amendment_id"]):
            raise ContractError("control.amendment_id: invalid")
        if type(config.get("expected_revision")) is not int or config["expected_revision"] < 0:
            raise ContractError("control.expected_revision: invalid")
    if config["type"] == "pause_dispatch" and type(config.get("paused")) is not bool:
        raise ContractError("control.paused: expected bool")
    return config


def apply_control(client: HerdrClient, store: StateStore, config: dict,
                  expected_generation: int, owner_epoch: int) -> dict:
    config = validate_control(config)
    _, private = inspect_team(client)
    run = store.load_run(config["run_id"])
    if run["generation"] != expected_generation or run["owner_epoch"] != owner_epoch:
        raise AssignmentError("needs_reconcile", "run generation or owner epoch changed")
    if run["scope"] != private["scope"]:
        raise AssignmentError("scope_mismatch", "owner tab changed")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    kind = config["type"]
    if kind == "future_instruction":
        entries = run.setdefault("future_instructions", [])
        if any(item["instruction_id"] == config["instruction_id"] for item in entries):
            raise AssignmentError("busy", "future instruction ID already recorded")
        entries.append({"instruction_id": config["instruction_id"],
                        "text": config["instruction"], "created_generation": expected_generation})
        return _save(run, store, owner_epoch)
    if kind == "pause_dispatch":
        if run["pause_dispatch"] == config["paused"]:
            return run
        run["pause_dispatch"] = config["paused"]
        return _save(run, store, owner_epoch)
    if kind == "cancel_assignment":
        raise AssignmentError("capability_blocked", "targeted process cancellation not certified")
    if kind == "change_goal":
        raise AssignmentError("capability_blocked", "native goal control not certified; goal remains optional")

    assignment = run["assignments"].get(config["assignment_id"])
    if not assignment or assignment["revision"] != config["expected_revision"]:
        raise AssignmentError("needs_reconcile", "assignment or revision changed")
    if assignment["state"] not in {"active", "dispatching"}:
        raise AssignmentError("needs_reconcile", "assignment is no longer active")
    if assignment["revision"] >= 100:
        raise ContractError("assignment.revision: limit reached")
    member = next((item for item in run["members"] if item["member_id"] == assignment["member_id"]), None)
    live = next((item for item in private["agents"] if member and item["pane_id"] == member["pane_id"]), None)
    if not member or not live:
        raise AssignmentError("identity_changed", "assigned worker missing")
    verify_binding(member, live, private["panes"].get(member["pane_id"]), run["scope"])
    if live.get("agent_status") != "working":
        raise AssignmentError("needs_reconcile", "worker no longer working; collect its outcome first")
    amendments = assignment.setdefault("amendments", [])
    if any(item["amendment_id"] == config["amendment_id"] for item in amendments):
        raise AssignmentError("busy", "amendment ID already recorded")
    revision = assignment["revision"] + 1
    amendments.append({"amendment_id": config["amendment_id"], "revision": revision,
                       "instruction": config["instruction"], "delivery": "dispatching",
                       "worker_ack": False})
    assignment["revision"] = revision
    try:
        _save(run, store, owner_epoch)
    except StateConflict as error:
        raise AssignmentError("needs_reconcile", "result or owner state changed before amendment") from error
    packet = json.dumps({"type": "assignment_amendment", "run_id": run["run_id"],
                         "assignment_id": assignment["assignment_id"],
                         "revision": revision, "amendment_id": config["amendment_id"],
                         "instruction": config["instruction"],
                         "boundary": "Continue this assignment in the same native conversation. Include the new revision and all acknowledged_amendments IDs in the result."},
                        ensure_ascii=False, separators=(",", ":"))
    try:
        client.agent_prompt(member["pane_id"], packet)
    except HerdrError as error:
        latest = store.load_run(run["run_id"])
        if latest["owner_epoch"] != owner_epoch:
            raise AssignmentError("needs_reconcile", "owner changed during amendment delivery") from error
        record = next((item for item in latest["assignments"][assignment["assignment_id"]]["amendments"]
                       if item["amendment_id"] == config["amendment_id"]), None)
        if record is None:
            raise AssignmentError("needs_reconcile", "amendment changed during delivery") from error
        if record["worker_ack"]:
            return latest
        record["delivery"] = "uncertain"
        try:
            _save(latest, store, owner_epoch)
        except StateConflict as conflict:
            raise AssignmentError("needs_reconcile", "amendment state changed during delivery") from conflict
        raise AssignmentError("delivery_uncertain", "amendment delivery uncertain; do not resend") from error
    latest = store.load_run(run["run_id"])
    if latest["owner_epoch"] != owner_epoch:
        raise AssignmentError("needs_reconcile", "owner changed during amendment delivery")
    record = next((item for item in latest["assignments"][assignment["assignment_id"]]["amendments"]
                   if item["amendment_id"] == config["amendment_id"]), None)
    if record is None:
        raise AssignmentError("needs_reconcile", "amendment changed during delivery")
    if record["worker_ack"]:
        return latest
    record["delivery"] = "queued"
    try:
        return _save(latest, store, owner_epoch)
    except StateConflict as error:
        raise AssignmentError("needs_reconcile", "amendment state changed during delivery") from error
