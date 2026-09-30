# Controlled team preparation

Run `team inspect` from the owner agent's actual Herdr pane. If it lists a
team, use `run init` with `mode: adopt_existing` and exact agreed pane IDs.
The roster freezes at initialization. A busy worker does not justify another
team or pane.

For a tab without a team, the owner can initialize a reviewed
`bootstrap.example.json` with explicit authorization, member IDs, cwd, source
pane, split direction and ratio, and native harness arguments. The plan is
stored before any split. Replace the example path and pane ID with observed
values. Run `team prepare` with the returned run ID, generation 0 and owner
epoch 1. Only the planned number of panes can be made; this release splits
only the owner pane and refuses zoomed or cramped layouts. It does not apply
a layout, move to another tab or change focus.

The setup journal records `planned`, `split_pending`, `pane_created`,
`launch_pending`, and `active` per member. The pane ID comes from Herdr's
response or unique post-split reconciliation. If the response is ambiguous,
preparation stops and never repeats the split. If agent startup fails, the
created pane is retained; retry `team prepare` with the current generation
after checking the cause. Do not create a replacement pane. The roster freezes
after all planned agents are verified with the expected terminal and native
session identity. `client_visibility` stays `unknown` until a client-specific
visibility check exists.

Local state is private under `$XDG_STATE_HOME/herdr-orchestration` or the
explicit `--state-dir`; keep it outside the repository and do not copy it into
worker prompts. `created_resources` distinguishes panes created by this run
from preexisting shells. No cleanup is automatic.

The dedicated Pi live test confirmed that a temporary shell-readiness
failure retained its pane and journal; retry started Pi in that same pane
without another split. Other harness startup and client visibility remain
uncertified.
