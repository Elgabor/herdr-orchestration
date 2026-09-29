# Delegation loop

Load this reference for multi-ticket work, optional research, repairs, or a
durable `/goal` run.

## Modes

- **Single turn:** one bounded implementation, review, test, or research task.
- **Ticket loop:** sequential tickets with owner acceptance between tickets.
- **Research gate:** one read-only question whose answer unblocks a decision.
- **Review gate:** independent read-only inspection before owner acceptance.

These modes compose. The selected harnesses and models are run parameters, not
properties of the skill.

## State machine

```text
READY -> DISPATCH -> WAIT -> REVIEW
                           |-> ACCEPT -> CHECKPOINT -> READY
                           |-> REPAIR -> DISPATCH
                           |-> RESEARCH -> WAIT -> REVIEW
                           `-> BLOCK
```

The owner is the only role that changes state after `REVIEW`. A worker may
report `done`, `blocked`, or `needs_info`, but cannot accept its own work.

## Cost and context invariants

- One atomic Herdr submission and wait per worker turn.
- Zero model-driven polling while a worker is `working`.
- No routine progress prompts or repeated instructions.
- One post-wait read, stored outside model context; load only the compact handoff.
- Pass the current ticket and current repository state, not the full owner chat.
- Keep repairs on the same worker session; send the failed criterion and new
  evidence rather than the original specification again.
- Add a researcher only when the owner can state the unresolved question and
  the decision its answer will change.
- Use the weakest adequate worker chosen by the user; model substitution remains
  a user decision.

## Owner decisions

`ACCEPT` requires relevant diff inspection, project-native verification, and no
unresolved acceptance criterion. The owner may then perform an authorized commit
and mark the ticket complete.

`REPAIR` names the exact failed criterion, evidence, allowed scope, and remaining
repair budget. Default budget: one repair.

`RESEARCH` contains one question, allowed sources, expected evidence, and a
read-only boundary. Return the answer to the owner, not the entire transcript.

`BLOCK` records the missing approval, failed invariant, conflict, unavailable
model, exhausted budget, or external dependency. Do not continue to another
ticket when it would hide the block.

## Checkpoint

After each accepted ticket, retain only:

```text
objective
ticket queue and current ticket
accepted ticket -> commit mapping
current HEAD
verification state
open decisions or blockers
```

Prefer an existing ticket tracker or a temporary state file. Do not treat the
conversation transcript as the queue.

## `/goal`

Use `/goal` only when the objective may exceed one owner turn and has a clear
stopping condition. The goal preserves continuity; Herdr events drive the loop.
The goal must not request status polling, periodic progress messages, or repeated
pane reads. At a continuation boundary, resume from the checkpoint above.
