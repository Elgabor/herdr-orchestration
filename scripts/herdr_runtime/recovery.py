"""Conservative same-owner recovery; never replay a worker prompt."""

from __future__ import annotations

from .assignment import AssignmentError, _save
from .context import inspect_team, verify_binding
from .state import StateConflict, StateStore
from .transport import HerdrClient, HerdrError


def _bound(client: HerdrClient, store: StateStore, run_id: str, owner_epoch: int):
    _, private = inspect_team(client)
    run = store.load_run(run_id)
    if run["owner_epoch"] != owner_epoch or run["scope"] != private["scope"]:
        raise AssignmentError("needs_reconcile", "run owner epoch or tab changed")
    verify_binding(run["owner"], private["owner"],
                   private["panes"].get(run["scope"]["owner_pane_id"]), run["scope"])
    return run, private


def _members(run: dict, private: dict) -> list[dict]:
    observed = []
    for member in run["members"]:
        live = next((item for item in private["agents"] if item["pane_id"] == member["pane_id"]), None)
        try:
            verify_binding(member, live, private["panes"].get(member["pane_id"]), run["scope"])
            condition = "bound"
        except HerdrError:
            condition = "missing_or_changed"
        observed.append({"member_id": member["member_id"], "condition": condition,
                         "lifecycle": live.get("agent_status") if live else "missing"})
    return observed


def inspect_resume(client: HerdrClient, store: StateStore, run_id: str,
                   expected_generation: int, owner_epoch: int) -> dict:
    run, private = _bound(client, store, run_id, owner_epoch)
    if run["generation"] != expected_generation:
        raise AssignmentError("needs_reconcile", "run changed; inspect again")
    if not run.get("awaiting_user_resume", False):
        run["awaiting_user_resume"] = True
        try:
            run = _save(run, store, owner_epoch)
        except StateConflict as error:
            raise AssignmentError("needs_reconcile", "result arrived during resume; inspect again") from error
    members = _members(run, private)
    outstanding = [{"assignment_id": item["assignment_id"], "state": item["state"],
                    "revision": item["revision"]}
                   for item in run["assignments"].values() if item["state"] != "collected"]
    pending = [{"event_id": key, "assignment_id": item["event"]["assignment_id"]}
               for key, item in run["outbox"].items() if not item["received"]]
    missing = sum(item["condition"] != "bound" for item in members)
    summary = (f"Run {run_id}: {len(members)} members, {missing} missing or changed; "
               f"{len(outstanding)} unresolved assignments and {len(pending)} pending events. "
               "Collect recorded events before confirming. Existing worker tasks were not resent. "
               "Owner confirmation is required before new dispatch.")
    return {"run_id": run_id, "generation": run["generation"], "owner_epoch": owner_epoch,
            "awaiting_user_resume": True, "summary": summary, "members": members,
            "outstanding": outstanding, "pending_events": pending,
            "reattach": "not_certified" if outstanding else "not_needed"}


def confirm_resume(client: HerdrClient, store: StateStore, run_id: str,
                   expected_generation: int, owner_epoch: int) -> dict:
    run, private = _bound(client, store, run_id, owner_epoch)
    if run["generation"] != expected_generation or not run.get("awaiting_user_resume", False):
        raise AssignmentError("needs_reconcile", "resume generation changed or no confirmation pending")
    if any(not item["received"] for item in run["outbox"].values()):
        raise AssignmentError("needs_reconcile", "collect pending events before confirming")
    if any(item["condition"] != "bound" for item in _members(run, private)):
        raise AssignmentError("identity_changed", "member binding changed; reconcile before new dispatch")
    if any(item["state"] in {"dispatching", "active", "delivery_uncertain", "needs_reconcile"}
           for item in run["assignments"].values()):
        raise AssignmentError("needs_reconcile", "active assignment needs a certified listener reattach")
    run["awaiting_user_resume"] = False
    try:
        return _save(run, store, owner_epoch)
    except StateConflict as error:
        raise AssignmentError("needs_reconcile", "run changed during confirmation") from error
