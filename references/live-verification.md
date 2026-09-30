# Live verification and delivery boundary, 2026-09-30

## Environment and result

All live work used the named `herdr-orchestration-v1-test` session and
`/Users/lorenzoborgato/code/herdr-orchestration-test`. Herdr client/server
were 0.9.2, protocol 22. The tested owner and worker were interactive Pi
0.87.1 instances in `w5:p1` and `w5:p2`, each using
`openai-codex/gpt-6-luna` with low thinking and test-local session
directories. No integration, account, login, global skill or default model
was changed. The tested result was read-only; repository-writing dispatch
remains blocked by the missing snapshot verifier.

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

At the end of the test, `/quit` was sent only to test Pi `w5:p2` and
`w5:p1`. A scoped server snapshot then reported **zero agents**. The named
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
| Pi | NOT_RUN | BLOCKED credits | **PARTIAL** read-only dispatch, wake, input, reset and collection passed | NOT_RUN |
| OpenCode | NOT_RUN | BLOCKED credits | NOT_RUN | NOT_RUN |

Codex 0.155.1 reached a directory trust prompt during the earlier owner
probe; it was declined, so no owner return was claimed. Claude Code 2.1.284
has no credits, per the user. OpenCode 1.18.33 is installed, but its Herdr
integration v11 is behind installed v13. Pi 0.87.1 has integration v8 behind
v9, yet the process-local bridge and reset were tested against the actual
installed combination. No updates were applied. The Pi→Pi cell remains
partial because active amendment, lost-listener recovery, goal pause,
visibility and full fault injection are not live certified.

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

- **Codex owner/worker:** in the dedicated folder, resolve the trust decision
  with the user, then test a process-local or native same-session callback,
  pre-completion input and native clean reset. Do not infer support from
  Herdr agent status.
- **Claude Code:** obtain account credit authorization and refresh its
  outdated Herdr integration only after explicit authorization; then run
  the owner and worker gates on an isolated test session.
- **OpenCode:** authorize an integration update or certify the installed v11
  behavior against v13's contract, then prove native callback and reset.
- **Pi:** implement and test active listener reattachment after interruption,
  versioned amendment while a worker is gated, lost-result/error callbacks,
  optional goal pause, and visibility in the real TUI.
- **Core:** implement repository snapshot verification, identity-safe cleanup,
  `events_lost` reconciliation, safe owner transfer and an end-to-end direct
  handoff grant before enabling those operations. Complete the `PARTIAL` and
  `NOT_RUN` entries in [coverage](../evals/coverage.md); run behavioral evals
  from [scenarios](../evals/scenarios.json) with separately authorized live
  accounts and budget.

No push, PR, merge, release, deploy or global installation was performed.
