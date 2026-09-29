# Implementation checkpoint

- Spec: HERDR-ORCHESTRATION-SPEC-v1.0, 2026-09-29. Work checkout initial HEAD:
  `81c22c9b09e3bf9e7708dcac068528f85c490454`.
- T01: DONE, commit `67a45f4`. Current: T03 offline contracts. T02 live gate:
  BLOCKED pending dedicated owner/worker test setup and authorization.
- Decision: use the user-specified standalone repository. The spec's
  `personal-skills` baseline cannot be fetched; no migration from it is assumed.
- Decision: develop against installed versions and mark critical capabilities
  unverified until a dedicated Herdr session proves them. Do not update tools.
- PASS: baseline and 13 offline contract/state tests. Read-only Herdr reports
  server not running, client schema v1, Codex integration current, Pi/Claude/
  OpenCode integrations outdated. No runtime mutation or installation.
- NOT RUN: T02 same-thread return and reset tests; live server compatibility.
- Next: finish T03 and commit; continue T04 independent fixture-based work.
