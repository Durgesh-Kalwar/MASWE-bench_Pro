# Things to fix

Working list only. Delete an item once it is implemented; delete the file when it is empty.
Current prompt text for every arm: `prompt_templates.md`. Evidence references are CHECKPOINT
sections.

---

## A. Blocks the multi-agent run on bench34_noreq

### A2. The SWE-agent prompt claims requirements are present
`aci/gen_solver_config.py:100-102` — *"The problem statement and requirements below are complete
and unedited."*

On `multiagent_pro_bench34_noreq` there are no requirements. The agent is told to look for a
section that is not there, and told nothing was withheld when something was. mini's prompt makes
no such claim, so this is also a scaffold asymmetry.

Fix: make the sentence conditional on `spec["include_requirements"]`, and reword the
withholding claim so it describes only what is actually complete (the problem statement) rather
than asserting nothing was removed.

### A3. The SWE-agent prompt contradicts itself on scope
`aci/gen_solver_config.py:90-95`. Paragraph 1: *"You own one file… you may read and edit anything
in this file."* Paragraph 2: *"You may read and edit anything in the repository except the files
your peers own."*

Paragraph 1 is simply wrong under `--distractors -1` (full mode, which bench34 uses): it tells
the agent its scope is one file when it is the whole repo minus peers' files.

Fix: delete paragraph 1; paragraph 2 is correct and already says everything.

---

### A6-residual. The scope guard still refuses commands that EXCLUDE a peer's file

A6 proper is implemented (2026-10-15): `_denied()` now checks each `&&` / `||` / `;` / newline
segment separately and exempts a segment whose first word is a comm bin or `cd`, so a pure
announcement passes while a mixed chain stays refused. CHECKPOINT 16.4 records the behaviour
change. What remains is the narrower case:

```
grep -rn ITERATING_ lib/ansible --include=*.py \
  | grep -v "play_iterator.py\|strategy/__init__.py\|strategy/linear.py"   -> REFUSED
```

The peer paths appear only in an EXCLUSION filter -- the command is explicitly avoiding those
files -- but `grep` is not a comm bin, so the segment is checked and the needles match. Observed
twice in the 2026-10-15 run (`ansible-395e5e20`, agent_1 round 4; the agent recovered with
`--exclude-dir`). Deliberately not fixed: telling an exclusion from an access needs per-flag
argument analysis, which is easy to get wrong in the permissive direction.

Note the opposite hole is older and still open: `grep -rn X lib/ansible/` names no peer path and
is allowed, yet recursion reads every peer file under it. That is the §10.5 / §13.6 "guard, not a
sandbox" leak, not something the segment check changed.

---

---

## B. Found while writing `prompt_templates.md`

### B2. The SWE-agent arm pays for tool documentation twice
`aci/gen_solver_config.py` — `SYSTEM_PROMPT` ends with `Available tools:\n{{command_docs}}`.

Function calling IS in use on this arm (confirmed on a real run: 40/40 traj steps carry structured
`tool_calls`, 36 `role: "tool"` messages, `tool_call_ids` on messages; and structurally,
`enable_bash_tool: false` would raise at construction under any other parser). So the tool schemas
already go out as the API's `tools=` parameter — `models.py:679`, built by
`commands.py::get_function_calling_tool`. Rendering `{{command_docs}}` as well sends the same
information a second time, as prose.

Measured on a real `broadcast/swe_agent` system message:

| | chars |
| --- | --- |
| rendered system message | 6,763 |
| our prose (`SYSTEM_PROMPT`) | 1,812 |
| `command_docs` | **4,951 — 73% of the system prompt** |

Re-sent on every request, and this gateway ignores prompt caching (§14.6), so at Opus 5.5 input
rates that is ~$0.30 per agent over 60 steps and **~$53 per instance** across 180 agents — before
any of the actual work.

The paper's single-agent config does NOT do this: `config/tool_use.yaml` never references
`command_docs`, and SWE-agent's own docs say the variable exists precisely for the case where you
are NOT using `FunctionCallingParser` (`sweagent/tools/parsing.py:30`).

**Nothing is lost by removing it — checked field by field across all 12 tools of this arm.** The
docstring becomes the schema `description`, and every argument description, `type`, `required`
flag and `enum` is carried through: 12/12 on both. The only string `command_docs` adds is the
CLI-style signature line (`scoped_view <path> [<start_line>] [<end_line>]`), which has no consumer
under function calling — the model fills structured arguments rather than typing a command line.

**Verified end to end on Opus 5.5** with the real 12-schema set, same instance, one call each:

| | system prompt | first action returned | valid | input tokens |
| --- | --- | --- | --- | --- |
| with `command_docs` | 6,878c | `scoped_list`, `scoped_search` | yes | 5,145 |
| without | 1,793c | `scoped_list`, `scoped_search` | yes | **3,454** |

Same tool choices, well-formed arguments, **1,691 fewer input tokens per request (-33%)**.

Caveat on that test: one prompt each, on an easy first step where the obvious move is to look
around. It demonstrates the mechanism, NOT that behaviour is unchanged over 60 steps. The honest
check is a few instances both ways.

Fix: drop `Available tools:\n{{command_docs}}` from `SYSTEM_PROMPT`, matching the paper. Keep it
only on a deliberate decision that redundant in-prompt docs help a weaker model — in which case
record that reasoning, because it is a 73% tax on the system prompt.

Two things to weigh before editing:

* This is a **behavioural change, not a pure cleanup**, so it belongs with section D: every
  harness50 run so far has the docs in-prompt, and changing this invalidates comparison with them.
* It is **not** symmetric with the mini arm, which must keep its `comm_docs` block: mini has no
  function-calling channel at all, so that text is the only way its agents learn the commands
  exist. Removing `command_docs` from SWE-agent brings the two arms closer together rather than
  further apart.

---

## C. Measured defects no prompt currently addresses

### C1. The interface registry omits the owning file
`aci/orchestrate.py::render_registry` prints `owner  signature` plus description — no path. In
§9.1 two consumers each invented a *different* wrong import path for a correctly published
contract; §9.2 showed agents can recover the location by dialogue, but it costs a two-round
round-trip that often does not happen.

Fix: render the publisher's gold file alongside the signature. The harness already knows it from
`AGENTS_ROSTER`, so this needs no extra agent effort. Smallest change on this list with the
highest certainty of payoff.

### C2. Nothing says "adopt the published contract instead of inventing a competitor"
§9.3 ranks this *"the single most reproducible defect"*; §11.1 recorded an agent reading a
published `prepare_multipart` and announcing a competing `_encode_multipart_formdata` anyway.
`NOTICE_REGISTRY` says *"the EXACT names to code against"* but never forbids publishing a rival
for a contract that already exists.

Fix: one line in the shared behavioural section — if the registry already lists a contract for
what you need, call it; do not define your own. Consider also having `publish_interface` warn
when the symbol duplicates an existing entry from another author.

### C3. Nothing forbids claiming completion in free text
§11.1: the existence check gates `publish_interface` only, so an agent whose edits had been
refused broadcast *"the `prepare_multipart` utility that I've just implemented"* in a
`send_message` and the board laundered the claim into fact. False attestation is the defect that
gets *worse* as coordination improves.

Fix: instruct agents not to state that something exists unless they have verified it in their own
file. A structural gate is harder (free text cannot be checked the way a signature can), so the
prompt is the available lever.

### C4. Nothing says to change approach after a refusal
§9.5 defect 3, seen again in §14.5 (steps 21 and 22 byte-identical). mini covers this only for
`sed`; SWE-agent has nothing, which is what produced the 20 identical rejected `scoped_insert`
calls that motivated adding mini at all (§13).

Fix: shared line — if the same command is refused twice, the command is not the problem; re-read
the file and change approach.

### C5. Round arithmetic is never explained
§8 established that an ask→answer→apply chain costs three round transitions. Agents are told
messages arrive next round, but not that a question asked in the final round can never be
answered — so they ask late.

Fix: state the arithmetic and the deadline explicitly, in both prompts.

---

## D. Decide deliberately: the scaffold comparison is confounded

`MINI_SYSTEM` is 2.4x the length of `SYSTEM_PROMPT` and carries three behavioural levers
SWE-agent has no equivalent of: the ~30-line editing section, *"a round spent only talking is a
round wasted"*, and *"answer what you are asked, even if your own file is unfinished"*. §13.5
measured how much that matters — adding the editing section alone moved mini from "3 of 4 agents
never edited a file" to "4/4 produced patches".

§13.1's own design rule is *"anything the two backends do not share silently confounds the
comparison."* Today broadcast-vs-p2p is clean (`COORD_*` is shared); mini-vs-SWE-agent is not —
it partly measures prompt-writing.

Two coherent resolutions, and this has to be chosen BEFORE any run, since changing it later
invalidates comparisons:

- **Parity** — factor the behavioural instructions (C2–C5 plus an editing section) into shared
  fragments like `COORD_*`, with only tool mechanics differing per scaffold.
- **Declared asymmetry** — treat each arm as "framework + its idiomatic prompt", stop calling
  prompt text controlled, and say so in the writeup.

Parity is more work and the stronger claim. Either way, C2–C5 should live in ONE place that both
prompts pull from, so they cannot drift.

---

## E. Tooling and instrumentation (not prompt defects)

These surfaced during the 2026-10-14 smoke run and are also listed in CHECKPOINT 15.7. E1 was
implemented on 2026-10-15 (CHECKPOINT 16.4).

### E2. `orchestrate.py` does not flush stdout

Piped through `tee`, both the log file and the tmux pane lag behind a block buffer, so a healthy
run is indistinguishable from a hung one (this already cost one false diagnosis in the solo arm).
Progress is only readable from `context/messages.jsonl` and `traj/round_*.json`, which are written
directly.

Fix: `export PYTHONUNBUFFERED=1` in the launcher -- no code change. Do this before the
34-instance sweep, where a frozen-looking log over several hours is a real problem.

### E3. `--mode dry` does not support mini

It loads `solver.yaml` unconditionally, and a mini-generated instance has only `mini.yaml`, so a
dry run on a mini cell dies with `FileNotFoundError`. The 2026-10-14 validation had to be done
with a one-off script instead.

Fix: branch on `comm_mode.json`'s `scaffold` key (the single source of truth `orchestrate.py`
already uses to pick the backend) and validate `mini.yaml` against mini's own `AgentConfig` /
`ScopedDockerEnvironmentConfig`.

### E5. The pooled instance budget is not enforced on the SWE-agent arm

`--per-agent-cost-budget X` (added 2026-10-17) pools X per agent into one cap of
`X * n_agents` per instance, checked at each round barrier in `orchestrate.py`. The gate reads
`StepResult.usage`, which only `MiniScaffold` fills in, so on the swe-agent scaffold every step
reports $0.00 and the gate never fires. `run_agents` prints a WARNING when the flag is passed on
that scaffold, but **a swe-agent cell is bounded by `step_limit` alone until this is done**, and
a cost comparison between the two arms is meaningless before then (one is governed, one is not).

What to do, all inside `SweAgentScaffold.step` in `aci/scaffolds.py`:

* `self.agent.model.stats` is an `InstanceStats` (`SWE-agent/sweagent/agent/models.py:274`) with
  `instance_cost`, `tokens_sent`, `tokens_received`, `api_calls`. It is cumulative per agent, and
  the class defines `__sub__`, so the per-step delta is a subtraction, not bookkeeping:
  take a copy before `self.agent.step()` and subtract after.
* Map onto the shared keys `aci/scaffolds.py::USAGE_KEYS` expects, so `sum_usage` and
  `_cost_stats` work unchanged: `tokens_sent -> tokens_in`, `tokens_received -> tokens_out`,
  `api_calls -> calls`, `instance_cost -> cost_litellm`.
* There is no `cost_gateway` equivalent here: SWE-agent's cost is litellm-computed, not the
  gateway's own billed figure. `_spend()` already falls back to `cost_litellm`, so nothing else
  changes -- but note the two arms' dollar figures then come from different sources, and record
  that where the numbers are reported. On this gateway they agree exactly (CHECKPOINT 16, E4),
  so it is a provenance difference, not a discrepancy.
* Unlike mini's, this arm's cost accounting WORKS: the submodule pin `ddff6a5` is the litellm
  cost-accounting fix these runs need (`docs/submodules.md`), so `instance_cost` is real and no
  price registry has to be wired first.
* Leave each agent's own `model.per_instance_cost_limit` well above its share, or at 0. It is a
  PER-AGENT cap despite the name (`build_agent_config` writes the CLI's
  `--per-instance-cost-limit` straight into it), so a tight value there would re-impose exactly
  the per-agent ceiling the pooled gate is meant to replace -- and SWE-agent raises
  `TotalCostLimitExceededError` out of `step()`, which `run_agents` catches by retiring the agent.

Verification: no live run needed for the arithmetic -- `_cost_stats` and `_spend` are pure and
already unit-tested. What does need a run is one short swe-agent instance with the flag set,
checking `cost_stats.json` has `budget_enforceable: true` and non-zero `per_agent` shares.

### E4. mini's cost tracking is inert, so `cost_limit` cannot bite

`build_mini_config` does not set `litellm_model_registry`, so litellm cannot price the gateway
model and mini RAISES rather than warns -- `MSWEA_COST_TRACKING=ignore_errors` is therefore
required, after which cost reports $0.00 and `cost_limit` does nothing. `step_limit` is the only
ceiling on this arm. The 2026-10-14 smoke run cost $1.35 against a reported $0.00; the 2026-10-15
6-round run cost **$4.23** ($1.54 ansible + $2.69 qutebrowser, 106 calls, 866,250 in / 38,142 out).

Those are measurements, not estimates. `cost_limit` being inert does NOT mean the usage is lost:
litellm returns it on every response, mini's `DefaultAgent` keeps it on the assistant message as
`extra.response`, and `dump_context` writes the whole message, so every call's receipt is sitting
in `<agent>/context/messages.jsonl` under `messages[].extra.response.usage` -- together with the
gateway's OWN billed figure at `metadata.usage_metric.total_token_cost`. Two things to know when
reading it: the context is dumped BEFORE each step, so the same assistant message recurs in later
dumps and rows must be de-duplicated by `response.id`; and `usage` is NOT among the top-level keys
of a dump row (those are `round`, `step_in_round`, `global_step`, `n_messages`, `chars`,
`messages`), so grepping the row keys suggests there is no token data when there is.

Since 2026-10-17 this no longer needs archaeology: `StepResult.usage` carries each step's receipt
into `traj/round_<n>.json`, `comm_stats.json` rows carry the per-round total, and
`cost_stats.json` holds per-agent and per-instance totals. That is bookkeeping only -- it does not
make `cost_limit` work, which is what the fix below is for.

Two facts worth keeping, both from the gateway's own billed figure rather than our arithmetic:
`cost_gateway` equals `tokens_in x $4/M + tokens_out x $20/M` exactly on all 50 solo instances and
on both 6-round instances, and `reasoning_tokens` is 0 everywhere (the gateway reports
`completion_tokens_details: null`). So there is no billed-but-unreported token category on this
gateway -- extended thinking is never requested, `temperature: 0.0` would be incompatible with it
anyway, and if it were ever enabled the provider would bill it inside `completion_tokens`.

Fix: pass the same registry the solo arm uses (`solo/gateway_model_prices.json`, written by
`build_solo.py::write_price_registry`) into `build_mini_config`'s model config, which makes
`cost_limit` a real dollar brake here as it is in the solo arm (CHECKPOINT 14.6). Note the
registry must carry SPLIT input/output rates -- a blended rate understates Opus 5.5 output by 5x.

### E6. FIXED (multi-agent only): a multi-block reply used to cost a step and run nothing

Measured on the 2026-10-19 gpt6_sol sweeps (`openai/openai/gpt6_sol`, both cells, 34 instances
each) against the Opus 5.5 cells on the same instance set, same prompts, same rounds and steps:

| cell | steps | format_error | rate | graded |
| --- | --- | --- | --- | --- |
| broadcast / claude_opus_5_5 | 3,939 | 4 | 0.1% | 28/34 |
| p2p / claude_opus_5_5 | 4,047 | 12 | 0.3% | 29/34 |
| broadcast / gpt6_sol | 6,220 | 1,928 | **31.0%** | 15/34 |
| p2p / gpt6_sol | 5,702 | 1,642 | **28.8%** | 20/34 |

**An earlier version of this entry had the diagnosis exactly backwards** and is corrected here,
because the wrong diagnosis implied the wrong fix. It claimed all 1,928 broadcast cases were
*zero* ```bash blocks -- the model narrating and stopping. The error came from counting blocks in
the trajectory's `thought` field, which is `_last_thought()` = everything before the first
```` ```bash ````, so it has zero blocks by construction. Counting blocks in the raw assistant
turns in `<agent>/context/messages.jsonl` instead gives the real distribution:

| cause | broadcast | p2p |
| --- | --- | --- |
| multiple blocks, DIFFERENT commands | 1,750 (90.8%) | 1,407 (85.7%) |
| redundant: every block identical | 174 (9.0%) | 231 (14.1%) |
| zero blocks | **3** (0.2%) | **3** (0.2%) |

Block counts, broadcast: 2 blocks 1,004 - 3 blocks 361 - 4 blocks 246 - 5 blocks 149 - 6+ 161.

So gpt6_sol was not under-acting, it was **over-acting**: chaining a multi-step plan into one
reply as several narration+block units, every block a valid command. `parse_action` requires
exactly one and rejected the lot.

Two further findings from the same scan:

* The trajectory actively hides this. `_last_action()` (`mini_scaffold.py`) uses `re.search`, so
  it displays the FIRST block, while `parse_action` uses `re.findall` and rejects on count. A
  multi-block step therefore reads in `traj/round_*.json` as a clean, valid command that
  inexplicably failed. Diagnosing this class from the trajectory alone is impossible.
* `exit_status="format_error"` is wider than its name: `mini_scaffold.step()` labels every
  `NonTerminatingException` that way, so `ExecutionTimeoutError` lands there too. Of the stored
  1,928 broadcast cases, 3 parse cleanly and were timeouts. Do not read the counter as a pure
  parse-failure count.
* The whole-response duplication quirk previously thought specific to `gpt6_1_sol` does occur in
  `gpt6_sol` (28 broadcast / 56 p2p whole-reply duplications), but it is a minority of the
  failures, not the mechanism.

#### Fix, as implemented

`MiniScaffold` now runs a `FirstActionAgent(DefaultAgent)` subclass
(`mini_scaffold.py::_first_action_agent_class`) that executes `actions[0]` when a reply carries
one or more blocks, appends a note to the observation saying the other N-1 were ignored, and still
raises `FormatError` on zero blocks. The submodule is NOT edited and the paper's solo arm keeps
upstream's exactly-one contract, so solo stays comparable with published mini numbers
(`docs/submodules.md`: a submodule fix would have to reach the fork before the pin could move,
and solo would inherit it).

**First, not last.** Taking the last block was considered and is actively dangerous: in 76% of
broadcast multi-block replies (1,330/1,750) and 74.9% of p2p (1,054/1,407) the LAST block is
`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` while the first is not. `has_finished()` turns that
into `Submitted`, a TerminatingException -- it would end the agent's round at that step and
discard the real work queued in block 1. Last blocks are 7.9% writes/edits versus 26.3% for first
blocks; in 5.6% of cases the last block is a write while the first is the read-only check the
model said it wanted first. Later blocks are also written blind, before the first block's output
exists, so they are speculative by construction -- which is what the step loop is for.

Verification, replaying every recorded step through the shipped class (raw assistant turns joined
to `traj/round_*.json`; script pattern: `parse_action` on stored content, compare to the recorded
`action`):

| cell | steps compared | identical action | recovered | still FormatError | different action |
| --- | --- | --- | --- | --- | --- |
| broadcast / claude_opus_5_5 | 3,939 | 3,755 | 3 | 1 | **0** |
| p2p / claude_opus_5_5 | 4,047 | 3,855 | 7 | 5 | **0** |
| broadcast / gpt6_sol | 6,220 | 4,113 | 1,924 | 3 | **0** |
| p2p / gpt6_sol | 5,702 | 3,881 | 1,638 | 3 | **0** |

Zero divergences in 19,908 steps: wherever a command actually ran, the override extracts a
byte-identical action. That is structural, not luck -- the recorded `action` already came from
`_last_action()`'s first-block `re.search`, so execution now matches what the trajectory always
displayed. 99.8% of gpt6_sol's parse failures are recovered; the 3 per cell that remain are
genuine zero-block replies with nothing to run. The 180 uncaptured steps per cell are exactly one
per agent (180 agents/cell) and always that agent's final step, because context snapshots are
written before each query.

**This is NOT a no-op for Opus**, contrary to a claim in the earlier version of this entry.
Exactly one step per cell changes: a 2-block reply in broadcast, and in p2p a 4-block reply whose
blocks were grep, `sed -i` on `task_include.py`, `send_message all`, then the submit echo -- the
clearest case for first-over-last, since last-match would have submitted that agent before its
edit ran. Its other recorded format_errors are 2 and 6 timeouts (untouched) plus 1 and 5 genuine
zero-block replies (still fail). Consequence: **the recorded 28/34 and 29/34 belong to the old
parsing rule and a re-run under the override will not reproduce them byte-identically.**

#### Still open

* The four graded cells were all produced under the OLD rule. gpt6_sol's 15/34 and 20/34 are
  therefore scores for a cell that lost ~31% / ~29% of its steps to parsing, and the p2p-minus-
  broadcast gap of +5 (versus Opus's +1) is not usable: 4 of its 7 flips are blowouts (broadcast
  missing 10/11, 4/4, 15/56, 33/39 on instances p2p resolved perfectly), the genuinely close
  instances are identical in both cells (same 6 near-misses, same margins), and the arm with more
  wasted steps is the arm that lost. Re-running both gpt6_sol cells under the override is what
  would make the model axis mean anything; until then only the Opus pair is a clean comparison.
* `openai/gpt6_1_sol` emits its entire response twice on 11 of 12 calls under this prompt. The
  override now handles identical repeated blocks (it runs the first), so the model may be usable,
  but this is UNTESTED -- its duplication rate was measured on single probes, not a trajectory.
  Priced in `custom_model_pricing.json` ($2/M in, $10/M out, solved from two probes).
* The gateway injects a garbage delimiter between repeated units in `gpt6_sol` output -- the
  literal string `รีเมียร์` appears verbatim between blocks. A serving-level defect, independent
  of parsing, and a further reason to treat this model's numbers cautiously.
* **A first-step probe cannot find any of this.** Pre-flight was 10/10 single-block, non-empty,
  all on step 1 with no observation history. Future model pre-flights must run a short real
  trajectory (2 rounds, one small instance) and read the `exit_status` histogram -- and, given the
  `thought`-field error above, count blocks in `context/messages.jsonl`, never in the trajectory.
