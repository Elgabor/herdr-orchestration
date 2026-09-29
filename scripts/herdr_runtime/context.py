"""Bind an owner and adopted agents to one verified Herdr tab."""

from __future__ import annotations

import hashlib
import os

from .contracts import ContractError, SCHEMA_VERSION, validate_run
from .state import StateStore
from .transport import HerdrClient, HerdrError

TESTED_HERDR_VERSION = "0.9.2"
TESTED_PROTOCOL = 22
KINDS = {"codex", "claude", "pi", "opencode"}


def _conversation(agent: dict) -> str | None:
    session = agent.get("agent_session")
    return session.get("value") if isinstance(session, dict) and isinstance(session.get("value"), str) else None


def _claim_key(session_id: str, pane_id: str) -> str:
    digest = hashlib.sha256(f"{session_id}\0{pane_id}".encode()).hexdigest()
    return f"pane-{digest}"


def inspect_team(client: HerdrClient, environ: dict | None = None) -> tuple[dict, dict]:
    """Return compact public view and a private binding view.

    The broad snapshot stays in memory; only agents from the caller's tab
    appear in the public return value.
    """
    environ = os.environ if environ is None else environ
    if environ.get("HERDR_ENV") != "1":
        raise HerdrError("HERDR_ENV=1 required; no session control outside Herdr")
    status = client.status()
    server, local = status.get("server", {}), status.get("client", {})
    if not server.get("running") or server.get("compatible") is not True:
        raise HerdrError("server absent or client/server incompatible")
    if (local.get("version"), server.get("version"), local.get("protocol"), server.get("protocol")) != (
        TESTED_HERDR_VERSION, TESTED_HERDR_VERSION, TESTED_PROTOCOL, TESTED_PROTOCOL
    ):
        raise HerdrError("Herdr client/server version or protocol not certified")
    if local.get("session") != server.get("session"):
        raise HerdrError("client/server session mismatch")
    current = client.current_pane()
    snapshot = client.snapshot()
    if (snapshot.get("version"), snapshot.get("protocol")) != (TESTED_HERDR_VERSION, TESTED_PROTOCOL):
        raise HerdrError("server snapshot version or protocol mismatch")
    pane_id = current.get("pane_id")
    live_panes = {pane.get("pane_id"): pane for pane in snapshot.get("panes", [])}
    if pane_id not in live_panes or current.get("terminal_id") != live_panes[pane_id].get("terminal_id"):
        raise HerdrError("caller pane cannot be resolved in authoritative snapshot")
    workspace_id, tab_id = current.get("workspace_id"), current.get("tab_id")
    if not workspace_id or not tab_id:
        raise HerdrError("caller workspace/tab unavailable")
    agents = [agent for agent in snapshot.get("agents", []) if
              agent.get("workspace_id") == workspace_id and agent.get("tab_id") == tab_id
              and agent.get("pane_id") in live_panes]
    owner = next((agent for agent in agents if agent.get("pane_id") == pane_id), None)
    if not owner or owner.get("agent") not in KINDS:
        raise HerdrError("caller is not a recognized owner agent")
    session_id = server.get("session") or "default"
    scope = {"session_id": session_id, "workspace_id": workspace_id,
             "tab_id": tab_id, "owner_pane_id": pane_id}
    candidates = [agent for agent in agents if agent["pane_id"] != pane_id and agent.get("agent") in KINDS]
    public = {
        "scope": scope,
        "owner": {"pane_id": pane_id, "harness": owner["agent"],
                  "conversation_known": _conversation(owner) is not None},
        "candidates": [
            {"pane_id": agent["pane_id"], "agent_alias": agent.get("name"),
             "harness": agent["agent"], "status": agent.get("agent_status"),
             "conversation_known": _conversation(agent) is not None}
            for agent in candidates
        ],
        "team_frozen": False,
        "client_visibility": "unknown",
    }
    private = {"scope": scope, "owner": owner, "agents": candidates,
               "panes": live_panes, "snapshot": snapshot}
    return public, private


def verify_binding(member: dict, live_agent: dict | None, live_pane: dict | None, scope: dict) -> None:
    if not live_agent or not live_pane:
        raise HerdrError("member pane or occupant missing")
    for key in ("workspace_id", "tab_id", "pane_id", "terminal_id"):
        expected = member[key]
        actual = live_agent.get(key)
        if actual != expected or live_pane.get(key) != expected:
            raise HerdrError(f"member {key} changed")
    if member["session_id"] != scope["session_id"]:
        raise HerdrError("member session changed")
    if live_agent.get("agent") != member["harness"] or live_agent.get("revision") != member["occupant_revision"]:
        raise HerdrError("member occupant changed")
    if member["identity_status"] != "verified" or _conversation(live_agent) != member["conversation_id"]:
        raise HerdrError("member conversation identity unverified or changed")


def adopt_existing(config: dict, private: dict, store: StateStore) -> dict:
    if config.get("mode") != "adopt_existing":
        raise ContractError("mode: expected adopt_existing")
    for key in ("run_id", "mission"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ContractError(f"{key}: required nonempty string")
    plans = config.get("members")
    if not isinstance(plans, list) or not plans:
        raise ContractError("members: explicit nonempty mapping required")
    if type(config.get("parallel_authorized")) is not bool or type(config.get("bootstrap_authorized")) is not bool:
        raise ContractError("parallel_authorized/bootstrap_authorized: expected bool")
    execution_mode = config.get("execution_mode")
    if execution_mode not in {"sequential", "parallel"}:
        raise ContractError("execution_mode: invalid")
    scope = private["scope"]
    owner_agent = private["owner"]
    available = {agent["pane_id"]: agent for agent in private["agents"]}
    members = []
    used = {scope["owner_pane_id"]}
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ContractError(f"members[{index}]: expected object")
        pane_id = plan.get("pane_id")
        agent = available.get(pane_id)
        if not agent or pane_id in used:
            raise ContractError(f"members[{index}].pane_id: unavailable, duplicate, or outside owner tab")
        if not isinstance(plan.get("member_id"), str) or not isinstance(plan.get("label"), str):
            raise ContractError(f"members[{index}]: member_id and label required")
        if plan.get("harness") is not None and plan["harness"] != agent["agent"]:
            raise ContractError(f"members[{index}].harness: live occupant differs")
        if plan.get("agent_alias") is not None and plan["agent_alias"] != agent.get("name"):
            raise ContractError(f"members[{index}].agent_alias: live alias differs")
        used.add(pane_id)
        conversation = _conversation(agent)
        members.append({
            "member_id": plan["member_id"], "label": plan["label"],
            "harness": agent["agent"], "session_id": scope["session_id"],
            "workspace_id": scope["workspace_id"], "tab_id": scope["tab_id"],
            "pane_id": pane_id, "terminal_id": agent["terminal_id"],
            "occupant_revision": agent["revision"],
            "identity_status": "verified" if conversation else "unknown",
            "agent_alias": agent.get("name"), "conversation_id": conversation,
            "created_by_run": False,
        })
    owner_conversation = _conversation(owner_agent)
    owner = {
        "member_id": "owner", "label": "Owner", "harness": owner_agent["agent"],
        "session_id": scope["session_id"], "workspace_id": scope["workspace_id"],
        "tab_id": scope["tab_id"], "pane_id": scope["owner_pane_id"],
        "terminal_id": owner_agent["terminal_id"],
        "occupant_revision": owner_agent["revision"],
        "identity_status": "verified" if owner_conversation else "unknown",
        "agent_alias": owner_agent.get("name"),
        "conversation_id": owner_conversation, "created_by_run": False,
    }
    run = {
        "schema_version": SCHEMA_VERSION, "run_id": config["run_id"],
        "mission": config["mission"], "generation": 0, "owner_epoch": 1,
        "scope": scope, "owner": owner, "execution_mode": execution_mode,
        "parallel_authorized": config["parallel_authorized"],
        "bootstrap_authorized": config["bootstrap_authorized"],
        "team_frozen": True, "pause_dispatch": False,
        "members": members, "assignments": {}, "outbox": {},
    }
    validate_run(run)
    claims = [_claim_key(scope["session_id"], pane) for pane in used]
    store.create_run_claimed(run, claims)
    return run
