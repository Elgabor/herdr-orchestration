"""One native Pi reset with a private proof and no LLM-turn wait."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat
import time

from .context import inspect_team, verify_binding
from .contracts import ContractError, ID
from .state import StateStore
from .transport import HerdrClient, HerdrError


class ResetError(RuntimeError):
    def __init__(self, outcome: str, message: str):
        self.outcome = outcome
        super().__init__(message)


def _save(run: dict, store: StateStore, owner_epoch: int) -> dict:
    previous = run["generation"]
    run["generation"] += 1
    return store.update_run(run, expected_generation=previous, owner_epoch=owner_epoch)


def _proof(root: Path, nonce: str, operation: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    path = root / f"{nonce}.json"
    while True:
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            break
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise ResetError("needs_reconcile", f"native {operation} proof absent; do not repeat mutation") from None
            time.sleep(0.1)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 4096:
            raise ResetError("protocol_error", "native proof is not a private bounded regular file")
        raw = os.read(fd, 4097)
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ResetError("protocol_error", "native proof is malformed") from error
    if not isinstance(data, dict) or data.get("nonce") != nonce or data.get("operation") != operation:
        raise ResetError("protocol_error", "native proof identity mismatch")
    return data


def _check_native(native: dict, live: dict, expected: dict | None = None) -> None:
    if not isinstance(native, dict) or not isinstance(native.get("session_file"), str):
        raise ResetError("protocol_error", "native session identity unavailable")
    live_session = live.get("agent_session")
    if native["session_file"] != (live_session.get("value") if isinstance(live_session, dict) else None):
        raise ResetError("identity_changed", "native and Herdr session identities differ")
    if native.get("cwd") != live.get("cwd"):
        raise ResetError("scope_mismatch", "native and Herdr cwd differ")
    if not isinstance(native.get("model"), dict) or not native["model"].get("provider") or not native["model"].get("id"):
        raise ResetError("capability_blocked", "native provider/model unavailable")
    if not isinstance(native.get("thinking"), str) or native["thinking"] == "unknown":
        raise ResetError("capability_blocked", "native effort unavailable")
    if type(native.get("trusted")) is not bool or not isinstance(native.get("tools"), list):
        raise ResetError("capability_blocked", "native permission/tool state unavailable")
    if expected:
        for key in ("cwd", "model", "thinking", "trusted", "tools"):
            if key in expected and native.get(key) != expected[key]:
                raise ResetError("identity_changed", f"native {key} differs from assigned configuration")


def _live_after(client: HerdrClient, pane_id: str, session_file: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        live = client.agent_get(pane_id)
        session = live.get("agent_session")
        if (isinstance(session, dict) and session.get("value") == session_file
                and live.get("agent_status") in {"idle", "done"}):
            return live
        if time.monotonic() >= deadline:
            raise ResetError("needs_reconcile", "Herdr did not confirm new native session")
        time.sleep(0.1)


def new_conversation(client: HerdrClient, store: StateStore, run_id: str, member_id: str,
                     expected_generation: int, owner_epoch: int, next_context_key: str,
                     bridge_dir: Path, expected_config: dict | None = None) -> dict:
    if not ID.fullmatch(next_context_key):
        raise ContractError("next_context_key: invalid")
    bridge_dir = Path(bridge_dir)
    if bridge_dir.is_symlink():
        raise ResetError("capability_blocked", "bridge directory is a symlink")
    info = bridge_dir.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ResetError("capability_blocked", "bridge directory must be owner-only")
    _, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["generation"] != expected_generation or run["owner_epoch"] != owner_epoch:
        raise ResetError("needs_reconcile", "run generation or owner epoch changed")
    if private["scope"] != run["scope"] or not run["team_frozen"]:
        raise ResetError("scope_mismatch", "owner scope or frozen roster differs")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    member = next((item for item in run["members"] if item["member_id"] == member_id), None)
    if not member:
        raise ContractError("member_id: not in frozen roster")
    if member.get("context_key") == next_context_key:
        raise ContractError("next_context_key: already current; keep the same conversation")
    if member["harness"] != "pi":
        raise ResetError("capability_blocked", f"{member['harness']} native reset not certified")
    if run.get("resets", {}).get(member_id, {}).get("state") in {"dispatching", "needs_reconcile"}:
        raise ResetError("needs_reconcile", "previous reset intent unresolved; do not repeat")
    if any(item["member_id"] == member_id and item["state"] not in {"collected", "cancelled"}
           for item in run["assignments"].values()):
        raise ResetError("busy", "previous assignment is not released")
    agent = next((item for item in private["agents"] if item["pane_id"] == member["pane_id"]), None)
    verify_binding(member, agent, private["panes"].get(member["pane_id"]), run["scope"])
    if agent.get("agent_status") not in {"idle", "done"} or agent.get("interactive_ready") is False:
        raise ResetError("busy", "worker is active or input is not ready")

    inspect_nonce = secrets.token_hex(16)
    client.agent_prompt(member["pane_id"], f"/herdrinspect {inspect_nonce}")
    before = _proof(bridge_dir, inspect_nonce, "inspect").get("current")
    _check_native(before, agent, expected_config)
    if before["session_file"] != member["conversation_id"]:
        raise ResetError("identity_changed", "member session differs from frozen binding")

    run.setdefault("resets", {})[member_id] = {
        "state": "dispatching", "next_context_key": next_context_key,
        "old_conversation_id": member["conversation_id"], "new_conversation_id": None,
    }
    _save(run, store, owner_epoch)
    nonce = secrets.token_hex(16)
    try:
        client.agent_prompt(member["pane_id"], f"/herdrnew {nonce}")
        proof = _proof(bridge_dir, nonce, "new")
        if proof.get("cancelled") or proof.get("error") or proof.get("before") != before:
            raise ResetError("needs_reconcile", "native reset cancelled or precondition changed")
        after = proof.get("after")
        if not isinstance(after, dict) or after.get("session_file") == before["session_file"]:
            raise ResetError("needs_reconcile", "native conversation did not change")
        live = _live_after(client, member["pane_id"], after["session_file"])
        for key in ("pane_id", "terminal_id", "workspace_id", "tab_id", "agent", "revision"):
            if live.get(key) != agent.get(key):
                raise ResetError("identity_changed", f"worker {key} changed during reset")
        post_nonce = secrets.token_hex(16)
        client.agent_prompt(member["pane_id"], f"/herdrinspect {post_nonce}")
        post = _proof(bridge_dir, post_nonce, "inspect").get("current")
        _check_native(post, live, expected_config)
        for key in ("cwd", "model", "thinking", "trusted", "tools"):
            if post[key] != before[key]:
                raise ResetError("identity_changed", f"native {key} changed during reset")
        if post["session_file"] != after["session_file"]:
            raise ResetError("identity_changed", "post-reset session changed again")
    except (HerdrError, ResetError) as error:
        run["resets"][member_id]["state"] = "needs_reconcile"
        _save(run, store, owner_epoch)
        if isinstance(error, ResetError):
            raise
        raise ResetError("needs_reconcile", "native reset delivery uncertain; do not retry") from error

    run["resets"][member_id].update(state="complete", new_conversation_id=post["session_file"])
    member["conversation_id"] = post["session_file"]
    member["context_key"] = next_context_key
    _save(run, store, owner_epoch)
    return run
