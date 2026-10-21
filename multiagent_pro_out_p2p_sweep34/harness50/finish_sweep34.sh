#!/usr/bin/env bash
# Unattended finish line for the P2P sweep34 run (2026-10-20). NO push: it waits for the resume
# launcher's DONE line, merges + grades every finished instance, runs the two post-hoc analyses,
# copies instance_*/ + patches.json + eval_out/ (the other out folders' exact layout) into
# multiagent_pro_out_p2p_sweep34/ and
# commits and pushes to comm-harness-50 (push explicitly requested by the user for an unattended run).
# Log: ~/harness50/finish_sweep34.log. Idempotent; safe to re-run.
set -u
REPO=/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro
ROOT=/home/asurite.ad.asu.edu/ubiswas2/harness50/p2p/mini_swe_agent/claude_opus_5_5
SRC=$REPO/multiagent_pro_bench34_noreq
DEST=$REPO/multiagent_pro_out_p2p_sweep34
H=/home/asurite.ad.asu.edu/ubiswas2/harness50
AN=$H/analysis_scripts
LOG=/home/asurite.ad.asu.edu/ubiswas2/harness50/finish_sweep34.log
export PATH=/home/asurite.ad.asu.edu/ubiswas2/miniconda3/envs/maswe/bin:$PATH PYTHONUNBUFFERED=1
exec >>"$LOG" 2>&1
echo "=== waiter started $(date -Is) (pid $$)"
until grep -q '^DONE' "$ROOT/progress.txt" 2>/dev/null; do sleep 120; done
echo "=== sweep finished $(date -Is): $(grep '^DONE' "$ROOT/progress.txt" | tail -1)"
cd "$REPO" || exit 1
# fixed.patch: the launcher skeleton omits it; the merger appends it for files no agent owns.
for d in "$ROOT"/instance_*; do f="$SRC/$(basename "$d")/fixed.patch"; [ -f "$f" ] && cp -n "$f" "$d/"; done
mapfile -t FIN < <(for d in "$ROOT"/instance_*; do
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['num_agents'])" "$d/spec.json")
  have=$(ls "$d"/agent_*.patch 2>/dev/null | wc -l); [ "$have" -eq "$want" ] && basename "$d"; done)
echo "=== ${#FIN[@]} finished instances"
python3 multiagent_pro/build_multiagent_pro.py --mode merge --instances "${FIN[@]}" --output "$ROOT" --prefix multiagent || echo "MERGE FAILED rc=$?"
rm -rf "$ROOT/eval_out"
sg docker -c "python3 swe_bench_pro_eval.py --raw_sample_path sampled_pro/raw_sample.jsonl --patch_path $ROOT/patches.json --output_dir $ROOT/eval_out --scripts_dir run_scripts --num_workers 4 --dockerhub_username jefzda --use_local_docker" || echo "GRADE FAILED rc=$?"
echo "=== graded $(date -Is): resolved $(grep -c ': true' "$ROOT/eval_out/eval_results.json" 2>/dev/null) / ${#FIN[@]}"
python3 -I "$AN/safety_audit.py" --run-root "$ROOT" --out "$H/analysis_safety" >/dev/null || echo "SAFETY FAILED"
python3 -I "$AN/coordination_metrics.py" --run-root "$ROOT" --eval-results "$ROOT/eval_out/eval_results.json" --out "$H/analysis_coordination" >/dev/null || echo "COORD FAILED"
# The out folder holds exactly what the other multiagent_pro_out_* folders hold: instance_*/,
# patches.json, eval_out/. Logs, progress.txt and the analysis outputs stay in ~/harness50.
mkdir -p "$DEST" && rsync -a --delete --include='instance_*/' --include='instance_*/**' --include='patches.json' \
    --include='eval_out/' --include='eval_out/**' --exclude='*' "$ROOT/" "$DEST/" && echo "=== synced $(du -sh "$DEST" | cut -f1): $(ls "$DEST" | grep -vc '^instance_') non-instance entries"
# Analysis scripts next to the other metrics scripts; everything else from ~/harness50 (logs,
# progress, analysis outputs, this finisher) under harness50/ -- minus p2p/, which IS the out folder.
cp "$AN"/safety_audit.py "$AN"/coordination_metrics.py multiagent_pro/metrics/
mkdir -p harness50/logs && rsync -a --delete --exclude 'p2p/' "$H/" harness50/ && rsync -a "$ROOT/logs/" harness50/logs/ && cp "$ROOT/progress.txt" harness50/
git add multiagent_pro/launchers/run_mini_sweep34_p2p_ubiswas2.sh multiagent_pro/launchers/run_mini_sweep34_p2p_ubiswas2_resume.sh \
    multiagent_pro/metrics/safety_audit.py multiagent_pro/metrics/coordination_metrics.py harness50 "$DEST"
git commit -q -m "Record the 34-instance P2P sweep (mini-swe-agent, Opus 5.5): $(grep -c ': true' "$ROOT/eval_out/eval_results.json" 2>/dev/null)/${#FIN[@]} resolved

multiagent_pro_out_p2p_sweep34/ follows the other multiagent_pro_out_* folders exactly:
instance_*/ (patches, boards, comm/cost stats, trajectories, context dumps), patches.json and
eval_out/ from the Pro evaluator. harness50/ holds the run logs, progress, the post-hoc safety audit
and coordination metrics (scripts in multiagent_pro/metrics/). Also the launcher
and its _resume twin (the machine rebooted mid-sweep at 17:01 on 2026-10-20).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && echo "=== COMMITTED $(git rev-parse --short HEAD)"
# Push, as explicitly instructed by the user (2026-10-20): the laptop may be unattended when this runs.
git push origin comm-harness-50 && echo "=== PUSHED $(date -Is)" || echo "PUSH FAILED rc=$?"
touch "$H/sweep34.complete"
