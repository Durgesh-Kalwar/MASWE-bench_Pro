# Reformulating SWE-bench **Pro** instances as multi-agent problems

This document defines how a SWE-bench **Pro** instance is recast as a **multi-agent**
problem in which several agents each have **limited read/write access** to a subset of the
repository, the **task description is split into per-agent local information**, and the
**number of agents varies per problem**. It is a port of the base SWE-bench formulation
(`SWE-bench/docs/multiagent_formulation.md`) to the Pro dataset and evaluation harness.

For now the pipeline is restricted to **Python** instances (`repo_language == "python"`:
`ansible/ansible`, `internetarchive/openlibrary`, `qutebrowser/qutebrowser`; ~266 of 731
instances). Other languages are a one-line toggle in `LANG_CONFIG` (see §5).

The scripts:
- [`sample_instances_pro.py`](sample_instances_pro.py) — Stage 1 (sample from HuggingFace).
- [`build_multiagent_pro.py`](build_multiagent_pro.py) — Stage 2 (build specs) + Stage 3 (merge).
- [`aci/`](aci/) — the **multi-agent ACI**: file-scoped tools + an inter-agent communication
  interface + a round-based orchestrator that drives the agents and grades the result. Its
  design and decision choices are documented in [`multiagent_aci.md`](multiagent_aci.md).

## 1. Formulation

A Pro instance `x` (description split across `problem_statement` + `requirements` +
`interface`, gold fix `x.patch`, hidden tests `x.test_patch` + `fail_to_pass`/`pass_to_pass`)
is mapped to a multi-agent instance

```
M(x) = (A, scope, local, integrate, grade)
```

- **Agents `A = {a_1 … a_N}`.** `N = number of distinct files the gold patch touches`.
  Data-driven and varies per problem. `N = 1` is the degenerate case (identical to standard
  single-agent Pro).

- **`scope(a_i)` — limited file access (oracle + distractors).** Each agent owns exactly one
  gold-patched file plus `K` *distractor* siblings drawn from the same directory at
  `x.base_commit`, enumerated **offline from the instance's Pro Docker image** (`git ls-tree`
  inside the image, which carries the repo at `base_commit`; no GitHub token). An agent may
  **read and write only files in its scope**. Distractors are assigned **disjoint** across
  agents, so the real target is hidden among decoys yet every needed file is owned by exactly
  one agent. `K = 0` reduces this to pure-oracle scoping. `--distractor-source` selects
  `docker` (default), `github` (contents API), or `oracle` (none).

  **Scope is what makes the problem "limited information".** Strict scoping (an agent cannot
  even *read* outside its files) is enforced at solve time by the multi-agent ACI — see
  [`multiagent_aci.md`](multiagent_aci.md).

  **`K = -1` — full-access baseline (denylist).** Passing `--distractors -1` flips scoping
  from an **allowlist** to a **denylist**: each agent gets read/write to the **entire repo
  EXCEPT the gold files owned by the other agents** (its own gold file stays editable). This is
  the unrestricted-baseline setting for comparison against scoped coordination. Enforcement is
  driven by two env vars the ACI tools read — `SCOPE_MODE=full` and `SCOPE_DENY` (JSON list of
  peers' gold files); `SCOPE_FILES` then names only the agent's primary file. Because agents
  can now edit the *same* non-gold file, the integrate step (plain concatenation) prints a
  loud overlap warning and the merged patch may fail `git apply` — that failure is reflected
  honestly in the grade rather than reconciled.

- **`local(a_i)` — per-agent task info (scope-limited, not text-limited).** Limited information
  is defined by **file scope, not by withholding the issue**: **every agent receives the FULL
  `problem_statement`** (and the full `requirements` when `--include-requirements`), plus a
  generated **`## Your focus`** section naming its gold file, its key symbols, and the issue
  passages that mention them. No agent is ever handed an empty slice. Two flags are the
  **ambiguity knob**:
  - `--include-requirements` — also include the Pro `requirements` field (impl-specific
    acceptance criteria naming concrete functions/files) in every agent's local info.
  - `--include-interface` — emit the shared coordination contract (see below).

  **`--partition-issue` — the genuine-coordination setting.** The default above makes
  cooperation *optional*: since every agent holds the full issue (which spells out the entire
  cross-file contract), the message board is redundant — verified empirically: across full
  qwen and gpt-4o-mini runs, agents made **zero** comm-tool calls yet gpt-4o-mini still
  passed. With `--partition-issue`, each agent's `local_issue.md` instead contains **only its
  exclusively-routed slice** of the issue: units (sentences / code blocks) are scored by
  symbol overlap and each goes to exactly ONE agent, with **definer priority** — a unit
  mentioning a name some agent's gold diff *introduces* (new `def`/`class`/enum members)
  routes to that definer, so a consumer genuinely never sees the definer's chosen names and
  must `send_message` to ask for them. Symbol-free units (repro steps, error
  text) are shared with everyone; there is no "Key symbols" hint (it would leak names right
  back). Incompatible with `--include-interface`; `--include-requirements` is routed through
  the same partition rather than given in full. Per-agent slice sizes land in `spec.json`
  (`local_units`; `0` = that agent must learn its task entirely over the board).

- **`integrate` — patch union.** Because scopes are disjoint, the candidate fix is the plain
  concatenation of each agent's scoped diff (`agent_<k>.patch`) into one `model_patch`.

- **`grade` — the Pro harness.** The merged `model_patch` is fed as an ordinary Pro prediction
  (`{instance_id, model_patch, prefix}`) to `swe_bench_pro_eval.py` (Modal or local Docker).
  An instance **passes only if `fail_to_pass ∪ pass_to_pass ⊆ {tests that PASSED}`**. The
  hidden tests are untouched. **No change to the Pro evaluator is required.**

### The cross-scope contract (Pro-specific)

When the gold patch spans multiple files they are coupled through a **shared interface
contract** — a symbol/signature one agent defines and another must use. Unlike base SWE-bench
(which *derived* this heuristically), Pro ships an explicit **`interface`** field listing the
signatures of any new public interface the gold solution introduces. The build uses that field
**directly** as the contract, written to `shared/coordination.md`:

- `--include-interface` **off** ⇒ no `coordination.md` (hardest: agents must discover the
  coupling themselves).
- `--include-interface` **on** and the field has content ⇒ `coordination.md` carries the exact
  interface signatures.
- `--include-interface` **on** but the field is the sentinel `"No new interfaces are
  introduced"` ⇒ `coordination.md` records an explicit "no contract" note (never fabricated).

The base-SWE-bench heuristic `derive_interface` is intentionally **dropped for the contract**;
symbol extraction is retained only for issue *routing*.

## 2. Usage

```bash
# Stage 1 — sample Python instances from HuggingFace -> sampled_pro/<id>/metadata.json
#           + sampled_pro/raw_sample.jsonl (the evaluator's --raw_sample_path)
python multiagent_pro/sample_instances_pro.py                 # all python instances
python multiagent_pro/sample_instances_pro.py --repo ansible -n 5
python multiagent_pro/sample_instances_pro.py --instances <instance_id> ...

# Stage 2 — build the multi-agent specs (K=3 distractors enumerated offline from the image)
python multiagent_pro/build_multiagent_pro.py --mode build \
    --distractor-source docker --distractors 3 --include-requirements --include-interface

# ...or the genuine-coordination build: full repo access (denylist) + partitioned issue text
# (no --include-interface here -- the two are incompatible by design)
python multiagent_pro/build_multiagent_pro.py --mode build --distractors -1 \
    --instances <instance_id> --include-requirements --partition-issue

# Inspect a decomposition
cat multiagent_pro_out/<instance_id>/README.md
cat multiagent_pro_out/<instance_id>/agent_1/SCOPE.txt          # files this agent may edit
cat multiagent_pro_out/<instance_id>/agent_1/local_issue.md     # full issue + this agent's focus
cat multiagent_pro_out/<instance_id>/shared/coordination.md     # the interface contract
```

### Stage 2b (optional) — tag coupling between the agent slices

[`metrics/tag_coupling.py`](metrics/tag_coupling.py) builds a **dependency graph between
the per-agent gold-patch slices** (the def-use approach of commit-untangling work,
ClusterChanges/SmartCommit): each slice's introduced definitions (`DEFS_NEW`), modified
definitions (`DEFS_MOD`), and the names its added lines reference are extracted by
ast-diffing the pre-patch file (fetched from the Pro image or GitHub raw at
`base_commit`, cached under `.coupling_cache/`) against the slice applied via `git apply`.
Directed edges point consumer → definer, cross-agent only:

- **DEF-USE** — agent j's added lines use a name agent i's slice *introduces*
  (e.g. `linear.py` reads `IteratingStates.TASKS`, an enum `play_iterator.py` creates).
- **USE-USE-ON-CHANGED** — agent j's added lines use a name agent i's slice *modifies*
  (e.g. `get_url.py` threads the new `use_netrc=` kwarg into `fetch_url`, whose
  signature `urls.py` changes).

An instance with ≥ 1 cross-agent edge is labeled **`coupled`** (agents provably must
coordinate on a symbol), else **`decomposable`** — an under-approximation: data-shape
contracts (dict keys, tuple arity, registration side effects) are invisible to def-use.
Ambiguous name matches are logged to `coupling_review.jsonl`, never silently linked.

```bash
# Tag every built instance: adds an ADDITIVE "coupling" key to each spec.json and
# writes a per-instance coupling_graph.svg/.png (PNGs need `pip install cairosvg`)
python multiagent_pro/metrics/tag_coupling.py

# Also collect every instance's dependency graph into one flat, pushable folder
python multiagent_pro/metrics/tag_coupling.py --graphs-dir multiagent_pro_out/coupling_graphs

# Empirical cross-check (costs (N+1) container runs per instance): grade the gold merge
# with one agent's slice removed at a time through the UNMODIFIED Pro evaluator; tests
# that break under two different removals are empirical coupling, reported against the
# static edges as static_and_empirical / static_only / empirical_only.
python multiagent_pro/metrics/tag_coupling.py --validate
```

What you get, per instance: `spec.json → coupling` = `{edges: [{from, to, kind, symbol}],
label: coupled|decomposable, per_agent: {in_degree, out_degree, role:
definer|consumer|both|isolated}, per_agent_defs, notes}` (instances without a spec.json
get a standalone `coupling.json`), plus `coupling_graph.png` — consumers left, definers
right; solid arrow = DEF-USE, dashed = USE-USE-ON-CHANGED, one labeled arrow per symbol.
Dataset-wide: `multiagent_pro_out/coupling_index.json` lists **every** Python instance
with its label and edge counts, sorted most→least coupled (full set: **121 coupled /
92 decomposable multi-file / 53 single-file degenerate**), and `coupling_summary.json`
summarizes the last run.

```bash
# Stage 3 — solve with the multi-agent ACI, then integrate + grade (see multiagent_aci.md)
python multiagent_pro/aci/gen_solver_config.py --instances <instance_id> --model <lm> \
    --per-instance-cost-limit 1.5

# ...or point agents at a custom OpenAI-compatible endpoint (self-hosted / institute-proxied
# model, e.g. ASU RC) instead of a standard Anthropic/OpenAI model:
python multiagent_pro/aci/gen_solver_config.py --instances <instance_id> \
    --model openai/qwen3-coder-30b-a3b-instruct \
    --api-base https://openai.rc.asu.edu/v1 \
    --price-per-million-tokens 0.34 --context-window 131100 \
    --per-instance-cost-limit 1.5 --per-instance-call-limit 60
#   api_key is read from $OPENAI_API_KEY at run time (never written to solver.yaml).
#   --price-per-million-tokens/--context-window are only needed the FIRST time a given
#   --model is used -- litellm has no built-in pricing for these, so the numbers (from your
#   institute/provider's model page) are saved to aci/custom_model_pricing.json and reused
#   automatically on every later run with that model name. Omitting them for an unregistered
#   model raises an error telling you exactly what to supply.

# COMMUNICATION HARNESS -- the study variable (add to either gen_solver_config call above).
# Delivery is always PUSH: there is no read tool. Whatever an agent posts in a round is
# injected straight into its recipients' context at the start of the next one, so receiving
# costs no step and what differs between cells is topology, not tool-call discipline.
#   --comm-mode p2p        (default) send_message may be addressed to ONE peer by id --
#                    delivered to that agent alone -- or to 'all'.
#   --comm-mode broadcast  send_message has NO recipient argument at all (the model never
#                    sees one) and always reaches every peer. There is no private channel.
#   --beliefs        adds `update_belief <peer> --note ...`: a PRIVATE per-peer note store no
#                    other agent ever sees, replayed to the agent at the start of every round
#                    and archived as <id>/<agent>/beliefs_round_N.json. Without it agents must
#                    infer whom to address from the messages themselves.
# publish_interface broadcasts in every cell, and REFUSES to announce a symbol that does not
# yet exist in a file the agent owns. The three cells studied are: broadcast / p2p /
# p2p --beliefs. Per-round communication counts land in <id>/comm_stats.json.
#
# The bundle is materialized per instance into <id>/_comm_bundle/ with only that cell's tools,
# so the harness a run used is archived beside it. REGENERATE solver.yaml after changing cell.

# Context window per agent (add to either gen_solver_config call above):
#   --last-n-observations N   keep the full text of only the last N tool observations; older
#                    ones become "Old environment output: (K lines omitted)". Actions and
#                    thoughts are never elided, and the window spans the WHOLE run, not a
#                    round -- SWE-agent has no round concept. Peer messages are EXEMPT: they
#                    are pushed in as message_type "user" and this processor only ever elides
#                    "observation", so an interface can no longer scroll irrecoverably out of
#                    context (it could under the old pull design). N now only bounds the
#                    agent's own file views; use N >= --steps-per-round to keep a full round
#                    of them. Costs more per step -- raise --per-instance-cost-limit with it.
#                    See multiagent_aci.md 2.6.

# Optional coordination gate (OFF by default; add to either gen_solver_config call above):
#   --submit-gate    scoped_submit REFUSES (pure refusal -- the harness never calls comm
#                    tools for the agent) until the agent has announced on the board any
#                    public def/class its edits delete (publish_interface / send_message).
#                    It used to also require reading the board each round; push delivery
#                    removed anything for an agent to fail to check, so that half is gone.

# Rounds are LOCKSTEP: the board is frozen at the start of each round, so every agent sees the
# same state and receives peers' messages from PREVIOUS rounds only -- turn order within a
# round carries no information advantage. Every agent gets a turn every round (including ones
# that already submitted, so late questions can be answered); the run stops once every
# still-active agent submits in the SAME round. An agent that lacks information a peer must
# supply can end its turn early with `no_op` and return next round.
python multiagent_pro/aci/orchestrate.py --mode agents --instances <instance_id> --grade
#   ...or drive the agents yourself, write each agent_<k>.patch, then merge directly:
python multiagent_pro/build_multiagent_pro.py --mode merge --instances <instance_id>
python swe_bench_pro_eval.py \
    --raw_sample_path sampled_pro/raw_sample.jsonl \
    --patch_path multiagent_pro_out/patches.json \
    --output_dir multiagent_pro_out/eval_out \
    --scripts_dir run_scripts --dockerhub_username jefzda --use_local_docker
```

`--emit-gold` additionally writes each agent's `agent_<k>/gold.patch` (the oracle solution for
its scope); `orchestrate.py --mode gold` then verifies the whole integrate→grade path offline.

### 2.1 Running each communication harness

The harness is fixed at **`gen_solver_config.py`** time, not at run time: it decides which comm
tools exist in the materialized bundle and what the system prompt says. So a cell is a
*build+generate+run* triple, and **switching cells means regenerating `solver.yaml`.**

**Give each cell its own `--output` root.** All per-run artifacts (`solver.yaml`, `board.json`,
`comm_stats.json`, the agent patches, `eval_out/`) live under `<root>/<instance_id>/`, so three
cells sharing one root overwrite each other and you end up grading whichever ran last.

```bash
# --- once: keys (bashrc has a non-interactive guard, so source explicitly) ----------------
eval "$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)"; export OPENAI_API_KEY="$CREATEAI_API_KEY"
eval "$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)"

export INST=instance_ansible__ansible-b748edea457a4576847a10275678127895d2f02f-v1055803c3a812189a1133297f7f5468579283f86
MODEL="--model openai/gpt4o_mini --api-base $CREATAI_BASE_URL \
       --price-per-million-tokens 0.375 --context-window 128000 --per-instance-cost-limit 1.5"

# --- run one cell: $1 = output root, $2.. = the harness flags -----------------------------
run_cell () {
  ROOT=$1; shift
  python multiagent_pro/build_multiagent_pro.py --mode build --distractors -1 \
      --instances $INST --output $ROOT --include-requirements --partition-issue
  python multiagent_pro/aci/gen_solver_config.py --output $ROOT --instances $INST \
      $MODEL --last-n-observations 10 "$@"
  rm -rf $ROOT/eval_out/$INST          # or the evaluator re-reports the STALE grade
  python multiagent_pro/aci/orchestrate.py --mode agents --output $ROOT \
      --instances $INST --rounds 3 --steps-per-round 6 --grade
}

# --- the three cells ----------------------------------------------------------------------
run_cell out_broadcast  --comm-mode broadcast     # send_message reaches everyone; no recipient arg
run_cell out_p2p        --comm-mode p2p           # send_message may target ONE peer, or 'all'
run_cell out_p2p_belief --comm-mode p2p --beliefs # p2p + private per-peer notes (update_belief)
```

`--comm-mode p2p` is the default, so the middle cell needs no flag; it is written out here so the
three commands read as one comparison. Add `--submit-gate` to all three or to none — it is a
separate variable (and now means only the publish-check, see below).

**Confirm the cell actually took effect** before spending a run on it:

```bash
cat $ROOT/$INST/comm_mode.json                       # {"mode": "...", "beliefs": ...}
ls  $ROOT/$INST/_comm_bundle/bin/                    # exactly this cell's tools; no read_messages
grep -c 'to:' $ROOT/$INST/_comm_bundle/config.yaml   # broadcast: send_message has no `to` argument
grep COMM_MODE $ROOT/$INST/agent_1/solver.yaml
```

`orchestrate.py` prints the harness it read from `comm_mode.json` at startup and in `--mode dry`.
Note **`--mode dry` only validates that `solver.yaml` parses** — it stops at `RunSingleConfig` and
never reaches `agent.setup()`, so it will *not* catch a declared-tool/missing-bin mismatch.

**What each cell writes, beyond the usual artifacts:**

| file | cells | content |
| --- | --- | --- |
| `<id>/comm_mode.json` | all | the cell, so `orchestrate.py` reads it from one source of truth |
| `<id>/_comm_bundle/` | all | the exact tool bundle the agents ran — archived beside the run |
| `<id>/comm_stats.json` | all | per agent per round: `received`, `sent_directed`, `sent_broadcast`, `interfaces_published`, `refused_interfaces`, `belief_updates`, `no_op`, `submitted`, `steps` |
| `<id>/<agent>/beliefs_round_N.json` | `--beliefs` | that agent's private per-peer notes at the end of round N, with every revision |

**Capturing exactly what each agent saw** (`orchestrate.py --dump-context`, off by default).
Before EVERY step it appends `agent.messages` — the post-history-processor list, i.e. literally
the payload sent to the API — to `<id>/<agent>/context/messages.jsonl`, one JSON object per line
(`round`, `step_in_round`, `global_step`, `n_messages`, `chars`, `messages`). This is the only
record of what the model *saw*: the trajectory stores what the tools *returned*, the board stores
what was *sent*, and an elided observation shows here as its `Old environment output: (K lines
omitted)` placeholder. It writes the whole conversation once per step, so the file grows
quadratically over a run — leave it off unless you intend to analyse decisions.

**Interface contracts are pinned, in every cell.** A `publish_interface` contract arrives as a
normal message the round it is published, and is then re-listed at the top of every subsequent
round notice as an always-current registry (newest-wins per author+symbol, the agent's own marked
`<- yours`). Messages are events and stay new-only; contracts are state and stay in view. This is
on in all three cells — interfaces broadcast everywhere, so holding it constant keeps a
broadcast-vs-p2p difference from being confounded by it.

**Reading the results.** Report `comm_stats.json` next to the grade, not after it — broadcast and
p2p differ in *context volume* as well as topology (a broadcast agent receives every message; a
p2p agent only its own mail plus interfaces), so messages-received is a covariate, not a
footnote. And score **FAIL_TO_PASS and PASS_TO_PASS separately**: on `b748edea` they are 5 and 41,
and 41/41 PASS_TO_PASS is what an *empty* patch earns. See `CHECKPOINT.md` §9.5 and §10.

```bash
python - <<'PY'   # per-cell totals  (INST must be exported, as above)
import json, os
inst = os.environ["INST"]
for root in ("out_broadcast", "out_p2p", "out_p2p_belief"):
    rows = json.load(open(f"{root}/{inst}/comm_stats.json"))
    k = lambda f: sum(r[f] for r in rows)
    print(f"{root:15s} recv={k('received'):3d} directed={k('sent_directed'):2d} "
          f"bcast={k('sent_broadcast'):2d} iface={k('interfaces_published'):2d} "
          f"refused={k('refused_interfaces'):2d} beliefs={k('belief_updates'):2d}")
PY
```

### Per-instance artifact tree

```
multiagent_pro_out/
├── patches.json                       # (merge) JSON LIST for swe_bench_pro_eval.py --patch_path
└── <instance_id>/
    ├── spec.json                       # machine-readable: scopes, symbols, flags, contract, grade_cmd
    ├── README.md                       # human summary + table + merge/eval commands
    ├── shared/coordination.md          # interface contract — only if --include-interface
    ├── roster.json                     # [{id, gold_file}] (after gen_solver_config)
    ├── comm_mode.json                  # the communication harness this run used (2.1)
    ├── _comm_bundle/                   # the EXACT comm tools that cell ran (materialized here,
    │                                   #   so the harness is archived beside the run)
    ├── board.json                      # every message posted, in publication order
    ├── board_after_round_<n>.json      # the board as frozen at each barrier
    ├── comm_stats.json                 # per agent per round: received / sent_directed /
    │                                   #   sent_broadcast / published / refused / no_op
    └── agent_<k>/
        ├── SCOPE.txt                    # gold file + K distractors (read/write allowlist)
        ├── local_issue.md              # FULL problem_statement [+ requirements] + focus highlight
        ├── solver.yaml                  # generated SWE-agent config (after gen_solver_config)
        ├── traj/round_<n>.json         # this agent's steps in each round
        ├── beliefs_round_<n>.json      # only with --beliefs: its PRIVATE per-peer notes
        ├── gold.patch                  # only if --emit-gold (oracle for this scope)
        └── agent_<k>.patch             # the agent's scoped diff -> input to merge
```

## 3. How this differs from base SWE-bench

| Aspect | base SWE-bench | SWE-bench Pro (this port) |
| --- | --- | --- |
| Source | `sampled_instances/<id>/metadata.json` | HF `ScaleAI/SWE-bench_Pro`, Python-filtered |
| Task text | routed slice per agent | **full** `problem_statement` (+ optional `requirements`) + per-file focus highlight |
| Limited info | file scope **and** routed text | **file scope only** (every agent sees the whole issue) |
| Distractors | GitHub contents API | offline `git ls-tree` in the Pro image (`--distractor-source`) |
| Solve-time ACI | n/a | scoped tools + comm interface ([`multiagent_aci.md`](multiagent_aci.md)) |
| Contract | heuristic (symbols in >1 gold region) | the dataset `interface` field, gated by `--include-interface` |
| Grade | `swebench.harness.run_evaluation` (`predictions.jsonl`) | `swe_bench_pro_eval.py` (`patches.json` list, `model_patch`) |
| Prediction key | `model_patch` | `model_patch` (same), with `prefix` |

## 4. Verification performed

- **Integrate is exact.** Concatenating each agent's gold hunks reproduces the original gold
  patch (order-independent line equality) for the verified N=2 and N=5 ansible instances.
- **Grade reuses the Pro harness end-to-end.** The gold-merged patch for
  `instance_ansible__ansible-f327e65d…` grades **`true` (100%)** through
  `swe_bench_pro_eval.py --use_local_docker`, confirming the integration grades correctly with
  no evaluator modification.
- **First real (non-gold) solve-mode run reached the evaluator.** With agents actually solving
  (not applying the gold patch), the full pipeline — boot → solve → coordinate → submit →
  collect → merge → grade — completed end-to-end for the first time and produced a real
  pass/fail score. See [`multiagent_aci.md`](multiagent_aci.md) §2.3 for the infra fixes this
  took (`git --no-pager diff`, writing `/root/model.patch` so SWE-agent recognizes a
  submission, per-round trajectory logging) and the lint-on-write syntax check added after
  that first run's failure mode (a syntax-breaking edit that slipped through uncaught).

## 5. Limitations & knobs

- **Python only (for now).** `LANG_CONFIG` in `sample_instances_pro.py` gates languages; flip
  `enabled: True` to add JavaScript/TypeScript/Go later. `fetch_distractors` is already
  suffix-keyed (language-agnostic); only `_SECTION_SYMBOL` (`def`/`class`) is Python-leaning
  and is a documented future per-language hook (e.g. add `function`).
- **Most instances may still be single-file.** Per-gold-file counting makes `N = 1` common;
  Pro patches tend to touch more files than base SWE-bench, so `N > 1` is exercised more often.
- **Focus highlight is heuristic.** The `## Your focus` selector uses symbol overlap, so it
  may surface a few off-target sentences — but every agent still has the full issue, so this
  never starves an agent. Faithful semantic decomposition would need an LLM pass.
- **Oracle scoping leaks localization signal.** Even with distractors, the target file is in
  some agent's scope. A solution-agnostic (module/dir-based) variant is a deliberate non-goal.
- **Distractors are offline by default.** `--distractor-source docker` enumerates siblings via
  `git ls-tree` inside the Pro image (no network/token). `github` (contents API) and `oracle`
  (`--distractors 0`) remain available; docker falls back to github then oracle.
- **Dataset text fields are JSON-double-encoded.** `problem_statement`/`requirements`/
  `interface` are stored as quoted JSON strings; the build's `decode_text()` unwraps one layer.
  `fail_to_pass`/`pass_to_pass` are Python-literal lists (the evaluator `eval()`s them).
- **The scoped edit tools only catch syntax errors, not logic errors.** `scoped_str_replace` /
  `scoped_insert` / `scoped_create` reject a `.py` edit that fails to parse (`compile()`), but an
  edit that parses fine and is still wrong (bad logic, wrong symbol name that resolves at
  runtime, etc.) is not caught — same limitation the single-agent ACI's own lint-on-edit tools
  have (they only run flake8, not the real test suite, on every edit).
