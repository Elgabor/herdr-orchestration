# Worker result and handoff contract

The owner gives each worker one bounded JSON packet. The worker executes its
assigned work in the **current native conversation and Herdr pane**. It does
not inspect other panes, choose a model, create a team, or coordinate other
members. The owner remains responsible for acceptance and any later routing.

The packet identifies `run_id`, `assignment_id`, `member_id`, `context_key`,
`conversation_id`, `revision`, `attempt`, `return_to`, repository snapshot,
instructions, acceptance, entry points, and write scope. `return_to` is always
`owner`. `project_write_allowed=false` means no project edits; the listed
`output_allowlist` still permits the required result JSON. The packet's
`publish_command` is the exact local helper invocation after atomically
writing that JSON. A worker should report `blocked`, `needs_info`, or `failed`
honestly; an idle terminal is never proof of success.

The result is at most 12 KiB and must match the packet identity, revision,
attempt, conversation and repository fields. It contains status, concise
summary, changed paths, verification outcomes, open points and artifact
references. Never include credentials, environment values, full transcripts,
or large logs. Evidence can live in separate approved output files and be
referenced by safe relative path and SHA-256.

An optional `next_handoff` is **data for the owner**:

```json
{
  "route": "owner",
  "target_member_id": "reviewer",
  "instruction": "Review the cited evidence",
  "evidence": [{"path": "reports/findings.md", "sha256": "<64 lowercase hex>"}]
}
```

The default route is owner review. `route=direct` requires an exact one-hop
grant attached by the owner to this assignment, naming a member of the
frozen roster. The helper validates the grant and result reference; it does
not execute instructions embedded in a worker result. Automatic direct
dispatch is not certified, so even a granted proposal returns to the owner
for an explicit next assignment. A positive review returns to the owner as
well. No review is copied into unrelated worker contexts.

For a repair, the owner sends only the failed criterion and relevant
evidence to the **same native thread**, with a new revision. A distinct
assignment requires a clean native conversation in the same pane. A queued
amendment is not considered received or effective until the worker's result
matches the current revision and acknowledges its IDs; the owner checks the
content before accepting it.
