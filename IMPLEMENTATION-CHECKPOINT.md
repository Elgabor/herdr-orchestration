# Implementation checkpoint

- Spec: HERDR-ORCHESTRATION-SPEC-v1.0, 2026-09-29. Work checkout initial HEAD:
  `81c22c9b09e3bf9e7708dcac068528f85c490454`.
- T01: DONE, commit `67a45f4`. T03: DONE, commit `ecb4332` (13 offline tests).
  T04: implementation and fixture tests complete; commit pending. T02 remains
  a partial gate: Pi process-local bridge is live-proven for
  wake, pre-completion input, and draft preservation. T02 remains BLOCKED for
  complete four-owner support; Codex/Claude/OpenCode owners are unverified.
- Decision: use the user-specified standalone repository. The spec's
  `personal-skills` baseline cannot be fetched; no migration from it is assumed.
- Decision: develop against installed versions and mark critical capabilities
  unverified until a dedicated Herdr session proves them. Do not update tools.
- PASS: 23 offline tests; dedicated Herdr 0.9.2 client/server protocol 22;
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
- Next: commit T04, then evaluate T05 provisioning with offline fixtures;
  integrate the Pi bridge with durable state after T06 contracts.
