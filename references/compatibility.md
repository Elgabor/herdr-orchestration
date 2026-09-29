# Compatibility baseline

Observed 2026-09-29 on macOS Darwin 25.6.0 arm64. This is a development
baseline, not a claim that owner return, reset, or steering works live.
Official release data came from each project's GitHub `releases/latest` API.
Installed versions came from the local executable's `--version`. No software
was installed or updated.

| Component | Latest stable release | Installed client | Server / protocol | Integration | Critical capability test |
| --- | --- | --- | --- | --- | --- |
| [Herdr](https://github.com/herdrdev/herdr/releases/tag/v0.9.2) | v0.9.2 | 0.9.2 | Dedicated server 0.9.2, protocol 22 | Not applicable | PASS for version match only |
| [Codex CLI](https://github.com/openai/codex/releases/tag/rust-v0.159.0) | rust-v0.159.0 | 0.155.1 | Dedicated Herdr server protocol 22 | Current v8 | NOT RUN; startup trust prompt declined |
| [Claude Code](https://github.com/anthropics/claude-code/releases/tag/v2.1.284) | v2.1.284 | 2.1.284 | Dedicated Herdr server protocol 22 | Outdated v9 < v10 | NOT RUN; no credits |
| [Pi](https://github.com/earendil-works/pi/releases/tag/v0.99.1) | v0.99.1 | 0.87.1 | Dedicated Herdr server protocol 22 | Outdated v8 < v9 | FAIL for blocking-wait steering; partial PASS for return/reset |
| [OpenCode](https://github.com/anomalyco/opencode/releases/tag/v1.18.33) | v1.18.33 | 1.18.33 | Dedicated Herdr server protocol 22 | Outdated v11 < v13 | NOT RUN |

`HERDR_ENV`, `HERDR_SESSION_ID`, `HERDR_WORKSPACE_ID`, and `HERDR_PANE_ID`
were unset in this shell. A read-only `herdr status server` reported `not
running`; no active session or pane inventory was queried. The bundled client
schema reports `schema_version=1`, 272,578 bytes, SHA-256
`9e2af207e9aa8183d4aeca5fde9cc48e7909bb40cdbd7cf21608a6d3ea78075b`.
This is **client schema only**. After the user authorized a dedicated test
session, `herdr --session herdr-orchestration-v1-test status --json` reported
client and server 0.9.2, protocol 22, `compatible=true`, and
`endpoint_compatible=true`. These observations apply only to that test server;
the default session remained stopped.

Read-only `herdr integration status` reports Codex current (v8), Pi outdated
(v8 < v9), Claude outdated (v9 < v10), and OpenCode outdated (v11 < v13).
No integration was changed. A dedicated Herdr session, available accounts, and
an authorized test budget are required for live checks. Test the installed
Codex and Pi versions first; any upgrade needs a separate instruction.

The user subsequently authorized low-cost LLM tests in a dedicated folder.
Claude Code has no credits. [The Pi owner gate](return-capability.md) found
working same-thread completion and reset, but failed pre-completion user input
with the blocking wait. The other owner adapters remain unverified.

## Migration inventory

Source checkout: `Elgabor/herdr-orchestration` at
`81c22c9b09e3bf9e7708dcac068528f85c490454` before changes, on local
branch `feature/herdr-orchestration-v1`. The specification describes
`Elgabor/personal-skills` at `ed3f23d...`, but that repository was not
accessible with a read-only remote check. The user supplied this standalone
checkout as the work target. It had no applicable repository `AGENTS.md`, no
existing tests or dependencies, and a clean working tree.

- Preserve the skill name, Codex metadata, concise Herdr identity rules, and
  the single Python helper entry point.
- Replace the ticket pipeline, universal repair budget, universal `/goal`
  advice, and `idle`-as-success assumption with scoped delegation and a
  validated result protocol.
- Evolve `scripts/herdr_agent_turn.py` into a migration entry point. Its old
  `--agent` plus `--prompt` invocation has no run, pane, conversation, or
  owner-return binding and must fail closed before any Herdr call.
- Keep state and result files private and outside commits. The current helper
  uses a temporary directory, which is not a sufficient durable run store.

The released [Herdr automation](https://herdr.dev/docs/agent-automation/),
[socket](https://herdr.dev/docs/socket-api/), and
[integration](https://herdr.dev/docs/integrations/) documents are candidate
API references. A local client schema and a server observation must be
compared in the dedicated Herdr session before a mutating adapter is enabled.
