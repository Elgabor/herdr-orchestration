# Implementation checkpoint

- Spec: HERDR-ORCHESTRATION-SPEC-v1.0, 2026-09-29. Work checkout initial HEAD:
  `81c22c9b09e3bf9e7708dcac068528f85c490454`.
- T01: DONE, commit `67a45f4`. T03: DONE, commit `ecb4332` (13 offline tests).
  T04: DONE, commit `4e2aca9`. T05: DONE, commit `c45afe9`.
  T06: Pi adapter committed `def8820`; other harnesses remain uncertified.
  T07: conservative quota reader/catalog committed `d1dbaee`.
  T08: dispatch/result core and tests committed `f1e4013`; repository writes
  await a certified checkout snapshot gate.
  T09: Pi owner bridge, correlated outbox/ack, and live Pi→Pi return committed
  `c21c992`. Other owners and crash recovery remain uncertified.
  T10: versioned future instruction, dispatch pause and same-thread amendment
  with queued/ack distinction committed `eed1359`. Targeted
  cancel and native goal mutation remain capability-blocked.
  T11: compact worker contract, read-only output allowlist, and bounded
  `next_handoff` data/grant validation committed `595d1de`.
  Automatic direct route is not certified and remains owner-mediated.
  T12: same-owner resume inspect/confirm and dispatch gate implemented;
  commit pending. Lost-listener reattach, owner transfer, and cleanup remain
  capability-blocked.
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
- NOT RUN: Codex/Claude/OpenCode owner return; Claude lacks credits. Codex
  startup hit a trust prompt, which was declined. No integration was updated.
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
- PASS: 65 offline tests. Live Pi same-owner `resume inspect` found one bound
  worker and no pending event, then explicit `resume confirm` advanced the
  generation without worker prompt.
- NOT RUN: lost owner/worker/server recovery live, listener reattach and owned
  resource cleanup.
- Next: commit T12 bounded recovery, then T13 skill rewrite and T14 regression
  coverage. Remaining capability gaps must stay explicit in final delivery.
