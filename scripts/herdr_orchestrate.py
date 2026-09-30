#!/usr/bin/env python3
"""Bounded Herdr orchestration CLI. Unsupported mutations fail closed."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from herdr_runtime.context import adopt_existing, inspect_team, TESTED_HERDR_VERSION, TESTED_PROTOCOL
from herdr_runtime.contracts import ContractError, MAX_ENVELOPE_BYTES
from herdr_runtime.state import StateConflict, StateStore, UnsafePath
from herdr_runtime.transport import HerdrClient, HerdrError
from herdr_runtime.provision import ProvisioningError, bootstrap_run, prepare_team
from herdr_runtime.native_reset import ResetError, new_conversation
from herdr_runtime.quota import check_choice, read_quota, validate_catalog
from herdr_runtime.assignment import (AssignmentError, collect_event, dispatch,
                                      pending_events, publish_result, reattach_wait)
from herdr_runtime.return_channel import PiReturnChannel
from herdr_runtime.control import apply_control
from herdr_runtime.recovery import confirm_resume, inspect_resume
from herdr_runtime.snapshot import SnapshotError, clean_snapshot


def envelope(outcome: str, message: str, **details: object) -> int:
    body = {"schema_version": 1, "outcome": outcome, "retry_safe": False,
            "message": message, **details}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        body = {"schema_version": 1, "outcome": "protocol_error",
                "retry_safe": False, "message": "public envelope exceeds 4 KiB"}
        encoded = json.dumps(body)
        outcome = "protocol_error"
    print(encoded)
    if outcome == "invalid_request":
        return 2
    if outcome in {"ok", "result_ready"}:
        return 0
    return 20


def read_config(path: Path) -> dict:
    if path.is_symlink():
        raise ContractError("config: symlink rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
            raise ContractError("config: expected bounded regular file")
        data = os.read(fd, 64 * 1024 + 1)
        if len(data) > 64 * 1024:
            raise ContractError("config: too large")
    finally:
        os.close(fd)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"config: invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("config: expected object")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    repo = sub.add_parser("repo", help="Read-only clean checkout identity")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)
    snapshot = repo_sub.add_parser("snapshot")
    snapshot.add_argument("--repo", required=True, type=Path)
    sub.add_parser("doctor", help="Read-only installed/server capability report")
    team = sub.add_parser("team", help="Inspect the caller's Herdr tab")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_sub.add_parser("inspect")
    prepare = team_sub.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--expected-generation", required=True, type=int)
    prepare.add_argument("--owner-epoch", required=True, type=int)
    prepare.add_argument("--state-dir", type=Path)
    run = sub.add_parser("run", help="Initialize an adopted team")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    init = run_sub.add_parser("init")
    init.add_argument("--config", required=True, type=Path)
    init.add_argument("--state-dir", type=Path)
    conversation = sub.add_parser("conversation", help="Native worker conversation control")
    conversation_sub = conversation.add_subparsers(dest="conversation_command", required=True)
    reset = conversation_sub.add_parser("reset")
    reset.add_argument("--run-id", required=True)
    reset.add_argument("--member-id", required=True)
    reset.add_argument("--next-context-key", required=True)
    reset.add_argument("--expected-generation", required=True, type=int)
    reset.add_argument("--owner-epoch", required=True, type=int)
    reset.add_argument("--bridge-dir", required=True, type=Path)
    reset.add_argument("--expected-config", type=Path)
    reset.add_argument("--state-dir", type=Path)
    quota = sub.add_parser("quota", help="Read scoped usage evidence without account side effects")
    quota_sub = quota.add_subparsers(dest="quota_command", required=True)
    for operation in ("read", "check"):
        command = quota_sub.add_parser(operation)
        command.add_argument("--catalog", required=True, type=Path)
        command.add_argument("--profile-id", required=True)
        command.add_argument("--state-dir", type=Path)
        command.add_argument("--ttl-seconds", type=int, default=300)
        if operation == "check":
            command.add_argument("--mode", choices=("explicit", "existing", "auto_authorized"), required=True)
    assignment = sub.add_parser("assignment", help="Dispatch one bounded worker task or publish its JSON result")
    assignment_sub = assignment.add_subparsers(dest="assignment_command", required=True)
    send = assignment_sub.add_parser("dispatch")
    send.add_argument("--config", required=True, type=Path)
    send.add_argument("--expected-generation", required=True, type=int)
    send.add_argument("--owner-epoch", required=True, type=int)
    send.add_argument("--state-dir", type=Path)
    send.add_argument("--bridge-dir", type=Path)
    send.add_argument("--bridge-nonce")
    reattach = assignment_sub.add_parser("reattach")
    reattach.add_argument("--run-id", required=True)
    reattach.add_argument("--assignment-id", required=True)
    reattach.add_argument("--expected-generation", required=True, type=int)
    reattach.add_argument("--owner-epoch", required=True, type=int)
    reattach.add_argument("--state-dir", type=Path)
    reattach.add_argument("--bridge-dir", required=True, type=Path)
    reattach.add_argument("--bridge-nonce", required=True)
    publish = assignment_sub.add_parser("publish")
    publish.add_argument("--run-id", required=True)
    publish.add_argument("--assignment-id", required=True)
    publish.add_argument("--result-root", required=True, type=Path)
    publish.add_argument("--result-path", required=True)
    publish.add_argument("--state-dir", type=Path)
    pending = assignment_sub.add_parser("pending")
    pending.add_argument("--run-id", required=True)
    pending.add_argument("--owner-epoch", required=True, type=int)
    pending.add_argument("--state-dir", type=Path)
    collect = assignment_sub.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--assignment-id", required=True)
    collect.add_argument("--event-id", required=True)
    collect.add_argument("--owner-epoch", required=True, type=int)
    collect.add_argument("--state-dir", type=Path)
    control = sub.add_parser("control", help="Apply one versioned owner instruction")
    control_sub = control.add_subparsers(dest="control_command", required=True)
    apply = control_sub.add_parser("apply")
    apply.add_argument("--config", required=True, type=Path)
    apply.add_argument("--expected-generation", required=True, type=int)
    apply.add_argument("--owner-epoch", required=True, type=int)
    apply.add_argument("--state-dir", type=Path)
    resume = sub.add_parser("resume", help="Inspect a bound run before owner confirmation")
    resume_sub = resume.add_subparsers(dest="resume_command", required=True)
    for operation in ("inspect", "confirm"):
        command = resume_sub.add_parser(operation)
        command.add_argument("--run-id", required=True)
        command.add_argument("--expected-generation", required=True, type=int)
        command.add_argument("--owner-epoch", required=True, type=int)
        command.add_argument("--state-dir", type=Path)
    return root


def state_dir(override: Path | None) -> Path:
    default = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "herdr-orchestration"
    return override or default


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "repo":
            observed = clean_snapshot(args.repo)
            return envelope("ok", "clean checkout identity; no file content read", **observed)
        if args.command == "quota":
            profiles = validate_catalog(read_config(args.catalog))
            profile = next((item for item in profiles if item["profile_id"] == args.profile_id), None)
            if profile is None:
                raise ContractError("profile_id: absent from catalog")
            observed = read_quota(profile, StateStore(state_dir(args.state_dir)),
                                  ttl_seconds=args.ttl_seconds)
            if args.quota_command == "read":
                return envelope("ok", "quota sample; unknown values are not credit", **observed)
            choice = check_choice(profile, observed["sample"], mode=args.mode)
            outcome = "ok" if choice["outcome"] in {"eligible", "eligible_with_uncertainty"} else choice["outcome"]
            return envelope(outcome, choice["reason"], eligibility=choice["outcome"], profile_id=args.profile_id,
                            unknown=choice.get("unknown", []), cache=observed["cache"])
        client = HerdrClient()
        if args.command == "resume":
            store = StateStore(state_dir(args.state_dir))
            if args.resume_command == "inspect":
                observed = inspect_resume(client, store, args.run_id,
                                          args.expected_generation, args.owner_epoch)
                return envelope("ok", observed.pop("summary"), **observed)
            run = confirm_resume(client, store, args.run_id,
                                 args.expected_generation, args.owner_epoch)
            return envelope("ok", "owner confirmed reconciliation; no worker prompt was sent",
                            run_id=run["run_id"], generation=run["generation"],
                            owner_epoch=run["owner_epoch"], awaiting_user_resume=False)
        if args.command == "control":
            config = read_config(args.config)
            run = apply_control(client, StateStore(state_dir(args.state_dir)), config,
                                args.expected_generation, args.owner_epoch)
            assignment = run["assignments"].get(config.get("assignment_id"))
            latest = assignment.get("amendments", [])[-1] if assignment and config["type"] == "amend_assignment" else None
            return envelope("ok", "owner control recorded; queued is not worker acceptance",
                            run_id=run["run_id"], generation=run["generation"],
                            control_type=config["type"], delivery=latest["delivery"] if latest else None,
                            worker_ack=latest["worker_ack"] if latest else None)
        if args.command == "assignment" and args.assignment_command == "dispatch":
            if bool(args.bridge_dir) != bool(args.bridge_nonce):
                raise ContractError("bridge-dir and bridge-nonce must be supplied together")
            config = read_config(args.config)
            channel = PiReturnChannel(client, args.bridge_dir, args.bridge_nonce) if args.bridge_dir else None
            run = dispatch(client, StateStore(state_dir(args.state_dir)), config,
                           args.expected_generation, args.owner_epoch, channel=channel)
            assignment_id = config["assignment"]["assignment_id"]
            assigned = run["assignments"][assignment_id]
            event_id = next((key for key, item in run["outbox"].items()
                             if item["event"]["assignment_id"] == assignment_id), None)
            state = assigned["state"]
            outcome = ("result_ready" if state == "result_received" else
                       state if state in {"blocked", "protocol_error", "needs_reconcile"} else "ok")
            return envelope(outcome, "worker wait returned; inspect the recorded event",
                            run_id=run["run_id"], assignment_id=assignment_id,
                            event_id=event_id, worker_status=assigned.get("result_status"),
                            assignment_state=state, generation=run["generation"])
        if args.command == "assignment" and args.assignment_command == "reattach":
            channel = PiReturnChannel(client, args.bridge_dir, args.bridge_nonce)
            run = reattach_wait(client, StateStore(state_dir(args.state_dir)), args.run_id,
                                args.assignment_id, args.expected_generation, args.owner_epoch, channel)
            assigned = run["assignments"][args.assignment_id]
            event_id = next((key for key, item in run["outbox"].items()
                             if item["event"]["assignment_id"] == args.assignment_id
                             and not item["received"]), None)
            state = assigned["state"]
            outcome = ("result_ready" if state == "result_received" else
                       state if state in {"blocked", "protocol_error", "needs_reconcile"} else "ok")
            return envelope(outcome, "existing worker observed; no task prompt was sent",
                            run_id=args.run_id, assignment_id=args.assignment_id,
                            event_id=event_id, assignment_state=state,
                            generation=run["generation"])
        if args.command == "assignment" and args.assignment_command == "publish":
            run, result = publish_result(client, StateStore(state_dir(args.state_dir)),
                                         args.run_id, args.assignment_id,
                                         args.result_root, args.result_path)
            return envelope("result_ready", "structured worker result recorded; owner collection pending",
                            run_id=run["run_id"], assignment_id=args.assignment_id,
                            worker_status=result["status"], generation=run["generation"])
        if args.command == "assignment" and args.assignment_command == "pending":
            events = pending_events(client, StateStore(state_dir(args.state_dir)),
                                    args.run_id, args.owner_epoch)
            return envelope("ok", "unreceived scoped events", run_id=args.run_id, events=events)
        if args.command == "assignment" and args.assignment_command == "collect":
            run, result, released = collect_event(client, StateStore(state_dir(args.state_dir)),
                                                  args.run_id, args.assignment_id,
                                                  args.event_id, args.owner_epoch)
            return envelope("result_ready" if result else "blocked",
                            "event received; project acceptance remains with owner",
                            run_id=args.run_id, assignment_id=args.assignment_id,
                            event_id=args.event_id, worker_status=result["status"] if result else None,
                            worker_released=released, generation=run["generation"])
        if args.command == "doctor":
            status = client.status()
            local, server = status.get("client", {}), status.get("server", {})
            compatible = (server.get("running") is True and server.get("compatible") is True
                          and local.get("version") == server.get("version") == TESTED_HERDR_VERSION
                          and local.get("protocol") == server.get("protocol") == TESTED_PROTOCOL)
            return envelope("ok", "read-only diagnosis", client_version=local.get("version"),
                            server_version=server.get("version"),
                            server_protocol=server.get("protocol"),
                            tested_version=TESTED_HERDR_VERSION,
                            context="inside_herdr" if os.environ.get("HERDR_ENV") == "1" else "outside_herdr",
                            critical_operations="not_certified" if compatible else "blocked")
        if args.command == "team" and args.team_command == "prepare":
            run = prepare_team(client, StateStore(state_dir(args.state_dir)), args.run_id,
                               args.expected_generation, args.owner_epoch)
            return envelope("ok", "planned team prepared and frozen", run_id=run["run_id"],
                            owner_epoch=run["owner_epoch"], generation=run["generation"],
                            members=len(run["members"]), team_frozen=run["team_frozen"])
        if args.command == "conversation" and args.conversation_command == "reset":
            expected_config = read_config(args.expected_config) if args.expected_config else None
            run = new_conversation(client, StateStore(state_dir(args.state_dir)), args.run_id,
                                   args.member_id, args.expected_generation, args.owner_epoch,
                                   args.next_context_key, args.bridge_dir, expected_config)
            return envelope("ok", "native Pi conversation reset and configuration verified",
                            run_id=run["run_id"], member_id=args.member_id,
                            generation=run["generation"], owner_epoch=run["owner_epoch"])
        public, private = inspect_team(client)
        if args.command == "team":
            return envelope("ok", "owner tab inspected without transcripts", **public)
        if args.command == "run":
            config = read_config(args.config)
            store = StateStore(state_dir(args.state_dir))
            if config.get("mode") == "adopt_existing":
                run = adopt_existing(config, private, store)
            elif config.get("mode") == "bootstrap_team":
                run = bootstrap_run(config, private, store)
            else:
                raise ContractError("mode: expected adopt_existing or bootstrap_team")
            return envelope("ok", "run initialized with scoped team plan",
                            run_id=run["run_id"], owner_epoch=1,
                            scope=run["scope"], members=len(run["members"]),
                            team_frozen=run["team_frozen"],
                            client_visibility="unknown")
    except ContractError as error:
        return envelope("invalid_request", str(error))
    except StateConflict as error:
        return envelope("busy", str(error))
    except ProvisioningError as error:
        return envelope(error.outcome, str(error))
    except ResetError as error:
        return envelope(error.outcome, str(error))
    except AssignmentError as error:
        return envelope(error.outcome, str(error))
    except SnapshotError as error:
        return envelope("needs_reconcile", str(error))
    except (HerdrError, UnsafePath) as error:
        return envelope("capability_blocked", str(error))
    except OSError as error:
        return envelope("invalid_request", f"file or transport error: {error.strerror}")
    return envelope("capability_blocked", "operation unavailable")


if __name__ == "__main__":
    raise SystemExit(main())
