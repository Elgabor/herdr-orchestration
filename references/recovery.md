# Same-owner recovery boundary

`resume inspect` runs only from the recorded owner pane and native
conversation. It verifies the Herdr session, tab and occupant, then compares
each frozen member to the current snapshot. It reports unresolved assignments
and pending outbox events without reading worker transcripts or sending
another task. Its summary is short and sets `awaiting_user_resume=true`.
During that state, new dispatch is blocked.

Collect any pending event through `assignment collect`. Then `resume
confirm` requires the observed run generation, owner epoch, no pending event,
unchanged member bindings and no active assignment needing a listener. It
clears the gate without prompting any worker. A concurrent result causes a
generation mismatch and requires another inspect. A pause remains in effect.

An owner process or native session that has changed cannot silently claim the
old run. A worker that is still active after a lost listener cannot be
redispatched or considered finished. For the **same live Pi owner process and
native session**, `/herdrreattach RUN_ID ASSIGNMENT_ID STATE_DIR GENERATION
EPOCH` arms a replacement listener and calls Herdr `agent wait` on the
existing worker without sending a prompt. `STATE_DIR` must be URL encoded
as with `/herdrdispatch`. The old listener PID must be absent and the owner,
member, pane, scope, and epoch bindings must still match. The replacement
handle is saved before waiting. A result arriving during the wait remains in
the outbox; a missing result produces a protocol error. This path passed
offline fault tests and a live same-process Pi exercise. Owner transfer,
`events_lost` reconciliation, and support-process cleanup are not certified;
these states return a blocking diagnosis. The helper never kills the Herdr
server or removes an adopted pane. A stale pane ID after a server restart is
not an identity match.

The dedicated Pi→Pi test recovered an already collected assignment with one
bound worker and no pending event; confirmation sent no worker prompt.
Owner-lost, worker-lost and server restart cases remain unverified live.
