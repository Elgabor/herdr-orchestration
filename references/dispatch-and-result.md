# Assignment and result boundary

`assignment dispatch` takes one versioned config bound to an existing run,
frozen member, native conversation and context key. Distinct work needs a
verified conversation reset first; a repair keeps the same assignment and
conversation. The packet sent to a worker contains only its scoped
instructions, acceptance criteria, entry points, write scope, output path
and compact result contract. It does not copy the orchestration spec.

Before one task byte is sent, the core checks the owner tab, member occupant,
idle/readiness state, assignment identity, explicit parallelism and writer
conflicts. It requires a return channel to be armed, then persists
`dispatching` with a handle. A lost send response is
`delivery_uncertain`; the same assignment ID cannot be resent. The Pi owner
bridge supplies the tested return path when its process-local command has
armed a private proof. Other owner harnesses remain blocked. `repo snapshot`
reads a clean checkout's canonical root, branch and HEAD without reading file
content. The assignment must carry that exact token; `dispatch` rechecks it
before sending. Existing tracked or untracked changes block the assignment,
and a repository writer must have a safe relative `write_scope`. An external
mutation between the final check and the worker's first action is still a
checkout race, so the owner must review the final diff before acceptance.

For repository assignments, publication compares `files_changed` with Git's
tracked and non-ignored untracked path names since the assigned HEAD. It
rejects omissions, invented or duplicate names, and paths outside
`write_scope`. Only the registered result JSON is excluded if it lives in
the checkout; worker-declared artifacts cannot widen the scope. Git rename
detection is disabled for this comparison so both the removed and added
paths must be in scope. The branch must still match the assigned snapshot,
and the assigned HEAD must be an ancestor of the current HEAD. Forward
commits remain possible; a branch switch or history rewind requires
reconciliation. This checks
paths, not file content, ignored files, concurrent writes after inspection,
or the quality of the change. Owner diff review is still required.

`assignment publish` is available to the assigned worker pane after a
dispatch exists. It reads at most 12 KiB from a safe relative path beneath
the registered output root, rejects symlinks and validates run, assignment,
member, revision, attempt, conversation and repository identity. It records
the result status and one stable outbox event. Repeating an identical result
is idempotent; a different result for the same assignment is rejected.
`result_ready` means a validated result is recorded. It is not project
acceptance and does not release a worker still running. The owner can list
pending events and collect one event idempotently with `assignment pending`
and `assignment collect`; a stale revision cannot close an amended task. A `blocked` result
remains blocked even if Herdr later reports the agent idle.

`control apply` takes a versioned config and expected run generation. A
`future_instruction` stays in the run until the next assignment packet and
does not prompt a busy worker. `pause_dispatch` only gates new assignments.
`amend_assignment` increments the current revision before one same-pane
prompt; a successful Herdr call is recorded as `queued`, not proof of worker
acceptance. The worker result must carry the new revision and exact
`acknowledged_amendments` IDs. The owner still judges whether the requested
change was effective from the result content. Targeted cancel and native
goal mutation are blocked until their process identity and callback paths
are certified. No goal is created to keep the return path alive.

The old `herdr_agent_turn.py --agent ... --prompt ...` interface cannot bind
these identities or guarantee a return. It now reports the migration
arguments without issuing a Herdr call. Its new subcommands forward to the
scoped CLI.
