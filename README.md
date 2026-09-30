# Herdr Orchestration

This Agent Skill teaches Codex, Claude Code, Pi and OpenCode how to use Herdr
as a terminal control plane. The owner assigns scoped work to real panes,
preserves its native conversation for user input, and receives compact worker
results. It does not choose a development process, team size or parallelism.

## Current support

The package targets Herdr 0.9.2, protocol 22. Pi 0.87.1 has a tested
process-local owner return bridge and native worker reset in a dedicated
session. Codex, Claude Code and OpenCode owner return/reset combinations are
not certified. Repository-writing assignments require a clean Git checkout,
an exact HEAD/snapshot binding and a tested return channel; the synthetic
Pi→Pi write case passed. See the [compatibility matrix](references/compatibility.md)
and [return evidence](references/return-capability.md) before use. The old
`herdr_agent_turn.py --agent ... --prompt-file ...` interface fails closed.

## Contents

| Path | Use |
| --- | --- |
| [SKILL.md](SKILL.md) | Short activation and operating procedure. |
| [scripts/herdr_orchestrate.py](scripts/herdr_orchestrate.py) | Scoped CLI for team, conversation, assignment, control and resume. |
| [adapters/pi](adapters/pi) | Process-local Pi reset and owner return bridges. |
| [references/handoff-contract.md](references/handoff-contract.md) | Worker packet and result fields. |
| [references/recovery.md](references/recovery.md) | Same-owner recovery limits. |
| [templates](templates) | JSON examples to bind to a real run. |
| [tests](tests) | Offline fixtures and fault tests. |

Run the offline suite with `python3 -m unittest discover -s tests -q` from
this directory. It uses the standard library and no live account. For a
production run, use only the adapter capabilities certified for the installed
versions. A real owner must be inside the intended Herdr pane (`HERDR_ENV=1`).

The [installation and rollback guide](references/installation.md) describes
one canonical copy and local harness discovery paths. It is a plan; this
repository does not install software, edit global profiles or enable bridges
automatically. [Examples U01–U10](references/scenarios.md) show the intended
behavior and current capability boundaries.

## License

Released under the [MIT License](LICENSE). Copyright © 2026 Lorenzo Borgato.
