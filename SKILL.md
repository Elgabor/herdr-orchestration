---
name: herdr-orchestration
description: Use Herdr to coordinate explicitly authorized coding agents in real panes, with scoped assignments, native conversations, observable owner return, and compact results. Does not choose an engineering workflow or start extra agents on its own.
metadata:
  short-description: Low-overhead Herdr agent coordination
---

# Herdr Orchestration

Herdr owns terminal layout and agent detection. Each coding harness owns its
model, permissions, tools and native conversation. A **pane** is a terminal;
its **occupant** can change; a **conversation** can change while the pane stays
the same. Bind all three before sending work. The owner decides task scope,
parallelism, acceptance and any later action. A worker performs the assigned
work in a real Herdr pane and returns a compact result to that same owner.

## Activate and bind

From inside the intended owner pane, require `HERDR_ENV=1`. Use the installed
Herdr client/server version and the local [compatibility matrix](references/compatibility.md).
Run `python3 <skill-directory>/scripts/herdr_orchestrate.py doctor`, then
`team inspect` to see only the caller's tab. Never use a global focused pane,
a human label, or another tab as authority. If bindings or version checks are
uncertain, stop that operation; do not switch sessions or update software.

Adopt only the user-mapped members already in the tab with `run init` and an
explicit config. If no team exists, `bootstrap_team` plus `team prepare`
requires a user-authorized minimal plan; the roster then freezes. A busy
member does not justify a new team. Keep configured provider, model, effort,
trust and tools. Automatic choice needs comparable cost and quota evidence;
unknown is unknown. Do not infer parallelism. See
[provisioning](references/provisioning.md) and [usage](references/usage-and-routing.md)
only for those decisions.

## Assign, wait, return

For distinct work, start a fresh **native conversation in the same worker
pane** and verify its configuration. A repair stays in the same thread and
sends only the change. The tested Pi reset uses `conversation reset`; other
harness reset adapters remain unverified. See
[native conversation](references/native-conversation.md) when changing tasks.

Create one bounded `assignment dispatch` config with member, conversation,
revision, scope, output path and acceptance. The default helper is
`scripts/herdr_orchestrate.py`; paths in examples resolve from this skill
directory. Read [worker contract](references/handoff-contract.md) when writing
the task packet. A read-only task may write only its approved result outputs.
Repo-writing dispatch is blocked until checkout snapshots are certified.

Arm an observable same-owner return **before** dispatch. The tested Pi owner
adapter is the process-local `adapters/pi/owner_return.ts`, loaded for that
interactive Pi process, and its `/herdrdispatch` command. It starts one
deterministic wait child and returns Pi to idle so the user can steer the owner
while the worker runs. On completion it wakes the same Pi session. Do not use
a blocking owner `agent prompt --wait`, UI notification, PID or background
process as proof of interruptible return. Codex, Claude Code and OpenCode owner
bridges remain uncertified. Never poll workers with model turns or redispatch
after an ambiguous send. See [return evidence](references/return-capability.md).

The worker writes a bounded JSON result and invokes the packet's
`publish_command`. The owner uses `assignment pending` and `assignment
collect` to acknowledge a correlated event once. `result_ready` is recorded
evidence, not acceptance; worker `done` does not override a blocked result.
Do not reset or reuse a worker still running. For steering, `control apply`
supports future instructions, dispatch pause and a versioned amendment. A
queued amendment is not worker acknowledgment; check its revision and IDs in
the result. Targeted cancel and native goal mutation are blocked pending a
certified adapter. See [dispatch](references/dispatch-and-result.md) when
handling an active assignment.

## Resume and authority

`resume inspect` compares the same owner and frozen roster to live bindings,
reports pending events and gates new dispatch. Collect saved results, then
`resume confirm` with the observed generation. Active work with a lost
listener, changed owner or reused pane ID needs reconciliation; never send the
task again to test whether it arrived. See [recovery](references/recovery.md).

`/goal` is optional and cannot supply the return channel. A paused goal stays
paused. The helper does not decide a development workflow, number of repairs,
review requirement, commit policy or model quality. It does not authorize
push, merge, deploy, installation, credential access or destructive cleanup.
