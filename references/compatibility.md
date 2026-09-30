# Compatibility and capability boundary

The core currently requires Herdr client and server **0.9.2**, protocol
**22**, with matching live bindings. Run `doctor` and `team inspect` inside
the intended owner pane before a mutating operation. A different version or
unverified integration blocks that operation; installed versions and
integrations may have changed since the tests below.

| Harness | Observed live evidence | Orchestration support in this package |
| --- | --- | --- |
| Pi 0.87.1 | Owner and worker in a dedicated Herdr 0.9.2 session: same-pane worker reset, scoped dispatch and result collection, owner input while the worker ran, same-session wake, and same-process listener reattachment passed. | Supported only with the process-local owner and worker extensions and the checked bindings. Owner process restart, reused pane identity and lost events remain uncertified. |
| Codex CLI 0.155.1 | One read-only turn completed; Herdr lifecycle remained `unknown` and a waited call timed out. | Owner return and native reset are not certified. |
| Claude Code 2.1.284 | No live model test; the test account had no credits. | Owner return and native reset are not certified. |
| OpenCode 1.18.33 | A test-local integration completed a Go model turn and a later new-conversation turn. No assignment callback was tested. | Owner return and native reset binding are not certified. |

The Pi observations used temporary, dedicated panes and an isolated test
folder. They do not certify another version, account, model, session or
installation. Use [owner return](return-capability.md) for the required
callback path and [recovery](recovery.md) for a lost listener. Targeted
cancel, native goal mutation and automatic quota-based model selection are
not certified. The helper preserves an explicitly assigned model and reports
unknown quota data as unknown.
