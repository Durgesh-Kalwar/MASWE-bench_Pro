#!/usr/bin/env bash
# Finish line for a SEALED sweep arm (2026-11-04): the harness50 finisher's steps without the
# commit/push. Usage: finish_seal.sh p2p | p2p_beliefs   (optionally: finish_seal.sh p2p smoke)
#
# Waits for the launcher's DONE line, copies fixed.patch (files no agent owns) into each instance,
# merges every FINISHED instance (one agent_<k>.patch per agent in spec.json), grades with the Pro
# evaluator on local Docker, runs the safety audit and coordination metrics, and copies
# instance_*/ + patches.json + eval_out/ into multiagent_pro_out_<arm>_seal/ (the other out
# folders' layout). Logs stay under ~/harness51. Idempotent; safe to re-run.
set -u
ARM=${1:?arm: p2p or p2p_beliefs}
SUB=${2:-}                                   # "smoke" selects the 2-instance smoke root
REPO=/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro
H=/home/asurite.ad.asu.edu/ubiswas2/harness51
ROOT=$H/${SUB:+$SUB/}$ARM/mini_swe_agent/claude_opus_5_5
SRC=$REPO/multiagent_pro_bench34_noreq
DEST=$REPO/multiagent_pro_out_${ARM}_seal${SUB:+_$SUB}
LOG=$H/finish_${ARM}${SUB:+_$SUB}.log
export PATH=/home/asurite.ad.asu.edu/ubiswas2/anaconda3/envs/maswe/bin:$PATH PYTHONUNBUFFERED=1
exec >>"$LOG" 2>&1
echo "=== waiter started $(date -Is) (pid $$) root=$ROOT"
# The sharded launcher writes one "DONE shard k" per shard and a final "DONE <date> rc=" line;
# only the final one counts, and a resumed shard (resume_seal_shard.sh) may still be running
# after it, so also wait until no orchestrate process is writing into this root.
until grep -q '^DONE 20' "$ROOT/progress.txt" 2>/dev/null && ! pgrep -f "orchestrate.py --mode agents --output $ROOT" >/dev/null; do sleep 120; done
echo "=== sweep finished $(date -Is): $(grep '^DONE' "$ROOT/progress.txt" | tail -1)"
cd "$REPO" || exit 1
for d in "$ROOT"/instance_*; do f="$SRC/$(basename "$d")/fixed.patch"; [ -f "$f" ] && cp --update=none "$f" "$d/"; done
mapfile -t FIN < <(for d in "$ROOT"/instance_*; do
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['num_agents'])" "$d/spec.json")
  have=$(ls "$d"/agent_*.patch 2>/dev/null | wc -l); [ "$have" -eq "$want" ] && basename "$d"; done)
echo "=== ${#FIN[@]} finished instances"
python3 multiagent_pro/build_multiagent_pro.py --mode merge --instances "${FIN[@]}" --output "$ROOT" --prefix multiagent || echo "MERGE FAILED rc=$?"
rm -rf "$ROOT/eval_out"
python3 swe_bench_pro_eval.py --raw_sample_path sampled_pro/raw_sample.jsonl --patch_path "$ROOT/patches.json" \
    --output_dir "$ROOT/eval_out" --scripts_dir run_scripts --num_workers 4 --dockerhub_username jefzda --use_local_docker \
    || echo "GRADE FAILED rc=$?"
echo "=== graded $(date -Is): resolved $(python3 -c "import json,sys; print(sum(1 for v in json.load(open(sys.argv[1])).values() if v))" "$ROOT/eval_out/eval_results.json" 2>/dev/null) / ${#FIN[@]}"
python3 -I multiagent_pro/metrics/safety_audit.py --run-root "$ROOT" --out "$H/analysis_safety_${ARM}${SUB:+_$SUB}" >/dev/null || echo "SAFETY FAILED"
python3 -I multiagent_pro/metrics/coordination_metrics.py --run-root "$ROOT" --eval-results "$ROOT/eval_out/eval_results.json" \
    --out "$H/analysis_coordination_${ARM}${SUB:+_$SUB}" >/dev/null || echo "COORD FAILED"
mkdir -p "$DEST" && rsync -a --delete --include='instance_*/' --include='instance_*/**' --include='patches.json' \
    --include='eval_out/' --include='eval_out/**' --exclude='*' "$ROOT/" "$DEST/" \
    && echo "=== synced $(du -sh "$DEST" | cut -f1) -> $DEST"
# Per-agent seal reports, aggregated, so the out folder says what was sealed in every container.
python3 - "$ROOT" "$DEST/scope_seal_summary.json" <<'EOF'
import json, sys, glob, os
root, out = sys.argv[1:3]
agg = {}
for f in glob.glob(f"{root}/instance_*/agent_*/scope_seal.json"):
    inst, aid = f.split("/")[-3], f.split("/")[-2]
    agg.setdefault(inst, {})[aid] = json.load(open(f))
tot = {k: sum(len(a.get(k, [])) for i in agg.values() for a in i.values()) for k in ("sealed", "compile_failed", "restored", "absent")}
json.dump({"totals": tot, "per_instance": agg}, open(out, "w"), indent=1)
print("=== seal summary:", tot)
EOF
docker ps -aq --filter "name=minisweagent-" --filter status=exited | xargs -r docker rm -f >/dev/null 2>&1
echo "=== done $(date -Is)"
touch "$H/${ARM}${SUB:+_$SUB}.complete"
