# Native conversation reset

For a distinct assignment, reset the selected worker in its existing pane
after the prior assignment is released. A repair or continuation keeps the
same conversation and passes only the changed instructions or evidence.
Never reset the owner as part of worker task turnover.

The Pi 0.87.1 adapter is a process-local extension at
`adapters/pi/native_context.ts`. Load it with Pi's `--extension` flag for that
specific interactive process and set `HERDR_ORCH_BRIDGE_DIR` for its pane to
an owner-only directory outside the repository. This is not a global Pi
installation. The extension registers `/herdrinspect` and `/herdrnew`; the
latter calls Pi's native `newSession` API. It writes bounded private proofs
with a per-operation nonce and performs no model call.

`conversation reset` sends the inspection command only after checking the
frozen pane binding, idle status, and released assignments. It records a
reset intent before `/herdrnew`. It never uses Herdr's LLM-task `--wait` gate
for the reset. After the native proof, it checks Herdr's new session identity,
the same pane and terminal, and a fresh native inspection of cwd, provider,
model, thinking level, project trust, and active tools. If delivery or any
postcondition is uncertain, it records `needs_reconcile` and does not send
the reset again. The owner session stays unchanged.

Use `--expected-config` with a private JSON object when the assignment has
an explicit model or permission binding. Supported keys are `cwd`, `model`
(`provider`, `id`), `thinking`, `trusted`, and `tools`. Without this file the
adapter preserves the observed pre-reset configuration; the owner remains
responsible for checking that it matches the user's assignment.

The dedicated Pi live test confirmed a new worker session in the same pane,
with its prior model and settings and the owner's session unchanged. Codex,
Claude Code and OpenCode native reset adapters are not certified in this
package.
