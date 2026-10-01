"""Bounded assignment dispatch and structured result publication."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import copy

from .context import TESTED_HERDR_VERSION, TESTED_PROTOCOL, inspect_team, verify_binding
from .contracts import (ContractError, ID, MAX_RESULT_BYTES, SCHEMA_VERSION,
                        event_id, read_result_file, validate_assignment,
                        validate_result_binding)
from .state import StateStore, _GenerationConflict
from .transport import HerdrClient, HerdrError
from .snapshot import SnapshotError, changed_paths, clean_snapshot


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


def _change_assignment(store: StateStore, baseline: dict, assignment_id: str, change,
                       *, allow_revision: bool = False, check_listener: bool = False) -> dict:
    """Retry only a local CAS, never an external action or wait.

    Each retry merges into fresh state. Identity/epoch/attempt changes invalidate
    the operation; an amendment may advance the revision only for wait completion
    or amendment delivery. No lock is held while invoking the channel.
    """
    original = baseline["assignments"][assignment_id]
    member = next((item for item in baseline["members"]
                   if item["member_id"] == original["member_id"]), None)
    identity = ("schema_version", "run_id", "assignment_id", "member_id", "context_key",
                "conversation_id", "attempt", "return_to", "repo", "base_head",
                "work_snapshot", "result_root", "result_path", "write_scope",
                "entry_points", "future_instruction_ids", "route_grant")
    for attempt in range(9):
        latest = store.load_run(baseline["run_id"])
        current = latest["assignments"].get(assignment_id)
        bound = next((item for item in latest["members"]
                      if item["member_id"] == original["member_id"]), None)
        if check_listener and latest["owner_epoch"] != baseline["owner_epoch"]:
            raise AssignmentError("needs_reconcile", "listener changed during wait")
        if (latest["run_id"] != baseline["run_id"] or latest["scope"] != baseline["scope"]
                or latest["owner"] != baseline["owner"]
                or latest["owner_epoch"] != baseline["owner_epoch"]
                or latest["generation"] < baseline["generation"]
                or member is None or bound != member or current is None
                or any(current.get(key) != original.get(key) for key in identity)
                or current["conversation_id"] != bound["conversation_id"]
                or current["context_key"] != bound.get("context_key")):
            raise AssignmentError("needs_reconcile", "assignment binding or owner changed during operation")
        if check_listener and current.get("return_handle") != original.get("return_handle"):
            raise AssignmentError("needs_reconcile", "listener changed during wait")
        if (current["revision"] < original["revision"]
                or (not allow_revision and current["revision"] != original["revision"])):
            raise AssignmentError("needs_reconcile", "assignment revision changed during operation")
        old_amendments = original.get("amendments", [])
        amendments = current.get("amendments", [])
        if (len(amendments) < len(old_amendments) or any(
            any(old.get(key) != new.get(key) for key in ("amendment_id", "revision", "instruction"))
            for old, new in zip(old_amendments, amendments)
        )):
            raise AssignmentError("needs_reconcile", "assignment amendments changed during operation")
        if not change(latest, current):
            return latest
        if attempt == 8:
            break  # Still allow a terminal winner after the last failed write.
        try:
            return _save(latest, store, baseline["owner_epoch"])
        except _GenerationConflict:
            # The failed CAS has not written anything. Revalidate all bindings
            # and recompute the transition against the winner's state.
            continue
    raise AssignmentError("needs_reconcile", "concurrent state updates did not settle; task was not resent")


def _has_result(run: dict, assignment: dict) -> bool:
    if assignment["state"] not in {"result_received", "collected"}:
        return False
    event = {"schema_version": SCHEMA_VERSION, "run_id": run["run_id"],
             "assignment_id": assignment["assignment_id"], "revision": assignment["revision"],
             "attempt": assignment["attempt"], "type": "result_ready",
             "result_digest": assignment.get("result_digest")}
    try:
        item = run["outbox"].get(event_id(event))
    except ContractError as error:
        raise AssignmentError("needs_reconcile", "terminal assignment has no valid result digest") from error
    if (not item or item["event"] != event
            or (assignment["state"] == "collected" and not item["received"])):
        raise AssignmentError("needs_reconcile", "terminal assignment has no matching result event")
    return True


def _finish_wait(store: StateStore, baseline: dict, assignment_id: str, completion,
                 *, reattach: bool = False, failed: bool = False) -> dict:
    def change(latest, current):
        if _has_result(latest, current):
            return False
        waiting = {"dispatching", "active", "delivery_uncertain", "needs_reconcile"}
        if current["state"] not in (waiting if reattach else {"dispatching"}):
            raise AssignmentError("needs_reconcile", "assignment changed while waiting")
        if failed:
            current["state"] = "needs_reconcile" if reattach else "delivery_uncertain"
            return True
        if completion is None and not reattach:  # Offline channel, no production wait.
            current["state"] = "active"
            return True
        lifecycle = completion.get("agent_status") if isinstance(completion, dict) else None
        current["worker_lifecycle"] = lifecycle or "unknown"
        if lifecycle in {"done", "idle", "blocked"}:
            current["state"] = "blocked" if lifecycle == "blocked" else "protocol_error"
            digest = hashlib.sha256(
                f"missing-result:{assignment_id}:{current['revision']}".encode()).hexdigest()
            event = {"schema_version": SCHEMA_VERSION, "run_id": latest["run_id"],
                     "assignment_id": assignment_id, "revision": current["revision"],
                     "attempt": current["attempt"], "type": current["state"], "result_digest": digest}
            latest["outbox"].setdefault(event_id(event), {
                "event": event, "received": False, "action_intent": None, "applied": False})
        else:
            current["state"] = "needs_reconcile"
        return True

    return _change_assignment(store, baseline, assignment_id, change,
                              allow_revision=True, check_listener=True)


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
    if assignment["repo"] is not None:
        if not Path(assignment["repo"]).is_absolute() or not assignment["base_head"] or not assignment["work_snapshot"]:
            raise ContractError("repo: absolute checkout, base_head and work_snapshot required")
        for value in config["write_scope"]:
            if (Path(value).is_absolute() or any(part in {"", ".", ".."} for part in value.split("/"))
                    or "\\" in value or "\x00" in value):
                raise ContractError("write_scope: expected safe relative paths")
    if config.get("route_grant") is not None:
        grant = config["route_grant"]
        if (not isinstance(grant, dict) or set(grant) != {"grant_id", "route", "target_member_id", "max_hops"}
                or not isinstance(grant.get("grant_id"), str) or not ID.fullmatch(grant["grant_id"])
                or grant.get("route") != "direct" or type(grant.get("max_hops")) is not int
                or grant["max_hops"] != 1 or not isinstance(grant.get("target_member_id"), str)
                or not ID.fullmatch(grant["target_member_id"])):
            raise ContractError("route_grant: expected exact one-hop target grant")
    if len(json.dumps(config, ensure_ascii=False).encode()) > 32 * 1024:
        raise ContractError("dispatch: exceeds 32 KiB")
    return config


def _packet(config: dict, state_root: Path) -> str:
    assignment = config["assignment"]
    body = {
        "assignment": {key: assignment[key] for key in (
            "run_id", "assignment_id", "member_id", "context_key", "conversation_id",
            "revision", "attempt", "return_to", "repo", "base_head", "work_snapshot")},
        "instructions": config["instructions"], "acceptance": config["acceptance"],
        "entry_points": config["entry_points"], "write_scope": config["write_scope"],
        "result": {"root": config["result_root"], "path": config["result_path"],
                   "schema_version": SCHEMA_VERSION, "max_bytes": MAX_RESULT_BYTES},
        "output_allowlist": [str(Path(config["result_root"]) / config["result_path"])],
        "project_write_allowed": bool(config["write_scope"]),
        "route_grant": config.get("route_grant"),
        "publish_command": ["python3", str(Path(__file__).resolve().parents[1] / "herdr_orchestrate.py"),
                            "assignment", "publish", "--run-id", assignment["run_id"],
                            "--assignment-id", assignment["assignment_id"],
                            "--result-root", config["result_root"], "--result-path", config["result_path"],
                            "--state-dir", str(state_root)],
        "worker_boundary": "Work only within the assigned scope. Write the JSON result atomically; do not orchestrate other panes or change the team.",
    }
    prefix = "Herdr assignment contract (JSON):\n"
    fixed = dict(body)
    for key in ("instructions", "acceptance", "entry_points", "write_scope"):
        fixed[key] = []
    if len((prefix + json.dumps(fixed, ensure_ascii=False, separators=(",", ":"))).encode()) > 1500:
        raise ContractError("worker contract: fixed fields exceed 1,500 bytes; use shorter approved paths")
    packet = prefix + json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(packet.encode()) > 64 * 1024:
        raise ContractError("worker packet: exceeds 64 KiB")
    return packet


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
    if private["owner"].get("agent_status") not in {"idle", "done"}:
        raise AssignmentError("busy", "owner is not idle for native return arm")
    if run["pause_dispatch"]:
        raise AssignmentError("busy", "dispatch paused by owner")
    if run.get("awaiting_user_resume", False):
        raise AssignmentError("busy", "resume needs owner confirmation before new dispatch")
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
        try:
            observed = clean_snapshot(Path(assignment["repo"]))
        except SnapshotError as error:
            raise AssignmentError("needs_reconcile", str(error)) from error
        if (observed["repo"], observed["base_head"], observed["work_snapshot"]) != (
            assignment["repo"], assignment["base_head"], assignment["work_snapshot"]
        ):
            raise AssignmentError("needs_reconcile", "checkout snapshot differs from assigned base")
    if assignment["return_to"] != "owner":
        raise AssignmentError("capability_blocked", "direct relay is not authorized")
    grant = config.get("route_grant")
    if grant is not None and (grant["target_member_id"] == assignment["member_id"] or not any(
        item["member_id"] == grant["target_member_id"] for item in run["members"]
    )):
        raise ContractError("route_grant: target absent from frozen roster or is source")
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

    packet_config = copy.deepcopy(config)
    future = run.get("future_instructions", [])
    packet_config["instructions"] = ([item["text"] for item in future]
                                     + packet_config["instructions"])
    packet = _packet(packet_config, store.root)
    try:
        handle = channel.arm(run, assignment, member)
    except (ValueError, OSError) as error:
        raise AssignmentError("capability_blocked", "owner return arm proof invalid") from error
    saved = dict(assignment)
    saved["result_root"] = config["result_root"]
    saved["result_path"] = config["result_path"]
    saved["write_scope"] = config["write_scope"]
    saved["entry_points"] = config["entry_points"]
    saved["future_instruction_ids"] = [item["instruction_id"] for item in future]
    if grant is not None:
        saved["route_grant"] = grant
    saved["return_handle"] = handle
    saved["state"] = "dispatching"
    run["assignments"][saved["assignment_id"]] = saved
    run["future_instructions"] = []
    baseline = copy.deepcopy(_save(run, store, owner_epoch))
    try:
        completion = channel.send(member["pane_id"], packet, handle)
    except RuntimeError as error:
        # Legacy channels use plain RuntimeError for uncertain delivery. Do not
        # absorb more specific state or implementation errors from the channel.
        if type(error) is not RuntimeError and not isinstance(error, HerdrError):
            raise
        latest = _finish_wait(store, baseline, saved["assignment_id"], None, failed=True)
        if _has_result(latest, latest["assignments"][saved["assignment_id"]]):
            return latest
        raise AssignmentError("delivery_uncertain", "task delivery uncertain; do not resend") from error
    return _finish_wait(store, baseline, saved["assignment_id"], completion)


def reattach_wait(client: HerdrClient, store: StateStore, run_id: str, assignment_id: str,
                  expected_generation: int, owner_epoch: int, channel) -> dict:
    """Arm a replacement Pi listener for an existing assignment; never prompt it."""
    if os.environ.get("HERDR_ENV") != "1":
        raise AssignmentError("capability_blocked", "reattach requires the recorded Herdr owner pane")
    _, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["generation"] != expected_generation or run["owner_epoch"] != owner_epoch:
        raise AssignmentError("needs_reconcile", "run generation or owner epoch changed")
    if run["scope"] != private["scope"]:
        raise AssignmentError("scope_mismatch", "owner scope changed")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    assignment = run["assignments"].get(assignment_id)
    if not assignment:
        raise AssignmentError("protocol_error", "assignment absent")
    member = next((item for item in run["members"] if item["member_id"] == assignment["member_id"]), None)
    live = next((item for item in private["agents"] if member and item["pane_id"] == member["pane_id"]), None)
    if not member:
        raise AssignmentError("identity_changed", "assigned member missing from frozen roster")
    verify_binding(member, live, private["panes"].get(member["pane_id"]), run["scope"])
    if (assignment["conversation_id"] != member["conversation_id"]
            or assignment["context_key"] != member.get("context_key")):
        raise AssignmentError("identity_changed", "assignment conversation/context differs from member")
    if _has_result(run, assignment):
        return run
    if assignment["state"] not in {"dispatching", "active", "delivery_uncertain", "needs_reconcile"}:
        raise AssignmentError("needs_reconcile", "assignment is not waiting for a result")
    if live.get("agent_status") not in {"working", "blocked", "idle", "done"}:
        raise AssignmentError("needs_reconcile", "worker lifecycle is unknown")
    previous = assignment.get("return_handle")
    if not isinstance(previous, dict) or previous.get("kind") != "pi_extension":
        raise AssignmentError("capability_blocked", "original listener identity is not certified")
    if channel is None or not channel.supports(run["owner"], member):
        raise AssignmentError("capability_blocked", "replacement owner return channel is not armed")
    try:
        handle = channel.arm(run, assignment, member)
    except (ValueError, OSError) as error:
        raise AssignmentError("capability_blocked", "replacement owner arm proof invalid") from error
    if (not isinstance(handle, dict) or handle.get("kind") != "pi_extension"
            or handle.get("owner_process_pid") != previous.get("owner_process_pid")
            or handle.get("owner_session_file") != previous.get("owner_session_file")):
        raise AssignmentError("capability_blocked", "owner process or session changed; transfer not certified")
    old_pid = previous.get("listener_pid")
    if not isinstance(old_pid, int) or old_pid <= 0 or old_pid == os.getpid():
        raise AssignmentError("capability_blocked", "original listener identity invalid or still active")
    try:
        os.kill(old_pid, 0)
    except ProcessLookupError:
        pass
    except OSError as error:
        raise AssignmentError("capability_blocked", "original listener liveness uncertain") from error
    else:
        raise AssignmentError("busy", "original listener is still running")
    handle["listener_version"] = previous.get("listener_version", 1) + 1

    def replace_listener(latest, current):
        if _has_result(latest, current):
            return False
        if current["state"] not in {"dispatching", "active", "delivery_uncertain", "needs_reconcile"}:
            raise AssignmentError("needs_reconcile", "assignment changed before listener replacement")
        current["return_handle"] = handle
        return True

    run = _change_assignment(store, run, assignment_id, replace_listener,
                             allow_revision=True, check_listener=True)
    if _has_result(run, run["assignments"][assignment_id]):
        return run
    baseline = copy.deepcopy(run)
    try:
        completion = channel.wait_existing(member["pane_id"], handle)
    except RuntimeError as error:
        if type(error) is not RuntimeError and not isinstance(error, HerdrError):
            raise
        latest = _finish_wait(store, baseline, assignment_id, None, reattach=True, failed=True)
        if _has_result(latest, latest["assignments"][assignment_id]):
            return latest
        raise AssignmentError("needs_reconcile", "existing-worker wait failed; task was not resent") from error
    return _finish_wait(store, baseline, assignment_id, completion, reattach=True)


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
    if assignment["repo"] is not None:
        try:
            changed = changed_paths(Path(assignment["repo"]), assignment["base_head"],
                                    assignment["work_snapshot"])
        except SnapshotError as error:
            raise AssignmentError("needs_reconcile", str(error)) from error
        # Only the registered result file is an output outside write_scope.
        # Worker-declared artifacts cannot exempt arbitrary project changes.
        try:
            output = (Path(result_root) / result_path).resolve().relative_to(Path(assignment["repo"]))
            changed.discard(output.as_posix())
        except ValueError:
            pass
        reported = set(result["files_changed"])
        if changed != reported or len(result["files_changed"]) != len(reported):
            raise AssignmentError("protocol_error", "reported files differ from Git changes since assigned base")
        allowed = assignment.get("write_scope", [])
        if any(not any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in allowed)
               for path in changed):
            raise AssignmentError("scope_mismatch", "Git change lies outside assigned write_scope")
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def change(latest, current):
        validate_result_binding(result, current)
        if _has_result(latest, current):
            if current.get("result_digest") == digest:
                return False
            raise AssignmentError("protocol_error", "different result already published for assignment")
        # A wait observation or delivery failure is not a worker result. Keep
        # its diagnostic event, but accept a later bound result for this attempt.
        if current["state"] not in {"active", "dispatching", "delivery_uncertain",
                                    "needs_reconcile", "blocked", "protocol_error"}:
            raise AssignmentError("needs_reconcile", "assignment is not accepting a result")
        current["result_digest"] = digest
        current["result_status"] = result["status"]
        for amendment in current.get("amendments", []):
            amendment["worker_ack"] = True
            amendment["delivery"] = "acknowledged"
        current["state"] = "result_received"
        event = {"schema_version": SCHEMA_VERSION, "run_id": run_id,
                 "assignment_id": assignment_id, "revision": current["revision"],
                 "attempt": current["attempt"], "type": "result_ready", "result_digest": digest}
        latest["outbox"].setdefault(event_id(event), {
            "event": event, "received": False, "action_intent": None, "applied": False})
        return True

    run = _change_assignment(store, run, assignment_id, change)
    return run, result


def pending_events(client: HerdrClient, store: StateStore, run_id: str, owner_epoch: int) -> list[dict]:
    _, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["owner_epoch"] != owner_epoch or run["scope"] != private["scope"]:
        raise AssignmentError("needs_reconcile", "owner epoch or scope changed")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    return [{"event_id": key, "assignment_id": value["event"]["assignment_id"],
             "type": value["event"]["type"], "revision": value["event"]["revision"]}
            for key, value in run["outbox"].items() if not value["received"]]


def collect_event(client: HerdrClient, store: StateStore, run_id: str, assignment_id: str,
                  event_key: str, owner_epoch: int) -> tuple[dict, dict | None, bool]:
    _, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["owner_epoch"] != owner_epoch or run["scope"] != private["scope"]:
        raise AssignmentError("needs_reconcile", "owner epoch or scope changed")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    assignment = run["assignments"].get(assignment_id)
    item = run["outbox"].get(event_key)
    if not assignment or not item or item["event"]["assignment_id"] != assignment_id:
        raise AssignmentError("protocol_error", "event does not belong to the assignment")
    event = item["event"]
    if event["revision"] != assignment["revision"] or event["attempt"] != assignment["attempt"]:
        def receive_stale(latest, current):
            record = latest["outbox"].get(event_key)
            if not record or record["event"] != event:
                raise AssignmentError("protocol_error", "event changed during collection")
            if record["received"]:
                return False
            record["received"] = True
            return True

        _change_assignment(store, run, assignment_id, receive_stale, allow_revision=True)
        raise AssignmentError("stale_event", "event predates current assignment revision")
    result = None
    if event["type"] == "result_ready":
        try:
            result = read_result_file(Path(assignment["result_root"]), assignment["result_path"])
            validate_result_binding(result, assignment)
        except ContractError as error:
            raise AssignmentError("protocol_error", f"recorded result no longer valid: {error}") from error
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != event["result_digest"] or digest != assignment.get("result_digest"):
            raise AssignmentError("protocol_error", "result digest changed after publication")
    elif event["type"] not in {"protocol_error", "blocked", "interrupted"}:
        raise AssignmentError("protocol_error", "unsupported event type")
    member = next((member for member in run["members"]
                   if member["member_id"] == assignment["member_id"]), None)
    worker = next((agent for agent in private["agents"]
                   if member and agent["pane_id"] == member["pane_id"]), None)
    released = bool(worker and worker.get("agent_status") in {"idle", "done"})
    def receive(latest, current):
        record = latest["outbox"].get(event_key)
        if not record or record["event"] != event:
            raise AssignmentError("protocol_error", "event changed during collection")
        if result is not None:
            validate_result_binding(result, current)
            if digest != current.get("result_digest") or not _has_result(latest, current):
                raise AssignmentError("protocol_error", "result changed during collection")
        if record["received"] and (result is None or current["state"] == "collected"):
            return False
        record["received"] = True
        if result is not None:
            current["state"] = "collected"
        return True

    run = _change_assignment(store, run, assignment_id, receive)
    return run, result, released
