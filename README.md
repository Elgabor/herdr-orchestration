# Herdr Orchestration

An Agent Skill for coordinating an owner and coding agents through Herdr. The
owner assigns a bounded task, waits for the agent to finish, reads a short
handoff, and decides whether to accept the work, request a repair, or stop.

Herdr manages terminals and agent state. Each coding harness keeps its own
models, tools, and permissions.

## When to use it

- You have a ticket with clear acceptance criteria to give to an agent.
- You need to coordinate agents across harnesses without repeated status checks.
- You want the owner to inspect the diff, tests, and risks before accepting work.

Use your chosen engineering process to define the product, specification, and
tickets. This skill handles delegation and handoffs inside Herdr.

## Requirements

- Herdr installed, with a target agent already recognized by Herdr.
- The owner running inside a Herdr session (`HERDR_ENV=1`).
- An agent that can load skills in the Agent Skills format.
- Python 3.10 or later for the optional `scripts/herdr_agent_turn.py` helper.
  The helper uses only the Python standard library.

The optional pane-creation example in
[`references/orchestration-patterns.md`](references/orchestration-patterns.md)
also uses `jq`.

## Install

Clone this repository into your harness's skill directory, keeping the folder
name `herdr-orchestration`:

```sh
git clone https://github.com/Elgabor/herdr-orchestration.git
```

`SKILL.md` is at the repository root. Follow your harness's instructions for
its skill directory, then start a fresh session to check that it discovers the
skill. Install Herdr separately.

## Quick start

Before controlling an agent, check that the owner is running inside Herdr:

```sh
test "${HERDR_ENV:-}" = 1
```

Then ask the owner agent, for example:

> Use `$herdr-orchestration` for the current ticket. The Herdr agent is named
> `implementer`. Send only the ticket and its acceptance criteria, wait for the
> result, inspect the diff and tests, and report your decision. Ask me before
> any push, merge, or deploy.

For one worker turn, prepare a file containing the worker prompt and run:

```sh
python3 scripts/herdr_agent_turn.py \
  --agent implementer \
  --prompt-file /path/to/current-ticket.md
```

The helper submits one prompt with `herdr agent prompt --wait`. When the wait
ends, it reads the agent state and terminal once and prints a compact JSON
result with paths to the handoff, terminal excerpt, and diagnostics. It writes
those artifacts to a private temporary directory. It does not automatically
retry an uncertain submission.

The owner reads the handoff, compares its file list with the actual diff, and
checks the reported verification. Only the owner chooses `ACCEPT`, `REPAIR`,
`RESEARCH`, or `BLOCK`. The worker handoff format is in
[`references/handoff-contract.md`](references/handoff-contract.md).

## What's included

| Path | Purpose |
| --- | --- |
| [`SKILL.md`](SKILL.md) | Activation conditions, delegation loop, and authority limits. |
| [`scripts/herdr_agent_turn.py`](scripts/herdr_agent_turn.py) | One submission and wait, with a compact JSON result. |
| [`references/handoff-contract.md`](references/handoff-contract.md) | Required handoff fields. |
| [`references/delegation-loop.md`](references/delegation-loop.md) | Tickets, reviews, repairs, and checkpoints. |
| [`references/orchestration-patterns.md`](references/orchestration-patterns.md) | Herdr commands, agent layouts, and recovery examples. |
| [`agents/openai.yaml`](agents/openai.yaml) | Codex display metadata. |

## Authority and safety

Seeing an agent in Herdr does not authorize publishing, installation, credential
access, or automatic approval. A worker supplies evidence; the owner makes the
decision. After a timeout or uncertain state, inspect the agent before sending
the same prompt again.

## License

Released under the [MIT License](LICENSE). Copyright © 2026 Lorenzo Borgato.
