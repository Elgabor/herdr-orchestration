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
    sub.add_parser("doctor", help="Read-only installed/server capability report")
    team = sub.add_parser("team", help="Inspect the caller's Herdr tab")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_sub.add_parser("inspect")
    run = sub.add_parser("run", help="Initialize an adopted team")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    init = run_sub.add_parser("init")
    init.add_argument("--config", required=True, type=Path)
    init.add_argument("--state-dir", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        client = HerdrClient()
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
        public, private = inspect_team(client)
        if args.command == "team":
            return envelope("ok", "owner tab inspected without transcripts", **public)
        if args.command == "run":
            config = read_config(args.config)
            default = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / "herdr-orchestration"
            store = StateStore(args.state_dir or default)
            run = adopt_existing(config, private, store)
            return envelope("ok", "existing team adopted and frozen",
                            run_id=run["run_id"], owner_epoch=1,
                            scope=run["scope"], members=len(run["members"]),
                            client_visibility="unknown")
    except ContractError as error:
        return envelope("invalid_request", str(error))
    except StateConflict as error:
        return envelope("busy", str(error))
    except (HerdrError, UnsafePath) as error:
        return envelope("capability_blocked", str(error))
    except OSError as error:
        return envelope("invalid_request", f"file or transport error: {error.strerror}")
    return envelope("capability_blocked", "operation unavailable")


if __name__ == "__main__":
    raise SystemExit(main())
