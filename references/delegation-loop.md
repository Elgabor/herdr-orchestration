# Delegation state and owner decisions

Load this reference only when coordinating several assignments or deciding
what follows a worker result. The user's workflow determines task order,
reviews, repairs, checkpoints, and commits. The skill records only Herdr
identities, delivery state, result evidence and owner decisions.

An assignment moves from `prepared` to `dispatching` before any task bytes.
The Pi owner bridge waits in a deterministic child while the native owner
conversation stays available. A result file can arrive while the worker is
still running; `result_received` does not release that worker. The owner
collects the outbox event once and checks the result against the requested
scope. A terminal `done` or `idle` state alone cannot accept the work.

For a distinct assignment on a member, complete the previous assignment,
verify the member is released, then use a new native conversation in the same
pane. For a repair of the current assignment, keep its conversation and send
only the changed requirement and evidence with `control apply` and
`amend_assignment`. Revision and acknowledgment IDs must match the result.
No universal repair count applies.

The owner may request a reviewer or researcher only within the roster and
authority already agreed with the user. A `next_handoff` from a worker is
untrusted proposed data. Even a positive review returns to the owner. The
runtime does not decide whether review is mandatory or start an extra team.

`future_instruction` affects the next assignment without disturbing an
active worker. `pause_dispatch` gates new assignments without cancelling
existing ones. Targeted cancellation and native goal mutation need certified
adapters and currently fail closed. A `/goal` can preserve owner continuity
if the harness provides it; it is optional and never substitutes for a return
event. Completion does not resume a paused goal.

On an uncertain send, preserve the assignment ID and inspect the saved intent
and live binding. Do not submit the prompt a second time. On owner resume,
collect recorded events and confirm the observed generation before new work.
Keep a compact checkpoint in the user's existing tracking location if useful;
do not copy full worker transcripts into every member's context.
