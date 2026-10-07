# Things to fix

Working list only. Delete an item once it is implemented; delete the file when it is empty.
Current prompt text for every arm: `prompt_templates.md`. Evidence references are CHECKPOINT
sections.

---

## A. Blocks the multi-agent run on bench34_noreq

### A1. mini's prompt makes Opus 5.5 return empty completions
`aci/gen_solver_config.py:346` — *"Put a THOUGHT section before it explaining your reasoning."*

Trips Opus 5.5's `reasoning_extraction` classifier. The gateway returns `content: ""`,
`finish_reason: "stop"`, **no error**; `parse_action` then finds no bash block, so EVERY step
becomes a `format_error` and the run produces a 0-line patch that scores like an ordinary bad
agent. Measured: dead on `claude5_5_opus`, fine on Opus 5 / Sonnet 5 / Opus 4.8 / gpt4o_mini
(§14.4).

Fix: port `solo/build_solo.py::apply_prompt_compat` to `build_mini_config` — same substitution,
same model gate, same hard error if the expected sentence is absent. Do not special-case it in
two places; share one helper.

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

## B. Found while writing `prompt_templates.md`

### B1. Multi-agent mini has no output truncation and no returncode
`build_mini_config` sets only `system_template` and `instance_template`, so mini's bare defaults
apply:

| template | multi-agent | solo (swebp.yaml) |
| --- | --- | --- |
| `action_observation_template` | `Observation: {{output}}` (23c) | 867c — 10,000-char cap, head/tail split, `<returncode>` |
| `format_error_template` | 61c default | 604c |

Consequences: one `cat` of a large file enters context whole, and the agent cannot distinguish a
failed command from a silent one. There is also no history processor on this arm, so context
growth is unbounded — and the gateway does not honour prompt caching (§14.6), making cost
quadratic in steps.

Fix: set both templates in `build_mini_config` from swebp.yaml's versions, so the solo and
multi-agent mini arms wrap observations identically. That also removes a solo-vs-multi confound.

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
