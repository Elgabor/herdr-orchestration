# Herdr integration update plan and isolated execution

Observed 2026-09-30 with Herdr 0.9.2: daily Pi v8 < v9, OpenCode v11 < v13,
Claude Code v9 < v10; Codex v8 is current. The user reviewed this plan and
authorized **only** the isolated installation below. Claude Code has no
credits for a live test.

## Completed: isolated integration installation

Use `/Users/lorenzoborgato/code/herdr-orchestration-test/integrations/home`
as `HOME` for the installer and for integration status. Read-only status with
that override resolved **all three** targets inside the test folder. Create
only these prerequisite agent configuration directories, then execute the
three installer commands separately:

```sh
test_home=/Users/lorenzoborgato/code/herdr-orchestration-test/integrations/home
mkdir -p "$test_home/.pi/agent" "$test_home/.claude" "$test_home/.config/opencode"
HOME="$test_home" herdr integration install pi
HOME="$test_home" herdr integration install opencode
HOME="$test_home" herdr integration install claude
HOME="$test_home" herdr integration status
```

Expected managed paths, according to the installed CLI's target resolution
and the [Herdr integration documentation](https://herdr.dev/docs/integrations/):

- Pi: `$test_home/.pi/agent/extensions/herdr-agent-state.ts`.
- OpenCode: `$test_home/.config/opencode/plugins/herdr-agent-state.js`,
  `herdr-tui-session.js`, `herdr-opencode/tui.js`, and TUI registration in
  `tui.jsonc` or `tui.json` and `cli.json`.
- Claude Code: `$test_home/.claude/hooks/herdr-agent-state.sh` and Herdr
  entries in `$test_home/.claude/settings.json`.

The destination was absent before setup, so no preexisting user data was
overwritten. All three install commands returned success. `HOME="$test_home"
herdr integration status` reported Pi **current v9**, OpenCode **current
v13**, Claude **current v10**. The installed file inventory matched the paths
above. The new test `integrations/` and `home/` directories were set to mode
0700, and the generated test `.claude/settings.json` to 0600. Read-only
status without the override still reported daily Pi v8, OpenCode v11 and
Claude v9, so those integrations were untouched. No auth material was copied
into this home;
whether Pi or OpenCode can run with the isolated configuration remains to be
tested. Claude's live adapter stays `BLOCKED` without credits. The test
installation can be reversed with `HOME="$test_home" herdr integration
uninstall <target>` for each installed target, followed by a status check.
Any remaining empty test directories are identified before deletion.

An additional no-model startup check ran in the dedicated Herdr session.
Pi with `PI_CODING_AGENT_DIR` set to the isolated v9 directory became
interactive and reported `idle`, its native session path, and
`screen_detection_skipped=true`; it then exited. OpenCode started with the
isolated `HOME` and became interactive, but displayed `/connect` because
that home has no provider account. `agent explain` attributed its `idle`
state to screen-manifest fallback, not the new plugin, and no session ID was
reported. It exited after two Ctrl-C presses. A scoped agent list was empty.
No model turn or authentication change occurred for either probe.

## Unexecuted alternative: update the daily integrations

The exact installer commands would be `herdr integration install pi`,
`herdr integration install opencode`, and `herdr integration install claude`.
They would touch these existing global paths:

- `~/.pi/agent/extensions/herdr-agent-state.ts` (currently v8).
- `~/.config/opencode/plugins/herdr-agent-state.js` and
  `~/.config/opencode/herdr-tui-session.js` (currently v11), plus a new
  `~/.config/opencode/herdr-opencode/tui.js` and `cli.json`, and existing
  `tui.jsonc` registration. OpenCode TUI and shared servers would need a
  restart to use the new plugin; daily processes would be affected.
- `~/.claude/hooks/herdr-agent-state.sh` (currently v9) and Herdr hook entries
  in `~/.claude/settings.json` (mode 0600). The updated matcher is restricted
  to documented Claude session-start sources.

The global path changes conflict with the original constraint against
changing global hooks and configuration unless explicitly authorized after
this plan. `herdr integration uninstall` removes the new integration but
does **not** restore the previous versions or exact settings. An exact
rollback would require handling existing configuration files, potentially
including private settings, which this task is not authorized to copy or
inspect. Therefore the global update is not proposed for execution yet.
No harness executable, model default, login, or Herdr server is updated by
either installer plan.
