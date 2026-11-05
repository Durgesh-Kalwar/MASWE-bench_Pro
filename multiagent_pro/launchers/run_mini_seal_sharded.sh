#!/usr/bin/env bash
# SEALED 34-instance sweep, one arm, split into N shards that run CONCURRENTLY, each shard under
# its own gateway key. Usage: run_mini_seal_sharded.sh p2p|p2p_beliefs [NSHARDS]
#
# Same config as run_mini_seal_<arm>.sh (and therefore as the October launchers: bench34_noreq,
# mini-swe-agent, Opus 5.5, 10 rounds x 6 steps, $3/agent pooled; the prompt is byte-identical).
# What differs is only HOW the 34 instances are scheduled: instance i goes to shard i mod N, and
# shard k runs `orchestrate.py --instances <its slice>` with OPENAI_API_KEY=${KEYS[k]}, so N
# instances are in flight at once and the monthly usage limit is spread over every key in
# ~/.config/createai/env (CREATEAI_KEYS, space-separated). Each orchestrate is independent per
# instance already (one container per agent, per-instance dirs), so sharding changes no result;
# the per-shard `merge` at the end of orchestrate rewrites patches.json with that shard's
# instances only, which finish_seal.sh repairs by re-merging everything.
#
# Output root is harness51/<arm>/..., logs in $ROOT/logs/shard_<k>.log, one progress.txt with
# START, one DONE per shard, and a final DONE line that finish_seal.sh waits for.
set -u
ARM=${1:?arm: p2p or p2p_beliefs}
NSHARDS=${2:-5}
REPO=/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro
SRC=$REPO/multiagent_pro_bench34_noreq
ROOT=/home/asurite.ad.asu.edu/ubiswas2/harness51/$ARM/mini_swe_agent/claude_opus_5_5
ROUNDS=10
STEPS=6
BUDGET=3.0
case "$ARM" in
  p2p)         BELIEFS=""; LABEL=p2p ;;
  p2p_beliefs) BELIEFS="--beliefs"; LABEL=p2p+beliefs ;;
  *) echo "unknown arm $ARM" >&2; exit 1 ;;
esac
cd "$REPO" || exit 1
export PATH=/home/asurite.ad.asu.edu/ubiswas2/anaconda3/envs/maswe/bin:$PATH  # maswe conda env

. ~/.config/createai/env   # CREATAI_BASE_URL + CREATEAI_KEYS (chmod 600)
read -r -a KEYS <<< "${CREATEAI_KEYS:-}"
[ "${#KEYS[@]}" -ge 1 ] && [ -n "${CREATAI_BASE_URL:-}" ] || { echo "need CREATEAI_KEYS and CREATAI_BASE_URL in ~/.config/createai/env" >&2; exit 1; }
# Required: build_mini_config does not wire litellm_model_registry, so litellm cannot price the
# gateway model and mini RAISES rather than warns -- the run would die at zero API calls. Cost
# then reports $0.00 through litellm; the pooled gate prices from the gateway's own billed
# figure instead (metadata.usage_metric.total_token_cost), which is why it still bites.
export MSWEA_COST_TRACKING=ignore_errors MSWEA_CONFIRM_EXIT=0
export PYTHONUNBUFFERED=1          # things_to_fix E2: otherwise the log lands in 8k blocks

mapfile -t INSTANCES < <(cd "$SRC" && ls -d instance_* | sort)
if [ "${#INSTANCES[@]}" -eq 0 ]; then echo "no instances found under $SRC" >&2; exit 1; fi

# Fresh per-run skeleton from the built benchmark specs -- never reuse a prior run's state.
for INST in "${INSTANCES[@]}"; do
  rm -rf "$ROOT/$INST"; mkdir -p "$ROOT/$INST"
  cp "$SRC/$INST/spec.json" "$SRC/$INST/README.md" "$ROOT/$INST/" 2>/dev/null
  cp -r "$SRC/$INST/shared" "$ROOT/$INST/" 2>/dev/null
  for d in "$SRC/$INST"/agent_*/; do
    a=$(basename "$d"); mkdir -p "$ROOT/$INST/$a"
    cp "$d/SCOPE.txt" "$d/local_issue.md" "$ROOT/$INST/$a/" 2>/dev/null
  done
done

mkdir -p "$ROOT/logs"
echo "START $(date -Is)  instances=${#INSTANCES[@]} rounds=$ROUNDS steps=$STEPS \
budget=\$$BUDGET/agent pooled model=claude_opus_5_5 harness=$LABEL shards=$NSHARDS keys=${#KEYS[@]}" > "$ROOT/progress.txt"

# Configs for every instance once, with the first key in the environment (gen_solver_config
# writes "$OPENAI_API_KEY" indirection into mini.yaml, never the key itself).
export OPENAI_API_KEY="${KEYS[0]}"
python3 multiagent_pro/aci/gen_solver_config.py --output "$ROOT" --instances "${INSTANCES[@]}" \
    --scaffold mini --comm-mode p2p $BELIEFS \
    --model openai/aws/claude5_5_opus --api-base "$CREATAI_BASE_URL" \
    --price-per-million-tokens 4.0 --output-price-per-million-tokens 20.0 \
    --context-window 200000 --per-instance-cost-limit 2.0 \
    --rounds "$ROUNDS" --steps-per-round "$STEPS" > "$ROOT/logs/gen_solver_config.log" 2>&1 \
  || { echo "gen_solver_config FAILED" >&2; echo "DONE $(date -Is) rc=2 (config)" >> "$ROOT/progress.txt"; exit 2; }

PIDS=()
for ((k = 0; k < NSHARDS; k++)); do
  SHARD=()
  for ((i = k; i < ${#INSTANCES[@]}; i += NSHARDS)); do SHARD+=("${INSTANCES[i]}"); done
  [ "${#SHARD[@]}" -eq 0 ] && continue
  KEY="${KEYS[k % ${#KEYS[@]}]}"
  echo "shard $k: ${#SHARD[@]} instances, key #$((k % ${#KEYS[@]} + 1))" >> "$ROOT/progress.txt"
  (
    export OPENAI_API_KEY="$KEY"
    python3 multiagent_pro/aci/orchestrate.py --mode agents --output "$ROOT" \
        --instances "${SHARD[@]}" --rounds "$ROUNDS" --steps-per-round "$STEPS" \
        --per-agent-cost-budget "$BUDGET" --dump-context
    echo "DONE shard $k $(date -Is) rc=$?" >> "$ROOT/progress.txt"
  ) > "$ROOT/logs/shard_$k.log" 2>&1 &
  PIDS+=($!)
done
RC=0
for p in "${PIDS[@]}"; do wait "$p" || RC=1; done
echo "DONE $(date -Is) rc=$RC" >> "$ROOT/progress.txt"
# Reap only exited containers: nothing else of ours is running by now.
docker ps -aq --filter "name=minisweagent-" --filter status=exited | xargs -r docker rm -f >/dev/null 2>&1
exit $RC
