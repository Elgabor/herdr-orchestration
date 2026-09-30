# User scenarios U01–U10

These examples show routing decisions, not a required development workflow.
Their full acceptance tests are tracked in the task matrix.

| Scenario | Expected owner action | Current evidence |
| --- | --- | --- |
| U01 Existing team | Map only agreed panes in the owner's tab; freeze roster and preserve models. | Offline PASS, Pi adoption live PASS; Codex owner NOT RUN. |
| U02 No worker | With explicit setup plan, split minimally in the same tab and freeze once ready. | Offline PASS, Pi setup live PASS; automatic cost choice BLOCKED by unknown quota. |
| U03 Next task and repair | Reset native thread in the same worker pane for distinct work; amend the same thread for repair. | Pi reset live PASS; repair offline PASS, live NOT RUN. |
| U04 Review | Treat `next_handoff` as data, route only within the authorized roster, return review to owner. | Validation offline PASS; direct route live NOT RUN. |
| U05 Steering during wait | Owner answers before worker gate release, amendment increments revision, result returns once. | Pi owner interaction live PASS; active amendment live NOT RUN. |
| U06 Goal optional | Return works without goal; paused goal stays paused. | No-goal Pi live PASS; native goal cases NOT RUN. |
| U07 Lost reply or pane | Preserve intent, do not resend task or create substitute pane. | Offline PASS for lost send/split; live pane loss NOT RUN. |
| U08 Resume | Reconcile saved results and live bindings, wait for owner confirmation before new dispatch. | Same Pi owner, completed worker live PASS; active lost listener BLOCKED. |
| U09 Invisible panes | Distinguish zoom, focus and geometry; no compensating pane. | Offline PASS; TUI visibility matrix NOT RUN. |
| U10 Uncertain quota | Keep session usage separate from account balance and preserve selected model. | Offline PASS; all live account readers unknown. |

The Pi→Pi live test used the separate
`/Users/lorenzoborgato/code/herdr-orchestration-test` directory and the
`herdr-orchestration-v1-test` named Herdr session. It used
`openai-codex/gpt-6-luna` with low thinking. None of these observations
certify a different owner harness, model, account or production session.
