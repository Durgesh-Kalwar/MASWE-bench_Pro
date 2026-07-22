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

- **`local(a_i)` — per-agent task info (scope-limited, not text-limited).** Limited information
  is defined by **file scope, not by withholding the issue**: **every agent receives the FULL
  `problem_statement`** (and the full `requirements` when `--include-requirements`), plus a
  generated **`## Your focus`** section naming its gold file, its key symbols, and the issue
  passages that mention them. No agent is ever handed an empty slice. Two flags are the
  **ambiguity knob**:
  - `--include-requirements` — also include the Pro `requirements` field (impl-specific
    acceptance criteria naming concrete functions/files) in every agent's local info.
  - `--include-interface` — emit the shared coordination contract (see below).

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

# Inspect a decomposition
cat multiagent_pro_out/<instance_id>/README.md
cat multiagent_pro_out/<instance_id>/agent_1/SCOPE.txt          # files this agent may edit
cat multiagent_pro_out/<instance_id>/agent_1/local_issue.md     # full issue + this agent's focus
cat multiagent_pro_out/<instance_id>/shared/coordination.md     # the interface contract

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

### Per-instance artifact tree

```
multiagent_pro_out/
├── patches.json                       # (merge) JSON LIST for swe_bench_pro_eval.py --patch_path
└── <instance_id>/
    ├── spec.json                       # machine-readable: scopes, symbols, flags, contract, grade_cmd
    ├── README.md                       # human summary + table + merge/eval commands
    ├── shared/coordination.md          # interface contract — only if --include-interface
    ├── roster.json                     # [{id, gold_file}] (after gen_solver_config)
    └── agent_<k>/
        ├── SCOPE.txt                    # gold file + K distractors (read/write allowlist)
        ├── local_issue.md              # FULL problem_statement [+ requirements] + focus highlight
        ├── solver.yaml                  # generated SWE-agent config (after gen_solver_config)
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
