# Reversible local installation plan

No installation is performed by this repository. Use the checked-out
`herdr-orchestration` directory as the single canonical copy, with its
`SKILL.md`, scripts, adapters, templates and references kept together. On
this development host that source is
`/Users/lorenzoborgato/code/herdr-orchestration`; replace it with the chosen
checkout path on another machine. Never copy only `SKILL.md`.

| Harness | Local discovery candidate | Invocation to verify after authorization |
| --- | --- | --- |
| Codex | project `.agents/skills/herdr-orchestration` or its configured skills directory | `$herdr-orchestration` |
| Claude Code | project `.claude/skills/herdr-orchestration` | `/herdr-orchestration` |
| Pi | project `.agents/skills/herdr-orchestration` or its configured skills directory | `/skill:herdr-orchestration` |
| OpenCode | project `.opencode/skills/herdr-orchestration`; it also searches `.agents` and `.claude` compatibility paths | native `skill` tool with ID `herdr-orchestration` |

These are discovery paths, not proof that the current four harnesses loaded
this revision. [Codex skill guidance](https://learn.chatgpt.com/docs/build-skills),
[Claude Code guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview),
[Pi guidance](https://pi.dev/docs/latest/skills), and
[OpenCode guidance](https://opencode.ai/docs/skills) describe their respective
loaders. Check the installed version's behavior before use.

For an approved project-local installation, inspect every candidate path and
its real target first. If a path is absent, link its whole skill directory to
the canonical checkout. If it exists, compare realpaths and file hashes;
never overwrite an unrelated or older user-managed skill automatically.
OpenCode may discover both `.agents/skills` and `.claude/skills` in one
project. Duplicate IDs must resolve to the **same canonical directory** and
the selected definition must be verified in that harness; otherwise leave
that harness disabled until the collision is resolved. Do not create four
independent forks of the skill.

The Pi owner and worker bridges are process-local files. Only after the
owner's live capability is certified, launch the intended interactive Pi
process with `--extension <skill-directory>/adapters/pi/owner_return.ts` for
an owner or `--extension <skill-directory>/adapters/pi/native_context.ts` for
a worker. Give that pane a private `HERDR_ORCH_BRIDGE_DIR` outside the repo.
The tested prototype did this in a dedicated Herdr session; it did not
change Pi global settings, hooks, integrations, login or default model.
No Codex, Claude or OpenCode bridge has an approved install step yet.

To roll back an approved local view, first stop using its bridge in new
processes. Remove **only** the specific symlink whose real target still
matches the canonical checkout, after identifying that exact path to the
owner. Restore any preexisting path from its recorded location. Do not
delete the checkout, run state, result files, Herdr panes or user profiles
as generic cleanup. Restart or reload the affected harness and verify that
the skill ID disappears or resolves to the intended previous copy.
