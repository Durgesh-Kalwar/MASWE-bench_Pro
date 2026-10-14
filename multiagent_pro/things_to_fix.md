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

---

### A6. The scope guard refuses coordination messages that name a peer's file

`aci/mini_scaffold.py` -- `ScopedDockerEnvironment._denied()` is substring matching over the whole
command string, so it cannot tell NAMING a file from ACCESSING one. Its split-reference rule (the
parent dir and the basename both appearing anywhere in the command) fires on a message body.

Observed in the 2026-10-14 smoke run, `qutebrowser-e57b6e0`, agent_2 -- refused without running:

```
cd /app/qutebrowser/components && send_message --message 'agent_2 (braveadblock.py) here.
Owner of blockutils.py: I am coding against upstream naming. Constructor:
BlocklistDownloads(urls, parent=None) with NO callbacks. Signals: ...'
  -> REFUSED: qutebrowser/components/adblock.py is owned by another agent
```

`cd /app/qutebrowser/components` supplied the parent directory, `adblock.py` appeared in the
MESSAGE TEXT, and a complete, correct interface announcement never reached the board.

This is inverted from the design intent. The guard exists so an agent cannot READ a peer's file and
must therefore ASK -- and here it blocked the asking. Coordination in this benchmark is largely
about peer files, so a well-formed message is likely to name one.

**Why it matters before the sweep: it silently suppresses the dependent variable.** The study
measures coordination, and this drops coordination messages while logging them as scope
violations. It hit once in 11 board-bound commands here; across 34 instances x 180 agents x 3
cells, a systematic bias against messages that name peer files would distort exactly the
comparison the benchmark exists to make -- and would read as "agents coordinated less in this
cell", not as a bug. It also corrupts the attempted-violation metric 13.2 introduced, since the
counts now include legitimate messages.

Fix: exempt the comm bins (`send_message`, `publish_interface`, `update_belief`, `list_agents`)
from `_denied()`, the way `internal=True` already exempts harness-issued commands. They are
standalone Python reading AGENT_ID / COMM_BOARD / AGENTS_ROSTER and writing JSON under
`/root/comm/` -- they never touch the repo, so there is nothing for the guard to protect.

The care is in the predicate: it must NOT be "contains send_message", or a read can be smuggled
through `send_message --message x && cat peers_file.py`. Require that EVERY command in the
`&&` / `||` / `;` chain is either a `cd` or one of the comm bins, so a mixed chain stays refused
while a pure announcement passes.

Verify by re-running the two smoke instances and confirming agent_2's announcement reaches
`board.json` with zero entries in `scope_violations.jsonl` for that command.

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

All four surfaced during the 2026-10-14 smoke run and are also listed in CHECKPOINT 15.7.

### E1. `mini_scaffold.py` records no action on terminating or format-error steps

`MiniScaffold.step()` builds its `StepResult` without `thought`/`action` in both the
`TerminatingException` and `NonTerminatingException` branches, so every submission and every
format error renders in the dashboard with an empty action -- 9 Submitted and 3 format_error steps
out of 50 in the smoke run. The model DID issue a command on those steps (the sentinel echo, or
whatever failed to parse), and on a format error the thought is the only evidence of what it was
attempting.

Fix: the same change already made in `solo/run_solo.py` -- capture `_last_thought()` /
`_last_action()` BEFORE appending the termination notice, since that append moves the assistant
turn away from the end of the message list.

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
