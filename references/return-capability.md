# Observable return to the same owner

Before dispatch, the owner must have a callback that can wake its **same
native conversation** with a correlated result event. A UI notification,
background process, PID or blocking `agent prompt --wait` is insufficient:
the owner must remain able to process user input while the worker runs.

The certified path uses interactive Pi 0.87.1 with Herdr 0.9.2. Load
`adapters/pi/owner_return.ts` only in the owner process and
`adapters/pi/native_context.ts` in the worker process. Give each pane a
private `HERDR_ORCH_BRIDGE_DIR` outside the repository. The owner invokes
`/herdrdispatch` once; the extension arms a bound, process-local listener,
returns control to Pi, then delivers the result event with Pi's native
`sendUserMessage()` in that owner session. The owner calls `assignment
pending` or `assignment collect` to read the durable event. It judges the
worker result separately from Herdr's terminal status.

In the dedicated Pi→Pi exercise, the owner completed a new user turn before
the worker gate opened. The worker published one JSON result, the listener
woke the same owner session, and the owner collected the matching event
without redispatching. An earlier prototype preserved an unsent Pi editor
draft; the production bridge has not been retested for draft restoration
after a restart.

If that listener is lost but the same owner process and native session
survive, `/herdrreattach` can wait on the existing worker after checking the
run, pane, epoch, generation and absent listener PID. This same-process path
passed a live exercise. An owner process restart, reused pane ID, lost event
or another harness owner has no certified return path here. Stop dispatch
when the return binding cannot be proved; do not poll with model turns or
send the assignment again.
