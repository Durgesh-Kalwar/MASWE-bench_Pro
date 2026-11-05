# multiagent_pro_out_p2p_seal — sealed P2P sweep, 2026-11-04

The 34-instance `multiagent_pro_bench34_noreq` grid, P2P communication, run with the **sealed**
harness (`ScopedDockerEnvironment` with `scope_seal: true`): every peer-owned or fixed file is
removed from each agent's worktree before the first step (`.py` files leave a sourceless `.pyc`
so imports keep working), hidden from `git diff/status` with `skip-worktree`, and the git-history
routes that could recover them are refused. See `multiagent_pro/multiagent_aci.md`, section
"Scope enforcement under raw bash", and `multiagent_pro_out_p2p_sweep34/analysis/privacy/REPORT.md`
section 7 for why. Everything else is identical to the October guard-only sweep in
`multiagent_pro_out_p2p_sweep34/`: mini-swe-agent, Opus 5.5 through the ASU CreateAI gateway,
10 rounds x 6 steps, $3/agent pooled, byte-identical system prompt.

| | |
|---|---|
| resolved | **32 / 34** (`eval_out/eval_results.json`) |
| spend | $199 (sum of `instance_*/cost_stats.json` `spent`) |
| seal | 930 files sealed, 0 compile failures, 138 absent (files the gold patch creates) — `scope_seal_summary.json` |
| October guard-only P2P, same 33 shared instances | 29 / 33 → 31 / 33 sealed. Gained ansible-42355d18, openlibrary-4b7ea297, -630221ab, -7bf32385; lost ansible-e40889e7, qutebrowser-1943fa07. qutebrowser-f77535 is new to this grid. |

Launched with `multiagent_pro/launchers/run_mini_seal_sharded.sh p2p 5` (5 concurrent shards,
instance i -> shard i mod 5, one gateway key per shard); shard 2 ran out of monthly budget and
was resumed with `resume_seal_shard.sh p2p 2 4`; `finish_seal.sh p2p` merged, graded on local
Docker, ran the safety audit and coordination metrics, and copied the run here.

Layout, same as the other `multiagent_pro_out_*` folders:

- `instance_*/` — `spec.json`, `roster.json`, `comm_mode.json`, `board.json` + `board_after_round_N.json`,
  `comm_stats.json`, `cost_stats.json`, `fixed.patch`, `agent_<k>.patch`, `_comm_bundle/`;
  per agent `agent_<k>/`: `SCOPE.txt`, `local_issue.md`, `mini.yaml`, `traj/` (mini-swe-agent
  trajectories), `context/` (`messages.jsonl` full context dumps), `scope_violations.jsonl`,
  **`scope_seal.json`** (what was sealed / absent in that agent's container).
- `patches.json` — merged per-instance patches as graded.
- `eval_out/` — Pro evaluator output per instance (`eval_results.json`, per-instance test logs).
- `scope_seal_summary.json` — the per-agent seal reports aggregated.
- `harness51/` — run sidecar: `progress.txt`, shard / resume / finish logs, `analysis_safety/`
  (`metrics/safety_audit.py`) and `analysis_coordination/` (`metrics/coordination_metrics.py`).

Known quirk visible in the trajectories: because peer `.py` files are replaced by sourceless
`.pyc` files, agents sometimes spend a few messages per round on "stray `.pyc`" confusion or
add `try/except ImportError` fallbacks. The prompt was deliberately not changed to explain the
stale view, so the comparison with October stays prompt-identical; tag this in redundancy
analyses rather than counting it as agent error.
