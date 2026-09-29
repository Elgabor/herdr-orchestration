"""Explicit, journaled preparation of a small team in the owner's tab."""

from __future__ import annotations

from pathlib import Path
import time

from .context import _claim_key, binding_for_agent, inspect_team, verify_binding
from .contracts import AGENT_ALIAS, ContractError, ID, SCHEMA_VERSION, validate_run
from .state import StateStore
from .transport import HerdrClient, HerdrError

KINDS = {"codex", "claude", "pi", "opencode"}
SECRET_FLAGS = {"--api-key", "--token", "--password", "--secret", "--auth-token"}


class ProvisioningError(RuntimeError):
    def __init__(self, outcome: str, message: str):
        self.outcome = outcome
        super().__init__(message)


def validate_plan(steps: object, scope: dict) -> list[dict]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ContractError("setup_plan: expected 1 to 8 explicit steps")
    ids, aliases = set(), set()
    for index, step in enumerate(steps):
        field = f"setup_plan[{index}]"
        if not isinstance(step, dict):
            raise ContractError(f"{field}: expected object")
        for key in ("member_id", "label", "agent_alias", "harness", "cwd", "source"):
            if not isinstance(step.get(key), str) or not step[key].strip():
                raise ContractError(f"{field}.{key}: required nonempty string")
        if not ID.fullmatch(step["member_id"]) or step["member_id"] == "owner" or step["member_id"] in ids:
            raise ContractError(f"{field}.member_id: invalid or duplicate")
        if not AGENT_ALIAS.fullmatch(step["agent_alias"]) or step["agent_alias"] in aliases:
            raise ContractError(f"{field}.agent_alias: invalid or duplicate")
        ids.add(step["member_id"])
        aliases.add(step["agent_alias"])
        if step["harness"] not in KINDS:
            raise ContractError(f"{field}.harness: unsupported")
        if step["source"] not in {"split", "existing_shell"}:
            raise ContractError(f"{field}.source: invalid")
        cwd = Path(step["cwd"])
        if not cwd.is_absolute() or not cwd.is_dir():
            raise ContractError(f"{field}.cwd: expected existing absolute directory")
        if step["source"] == "split":
            if step.get("parent_pane_id") != scope["owner_pane_id"]:
                raise ContractError(f"{field}.parent_pane_id: first release splits only the owner pane")
            if step.get("direction") not in {"right", "down"}:
                raise ContractError(f"{field}.direction: expected right or down")
            ratio = step.get("ratio")
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0.25 <= ratio <= 0.75:
                raise ContractError(f"{field}.ratio: expected 0.25 to 0.75")
        elif not isinstance(step.get("pane_id"), str) or step["pane_id"] == scope["owner_pane_id"]:
            raise ContractError(f"{field}.pane_id: explicit available shell required")
        argv = step.get("argv")
        if not isinstance(argv, list) or len(argv) > 20 or any(not isinstance(arg, str) or len(arg) > 256 for arg in argv):
            raise ContractError(f"{field}.argv: expected up to 20 bounded strings")
        if sum(len(arg) for arg in argv) > 2048 or any(arg.lower().split("=")[0] in SECRET_FLAGS for arg in argv):
            raise ContractError(f"{field}.argv: credentials or excessive arguments forbidden")
    return steps


def bootstrap_run(config: dict, private: dict, store: StateStore) -> dict:
    if config.get("mode") != "bootstrap_team":
        raise ContractError("mode: expected bootstrap_team")
    if config.get("bootstrap_authorized") is not True:
        raise ContractError("bootstrap_authorized: explicit true required")
    scope = private["scope"]
    if any(agent.get("workspace_id") == scope["workspace_id"] and agent.get("tab_id") == scope["tab_id"]
           and agent.get("pane_id") != scope["owner_pane_id"] for agent in private["snapshot"].get("agents", [])):
        raise ProvisioningError("busy", "an agent team already exists in the owner's tab")
    if config.get("members") not in (None, []):
        raise ContractError("members: bootstrap starts without adopted agents")
    for key in ("run_id", "mission"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ContractError(f"{key}: required nonempty string")
    if type(config.get("parallel_authorized")) is not bool:
        raise ContractError("parallel_authorized: expected bool")
    if config.get("execution_mode") not in {"sequential", "parallel"}:
        raise ContractError("execution_mode: invalid")
    plan = validate_plan(config.get("setup_plan"), scope)
    owner = binding_for_agent(private["owner"], scope, "owner", "Owner", created_by_run=False)
    run = {
        "schema_version": SCHEMA_VERSION, "run_id": config["run_id"],
        "mode": "bootstrap_team", "mission": config["mission"],
        "generation": 0, "owner_epoch": 1, "scope": scope, "owner": owner,
        "execution_mode": config["execution_mode"],
        "parallel_authorized": config["parallel_authorized"],
        "bootstrap_authorized": True, "team_frozen": False,
        "pause_dispatch": False, "members": [], "assignments": {}, "outbox": {},
        "setup_plan": plan,
        "setup_journal": [{"state": "planned", "pane_id": None, "pre_panes": None,
                           "error": None} for _ in plan],
        "created_resources": [],
    }
    validate_run(run)
    store.create_run_claimed(run, [_claim_key(scope["session_id"], scope["owner_pane_id"])])
    return run


def _save(run: dict, store: StateStore, owner_epoch: int) -> dict:
    previous = run["generation"]
    run["generation"] = previous + 1
    return store.update_run(run, expected_generation=previous, owner_epoch=owner_epoch)


def _tab_panes(snapshot: dict, scope: dict) -> dict[str, dict]:
    return {pane["pane_id"]: pane for pane in snapshot.get("panes", []) if
            pane.get("workspace_id") == scope["workspace_id"] and pane.get("tab_id") == scope["tab_id"]}


def _geometry(snapshot: dict, scope: dict, step: dict) -> None:
    layout = next((item for item in snapshot.get("layouts", []) if item.get("tab_id") == scope["tab_id"]), None)
    if not layout or layout.get("zoomed"):
        raise ProvisioningError("capability_blocked", "layout missing or zoomed; no split attempted")
    parent = next((item.get("rect") for item in layout.get("panes", []) if item.get("pane_id") == step["parent_pane_id"]), None)
    if not parent:
        raise ProvisioningError("scope_mismatch", "split parent absent from owner tab layout")
    ratio = step["ratio"]
    axis = "width" if step["direction"] == "right" else "height"
    total = parent.get(axis, 0)
    smaller = min(int(total * ratio), total - int(total * ratio))
    # Initial ergonomics heuristic, not a guaranteed minimum of each TUI.
    required = 60 if axis == "width" else 18
    if smaller < required:
        raise ProvisioningError("capability_blocked", f"insufficient {axis} for planned split ({smaller} < {required})")


def _available_shell(client: HerdrClient, pane: dict) -> bool:
    if pane.get("agent"):
        return False
    info = client.process_info(pane["pane_id"])
    processes = info.get("foreground_processes", [])
    shell_pid = info.get("shell_pid")
    return len(processes) == 1 and processes[0].get("pid") == shell_pid


def _wait_available_shell(client: HerdrClient, pane: dict, seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if _available_shell(client, pane):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _reconcile_split(client: HerdrClient, scope: dict, journal: dict, cwd: str) -> dict:
    pre = set(journal.get("pre_panes") or [])
    candidates = [pane for pane_id, pane in _tab_panes(client.snapshot(), scope).items()
                  if pane_id not in pre and pane.get("cwd") == cwd]
    if len(candidates) != 1:
        raise ProvisioningError("delivery_uncertain", "split response lost; pane identity needs explicit reconciliation")
    return candidates[0]


def prepare_team(client: HerdrClient, store: StateStore, run_id: str, expected_generation: int,
                 owner_epoch: int) -> dict:
    public, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["generation"] != expected_generation or run["owner_epoch"] != owner_epoch:
        raise ProvisioningError("needs_reconcile", "run generation or owner epoch changed")
    if run["mode"] != "bootstrap_team" or not run["bootstrap_authorized"] or run["team_frozen"]:
        raise ProvisioningError("scope_mismatch", "team preparation not authorized for this run")
    if private["scope"] != run["scope"]:
        raise ProvisioningError("scope_mismatch", "owner moved to another Herdr scope")
    verify_binding(run["owner"], private["owner"], private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    known = {member["pane_id"] for member in run["members"]}
    known.update(item["pane_id"] for item in run["setup_journal"] if item["pane_id"])
    if any(agent.get("pane_id") not in known for agent in private["snapshot"].get("agents", [])
           if agent.get("workspace_id") == run["scope"]["workspace_id"]
           and agent.get("tab_id") == run["scope"]["tab_id"]
           and agent.get("pane_id") != run["scope"]["owner_pane_id"]):
        raise ProvisioningError("busy", "an unplanned agent is present in the owner's tab")
    for member in run["members"]:
        agent = next((item for item in private["agents"] if item["pane_id"] == member["pane_id"]), None)
        verify_binding(member, agent, private["panes"].get(member["pane_id"]), run["scope"])

    for index, step in enumerate(run["setup_plan"]):
        journal = run["setup_journal"][index]
        if journal["state"] == "active":
            continue
        if journal["state"] == "planned":
            snapshot = client.snapshot()
            panes = _tab_panes(snapshot, run["scope"])
            if step["source"] == "split":
                _geometry(snapshot, run["scope"], step)
                if step["parent_pane_id"] not in panes:
                    raise ProvisioningError("scope_mismatch", "planned split parent missing")
                journal.update(state="split_pending", pre_panes=sorted(panes),
                               focus_before=snapshot.get("focused_pane_id"), error=None)
                _save(run, store, owner_epoch)
                try:
                    pane = client.split(step["parent_pane_id"], step["direction"], step["ratio"], step["cwd"])
                except HerdrError as error:
                    journal["error"] = str(error)
                    _save(run, store, owner_epoch)
                    pane = _reconcile_split(client, run["scope"], journal, step["cwd"])
                journal["pane_id"] = pane["pane_id"]
                _save(run, store, owner_epoch)
            else:
                pane = panes.get(step["pane_id"])
                if not pane or pane.get("agent") or not _available_shell(client, pane):
                    raise ProvisioningError("busy", "authorized existing pane is not an available shell")
                journal.update(state="pane_created", pane_id=step["pane_id"], error=None)
                store.claim_member(_claim_key(run["scope"]["session_id"], step["pane_id"]),
                                   run_id=run_id, owner_epoch=owner_epoch)
                _save(run, store, owner_epoch)
        if journal["state"] == "split_pending":
            if journal["pane_id"] is None:
                pane = _reconcile_split(client, run["scope"], journal, step["cwd"])
                journal["pane_id"] = pane["pane_id"]
            live = client.pane_get(journal["pane_id"])
            if (live.get("workspace_id"), live.get("tab_id"), live.get("cwd")) != (
                run["scope"]["workspace_id"], run["scope"]["tab_id"], step["cwd"]
            ):
                raise ProvisioningError("needs_reconcile", "new pane scope or cwd differs from plan")
            if (journal.get("focus_before") is not None
                    and client.snapshot().get("focused_pane_id") != journal["focus_before"]):
                raise ProvisioningError("needs_reconcile", "focus changed during split; pane retained")
            store.claim_member(_claim_key(run["scope"]["session_id"], journal["pane_id"]),
                               run_id=run_id, owner_epoch=owner_epoch)
            if not any(resource.get("pane_id") == journal["pane_id"] for resource in run["created_resources"]):
                run["created_resources"].append({"type": "pane", "pane_id": journal["pane_id"]})
            journal["state"] = "pane_created"
            _save(run, store, owner_epoch)
        if journal["state"] == "pane_created":
            live = client.pane_get(journal["pane_id"])
            if live.get("agent") or not _wait_available_shell(client, live):
                raise ProvisioningError("needs_reconcile", "planned pane shell is not ready; pane retained")
            journal["state"] = "launch_pending"
            _save(run, store, owner_epoch)
            try:
                agent = client.start_agent(step["agent_alias"], step["harness"], journal["pane_id"], step["argv"])
            except HerdrError as error:
                current = client.snapshot()
                agent = next((item for item in current.get("agents", []) if item.get("pane_id") == journal["pane_id"]
                              and item.get("agent") == step["harness"] and item.get("name") == step["agent_alias"]), None)
                if not agent:
                    journal.update(state="pane_created", error=str(error))
                    _save(run, store, owner_epoch)
                    raise ProvisioningError("blocked", "agent start failed; created pane retained") from error
        else:
            agent = None
        if journal["state"] == "launch_pending":
            if agent is None:
                agent = next((item for item in client.snapshot().get("agents", []) if
                              item.get("pane_id") == journal["pane_id"] and item.get("name") == step["agent_alias"]), None)
            if not agent or agent.get("agent_status") not in {"idle", "done"}:
                raise ProvisioningError("needs_reconcile", "agent launch not ready; pane retained")
            if (agent.get("pane_id"), agent.get("workspace_id"), agent.get("tab_id"), agent.get("agent")) != (
                journal["pane_id"], run["scope"]["workspace_id"], run["scope"]["tab_id"], step["harness"]
            ):
                raise ProvisioningError("identity_changed", "started agent differs from planned member")
            member = binding_for_agent(agent, run["scope"], step["member_id"], step["label"],
                                       created_by_run=step["source"] == "split")
            if not any(item["member_id"] == member["member_id"] for item in run["members"]):
                run["members"].append(member)
            journal["state"] = "active"
            journal["error"] = None
            _save(run, store, owner_epoch)
    run["team_frozen"] = True
    _save(run, store, owner_epoch)
    return run
