# Owner return capability gate

Live observations on 2026-09-29 used only the named Herdr session
`herdr-orchestration-v1-test` and the separate folder
`/Users/lorenzoborgato/code/herdr-orchestration-test`. No integration,
global configuration, login, or installed executable was changed. This report
is evidence for adapter design, not a supported four-harness claim.

| Harness / role | Normal same-owner return | User input before worker finish | Interrupted wait preserves worker | Native new conversation, same pane | Status |
| --- | --- | --- | --- | --- | --- |
| Pi 0.87.1 owner, Pi 0.87.1 worker | PASS | FAIL with blocking Bash `--wait` | PASS after owner Escape and explicit `agent wait` reattach | PASS for worker `/new` | Native blocking wait alone is insufficient |
| Codex CLI 0.155.1 owner | NOT RUN | NOT RUN | NOT RUN | NOT RUN | Startup stopped at directory trust prompt; no persistent trust or hook change made |
| Claude Code 2.1.284 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | Account has no credits, per user |
| OpenCode 1.18.33 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | Integration v11 is outdated against installed v13 |

## Pi experiment

The test server and client were both Herdr 0.9.2, protocol 22, compatible.
Owner pane `w2:p1` and worker pane `w2:p2` were in the same test tab. Both Pi
processes used `openai-codex/gpt-6-luna` with low thinking and test-local
session directories. No headless agent was launched.

1. The owner made one `herdr agent prompt test-pi ... --wait` call. The worker
   ran a deterministic file gate (`trial1`). The owner had a pending Bash tool
   call while the gate was closed.
2. A new prompt sent to the working owner was accepted by Herdr and displayed
   in Pi as a queued steering message. After 12 seconds, while the worker gate
   remained closed, the requested steering marker did not exist. It was
   created only after the gate was released and the Bash tool returned. Thus
   the requirement to process user input *before* worker completion failed.
3. The owner received the completed tool result in its original Pi session.
   No manual user message was needed to retrieve that result.
4. On a second gate, sending Pi's documented Escape to the owner aborted its
   tool call. Herdr still reported the worker `working`, and the gate was still
   active. The owner then called `agent wait` for the existing worker once,
   without resending the task. After release, the owner reported `idle`.
5. Pi worker `/new` submitted without `--wait` changed its native session path
   while keeping pane `w2:p2`; Herdr returned to `idle`, and the displayed
   provider/model/thinking remained `openai-codex/gpt-6-luna • low`.

Herdr's [`agent prompt --wait` lifecycle](https://herdr.dev/docs/agent-automation/)
does not correlate an application assignment and does not make a blocking
owner tool interruptible by itself. [Pi's documented steering](https://github.com/earendil-works/pi/blob/v0.87.1/packages/coding-agent/docs/usage.md)
queues an Enter message until the current response and tool calls complete.
The test matched that behavior. A Pi owner bridge must return control to the
normal conversation while a deterministic listener watches the worker, then
deliver completion into that *same* native session. The bridge is a candidate
until user input, draft preservation, duplicate delivery, and owner epoch are
demonstrated live.

No UI notification, detached PID, background `--wait`, or `/goal` is treated
as proof of owner return. Critical dispatch remains disabled until its owner
adapter satisfies the whole gate.
