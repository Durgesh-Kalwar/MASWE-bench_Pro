#!/usr/bin/env python
"""Regenerate `multiagent_pro/prompt_templates.md` from the live templates.

The doc is the RENDERED prompt for every arm -- placeholders substituted, fragments spliced --
so it goes stale the moment a template changes. Run this instead of hand-editing it:

    python multiagent_pro/gen_prompt_templates.py

Everything is read from source at run time: our two multi-agent prompts from
`aci/gen_solver_config.py`, the round notice from `aci/orchestrate.py`, and each single-agent
prompt from its own submodule's paper config (`mini-swe-agent/.../config/swebp.yaml`,
`SWE-agent/config/tool_use.yaml`). Nothing here is a copy.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "multiagent_pro" / "prompt_templates.md"
BR, KET = "{", "}"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fence(s: str, lang: str = "") -> str:
    """Wrap in a fence LONGER than any backtick run inside, because several of these templates
    contain ``` examples of their own -- a 3-backtick fence would be closed early by them and the
    rest of the template would render as prose (and its `##` lines as document headings)."""
    longest = max((len(m) for m in re.findall(r"`+", s)), default=0)
    bars = "`" * max(3, longest + 1)
    return f"{bars}{lang}\n{s.rstrip()}\n{bars}"


def collect() -> dict:
    import sys
    sys.path.insert(0, str(REPO / "multiagent_pro" / "aci"))
    g = _load("g", REPO / "multiagent_pro" / "aci" / "gen_solver_config.py")
    o = _load("o", REPO / "multiagent_pro" / "aci" / "orchestrate.py")
    sb = _load("sb", REPO / "multiagent_pro" / "solo" / "build_solo.py")

    P: dict = {}
    # --- our multi-agent prompts ---
    P["swe_system_p2p"] = g.system_template("full", "p2p", False, rounds=10, steps_per_round=6)
    P["swe_instance"] = g.INSTANCE_PROMPT
    P["coord_broadcast"] = g.COORD_BROADCAST
    P["coord_p2p"] = g.COORD_P2P
    P["coord_beliefs"] = g.COORD_BELIEFS
    P["mini_comm_docs_p2p"] = g._MINI_COMM_DOCS["p2p"] + g._MINI_BELIEF_DOC
    P["mini_comm_docs_bcast"] = g._MINI_COMM_DOCS["broadcast"]
    P["mini_system_p2p_bel"] = g.MINI_SYSTEM.format(
        coord=g.COORD_P2P + g.COORD_BELIEFS, comm_docs=P["mini_comm_docs_p2p"],
        rounds=10, steps=6)
    P["mini_instance"] = g.MINI_INSTANCE
    # The superseded v1 prompt, frozen in the repo rather than recovered from a run: every
    # mini multi-agent result up to and including harness50 was produced with it, so it has to
    # stay readable after MINI_SYSTEM moves on.
    v1 = REPO / "multiagent_pro" / "prompt_archive" / "mini_system_v1.txt"
    P["mini_system_v1"] = v1.read_text() if v1.is_file() else ""
    P["mini_system_v1_rendered"] = (
        P["mini_system_v1"].format(coord=g.COORD_BROADCAST,
                                   comm_docs=g._MINI_COMM_DOCS["broadcast"],
                                   rounds=10, steps=6) if P["mini_system_v1"] else "")

    # --- mini single agent: the Pro paper's own config, plus our Opus 5.5 substitution ---
    t = sb.load_swebp_templates()
    P["solo_compat_applied"] = sb.apply_prompt_compat(t, "openai/aws/claude5_5_opus", "auto")
    for k in ("system_template", "instance_template",
              "action_observation_template", "format_error_template"):
        P["solo_" + k] = t["agent"][k]

    # --- swe-agent single agent: the Pro paper's own config, used AS IS ---
    sw = yaml.safe_load((REPO / "SWE-agent" / "config" / "tool_use.yaml").read_text())
    for k, v in (sw.get("agent", {}).get("templates") or {}).items():
        P["swesolo_" + k] = v
    P["swesolo_tools"] = sw["agent"]["tools"]
    P["swesolo_launch"] = (REPO / "SWE-agent" / "sweagent_wrapper_configs"
                           / "example_config.yaml").read_text()
    # Instance source: is the paper's problem_statement the composed three-field string?
    insts = yaml.safe_load((REPO / "SWE-agent" / "data" / "instances.yaml").read_text())
    insts = insts["instances"] if isinstance(insts, dict) and "instances" in insts else insts
    ps = insts[0].get("problem_statement", "")
    P["swesolo_n_instances"] = len(insts)
    P["swesolo_ps_len"] = len(ps)
    P["swesolo_ps_has_req"] = "Requirements:" in ps
    P["swesolo_ps_has_itf"] = "New interfaces introduced:" in ps
    P["swesolo_ps_escaped"] = ps.lstrip().startswith('"')
    # Do the two single-agent instance templates say the same thing?
    P["solo_vs_swesolo_identical"] = (
        P["solo_instance_template"].strip() == P.get("swesolo_instance_template", "").strip())

    # --- the round notice, both variants ---
    board = [{"type": "interface", "from": "agent_3",
              "signature": "def prepare_multipart(fields)",
              "text": "Returns (body_bytes, content_type_header). Raises TypeError if fields "
                      "is not a Mapping."}]
    delivered = [{"type": "message", "from": "agent_4", "to": "agent_1",
                  "text": "What exact name did you give the enum?"}]
    reg = o.interface_registry(board)
    P["notice_working"] = o.build_notice(1, "agent_1", delivered, {}, None, reg)
    P["notice_submitted"] = o.build_notice(
        4, "agent_1", [],
        {"agent_2": {"note": "owns urls.py; promised prepare_multipart", "round": 2}}, 3, reg)
    return P


def render(P: dict) -> str:
    L = lambda k: len(P[k])                                               # noqa: E731
    swe_tools = P["swesolo_tools"]
    bundles = [b.get("path") for b in (swe_tools.get("bundles") or [])]
    # Precomputed: a dict literal inside an f-string replacement field is parsed as Python, so
    # `.get(k, {})` there becomes a set containing a dict and raises.
    parse_fn = (swe_tools.get("parse_function") or {}).get("type")
    enable_bash = swe_tools.get("enable_bash_tool")
    exec_timeout = swe_tools.get("execution_timeout")
    return f"""# Chat templates, as the model actually receives them

Every block below is the RENDERED text, extracted from the live templates rather than retyped --
placeholders already substituted, fragments already spliced.

**This file is generated. Do not hand-edit it** -- run
`python multiagent_pro/gen_prompt_templates.py` after changing any template.

Sources: `multiagent_pro/aci/gen_solver_config.py` (both multi-agent prompts),
`multiagent_pro/aci/orchestrate.py` (the round notice), and for each single-agent arm the SWE-bench
Pro paper's own config inside that scaffold's submodule --
`mini-swe-agent/src/minisweagent/config/swebp.yaml` and `SWE-agent/config/tool_use.yaml`.

## The four arms

| arm | system prompt | source |
| --- | --- | --- |
| mini x SINGLE | swebp.yaml, {L('solo_system_template')}c (+1 substitution) | the paper's config, in the submodule |
| mini x MULTI | `MINI_SYSTEM`, {L('mini_system_p2p_bel')}c rendered | ours |
| swe-agent x SINGLE | tool_use.yaml, {L('swesolo_system_template')}c | the paper's config, in the submodule |
| swe-agent x MULTI | `SYSTEM_PROMPT`, {L('swe_system_p2p')}c rendered | ours |

Both single-agent prompts come from the paper and are documented here as the reference baselines.
Note what that does and does not mean for this repo: **only the mini single-agent arm has a build
path** (`solo/build_solo.py`, which emits `mini.yaml` and nothing else). A swe-agent single-agent
run would use `tool_use.yaml` through SWE-agent's own `run-batch`, outside this harness; nothing
here generates it, and the CHECKPOINT 14 baseline is mini-only.

Three things to hold in mind while reading:

1. **The system prompt is not the whole prompt.** In the multi-agent arms there is no tool an
   agent can call to see its mail, so the ROUND NOTICE (section 6) is injected as a user turn at
   the start of every round from round 2 on, carrying the interface registry, new messages,
   private notes and the what-to-do-next instruction. For coordination behaviour it matters as
   much as the system prompt. The single-agent arms have no notice at all.
2. **Both paper single-agent prompts put almost nothing in the system prompt** and almost
   everything in the instance template -- one line and {L('solo_system_template')}c respectively,
   against instance templates of {L('swesolo_instance_template')}c and
   {L('solo_instance_template')}c. Our multi-agent prompts invert that.
3. **Our two multi-agent prompts differ by far more than tool mechanics.** `MINI_SYSTEM` is
   {L('mini_system_p2p_bel')/L('swe_system_p2p'):.1f}x the length of `SYSTEM_PROMPT` and carries
   behavioural instructions SWE-agent has no equivalent of. The `COORD_*` fragments are shared on
   purpose (they are the study variable); nothing else is. See `things_to_fix.md` section D.

---

# 1. mini x SINGLE AGENT (the solo baseline, CHECKPOINT 14)

Written by `multiagent_pro/solo/build_solo.py`; templates read from the submodule's
`config/swebp.yaml` at build time so they track upstream. Prompt-compat substitution applied for
Opus 5.5: **{P['solo_compat_applied']}**.

No rounds, no peers, no comm tools, no scope guard, no round notice. One agent, whole repo.

## 1.1 system_template ({L('solo_system_template')}c)

Exactly one line differs from the paper's. The original read *"Include a THOUGHT section before
your command where you explain your reasoning process."* -- that trips Opus 5.5's
`reasoning_extraction` classifier, after which the gateway returns an empty completion with no
error and every step becomes a format error (CHECKPOINT 14.4).

{fence(P['solo_system_template'])}

## 1.2 instance_template ({L('solo_instance_template')}c)

`{BR}{BR}working_dir{KET}{KET}` -> `/app`. `{BR}{BR}problem_statement{KET}{KET}` -> the composed
issue: dataset `problem_statement` + `interface`, requirements WITHHELD, all JSON-decoded.

{fence(P['solo_instance_template'])}

## 1.3 action_observation_template ({L('solo_action_observation_template')}c)

Wraps every command's output. Note the 10,000-character cap with head/tail split, and the
`<returncode>` -- neither of which our multi-agent mini arm has (2.4).

{fence(P['solo_action_observation_template'])}

## 1.4 format_error_template ({L('solo_format_error_template')}c)

{fence(P['solo_format_error_template'])}

---

# 2. mini x MULTI AGENT

Written by `gen_solver_config.py::build_mini_config` (`--scaffold mini`).

## 2.1 system_template -- rendered for `--comm-mode p2p --beliefs`, rounds=10, steps=6 ({L('mini_system_p2p_bel')}c)

This is **v2**, rewritten 2026-10-14 and used from `multiagent_pro_bench34_noreq` onward. The
prompt it replaced is preserved verbatim in **section 7**, along with what changed and why --
every mini multi-agent result up to and including harness50 was produced with that one, so the
two are not comparable on prompt text.

`{BR}coord{KET}` <- the `COORD_*` fragments (section 5). `{BR}comm_docs{KET}` <- the per-cell
command list (2.3). `{BR}rounds{KET}`/`{BR}steps{KET}` <- the orchestrator's real budget; these
MUST match what `orchestrate.py` actually runs, or the prompt lies to the agent about its own
budget.

{fence(P['mini_system_p2p_bel'])}

## 2.2 instance_template ({L('mini_instance')}c)

`{BR}{BR}problem_statement{KET}{KET}` <- this agent's own `local_issue.md`, which under
`--route-interface` holds the COMPLETE problem statement and only the interface entries for its
own file.

{fence(P['mini_instance'])}

## 2.3 comm_docs, spliced in per cell

p2p (+ beliefs):

{fence(P['mini_comm_docs_p2p'])}

broadcast -- `send_message` has NO recipient argument at all. The affordance is withheld rather
than refused, because a declared-but-rejected argument would still tell the model that addressing
exists, which is the variable under test:

{fence(P['mini_comm_docs_bcast'])}

## 2.4 The other agent settings, and where they come from

| setting | multi-agent | solo (swebp) |
| --- | --- | --- |
| `action_observation_template` | {L('solo_action_observation_template')}c, read from swebp.yaml -- **identical to solo** | {L('solo_action_observation_template')}c |
| `format_error_template` | {L('solo_format_error_template')}c, read from swebp.yaml -- **identical to solo** | {L('solo_format_error_template')}c |
| `timeout_template` | mini default, 234c | not set |
| history processor | none | none |
| `step_limit` | `rounds x steps` = 60 | 250 (the paper's call limit) |
| `cost_limit` | 0 -- INERT, see below | 5.0, a real brake |

The first two were **unset until 2026-10-14**, so mini's bare defaults applied: a 23-char
`Observation: {BR}{BR}output{KET}{KET}` with no cap and no returncode, where the solo arm had
swebp's 10,000-character head/tail wrapper. Raw command output therefore entered context whole, on
an arm that also has no history processor and a gateway that ignores prompt caching, and an agent
could not tell a failed command from a silent one. Both are now read from swebp.yaml by
`gen_solver_config.py::swebp_templates`, so the two mini arms wrap observations identically and
cannot drift (things_to_fix B1, closed).

`cost_limit` is still 0 because the multi-agent runs export
`MSWEA_COST_TRACKING=ignore_errors`, under which litellm reports $0.00 -- `step_limit` is the only
ceiling there. The solo arm registers real per-token prices instead (CHECKPOINT 14.6).

---

# 3. swe-agent x SINGLE AGENT (the paper's config, not built by this harness)

`SWE-agent/config/tool_use.yaml`, driven by SWE-agent's own `run-batch`. Its header records the
lineage: *"a fork of 250225_anthropic_filemap_simple_review.yaml ... heavily inspired by anthropic
and openhands"*.

No rounds, no peers, no comm tools, no scope guard, no round notice.

## 3.1 system_template ({L('swesolo_system_template')}c)

One sentence. Everything substantive is in the instance template.

{fence(P['swesolo_system_template'])}

## 3.2 instance_template ({L('swesolo_instance_template')}c)

`{BR}{BR}working_dir{KET}{KET}` -> the repo root; `{BR}{BR}problem_statement{KET}{KET}` -> the
instance's composed issue text (3.5).

Near-identical in substance to mini's swebp instance template (1.2) -- same `<pr_description>`
framing, same five numbered steps, same "I've already taken care of all changes to any of the test
files" line. Byte-identical: **{P['solo_vs_swesolo_identical']}**. mini's is longer because it
additionally carries the response-format rules and shell examples that a function-calling scaffold
does not need.

{fence(P['swesolo_instance_template'])}

## 3.3 Per-step templates

`next_step_template`:

{fence(P['swesolo_next_step_template'])}

`next_step_no_output_template`:

{fence(P['swesolo_next_step_no_output_template'])}

## 3.4 Action space -- THREE tools, and a real shell

`enable_bash_tool: {enable_bash}`, `parse_function: {parse_fn}`,
`execution_timeout: {exec_timeout}`.

| bundle | tools |
| --- | --- |
| `tools/registry` | none declared -- support bundle only (`_read_env` / `_write_env`, the cross-tool state registry) |
| `tools/edit_anthropic` | `str_replace_editor` -- one tool with a `command` enum: `view`, `create`, `str_replace`, `insert`, `undo_edit` |
| `tools/submit` | `submit` |
| (built in) | `bash` -- because `enable_bash_tool` is true |

Bundles loaded: `{bundles}`.

That is the sharpest contrast in this document. The paper's single-agent SWE-agent has **a shell
plus one editing tool**; our multi-agent SWE-agent arm has **no shell at all** and nine
`scoped_fs` tools plus the comm bundle (4.3). So "SWE-agent" does not denote one action space --
the single-agent and multi-agent arms differ more from each other than mini's two arms do.

Two settings worth knowing:

* `env_variables: USE_FILEMAP: 'true'` is **vestigial here**. The `filemap` command lives in
  `tools/filemap`, which is NOT in this config's bundle list, and nothing in the three loaded
  bundles reads the variable. It is inherited from the `anthropic_filemap.yaml` ancestor named in
  the header comment.
* **No history processor is set**, so SWE-agent's default applies -- and
  `DefaultHistoryProcessor.__call__` returns the history unchanged. There is NO elision in this
  arm, unlike our multi-agent SWE-agent arm's `last_n_observations` (4.4).

## 3.5 What fills `{BR}{BR}problem_statement{KET}{KET}`

`SWE-agent/data/instances.yaml` -- {P['swesolo_n_instances']} instances (the full Pro set), each
carrying one pre-composed `problem_statement` field of ~{P['swesolo_ps_len']}c. Measured on the
first instance: contains `Requirements:` **{P['swesolo_ps_has_req']}**, contains
`New interfaces introduced:` **{P['swesolo_ps_has_itf']}**, still JSON-escaped (starts with a
quote, literal `\\n` throughout) **{P['swesolo_ps_escaped']}**.

So this arm is the three dataset fields concatenated by
`helper_code/create_problem_statement.py`, exactly as mini's paper arm is -- **requirements
INCLUDED**, and undecoded. Our solo arm (section 1) differs on both counts deliberately: it
withholds requirements and decodes the text (CHECKPOINT 14, `solo/README.md`).

## 3.6 The paper's launch command

Reproduced verbatim from `SWE-agent/sweagent_wrapper_configs/example_config.yaml`. Read it as an
example rather than the published run: `--instances.slice :25` and
`--agent.model.per_instance_call_limit 3` are smoke-test values, and the model pinned here is
Claude 3.7 Sonnet.

{fence(P['swesolo_launch'], 'yaml')}

---

# 4. swe-agent x MULTI AGENT

Written by `gen_solver_config.py::build_agent_config` (`--scaffold swe-agent`).

## 4.1 system_template -- rendered for `--comm-mode p2p`, rounds=10, steps=6 ({L('swe_system_p2p')}c)

Substitution is `str.replace`, never `str.format`: the prompt also carries the jinja literal
`{BR}{BR}command_docs{KET}{KET}` that SWE-agent renders later, and `.format()` would silently
collapse it to `{BR}command_docs{KET}` and break tool documentation for every agent.

{fence(P['swe_system_p2p'])}

## 4.2 instance_template ({L('swe_instance')}c)

{fence(P['swe_instance'])}

## 4.3 What `{BR}{BR}command_docs{KET}{KET}` expands to

`enable_bash_tool: false` and `parse_function: function_calling`, so these ARE the agent's entire
action space -- there is no shell, which is the whole contrast with the mini arm and with 3.4.

| bundle | tools |
| --- | --- |
| `aci/tools/scoped_fs` (9) | `scoped_list`, `scoped_view`, `scoped_str_replace`, `scoped_insert`, `scoped_create`, `scoped_search`, `scoped_submit`, `no_op`, `exit_forfeit` |
| `<instance>/_comm_bundle` (3-4) | `list_agents`, `send_message`, `publish_interface`, plus `update_belief` under `--beliefs` |

The bundle is materialized per instance holding ONLY that cell's declarations and bins -- a
declared tool with no bin hard-fails at `agent.setup()`, so the two are selected together.
Verified: regenerating a cell without `--beliefs` drops the `update_belief` bin as well as its
declaration, so a stale affordance cannot leak between cells.

## 4.4 Per-step templates and history

`next_step_template`:

{fence("OBSERVATION:" + chr(10) + BR + BR + "observation" + KET + KET)}

`next_step_no_output_template`: `Your command ran successfully and did not produce any output.`

History processor: `last_n_observations`, n = `--last-n-observations` (default 6; the harness50
runs used 10). It elides only entries typed `observation`, which is why pushed round notices are
never dropped -- that is what makes push delivery immune to the elision bug of CHECKPOINT 9.4.
Contrast 3.4: the paper's single-agent arm elides nothing.

---

# 5. COORD_* -- the study variable, shared by both multi-agent scaffolds

The only text that differs between harness cells, and the only text deliberately identical across
scaffolds: "harness" is what the study varies, so the paragraph defining it must not also vary by
framework.

## COORD_BROADCAST ({L('coord_broadcast')}c)
{fence(P['coord_broadcast'])}

## COORD_P2P ({L('coord_p2p')}c)
{fence(P['coord_p2p'])}

## COORD_BELIEFS ({L('coord_beliefs')}c, appended under `--beliefs`)
{fence(P['coord_beliefs'])}

---

# 6. The ROUND NOTICE -- injected every round, both multi-agent scaffolds

`orchestrate.py::build_notice`. Byte-identical for both backends; only the injection mechanics
differ (SWE-agent `_append_history` with `message_type: "user"`, mini `add_message("user", ...)`).
Injected from round 2 on. **This is the entire delivery mechanism** -- there is no tool an agent
could call to fetch any of it. Neither single-agent arm has one.

Order is deliberate: the registry comes FIRST and repeats every round; messages are new-only. A
contract is state, a message is an event.

## 6.1 A working agent's notice, round 2 ({L('notice_working')}c)

{fence(P['notice_working'])}

## 6.2 An already-submitted agent's notice, round 5, with beliefs ({L('notice_submitted')}c)

`NOTICE_SUBMITTED` replaces `NOTICE_WORKING` for an agent that has already submitted. It exists
because agents are never retired on submission -- peers can only reach an agent while it keeps
taking turns.

{fence(P['notice_submitted'])}

## 6.3 Message expiry

A notice is superseded by the next one, so every earlier notice is pruned. An agent's OWN outgoing
message survives one extra round, because the reply to a question asked in round N-1 only arrives
at the start of round N -- dropping it on the same boundary would show the agent an answer with no
memory of what it asked. Published interfaces are exempt: the registry reprints them every round.

---

# 7. mini x MULTI AGENT -- the superseded v1 system prompt

Kept because **every mini multi-agent result up to and including harness50 was produced with
this text**, so those runs and anything from `bench34_noreq` onward are not comparable on prompt
content. Frozen at `multiagent_pro/prompt_archive/mini_system_v1.txt`; section 2 holds the
current v2.

## 7.1 What changed from v1 to v2

| | v1 (through harness50) | v2 (from bench34_noreq) |
| --- | --- | --- |
| rendered size (broadcast) | {len(P['mini_system_v1_rendered'])}c | see 2.1 |
| reasoning instruction | *"Put a THOUGHT section before it explaining your reasoning"* | *"Before the command, write a short explanation of what you are about to do and why"* |
| editing-safety block | ~25 lines: `>` destroys the file, `>>` only appends, python heredoc read-modify-write, `git diff` after every edit, `git checkout --` to recover, switch approach after two `sed` failures | **removed** |
| "a round spent only talking is a round wasted" | present | removed |
| `no_op` | advertised | **removed** |
| `scoped_submit` | advertised | **removed**; the agent echoes the sentinel itself |
| structure | one flat run of prose | `## Response format` / `## Command examples` / `## Coordination` / `## Rounds...` / `## Rules` |
| subshell rule | absent | stated (every action runs in a new subshell) |

Why each of the three removals was safe or deliberate:

* **THOUGHT** -- a hard fix, not a preference. On `claude5_5_opus` that sentence trips the
  `reasoning_extraction` classifier and the gateway returns an empty completion with no error, so
  `parse_action` finds no bash block and every step becomes a `format_error`: a full-budget run
  producing a 0-line patch that scores like an ordinary bad agent (CHECKPOINT 14.4).
* **`no_op`** -- it never existed for mini. `MiniScaffold._install_tools` only ever installed the
  comm bins, `scoped_submit` and `submit_gate.py`; `no_op` lives in `tools/scoped_fs/bin/` and was
  never copied. Measured: 0 recorded across 40 agent-rounds in `broadcast/mini_swe_agent`, against
  3 and 2 in the `broadcast/swe_agent` cells. v1 advertised a command that returned
  `command not found`.
* **`scoped_submit`** -- a thin wrapper that optionally ran the gate, then echoed the sentinel and
  a `git diff --stat`. The graded patch never came from it (`orchestrate.py` recomputes the diff
  from the worktree), and `has_finished()` matches the sentinel on the first output line of ANY
  command, so echoing it directly is equivalent. **Consequence:** `--submit-gate`'s
  delete-announcement check ran inside that wrapper and is now SWE-agent-only. The independent
  false-attestation guard is unaffected -- the `publish_interface` existence check lives in
  `comm/lib/verify.py` and runs inside the tool.

The editing-safety removal was a deliberate call on the grounds that Opus 5.5 is far stronger than
the gpt-4o-mini that produced the 13.5 failures. Two things it gives up, recorded so a later
regression is recognisable rather than mysterious: the `>`-truncation warning that took a run from
`P2P 0/66` back to working (13.5 v2 -> v3), and the only change-approach-after-refusal guidance
anywhere -- which 14.5 then observed Opus 5.5 itself needing, issuing byte-identical commands on
consecutive steps.

## 7.2 The v1 prompt, rendered for broadcast ({len(P['mini_system_v1_rendered'])}c)

{fence(P['mini_system_v1_rendered'])}
"""


def main():
    P = collect()
    doc = render(P)
    OUT.write_text(doc)
    print(f"wrote {OUT.relative_to(REPO)}  ({len(doc)} chars, {doc.count(chr(10))} lines)")
    # Structural check: no heading may escape a fenced block, which is what happens when a
    # template's own ``` closes the fence early.
    depth, stray = None, []
    for line in doc.splitlines():
        s = line.strip()
        m = re.match(r"^(`{3,})", s)
        if m:
            bars = m.group(1)
            if depth is None:
                depth = bars
            elif bars == depth:
                depth = None
            continue
        if depth is None and s.startswith("#"):
            stray.append(s)
    own = [s for s in stray if re.match(r"^#+ (\d|The |COORD|Chat templates)", s)]
    leaked = [s for s in stray if s not in own]
    print(f"headings outside fences: {len(stray)} ({len(own)} ours)")
    if leaked:
        print("LEAKED from inside a template -- fencing is wrong:")
        for s in leaked:
            print("   ", s[:80])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
