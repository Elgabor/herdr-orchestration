# Compact handoff contract

Load this reference before constructing a worker prompt. A handoff is evidence
for the owner, not a transcript and not an acceptance decision.

## Required fields

Ask the worker to write a short Markdown file with this shape:

```markdown
status: done | blocked | needs_info
task: <ticket or bounded task identifier>
base_head: <commit inspected before work, if applicable>
result: <one-paragraph factual summary>
files_changed:
  - <path or none>
verification:
  - command: <exact command>
    result: PASS | FAIL | NOT RUN
risks:
  - <remaining risk or none>
next_decision: <what the owner must decide>
```

Keep the handoff under 12 KB. Put verbose logs, screenshots, generated reports,
or full reviews in separate files and link their paths. Never paste secrets,
environment values, credentials, or unrelated source into the handoff.

## Prompt tail

The bundled helper appends the following intent to the supplied task:

```text
Before finishing, write the compact handoff to the exact supplied path. Include
status, task, base_head, result, files_changed, verification, risks, and
next_decision. Keep detailed evidence in separate files. Your final terminal
message should contain only the handoff path.
```

## Owner validation

The owner verifies:

1. the handoff belongs to the dispatched task and expected base;
2. listed files match the actual diff;
3. verification commands and results are credible and reproducible;
4. risks and unmet criteria are explicit;
5. acceptance, repair, research, or blocking follows from repository evidence.

If the handoff is absent or oversized, inspect the saved terminal excerpt once.
Ask for a corrected handoff only if the worker actually finished and another
prompt is within the repair budget.
