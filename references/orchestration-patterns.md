# Herdr orchestration patterns

Use these patterns only after the activation and authority checks in `SKILL.md`.
The installed `herdr --help` and `herdr --skill` output are authoritative for
the local version.

## Map an existing control room

Discover IDs and names instead of inferring them from screen position:

```sh
herdr pane current --current
herdr pane list --workspace "$HERDR_WORKSPACE_ID"
herdr agent list
```

Preserve meaningful names. If the layout is ambiguous, ask the user which pane
is owner, implementer, researcher, reviewer, or tests before prompting anyone.

## One atomic agent turn

Prefer the bundled helper because it keeps terminal output outside the owner's
model context:

```sh
python3 <skill-directory>/scripts/herdr_agent_turn.py \
  --agent implementer \
  --prompt-file /path/to/current-ticket.md
```

It submits one prompt, waits for Herdr's settled lifecycle state, performs one
post-wait inspection, and prints a small JSON envelope. It never polls or
retries. The full terminal read and worker handoff remain at the returned paths.

Direct CLI alternative:

```sh
herdr agent prompt implementer "$(cat /path/to/current-ticket.md)" --wait
herdr agent read implementer --source recent-unwrapped --lines 80
```

Herdr waits indefinitely after it observes activity when no timeout is supplied.
If the calling tool yields a process or session handle, continue waiting on that
same handle; do not start `agent wait`, `agent get`, or `agent read` loops.

## Ticket queue

Keep the queue in the existing specification or ticket tracker. For each ticket,
write a small prompt file containing only:

- ticket identifier and acceptance criteria;
- current base commit and allowed files or subsystem;
- project-native verification commands;
- permissions and stop conditions;
- the handoff fields required by `handoff-contract.md`.

After `ACCEPT`, record the commit and advance. For `REPAIR`, give the same worker
only the failed criterion and relevant evidence. For `RESEARCH`, ask a separate
read-only agent one explicit question, wait once, and feed its compact answer to
the owner or implementer. Stop at the repair budget or an approval boundary.

## Safe topology

- One checkout: one writer, optional read-only reviewer, and a shell/test pane.
- Multiple writers: separate worktrees or repositories with explicit ownership.
- Research and review: state read-only scope in the prompt.
- Tests and servers: use pane commands unless a recognized agent owns the work.

If the user authorizes a new pane, preserve focus and the current directory:

```sh
split=$(herdr pane split --current --direction right --cwd "$PWD" --no-focus)
worker_pane=$(printf '%s\n' "$split" | jq -r '.result.pane.pane_id')
herdr agent start implementer --kind opencode --pane "$worker_pane"
```

Use the exact requested kind and native arguments. `agent start` needs an
existing available shell pane and does not create layout itself.

## Recovery

On `blocked`, inspect once and do not answer approval dialogs automatically:

```sh
herdr agent get implementer
herdr agent read implementer --source visible --lines 80
```

On `timeout` or `agent_prompt_stalled`, inspect before any retry because the
prompt may already have been delivered:

```sh
herdr agent get implementer
herdr agent read implementer --source recent-unwrapped --lines 80
```

Treat `unknown` as inconclusive:

```sh
herdr agent explain implementer --json
```

Do not close panes, tabs, workspaces, or sessions that the orchestration did not
create. Never stop the Herdr server unless the user explicitly intends to stop
its pane processes.
