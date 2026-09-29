---
name: herdr-orchestration
description: Coordinate coding agents through Herdr with event-driven waits, compact handoffs, and owner-controlled acceptance. Use when the user explicitly asks for Herdr orchestration, multi-harness delegation, or an owner-worker ticket loop; it complements rather than replaces specification and engineering workflow skills.
metadata:
  short-description: Low-overhead Herdr agent coordination
---

# Herdr Orchestration

Herdr is the terminal control plane. Each harness still owns its model,
permissions, tools, memory, and side effects. The owner/orchestrator owns task
selection, acceptance, commits, and the final result.

## Activation boundary

Designing a workflow can happen anywhere. Before controlling Herdr, require:

```sh
test "${HERDR_ENV:-}" = 1
```

If it fails, stop instead of controlling another Herdr session from outside.
Use the requested harness, provider, model, and effort exactly; report an
unavailable choice rather than substituting silently.

## Establish the run

Record only what changes decisions:

- objective and verifiable stopping condition;
- authority and actions that still require approval;
- repo, branch or worktree, current commit, and one writer per checkout;
- named owner, implementer, and optional researcher or reviewer;
- ticket source, verification commands, repair budget, and external actions.

Reuse clear pane and agent names. Ask for a mapping only when existing panes are
ambiguous. Herdr visibility never authorizes push, merge, deploy, installation,
credential access, destructive cleanup, or approval dialogs.

## Event-driven loop

For each bounded unit of work:

1. Give the worker one complete prompt with scope, acceptance criteria,
   boundaries, verification, and the compact handoff contract.
2. Submit and wait atomically with `agent prompt --wait`. While the worker is
   `working`, leave it alone.
3. If the host exposes an ongoing process handle, wait on that same handle with
   the longest supported wait. Do not replace it with state, pane, or log polls.
4. On `done` or `idle`, read the compact handoff and inspect only the relevant
   diff, files, and test evidence.
5. Decide `ACCEPT`, `REPAIR`, `RESEARCH`, or `BLOCK`. Keep a repair on the same
   worker session and send only the delta. Start research only for a concrete
   unresolved question.
6. After acceptance, the owner performs the authorized commit or tracking
   update and advances to the next unit.

Default to one repair attempt unless the user or approved workflow sets another
budget. A worker report is evidence, never acceptance.

For the deterministic wait and compact result envelope, run:

```sh
python3 <skill-directory>/scripts/herdr_agent_turn.py \
  --agent implementer --prompt-file /path/to/prompt.md
```

The helper invokes the named Herdr agent exactly once; it contains no provider
routing and never retries. Read
[`references/handoff-contract.md`](references/handoff-contract.md) before
constructing worker prompts. For ticket queues, research gates, repair rules,
and `/goal`, read
[`references/delegation-loop.md`](references/delegation-loop.md).

## Lifecycle rules

- `working`: wait without messaging or polling.
- `blocked`: inspect once and request the necessary human decision; never
  auto-approve.
- `done` or `idle`: ready for handoff inspection or another prompt.
- `unknown`: inconclusive; use `agent get` or `agent explain`, not acceptance.
- `timeout` or `agent_prompt_stalled`: the prompt may have been delivered.
  Inspect once before deciding; never resubmit automatically.

Use pane commands for tests, servers, and ordinary processes. Use agent commands
only for recognized agents. If a full response is unavailable, request a file
path instead of repeatedly expanding terminal history.

## Durable goals

`/goal` is optional continuity for work that may outlive one owner turn. It is
not a scheduler and does not justify polling. Keep the authoritative queue and
checkpoint outside the conversation; resume from current ticket, accepted
commits, open decision, and verification state rather than replaying transcripts.

For topology, direct CLI alternatives, worktrees, and recovery examples, read
[`references/orchestration-patterns.md`](references/orchestration-patterns.md).
