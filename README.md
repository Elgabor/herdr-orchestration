# Herdr Orchestration

A skill that helps your coding agent work with other agents in
[Herdr](https://herdr.dev/), where they run in separate terminal panes.

You talk to your main agent. It gives another agent a task, collects the
result, and brings it back to your conversation.

## Why use it?

Coordinating several agents usually means passing instructions between them
and keeping track of their work. This skill gives your main agent a consistent
way to handle that coordination.

- **Less manual coordination:** your agent handles assignments and results.
- **Clear tasks:** each worker gets the context it needs and limits on its work.
- **Results you can review:** the main agent checks what came back before
  deciding the next step.

You choose the task, the agents involved and their models.

## Install

Paste this prompt into your coding agent, whether you use Codex, Claude Code,
Pi or OpenCode:

```text
Install herdr-orchestration for the harness we are using.

Find the appropriate skills folder, alongside my existing skills or in this
project, and clone the repository there:
git clone https://github.com/Elgabor/herdr-orchestration.git

Preserve existing installations. Read SKILL.md and references/installation.md,
verify that this harness can load the skill, and tell me how to use it.
```

The agent handles the installation details for your harness. Keep the whole
skill folder so it has the instructions, scripts and references it needs.

## Use

To coordinate work, you need Herdr and your coding agents set up. Then ask
your main agent for the task you want to delegate. For example:

> Use herdr-orchestration to have the existing worker investigate the failing
> test and report the likely cause, without changing project files.

The agent follows the skill's instructions and checks that your setup supports
the task. You review the result and decide what happens next.

The complete workflow has currently been verified with Pi running both agents.
Other harnesses can load the skill, but returning results to their main
conversation is still unverified. See the [support details](references/compatibility.md).

## Instructions for the agent

Read [SKILL.md](SKILL.md) for the operating procedure and the
[installation guide](references/installation.md) for harness-specific setup.
Follow their capability checks before sending work to another agent.

## License

[MIT](LICENSE). Copyright © 2026 Lorenzo Borgato.
