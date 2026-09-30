# Implementation checkpoint

- Spec: HERDR-ORCHESTRATION-SPEC-v1.0, 2026-09-29. Work checkout initial HEAD:
  `81c22c9b09e3bf9e7708dcac068528f85c490454`.
- T01: DONE, commit `67a45f4`. T03: DONE, commit `ecb4332` (13 offline tests).
  T04: DONE, commit `4e2aca9`. T05: DONE, commit `c45afe9`.
  T06: Pi adapter committed `def8820`; other harnesses remain uncertified.
  T07: conservative quota reader/catalog committed `d1dbaee`.
  T08: dispatch/result core and tests committed `f1e4013`; clean Git checkout
  snapshot gate and synthetic Pi→Pi write test committed `e21394e`.
  T09: Pi owner bridge, correlated outbox/ack, and live Pi→Pi return committed
  `c21c992`. Other owners and crash recovery remain uncertified.
  T10: versioned future instruction, dispatch pause and same-thread amendment
  with queued/ack distinction committed `eed1359`. Targeted
  cancel and native goal mutation remain capability-blocked.
  T11: compact worker contract, read-only output allowlist, and bounded
  `next_handoff` data/grant validation committed `595d1de`.
  Automatic direct route is not certified and remains owner-mediated.
  T12: same-owner resume inspect/confirm and dispatch gate committed
  `545a0f7`. Lost-listener reattach, owner transfer, and cleanup remain
  capability-blocked.
  T13: short SKILL.md, aligned references, examples U01–U10, package tests
  and reversible installation plan committed `f3acd7e`. No harness
  profile or installed skill changed.
  T14: dispatch fault/busy/release tests, ten unrun behavior eval scenarios
  and X01–X56/R01–R18 coverage report committed `c50e083`. The full fault
  matrix is not complete.
  T15: Pi-only live matrix, small scenario comparison, clean test-agent
  shutdown and limitations report committed `5d063f7`, with write-case update
  in `e21394e`. Full
  four-harness live certification and TUI viewport proof remain NOT_RUN.
  T02 remains
  a partial gate: Pi process-local bridge is live-proven for
  wake, pre-completion input, and draft preservation. T02 remains BLOCKED for
  complete four-owner support; Codex/Claude/OpenCode owners are unverified.
- Decision: use the user-specified standalone repository. The spec's
  `personal-skills` baseline cannot be fetched; no migration from it is assumed.
- Decision: develop against installed versions and mark critical capabilities
  unverified until a dedicated Herdr session proves them. Do not update tools.
- PASS: dedicated Herdr 0.9.2 client/server protocol 22;
  Pi→Pi normal same-owner return, interrupted owner wait plus worker reattach,
  and worker `/new` in the same pane with configuration preserved.
- PASS: live `team inspect` from `w2:p2` bound to `w2:t1`, and live test-run
  adoption froze one mapped member with private `0600` state. The owner-binding
  field added afterward is covered by fixtures, not a second live adoption.
- FAIL: Pi owner blocking `--wait` queued user input until the worker finished.
- PASS: Pi process-local extension returned the owner to idle while the worker
  ran; a user turn completed before release, then a native `sendUserMessage`
  woke the same owner session. Unsent editor text survived a second return.
- NOT RUN: Codex/Claude/OpenCode owner return; Claude lacks credits. An
  initial Codex trust prompt was declined, then the user authorized trust
  for the test folder only. No integration was updated.
- PASS: 55 offline tests for contracts, tab scope, provisioning, native Pi
  reset and state.
  Live `run init` stored an explicit one-worker plan before split; the first
  `team prepare` recorded pane `w3:p2` but found its shell not yet ready.
  The same pane was reused on retry, Pi started there, and roster froze at
  generation 6. Global focus remained at `w2:p1`; no second split occurred.
- PASS: Pi process-local `/herdrnew` changed a native session without changing
  pane, provider, model, effort, trust or tools. Live CLI `conversation reset`
  from Pi owner `w4:p1` reset worker `w4:p2`, generation 0 to 2, and left the
  owner session unchanged. No LLM task wait was used for reset.
- NOT RUN: Codex, Claude Code and OpenCode native reset. Their adapter
  mutations remain disabled; Claude lacks credits.
- PASS: T07 offline cache tests keep session usage separate from account
  balance, invalidate stale/account-shifted samples, and preserve an explicit
  profile. No live account quota was read; all four harness readers return
  unknown. Automatic cost choice stays `needs_info` without comparable data.
- PASS: T08 fixture channel records `dispatching` before a single send,
  rejects duplicate/lost-response resend, verifies result binding and
  deduplicates publication. Production `assignment dispatch` remains
  `capability_blocked` without a same-owner return channel; no live task
  dispatch was claimed.
- PASS: T09 live Pi owner extension dispatched one read-only assignment,
  accepted a separate user turn while the worker gate was closed, then woke
  the same owner session with one event. Owner collection set `received=true`
  and `collected` without redispatch. The first wake prompt omitted exact CLI
  syntax; corrected adapter text was not reloaded live.
- NOT RUN: Codex, Claude Code, OpenCode owner bridges; Pi restart recovery,
  event loss, and burst fault injection. No model polling fallback enabled.
- PASS: T10 offline tests distinguish queued amendment from worker result
  acknowledgment; old revision and missing amendment ID cannot close the
  task. Future instruction is consumed once, pause does not cancel active work.
- NOT RUN: T10 live amendment/cancel/goal; cancel and native goal control are
  blocked by absent certified adapters.
- PASS: T11 offline result template and malicious handoff field rejection;
  unplanned direct route cannot target a member outside the frozen roster.
- NOT RUN: direct route live. A matching grant validates the result but does
  not dispatch a second worker automatically.
- PASS: live Pi same-owner `resume inspect` found one bound
  worker and no pending event, then explicit `resume confirm` advanced the
  generation without worker prompt.
- NOT RUN: lost owner/worker/server recovery live, listener reattach and owned
  resource cleanup.
- PASS: T13 `SKILL.md` is 82 lines and about 670 words,
  under the 180-line/1,500-word budget. Local links, scenario IDs and Codex
  metadata were checked. No four-harness skill loading was live tested.
- PASS: 79 offline tests, including result arriving during a wait, lost
  transport reply after publication, busy owner before send, and result
  collected while worker still working, plus fixed worker contract size guard.
  `evals/scenarios.json` is a manifest,
  not a completed LLM eval; every real eval remains `NOT_RUN`.
- PASS: dedicated Pi test agents exited via `/quit`; scoped snapshot shows
  zero active agents. Test Herdr server remains running with test artifacts.
- PASS: clean Git root/branch/HEAD/snapshot verified before repo dispatch;
  dirty tracked/untracked work blocked. Live Pi→Pi synthetic repository write
  modified only `README.md`, returned a correlated result and was collected
  by the same owner. Four test agents have exited; scoped snapshot shows zero.
- PASS: 84 offline tests after Git publication checks. The worker's reported
  paths must match tracked and non-ignored untracked Git changes and stay
  within `write_scope`; a declared artifact cannot exempt a project file.
  No new live publication was run after this check.
- PARTIAL: Codex 0.155.1 ran one no-tool low-effort test turn in `w7:p1` and
  replied correctly. FAIL: Herdr lifecycle stayed `unknown`, so `--wait`
  timed out despite visible completion. Native `/new` showed a fresh TUI and
  a new session ID on exit, but Herdr retained the earlier ID before exit.
  Codex was exited; dedicated scoped agent list was empty. Codex owner
  return and bound reset remain uncertified. No update was made.
- PASS: after reviewing `references/integration-update-plan.md`, the owner
  authorized only its isolated variant. Herdr installed Pi v9, OpenCode v13
  and Claude v10 under the private test HOME. Read-only status confirms
  those versions there and the older daily versions still in place. No
  isolated-version model test has run; Claude remains blocked by credits.
- PARTIAL: isolated Pi v9 loaded in a dedicated pane and reported native
  identity plus `idle` without screen detection; no model call. Isolated
  OpenCode v13 reached its TUI but has no provider in that empty home;
  Herdr's `idle` came from screen fallback and no native session appeared.
  Both agents exited; scoped agent list is empty. Neither startup certifies
  a result callback or owner return.
- PASS: 85 offline tests. A staged rename from outside to inside the allowed
  path set now exposes both paths to `write_scope` validation.
- PASS: 86 offline tests. A result publication on a different branch or
  rewound HEAD now needs reconciliation, while a forward commit on the
  assigned branch remains eligible for path review.
- PASS: final local audit found a clean branch worktree, no whitespace errors
  versus `origin/main`, no runtime state in tracked files, 86 passing offline
  tests, and a skill of 83 lines / 684 words. No push or publication.
- Remaining: complete critical missing adapters only when their prerequisites
  and live tests are available. Pi active listener reattach, identity-safe
  cleanup, direct route execution and wider fault windows remain unfinished
  code work; four-owner certification and account-backed checks remain
  blocked or unrun as detailed in the coverage matrix.

## Continuation, 2026-09-30

- `6f5706a`: same-process Pi `/herdrreattach` saves a replacement listener
  and calls Herdr `agent wait` without a second worker prompt. An epoch change,
  live old listener, changed owner process, and missing result fail closed.
  **PASS** 90 offline tests and `node --check`; production live reattach
  **NOT_RUN**. Owner process restart and `events_lost` still unsupported.
- OpenCode Go in dedicated `wA:p1`: **PASS** one free-model turn with visible
  `OC_GO_OK`, native session ID and full v13 lifecycle hook authority. `/new`
  in the same pane showed a blank TUI, then a second turn produced a new native
  session ID and `OC_NEW_OK`. Immediate identity update before that turn
  **FAIL**; native reset adapter and owner return remain **BLOCKED**. The
  existing account was used opaquely with only test-local config; no account
  setting was changed. The test agent exited; scoped list reported zero.
- Amendment/result race: result publication now preserves the worker ack and
  an acknowledged delivery state when a result arrives during amendment
  prompt delivery. **PASS** 91 offline tests; live amendment **NOT_RUN**.
- The prior "Remaining" paragraph was the status at commit `ad93672`.
  Pi reattach is now implemented offline but still needs a live gate. Final
  cleanup and publication have not yet run.
- Pi reattach live gate subsequently **PASS**: in `wB:t1`, one worker prompt
  was dispatched, exact listener PID `7010` was terminated while the worker
  remained active, `/herdrreattach` saved listener version 2, and one result
  reached the same owner and was collected at generation 6. No second worker
  prompt. The test agents exited and scoped agent list was empty. Owner
  process transfer and `events_lost` remain **NOT_RUN**. The immediately
  preceding bullet records the status before this gate.
