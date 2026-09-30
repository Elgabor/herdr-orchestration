# Usage evidence and configuration choice

`quota read --catalog <file> --profile-id <id>` returns a versioned sample
with separate session usage, rate limit, plan quota, API balance, and input
and output prices. Each metric carries state, value, unit, scope, observation
time and source. Unknown values are `null`; they do not mean zero, free or
unlimited. Available models have their own known/unknown state. The example
catalog is intentionally unauthorized until the owner fills and approves it.

The installed Codex, Claude Code, Pi and OpenCode CLIs do not provide a
certified, non-invasive account quota reader in this package. Consequently
the current live reader returns `unknown` for these account metrics. It does
not inspect credentials, session stores, browser cookies, keychains or a
busy worker's UI. Pi and OpenCode local token statistics are not treated as
account balance. Claude lacks credits for live characterization. The private
cache has a 300-second default TTL keyed by harness, version, provider,
non-sensitive account reference, auth mode, model and effort. Expired samples
return `stale` with null values until a certified reader refreshes them;
account changes miss the old cache. Fixture data is not a live quota source.

`quota check --mode explicit|existing|auto_authorized` evaluates the selected
profile and preserves its identity. A configured model is never silently
replaced. An explicit or existing profile can be reported eligible with
uncertainty if it is authorized and limits are unknown; the owner must still
respect the user's budget. Automatic cost selection returns `needs_info`
until comparable quota and price evidence exists. Model suitability remains
the owner's decision. The package does not rank model quality or activate
extra usage, purchases or limit changes.
