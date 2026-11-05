#!/usr/bin/env bash
# Resume ONE shard of a sealed sweep on a different gateway key, after its key ran out of
# monthly budget mid-run. Usage: resume_seal_shard.sh p2p|p2p_beliefs SHARD_K KEY_INDEX [NSHARDS]
#
# Recomputes shard k's instance slice exactly as run_mini_seal_sharded.sh did (instance i ->
# shard i mod N), skips instances that already have one agent_<j>.patch per agent, RESETS the
# unfinished ones from the benchmark skeleton (a half-run instance is restarted from scratch:
# its trajectories, board and patches are discarded) and regenerates their configs, then runs
# orchestrate.py on them with CREATEAI_KEY_<KEY_INDEX>. CREATEAI_KEYS is exported too, so the
# scaffold's key rotation (MiniScaffold._install_key_rotation) can move on again if this key
# also runs dry. The caller must have stopped the shard's old orchestrate process first.
set -u
ARM=${1:?arm}; K=${2:?shard index}; KI=${3:?key index (1-based)}; NSHARDS=${4:-5}
REPO=/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro
SRC=$REPO/multiagent_pro_bench34_noreq
ROOT=/home/asurite.ad.asu.edu/ubiswas2/harness51/$ARM/mini_swe_agent/claude_opus_5_5
ROUNDS=10; STEPS=6; BUDGET=3.0
case "$ARM" in p2p) BELIEFS="";; p2p_beliefs) BELIEFS="--beliefs";; *) echo "unknown arm" >&2; exit 1;; esac
cd "$REPO" || exit 1
export PATH=/home/asurite.ad.asu.edu/ubiswas2/anaconda3/envs/maswe/bin:$PATH
. ~/.config/createai/env
KEYVAR="CREATEAI_KEY_$KI"; KEY="${!KEYVAR:-}"
[ -n "$KEY" ] || { echo "no $KEYVAR in ~/.config/createai/env" >&2; exit 1; }
export MSWEA_COST_TRACKING=ignore_errors MSWEA_CONFIRM_EXIT=0 PYTHONUNBUFFERED=1

mapfile -t INSTANCES < <(cd "$SRC" && ls -d instance_* | sort)
PENDING=()
for ((i = K; i < ${#INSTANCES[@]}; i += NSHARDS)); do
  INST=${INSTANCES[i]}; d=$ROOT/$INST
  want=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['num_agents'])" "$SRC/$INST/spec.json")
  have=$(ls "$d"/agent_*.patch 2>/dev/null | wc -l)
  if [ "$have" -eq "$want" ]; then echo "  done:    $INST"; continue; fi
  echo "  pending: $INST (reset)"
  rm -rf "$d"; mkdir -p "$d"
  cp "$SRC/$INST/spec.json" "$SRC/$INST/README.md" "$d/" 2>/dev/null
  cp -r "$SRC/$INST/shared" "$d/" 2>/dev/null
  for a in "$SRC/$INST"/agent_*/; do n=$(basename "$a"); mkdir -p "$d/$n"; cp "$a/SCOPE.txt" "$a/local_issue.md" "$d/$n/" 2>/dev/null; done
  PENDING+=("$INST")
done
[ "${#PENDING[@]}" -gt 0 ] || { echo "shard $K has nothing pending"; exit 0; }
echo "shard $K RESUMED $(date -Is): ${#PENDING[@]} instances on key #$KI" >> "$ROOT/progress.txt"

export OPENAI_API_KEY="$KEY"
python3 multiagent_pro/aci/gen_solver_config.py --output "$ROOT" --instances "${PENDING[@]}" \
    --scaffold mini --comm-mode p2p $BELIEFS \
    --model openai/aws/claude5_5_opus --api-base "$CREATAI_BASE_URL" \
    --price-per-million-tokens 4.0 --output-price-per-million-tokens 20.0 \
    --context-window 200000 --per-instance-cost-limit 2.0 \
    --rounds "$ROUNDS" --steps-per-round "$STEPS" >> "$ROOT/logs/gen_solver_config.log" 2>&1 || exit 2
python3 multiagent_pro/aci/orchestrate.py --mode agents --output "$ROOT" \
    --instances "${PENDING[@]}" --rounds "$ROUNDS" --steps-per-round "$STEPS" \
    --per-agent-cost-budget "$BUDGET" --dump-context > "$ROOT/logs/shard_${K}_resume.log" 2>&1
RC=$?
echo "DONE shard $K resume $(date -Is) rc=$RC" >> "$ROOT/progress.txt"
exit $RC
