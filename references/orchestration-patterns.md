# Herdr pane and conversation patterns

Use this reference when mapping a tab or preparing a team. Confirm local
syntax with installed `herdr --help`; the package is certified only against
the version listed in [compatibility](compatibility.md).

From inside the owner pane, `team inspect` verifies `HERDR_ENV`, compatible
client/server protocol, current pane and terminal ID, then filters the server
snapshot to the caller's tab. It emits only compact candidate metadata, not
their transcripts. Human labels may have spaces; Herdr agent aliases have a
different grammar. Map explicit pane IDs and preserve existing names.

`run init --config <absolute-json> --state-dir <private-directory>` adopts the
agreed members or stores an authorized bootstrap plan. `team prepare` only
acts on that plan in the same tab. It records split intent and created pane
IDs so a lost response cannot justify another split. It preserves focus and
freezes the roster after the planned members are ready. A busy worker does
not trigger new pane creation.

An assignment is bound to session, workspace, tab, pane, terminal, occupant
revision, native conversation and context key. Herdr's `agent_status=done`
means the harness turn ended; it says nothing about result validity or whether
the user can see the pane. Zoom, another tab, a small layout and another
client's focus are distinct states. The helper does not create compensating
panes to make an agent visible.

For a distinct assignment, use [native conversation](native-conversation.md).
For a return to the same owner, use [return capability](return-capability.md).
For uncertainty after dispatch, use [recovery](recovery.md). The old
`herdr_agent_turn.py --agent ... --prompt-file ...` command is intentionally
disabled: it cannot bind a run, conversation or return channel. Its scoped
subcommands forward to `herdr_orchestrate.py` for migration.
