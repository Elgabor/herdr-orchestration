# Owner return capability gate

Live observations on 2026-09-29 used only the named Herdr session
`herdr-orchestration-v1-test` and the separate folder
`/Users/lorenzoborgato/code/herdr-orchestration-test`. No integration,
global configuration, login, or installed executable was changed. This report
is evidence for adapter design, not a supported four-harness claim.

| Harness / role | Normal same-owner return | User input before worker finish | Interrupted wait preserves worker | Native new conversation, same pane | Status |
| --- | --- | --- | --- | --- | --- |
| Pi 0.87.1 owner, Pi 0.87.1 worker | PASS with a process-local Pi extension | PASS with the extension; FAIL with blocking Bash `--wait` | PASS after owner Escape and explicit `agent wait` reattach | PASS for worker `/new` | Return bridge proven in test; production state/recovery pending |
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
deliver completion into that *same* native session.

## Pi process-local bridge prototype

A temporary `--extension` file in the separate test folder registered one Pi
command. It spawned one asynchronous Herdr `agent prompt --wait` child and
returned the Pi command immediately. On child completion, it called Pi's
native `sendUserMessage()` in the existing process. It performed no model call
itself. The extension was loaded by path for this test; it was not installed
globally or included as a second production runtime.

With worker gate `trial3` still closed, the owner completed a fresh user turn
and created `trial3.steered`. Only afterward was the worker released. The
extension then delivered a completion message to the **same** Pi session
(`01a0ee9e-52b7-7659-ad97-e505c3822699`), which started and finished a new
model turn without a manual user message. With `trial4`, the owner had the
unsent editor text `DRAFT-TRIAL4-KEEP`; the same completion path ran and the
draft remained in the editor afterward. These observations demonstrate
same-session wake, pre-completion user input, and draft preservation for Pi
0.87.1 in the tested configuration. The prototype only has in-process duplicate
suppression; durable outbox, epoch fencing, crash recovery, and assignment
identity belong in the production adapter and remain unverified live.

The [Pi 0.87.1 extension API](https://raw.githubusercontent.com/earendil-works/pi/v0.87.1/packages/coding-agent/src/core/extensions/types.ts)
defines `sendUserMessage()` as triggering a turn. The test checked this
behavior in the interactive pane while the delegated worker was active.

No UI notification, detached PID, background `--wait`, or `/goal` is treated
as proof of owner return. Critical dispatch remains disabled until its owner
adapter satisfies the whole gate.

## Production Pi bridge exercise, 2026-09-30

In the same dedicated named session, a new `w5` workspace held Pi owner
`w5:p1` and Pi worker `w5:p2`, both on `openai-codex/gpt-6-luna` with low
thinking and separate test-local session directories. The owner loaded
`adapters/pi/owner_return.ts` by `--extension`; the worker loaded the native
context extension by path. An adopted run was frozen in that tab, and the
worker's `/new` established the assignment context key.

The owner issued `/herdrdispatch` once. The private arm proof matched the
owner session, pane, epoch, generation, and process PID. State reached
`dispatching` and the worker began a deterministic file gate. While that gate
remained closed and Herdr still reported the worker `working`, a separate user
prompt to the owner completed and wrote `return-task-1.steered`. After the
gate was released, the worker published one correlated JSON result. The Pi
extension delivered a native user message to the **same owner session** with
the event ID; that turn completed without a manual wake. The owner then ran
`assignment collect` and the run reached `collected`, with its outbox entry
`received=true` and `worker_released=true`. No assignment was redispatched.

The first wake message asked the owner to inspect and collect but omitted CLI
syntax. The owner guessed nonexistent `run inspect` and `events collect`
commands. The extension was corrected to include the exact `assignment
collect` or `assignment pending` command. The corrected wording has offline
review but was not reloaded into the live Pi process in this exercise.

This certifies the tested Pi→Pi normal return, pre-completion user turn,
same-session wake, and correlated collection path. It does **not** certify
Pi crash recovery, `events_lost`, other owner harnesses, or a restored draft
after a bridge restart. Those remain blocked or not run, without a polling
fallback.
