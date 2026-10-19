#!/usr/bin/env bash
# Full 34-instance sweep: bench34_noreq, broadcast, mini-swe-agent, gpt6_sol (gpt-6-sol).
#
# Same launch path as run_mini_v2_smoke6.sh (which was its dress rehearsal), with three
# differences:
#   * all 34 instances instead of 2, read from the built set rather than hardcoded;
#   * 10 rounds instead of 6;
#   * --per-agent-cost-budget 3.0 -- a POOLED instance cap of $3.00 x n_agents, checked at each
#     round barrier. No per-agent ceiling: an agent may spend past its share while the instance
#     pool has room. Agent counts run 3..13 here, so caps run $9.00..$39.00 and the sweep
#     ceiling is $540 across 180 agents.
#
# The $2.00 --per-instance-cost-limit below is NOT the budget: build_mini_config ignores it
# entirely (it goes only to the swe-agent path), and mini's own cost_limit stays 0. The pooled
# gate in orchestrate.py is the only dollar brake on this arm. Left in place so the generated
# configs stay byte-comparable with the smoke run's.
set -u
REPO=/home/asurite.ad.asu.edu/dkalwar/MASWE-bench_Pro
SRC=$REPO/multiagent_pro_bench34_noreq
ROOT=/media/data/dkalwar/harness50/broadcast/mini_swe_agent/gpt6_sol
ROUNDS=10
STEPS=6
BUDGET=3.0
cd "$REPO" || exit 1

eval "$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)"
eval "$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)"
export OPENAI_API_KEY="$CREATEAI_API_KEY"
# Required: build_mini_config does not wire litellm_model_registry, so litellm cannot price the
# gateway model and mini RAISES rather than warns -- the run would die at zero API calls. Cost
# then reports $0.00 through litellm; the pooled gate prices from the gateway's own billed
# figure instead (metadata.usage_metric.total_token_cost), which is why it still bites.
export MSWEA_COST_TRACKING=ignore_errors MSWEA_CONFIRM_EXIT=0
export PYTHONUNBUFFERED=1          # things_to_fix E2: otherwise the log lands in 8k blocks

# Every instance of the built set, in a stable order.
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
budget=\$$BUDGET/agent pooled model=gpt6_sol harness=broadcast" > "$ROOT/progress.txt"

# --rounds/--steps here are written into the PROMPT TEXT; they must match what orchestrate
# actually runs below, or the prompt lies to the agent about its own budget.
{
  python3 multiagent_pro/aci/gen_solver_config.py --output "$ROOT" --instances "${INSTANCES[@]}" \
      --scaffold mini --comm-mode broadcast \
      --model openai/openai/gpt6_sol --api-base "$CREATAI_BASE_URL" \
      --price-per-million-tokens 2.0 --output-price-per-million-tokens 10.0 \
      --context-window 400000 --per-instance-cost-limit 2.0 \
      --rounds "$ROUNDS" --steps-per-round "$STEPS" \
  && python3 multiagent_pro/aci/orchestrate.py --mode agents --output "$ROOT" \
      --instances "${INSTANCES[@]}" --rounds "$ROUNDS" --steps-per-round "$STEPS" \
      --per-agent-cost-budget "$BUDGET" --dump-context
} 2>&1 | tee "$ROOT/logs/sweep34.log"
RC=${PIPESTATUS[0]}
echo "DONE $(date -Is) rc=$RC" >> "$ROOT/progress.txt"
# Reap only exited containers: nothing else of ours is running by now.
docker ps -aq --filter "name=minisweagent-" --filter status=exited | xargs -r docker rm -f >/dev/null 2>&1
exit $RC
