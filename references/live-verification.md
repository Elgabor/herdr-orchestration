# Live verification and delivery boundary, 2026-09-30

## Environment and result

All live work used the named `herdr-orchestration-v1-test` session and
`/Users/lorenzoborgato/code/herdr-orchestration-test`. Herdr client/server
were 0.9.2, protocol 22. The tested owner and worker were interactive Pi
0.87.1 instances in `w5:p1` and `w5:p2`, each using
`openai-codex/gpt-6-luna` with low thinking and test-local session
directories. No integration, account, login, global skill or default model
was changed. The first tested result was read-only. A second Pi→Pi run used
a fresh synthetic Git repository and the new clean-checkout snapshot gate.

The Pi owner bridge passed a normal same-session return. Its worker prompt
was sent once. While a deterministic gate held the worker, the owner
completed a separate user turn and wrote a marker. After release, the worker
published a correlated JSON result, the bridge woke the same owner session
with its event ID, and the owner collected it once. A later same-owner
`resume inspect` and `resume confirm` recovered the saved completed state
without resending work. The owner bridge's corrected exact collection
wording was not reloaded into that live process; the first wording led the
owner to guess invalid CLI commands, then an explicit valid command
collected the event. See [return evidence](return-capability.md).

The second run bound owner `w6:p1` and worker `w6:p2` to the same named test
session. `repo snapshot` recorded exact root, branch, HEAD and a clean token.
The worker changed only synthetic `README.md`, ran `git diff --check`, and
published a result bound to that base. The owner extension's revised exact
collection command worked without an extra user prompt: state reached
`collected` with its outbox event received. The changed checkout then caused
`repo snapshot` to return `needs_reconcile` as designed. The write packet
was 1,806 bytes including task text; its fixed contract was 1,495 bytes.
This proves the tested Pi write path, not a general race-free Git lock or
support for preexisting dirty worktrees.

At the end of the tests, `/quit` was sent only to test Pi `w5:p2`, `w5:p1`,
`w6:p2` and `w6:p1`. A scoped server snapshot then reported **zero agents**. The named
test server and test files remain for review; no daily Herdr session was
altered. The TUI was inspected through Herdr pane reads and lifecycle APIs;
an independent visual check of actual viewport visibility was **NOT_RUN**.

## Owner × worker matrix

Each cell requires an assignment and correlated return before it can be
certified. A row also needs owner steering; a column needs native worker
reset, block and quota evidence.

| Owner ↓ / Worker → | Codex | Claude Code | Pi | OpenCode |
| --- | --- | --- | --- | --- |
| Codex | NOT_RUN | BLOCKED credits | NOT_RUN | NOT_RUN |
| Claude Code | BLOCKED credits | BLOCKED credits | BLOCKED credits | BLOCKED credits |
| Pi | NOT_RUN | BLOCKED credits | **PARTIAL** read-only and clean-repo write dispatch, wake, input, reset and collection passed | NOT_RUN |
| OpenCode | NOT_RUN | BLOCKED credits | NOT_RUN | NOT_RUN |

Codex 0.155.1 reached a directory trust prompt during the earlier owner
probe; it was declined then. The user later authorized trust for the test
folder only. In `w7:p1`, Codex ran a no-tool test turn using `gpt-6-luna`
with low effort and replied exactly as requested. Herdr v8 reported a native
session ID, but kept lifecycle `unknown`; `agent prompt --wait` timed out
after 45 seconds even though the turn visibly completed. `/new` showed a
fresh TUI and a new session ID on exit, while Herdr still showed the old
identity before exit. The test Codex process exited; the scoped agent list
returned zero. No Codex owner return, steering, or reset identity binding is
certified. The Codex TUI reported 17,449 total tokens for that one test turn,
mostly input context, despite the low-cost model and eight output tokens.
Claude Code 2.1.284
has no credits, per the user. OpenCode 1.18.33 is installed, but its Herdr
integration v11 is behind installed v13. Pi 0.87.1 has integration v8 behind
v9, yet the process-local bridge and reset were tested against the actual
installed daily combination. After those live tests, the user authorized
isolated Herdr integrations in the test folder: Pi v9, OpenCode v13 and
Claude v10 now report current there; daily integrations remain unchanged.
At the time of those startup checks, no model turn had run with the isolated
versions. The Pi→Pi cell remains partial because active amendment,
lost-listener recovery, goal pause, visibility and full fault injection are
not live certified.

After isolated installation, Pi v9 was started in test pane `w8:p1` with
`PI_CODING_AGENT_DIR` pointing into the test home. Herdr reported `idle`, a
native session path, and `screen_detection_skipped=true`; the agent exited
without a model turn. OpenCode v13 started in `w9:p1` with test-only `HOME`.
Its TUI requested `/connect`; no provider was available there. Herdr's
`agent explain` attributed `idle` to screen fallback, not the new plugin,
and no native session ID appeared. OpenCode exited without a model turn.
The scoped agent list was again empty. These startup checks do not change
the owner×worker matrix.

An additional OpenCode Go probe used `wA:p1` in the same dedicated server,
with `XDG_CONFIG_HOME` pointing to the test-local v13 integration and the
existing OpenCode account consumed opaquely. The installed catalog listed
`opencode-go/space-bunny-free` at zero input/output cost. A one-turn `agent
prompt --wait` returned `done`, the visible TUI replied `OC_GO_OK`, and Herdr
reported native session `ses_f0d55227fffeRbWeUGfDhm8RFb` with
`screen_detection_skip_reason=full_lifecycle_hook_authority`. `/new` cleared
the TUI in the same pane, but Herdr still reported the previous session ID
until the next model turn. That turn replied `OC_NEW_OK` and reported native
session `ses_f0d5491e5ffeMmCu8soAX6FY4V`. This certifies OpenCode Go
access and the v13 lifecycle during turns. Immediate reset identity before
a new turn and owner return remain **BLOCKED**. Both test sessions are
designated for deletion during final cleanup; existing OpenCode sessions
are untouched.

## Same-process Pi listener reattachment

In `wB:t1`, a Pi owner and worker used the existing daily Pi account and
the repository's process-local extensions, with all state and session files
under the dedicated test folder. The isolated Pi v9 directory was tried
first, but had no model access; that attempt stopped before any model call.
The daily Pi integration was not changed. The owner adopted one member,
reset its native conversation, and dispatched `reattach-task` once. A
deterministic gate held the worker in `working`.

The original listener PID `7010` was checked against its owner PID and exact
test `assignment dispatch` command, then sent TERM. The owner extension
returned a listener error and one `assignment pending` check showed no event.
While the worker remained active, `/herdrreattach` in that same owner process
saved listener version 2 at generation 4 and called Herdr `agent wait` without
a second prompt. After the gate was released, the worker published one
correlated result. The same owner session received its event ID and collected
it; generation 6 recorded `collected`, one outbox event with `received=true`,
and `worker_released=true`. Both test Pi processes exited and the named
session's agent list returned zero. This is a **PASS** for a lost listener in
the same owner process. Owner process restart, non-Pi owners, and
`events_lost` remain unverified.

## Small scenario comparison

The earlier blocking Pi `agent prompt --wait` gate and the later production
bridge gate both used one worker task submission and zero model polling
turns. The blocking wait returned to the owner after completion but queued
new user input until then: steering before release **FAIL**. The production
bridge kept the owner idle during the worker gate: steering before release
**PASS**, same-session wake **PASS**, correlated collection **PASS**. No
duplicate task submission was observed in either gate. These were different
small test instructions, so this is a behavior comparison, not a controlled
token or latency benchmark.

For the production test config, the serialized worker packet was 1,584
UTF-8 bytes, including task text; the fixed contract without task text was
1,347 bytes. The helper now rejects fixed contracts over 1,500 bytes and
total packets over 64 KiB. Comparable baseline packet bytes, owner-context
bytes, task-isolated token counts and technical return latency were not
recorded. No savings percentage is asserted. The test Pi TUI displayed
usage/cost estimates, but they cover whole sessions rather than matching
single scenarios and are not treated as account quota.

## Remaining gates and precise next action

- **Codex owner/worker:** the dedicated-folder trust decision is resolved.
  Investigate the observed `unknown` lifecycle and stale post-`/new` Herdr
  identity, then test a process-local or native same-session callback,
  pre-completion input and bound clean reset. Do not infer support from
  visible Codex output alone.
- **Claude Code:** obtain account credit authorization and refresh its
  outdated Herdr integration only after explicit authorization; then run
  the owner and worker gates on an isolated test session.
- **OpenCode:** authorize an integration update or certify the installed v11
  behavior against v13's contract, then prove native callback and reset.
- **Pi:** implement and test active listener reattachment after interruption,
  versioned amendment while a worker is gated, lost-result/error callbacks,
  optional goal pause, and visibility in the real TUI.
- **Core:** strengthen checkout race detection for concurrent external writes,
  implement identity-safe cleanup, `events_lost` reconciliation, safe owner
  transfer and an end-to-end direct
  handoff grant before enabling those operations. Complete the `PARTIAL` and
  `NOT_RUN` entries in [coverage](../evals/coverage.md); run behavioral evals
  from [scenarios](../evals/scenarios.json) with separately authorized live
  accounts and budget.

No push, PR, merge, release, deploy or global installation was performed.
