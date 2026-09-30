# Verification coverage, 2026-09-30

`PASS` below means the stated part was actually exercised; it does not make
the whole four-harness scenario supported. `PARTIAL` means a required branch
of that test remains open. `NOT_RUN` is not green. Offline module keys:
`C` context, `P` provision, `N` native reset, `A` assignment, `U` control and
resume, `K` contracts, `S` state, `Q` quota, `R` return channel, `PK` skill
package. They live under `tests/test_<name>.py`. Live Pi evidence is in
`references/return-capability.md`, `references/native-conversation.md` and
`references/recovery.md`. No real LLM behavioral eval from
`evals/scenarios.json` has been run.

| ID | Offline | Live | Eval / remaining requirement |
| --- | --- | --- | --- |
| X01 | PASS C | NOT_RUN | No external session control. |
| X02 | PASS C | PARTIAL version match only | Drifted server live NOT_RUN. |
| X03 | PASS C | PASS Pi adoption with other focus | Other owner harnesses NOT_RUN. |
| X04 | PASS C explicit pane mapping | NOT_RUN | E NOT_RUN. |
| X05 | PASS K/C | NOT_RUN | Human label preserved. |
| X06 | PASS C | PASS Pi scoped tab | Other harnesses NOT_RUN. |
| X07 | PARTIAL Q/C | NOT_RUN | E NOT_RUN; unavailable-model setup case absent. |
| X08 | PARTIAL P | NOT_RUN | Editor/server foreground case absent. |
| X09 | PASS C/U changed terminal | NOT_RUN | Owner/worker move live absent. |
| X10 | PASS P | PASS Pi setup | Other harnesses NOT_RUN. |
| X11 | PASS S/A roster freeze | NOT_RUN | E NOT_RUN. |
| X12 | PASS P zoom | NOT_RUN | TUI case absent. |
| X13 | PASS P geometry | NOT_RUN | TUI case absent. |
| X14 | PASS P lost split response | NOT_RUN | No second split. |
| X15 | PASS P failed start | PASS Pi retry same pane | Other harnesses NOT_RUN. |
| X16 | PASS N | PASS Pi `/new`; PARTIAL OpenCode Go `/new` | OpenCode new ID appeared after first new turn, not immediately. Codex/Claude reset binding NOT_RUN. |
| X17 | PASS N | PASS Pi reset without task wait | Other harnesses NOT_RUN. |
| X18 | PARTIAL N changed session check | NOT_RUN | E NOT_RUN for clear/compact/fork. |
| X19 | PASS U same-thread revision | NOT_RUN | E NOT_RUN; live repair absent. |
| X20 | PASS N busy guard | NOT_RUN | E NOT_RUN. |
| X21 | PASS K truncated result | NOT_RUN | Missing-result lifecycle tested A. |
| X22 | PASS K/A binding | NOT_RUN | Other attempt rejected. |
| X23 | PASS A blocked status | NOT_RUN | Done terminal cannot imply success. |
| X24 | PASS U old revision | NOT_RUN | Old result cannot close amendment. |
| X25 | PASS K/S nofollow and size | NOT_RUN | No unsafe file execution. |
| X26 | PASS A busy owner/worker | NOT_RUN | No prompt sent in fixture. |
| X27 | PASS A lost send reply | NOT_RUN | No automatic task retry. |
| X28 | PASS A working worker after result | NOT_RUN | Member not released. |
| X29 | PASS A/R correlated return | PASS Pi→Pi | Other owner harnesses NOT_RUN. |
| X30 | PARTIAL U revision logic | PASS Pi user turn before release | Live amendment absent. |
| X31 | PASS A same-owner reattach and epoch fault | PASS Pi production `/herdrreattach` after listener termination | Other owner harnesses BLOCKED; owner process restart NOT_RUN. |
| X32 | NOT_RUN | PASS Pi prototype unsent draft | Production bridge draft NOT_RUN. |
| X33 | PASS R arm proof | PASS Pi same-session wake | Other owner bridges BLOCKED. |
| X34 | PARTIAL S/A dedup and race | NOT_RUN | Full crash-window scheduler absent. |
| X35 | PASS A missing result | NOT_RUN | Live lifecycle error absent. |
| X36 | PASS Q metric separation | NOT_RUN | E NOT_RUN. |
| X37 | PASS Q TTL/account shift | NOT_RUN | Live account reader unavailable. |
| X38 | PASS Q passive reader | NOT_RUN | Busy-worker live test absent. |
| X39 | PASS Q fixed profile | NOT_RUN | E NOT_RUN. |
| X40 | PARTIAL Q refuses invented ranking | NOT_RUN | E NOT_RUN; comparable-data choice absent. |
| X41 | PASS U no goal dependency | PASS Pi without goal | Other harnesses NOT_RUN. |
| X42 | NOT_RUN | NOT_RUN | Native goal pause adapter absent. |
| X43 | PASS K/A parallel and single-writer guard | PARTIAL Pi one clean repo writer | E NOT_RUN. |
| X44 | PARTIAL U future instruction | NOT_RUN | Cancel BLOCKED; no live control. |
| X45 | PARTIAL K/A grant validation | NOT_RUN | Direct route BLOCKED; E NOT_RUN. |
| X46 | PASS U saved result recovery | PASS Pi same owner | Reopened owner with active worker BLOCKED. |
| X47 | PASS S claims/epoch | NOT_RUN | No two live owners. |
| X48 | NOT_RUN | NOT_RUN | `events_lost` re-subscription absent. |
| X49 | NOT_RUN | NOT_RUN | Identity-safe cleanup absent. |
| X50 | PARTIAL K rejects handoff command | NOT_RUN | E NOT_RUN; quota redaction fault absent. |
| X51 | PASS C/P scope/focus | PARTIAL Pi focus preserved | Concurrent client layout change NOT_RUN. |
| X52 | PASS A/R one send/no transcript loop | PASS Pi quiet wait | E NOT_RUN; other owners blocked. |
| X53 | PASS C version gate | PARTIAL live match; Codex lifecycle `unknown`; OpenCode v13 full hook on two turns | Hook/schema drift recovery NOT_RUN. |
| X54 | PASS A output allowlist and Git path/branch checks | PASS Pi read-only result and synthetic repo write | Git publication hardening is offline only; other workers NOT_RUN. |
| X55 | PASS N Pi config check | PASS Pi reset preserves config | Other worker harnesses BLOCKED. |
| X56 | PASS PK links/metadata | NOT_RUN | Four-harness skill load absent. |

## Requirements R01–R18

| Requirement | Status | Main remaining evidence |
| --- | --- | --- |
| R01 | PARTIAL | Skill rewritten; four-harness behavior eval absent. |
| R02 | PARTIAL | Pi scoped adoption tested; Codex/Claude/OpenCode owner cases absent. |
| R03 | PARTIAL | Pi planned setup passed; automatic cost choice blocked by unknown quota. |
| R04 | PARTIAL | No hidden agent in code or tests; full live harness matrix absent. |
| R05 | PARTIAL | Pi reset passed; OpenCode `/new` visible but Herdr identity lagged until first new turn; other adapters absent. |
| R06 | PARTIAL | Bounded packet/result and 1,500-byte fixed contract guard tested; other harness contexts unverified. |
| R07 | PARTIAL | Pi event return and same-process listener reattach passed live; other owners blocked. |
| R08 | PARTIAL | Pi owner user turn before worker finish passed; amendment live absent. |
| R09 | PARTIAL | No-goal Pi passed; paused native goal case absent. |
| R10 | PARTIAL | Offline parallel guard passed; broad behavioral eval absent. |
| R11 | PARTIAL | Fixed profile preserved; verified automatic cost comparison unavailable. |
| R12 | PASS offline | All live account readers return unknown; no balance claim. |
| R13 | PARTIAL | Process-local Pi bridge passed; other harness adapters absent. |
| R14 | PARTIAL | Same-owner completed run resumed; active listener/owner transfer blocked. |
| R15 | PARTIAL | Correlated Pi result passed; full error/revision live matrix absent. |
| R16 | PARTIAL | State/result private offline and final diff audit clean; cross-harness runtime context not certified. |
| R17 | PARTIAL | Baseline recorded; only Pi path live certified. |
| R18 | PARTIAL | No blind retry; cleanup and full crash windows absent. |
