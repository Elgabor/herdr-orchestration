# Implementation checkpoint

- Spec: HERDR-ORCHESTRATION-SPEC-v1.0, 2026-09-29. Work checkout initial HEAD:
  `81c22c9b09e3bf9e7708dcac068528f85c490454`.
- T01: DONE, commit `67a45f4`. T03: DONE, commit `ecb4332` (13 offline tests).
  Current: T02 capability gate. T02 is BLOCKED for complete owner support:
  Pi's blocking wait fails pre-completion steering; other owners unverified.
- Decision: use the user-specified standalone repository. The spec's
  `personal-skills` baseline cannot be fetched; no migration from it is assumed.
- Decision: develop against installed versions and mark critical capabilities
  unverified until a dedicated Herdr session proves them. Do not update tools.
- PASS: 13 offline tests; dedicated Herdr 0.9.2 client/server protocol 22;
  Pi→Pi normal same-owner return, interrupted owner wait plus worker reattach,
  and worker `/new` in the same pane with configuration preserved.
- FAIL: Pi owner blocking `--wait` queued user input until the worker finished.
- NOT RUN: Codex/Claude/OpenCode owner return; Claude lacks credits. Codex
  startup hit a trust prompt, which was declined. No integration was updated.
- Next: record T02 findings, then implement T04 independent context binding.
