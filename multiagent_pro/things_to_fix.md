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

### E4. mini's cost tracking is inert, so `cost_limit` cannot bite

`build_mini_config` does not set `litellm_model_registry`, so litellm cannot price the gateway
model and mini RAISES rather than warns -- `MSWEA_COST_TRACKING=ignore_errors` is therefore
required, after which cost reports $0.00 and `cost_limit` does nothing. `step_limit` is the only
ceiling on this arm. Real spend has to be reconstructed from the token counts in the context
dumps (the smoke run cost $1.35 that way, against a reported $0.00).

Fix: pass the same registry the solo arm uses (`solo/gateway_model_prices.json`, written by
`build_solo.py::write_price_registry`) into `build_mini_config`'s model config, which makes
`cost_limit` a real dollar brake here as it is in the solo arm (CHECKPOINT 14.6). Note the
registry must carry SPLIT input/output rates -- a blended rate understates Opus 5.5 output by 5x.
