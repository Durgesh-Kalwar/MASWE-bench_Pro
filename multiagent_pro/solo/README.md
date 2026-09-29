# Solo arm — the requirements ablation

One agent, the whole repo, no communication. Decides **which bench50 instances are solvable once
the dataset's `requirements` field is withheld**; only those go on to the multi-agent grid.

The `requirements` field is a prose implementation spec (on the instances measured here, 804–2578
characters of "Replace all remaining direct uses of `UnsafeProxy` with `wrap_var(...)`", "`wrap_var(v)`
must behave as follows: …"). An instance can look solvable because that spec was handed over
rather than because the task is well posed, and the multi-agent benchmark includes it in every
agent's issue text. This arm removes it.

## Result (2026-09-28, Opus 5.5)

**34 of 50 bench50 instances resolved with the `requirements` spec withheld** — Pro's full
criterion, every F2P and P2P test passing. F2P 340/385, P2P 3217/3219, $77.66 total
(mean $1.55/instance), 87 min at 4 workers, steps 5–37.

Read as **34 solvable, 15 failed on merit, 1 undetermined** — `ansible-811093f0` was cut by the
cost brake after 22 steps of pure exploration with no edit attempted, so it is not evidence either
way. Full analysis, per-repo and per-N breakdowns, and the alternative criteria (`f2p_all` → 35,
`f2p_any` → 43) are in `../CHECKPOINT.md` §14.

These numbers are **not comparable to published SWE-bench Pro results**, which include the
`requirements` field. `--arm withreq` reproduces the paper's composition if that is wanted.

## Pipeline

```bash
# 0. keys (bashrc has a non-interactive guard -- source explicitly)
eval "$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)"
eval "$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)"
export OPENAI_API_KEY="$CREATEAI_API_KEY"

# 1+2+3 in one wrapper (recommended)
/media/data/dkalwar/harness50/run_solo.sh noreq claude_opus_5_5 250 $(cat ids.txt)

# or by hand
python multiagent_pro/solo/build_solo.py --arm noreq --step-limit 250 --instances <ids>
python multiagent_pro/solo/run_solo.py   --root <cell> --instances <id>
python multiagent_pro/solo/grade_solo.py --root <cell>       # writes solvable.txt
cd /media/data/dkalwar/harness50/dashboard && ./serve.sh     # visualise
```

`--arm withreq` builds the paper's composition (statement + requirements + interface) as a
control; the two arms differ only in that one block.

Output lands in the harness50 grid as an ordinary cell
(`solo_<arm>/mini_swe_agent/<model>/`), so the existing dashboard discovers it with no
configuration. Verified: context/trajectory alignment 6/6 on the calibration run.

## The paper's parameters, and every deviation from them

From `msweagent_wrapper_configs/swebench_pro_mini_example.yaml` plus the recorded
`run_batch.config.yaml` in the submodule.

| parameter | paper | here | why |
| --- | --- | --- | --- |
| prompt config | `config/swebp.yaml` | same, read from the submodule | not copied, so it follows upstream |
| per-instance-call-limit | 250 | 250 (`--step-limit`) | — |
| per-instance-cost-limit | 0 = unlimited | **5.0** | Opus 5.5 is ~40x the gpt-4o-mini runs; unlimited is a runaway |
| temperature | 0.0 | 0.0 | — |
| history | full, no elision | same | — |
| observation truncation | 10k chars (5k head + 5k tail) | same | — |
| deployment | modal | local docker | matches how the multi-agent runs execute |
| command timeout | 30s (mini default) | 60s | 30s can kill a legitimate test run |
| container_timeout | 2h (mini default) | 8h | a 250-step Opus run can exceed 2h |
| run_args | `["--rm"]` (default) | `["--rm","--entrypoint",""]` | these images set `ENTRYPOINT ["/bin/bash"]`; setting run_args REPLACES the default, so `--rm` must be repeated or containers leak |
| cwd | `/` (default) | `/app` | Pro images check the repo out at /app |
| JSON-encoded text fields | not decoded | **decoded** | see below |
| THOUGHT sentence | as shipped | **rewritten for Opus 5.5** | see below |

### Deviation 1 — the text fields are decoded

`problem_statement` / `requirements` / `interface` are JSON-encoded strings, and
`helper_code/create_problem_statement.py` never decodes them, so the paper's prompt contains
literal `\n` and wrapping quotes. `multiagent_pro` decodes them. Both arms decode here: the
comparison that matters is solo vs multi-agent inside this study, and keeping the escaping would
leave the solo arm reading mangled text while the multi-agent arm reads clean text — any gap
would then partly measure prompt formatting. `--raw-json-text` restores paper-faithful escaping.

### Deviation 2 — Opus 5.5 refuses the paper's prompt (MEASURED)

swebp.yaml's system prompt contains:

> Include a THOUGHT section before your command where you explain your reasoning process.

On `claude5_5_opus` that sentence makes the gateway return an **empty completion** — 1–8 output
tokens, `content: ""`, `finish_reason: "stop"`, no error. mini's `parse_action` then finds 0 bash
blocks, so **every step becomes a `format_error`**: a 250-step run would spend the whole budget
and produce a 0-line patch, and the aggregate score would look like an ordinary bad run.

Opus 5.5 added a `reasoning_extraction` safety classifier, and asking for a labelled section of
the model's reasoning trips it. Through an OpenAI-compatible shim there is no `stop_details`
field, so the refusal arrives as empty content rather than `stop_reason: "refusal"`.

Measured with the paper's prompt verbatim, same gateway, same request:

| model | result |
| --- | --- |
| `claude5_5_opus` | **DEAD** — 0 chars |
| `claude5_opus` | ok |
| `claude5_sonnet` | ok |
| `claude4_8_opus` | ok |
| `gpt4o_mini` | ok |

The fix is the smallest one that clears the classifier — that one sentence becomes "Before the
command, write a short explanation of what you are about to do and why." Everything else stays
byte-identical, **including the instance_template's own `THOUGHT:` example, which does not trip
it**, and `parse_action` never required a THOUGHT section anyway (it matches only the ```bash
fence). `--prompt-compat auto` (default) applies it only to models measured to need it, so an
Opus 5 or Sonnet 5 run is still the paper's prompt byte-for-byte. A requested substitution that
finds nothing is a hard error, not a silent no-op.

## Cost

Two facts set the shape:

1. **No prompt caching on this gateway.** Measured: an identical 28,930-token prefix sent three
   times reported `cached_tokens: 0` every time, with and without `cache_control` blocks. So
   `set_cache_control` is deliberately left unset — it would buy nothing.
2. **Full history, no elision**, so cumulative input grows ~quadratically in step count:
   `n·s0 + d·n(n+1)/2`. Halving the step budget quarters the worst case.

The 250-step ceiling is therefore expensive *if an agent never finishes* (~$250/instance), but
that is a worst case, not the expected cost: on the calibration instance the agent **submitted at
step 7** for **$0.31**. `--cost-limit` is what bounds the tail — at 5.0 the whole 50-instance
sweep cannot exceed ~$250 regardless of how badly individual agents flail.

`run_solo.py` fits `d` from whatever run it just did and prints projections at 60/125/250 steps,
so a short `--max-steps 25` run calibrates the real number for ~$0.30.

Cost tracking is **live**, unlike the multi-agent runs: `build_solo.py` registers real per-token
prices for the gateway ids (`gateway_model_prices.json`, verified — a 28,930-token input billed
$0.11582 = exactly $4.00/M), so mini's `cost_limit` is a real dollar brake instead of the inert
$0.00 that `MSWEA_COST_TRACKING=ignore_errors` produces. Do **not** set that variable here.

## Scoring

`grade_solo.py` grades through the same `swe_bench_pro_eval.py` path as the multi-agent runs — a
different grader would confound the filter with the thing it filters for. Two rules it enforces:

- **F2P and P2P are scored separately.** P2P is a damage gauge; an empty patch earns ~100% of it.
- **An uncollected test is a failed test.** One broken top-level import removes a whole module as
  a single collection error, shrinking the denominator; the collected count is reconciled against
  the expected total and any shortfall is reported.

`--criterion` selects the filter: `resolved` (default, full Pro criterion), `f2p_all`, or
`f2p_any`. Per-instance F2P/P2P counts are always recorded in `solo_scores.json`, so the
threshold can be re-cut later without re-running anything.
