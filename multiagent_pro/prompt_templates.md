# Chat templates, as the model actually receives them

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
| mini x SINGLE | swebp.yaml, 638c (+1 substitution) | the paper's config, in the submodule |
| mini x MULTI | `MINI_SYSTEM`, 4567c rendered | ours |
| swe-agent x SINGLE | tool_use.yaml, 77c | the paper's config, in the submodule |
| swe-agent x MULTI | `SYSTEM_PROMPT`, 1895c rendered | ours |

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
   everything in the instance template -- one line and 638c respectively,
   against instance templates of 1208c and
   2697c. Our multi-agent prompts invert that.
3. **Our two multi-agent prompts differ by far more than tool mechanics.** `MINI_SYSTEM` is
   2.4x the length of `SYSTEM_PROMPT` and carries
   behavioural instructions SWE-agent has no equivalent of. The `COORD_*` fragments are shared on
   purpose (they are the study variable); nothing else is. See `things_to_fix.md` section D.

---

# 1. mini x SINGLE AGENT (the solo baseline, CHECKPOINT 14)

Written by `multiagent_pro/solo/build_solo.py`; templates read from the submodule's
`config/swebp.yaml` at build time so they track upstream. Prompt-compat substitution applied for
Opus 5.5: **True**.

No rounds, no peers, no comm tools, no scope guard, no round notice. One agent, whole repo.

## 1.1 system_template (638c)

Exactly one line differs from the paper's. The original read *"Include a THOUGHT section before
your command where you explain your reasoning process."* -- that trips Opus 5.5's
`reasoning_extraction` classifier, after which the gateway returns an empty completion with no
error and every step becomes a format error (CHECKPOINT 14.4).

````
You are a helpful assistant that can interact with a computer.

Your response must contain exactly ONE bash code block with ONE command (or commands connected with && or ||).
Before the command, write a short explanation of what you are about to do and why.
Format your response as shown in <format_example>.

<format_example>
Your reasoning and analysis here. Explain why you want to perform the action.

```bash
your_command_here
```
</format_example>

Failure to follow these rules will cause your response to be rejected.
To finish, issue the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
without any other command.
````

## 1.2 instance_template (2697c)

`{{working_dir}}` -> `/app`. `{{problem_statement}}` -> the composed
issue: dataset `problem_statement` + `interface`, requirements WITHHELD, all JSON-decoded.

````
<uploaded_files>
{{working_dir}}
</uploaded_files>
I've uploaded a python code repository in the directory {{working_dir}}. Consider the following PR description:

<pr_description>
{{problem_statement}}
</pr_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <pr_description> are met?
I've already taken care of all changes to any of the test files described in the <pr_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Your task is to make the minimal changes to non-tests files in the {{working_dir}} directory to ensure the <pr_description> is satisfied.
Follow these steps to resolve the issue:
1. As a first step, it might be a good idea to find and read code relevant to the <pr_description>
2. Create a script to reproduce the error and execute it with `python <filename.py>` using the bash tool, to confirm the error
3. Edit the sourcecode of the repo to resolve the issue
4. Rerun your reproduce script and confirm that the error is fixed!
5. Think about edgecases and make sure your fix handles them as well
Your thinking should be thorough and so it's fine if it's very long.

## Important Rules

1. Every response must contain exactly one action
2. The action must be enclosed in triple backticks
3. Directory or environment variable changes are not persistent. Every action is executed in a new subshell.
   However, you can prefix any action with `MY_ENV_VAR=MY_VALUE cd /path/to/working/dir && ...` or write/load environment variables from files
4. To finish, issue the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`.
   Do not combine it with any other command.

## Formatting your response

Here is an example of a correct response:

<example_response>
THOUGHT: I need to understand the structure of the repository first. Let me check what files are in the current directory to get a better understanding of the codebase.

```bash
ls -la
```
</example_response>

## Useful command examples

### Create a new file:

```bash
cat <<'EOF' > newfile.py
import numpy as np
hello = "world"
print(hello)
EOF
```

### Edit files with sed:

```bash
# Replace all occurrences
sed -i 's/old_string/new_string/g' filename.py

# Replace only first occurrence
sed -i 's/old_string/new_string/' filename.py

# Replace first occurrence on line 1
sed -i '1s/old_string/new_string/' filename.py

# Replace all occurrences in lines 1-10
sed -i '1,10s/old_string/new_string/g' filename.py
```

### View file content:

```bash
# View specific lines with numbers
nl -ba filename.py | sed -n '10,20p'
```

### Any other command you want to run

```bash
anything
```
````

## 1.3 action_observation_template (867c)

Wraps every command's output. Note the 10,000-character cap with head/tail split, and the
`<returncode>` -- neither of which our multi-agent mini arm has (2.4).

```
<returncode>{{output.returncode}}</returncode>
{% if output.output | length < 10000 -%}
<output>
{{ output.output -}}
</output>
{%- else -%}
<warning>
The output of your last command was too long.
Please try a different command that produces less output.
If you're looking at a file you can try use head, tail or sed to view a smaller number of lines selectively.
If you're using grep or find and it produced too much output, you can use a more selective search pattern.
If you really need to see something from the full command's output, you can redirect output to a file and then search in that file.
</warning>
{%- set elided_chars = output.output | length - 10000 -%}
<output_head>
{{ output.output[:5000] }}
</output_head>
<elided_chars>
{{ elided_chars }} characters elided
</elided_chars>
<output_tail>
{{ output.output[-5000:] }}
</output_tail>
{%- endif -%}
```

## 1.4 format_error_template (604c)

````
Please always provide EXACTLY ONE action in triple backticks, found {{actions|length}} actions.
If you want to end the task, please issue the following command: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
without any other command.
Else, please format your response exactly as follows:

<response_example>
Here are some thoughts about why you want to perform the action.

```bash
<action>
```
</response_example>

Note: In rare cases, if you need to reference a similar format in your command, you might have
to proceed in two steps, first writing TRIPLEBACKTICKSBASH, then replacing them with ```bash.
````

---

# 2. mini x MULTI AGENT

Written by `gen_solver_config.py::build_mini_config` (`--scaffold mini`).

## 2.1 system_template -- rendered for `--comm-mode p2p --beliefs`, rounds=10, steps=6 (4567c)

`{coord}` <- the `COORD_*` fragments (section 5). `{comm_docs}` <- the per-cell
command list (2.3). `{rounds}`/`{steps}` <- the orchestrator's real budget; these
MUST match what `orchestrate.py` actually runs, or the prompt lies to the agent about its own
budget.

````
You are one of several software-engineering agents fixing the same GitHub issue in a shared
repository. Each of you owns exactly one file.

YOUR JOB IS TO EDIT YOUR OWN FILE so the issue is resolved. Coordination exists to serve that;
a round spent only talking is a round wasted. Read your file, work out the change, make it, and
check that it landed.

You may read and edit anything in the repository EXCEPT the files your peers own -- those are
invisible to you, and yours are invisible to them. A command touching a peer's file is refused
without running.

MAKING CHANGES. You have an ordinary shell, so use ordinary tools. Look before you edit and
verify after:

  sed -n '1,60p' path/to/your_file.py        read a range
  grep -n "def some_function" path/to/f.py   find the line to change
  git diff                                   CONFIRM your change is what you meant

NEVER redirect onto a source file with a single `>`. `echo ... > your_file.py` and
`cat > your_file.py` DELETE the entire file and leave only what you just wrote -- every other
class and function in it is gone, nothing can import it any more, and the whole test suite
fails. This is the single most damaging mistake available to you.

`echo ... >>` is not the answer either: it appends to the END of the file, so it cannot put a
method inside a class and cannot replace anything, and running it twice leaves two copies.

For anything structural, read the file, change it in memory, and write it back in one step:

  python - <<'EOF'
  import re
  path = "path/to/your_file.py"
  src = open(path).read()
  src = src.replace("old exact text", "new exact text")   # or insert at a located line
  open(path, "w").write(src)
  EOF

That is safe because the replacement is computed from the file's real current contents. Quoting
inside `sed -i` is easy to get wrong -- if a `sed` command fails twice, switch to the heredoc
above rather than trying a third escaping.

After every edit run `git diff` and read it. If it shows hundreds of REMOVED lines, you have
destroyed the file: recover immediately with `git checkout -- path/to/your_file.py` and redo the
change properly. A patch that deletes the module it was meant to extend scores zero.

COORDINATION. Your peers cannot read your code, so they will not discover the names you choose
-- you have to tell them, and they have to tell you. Ask for what you need, and answer what you
are asked, even if your own file is unfinished.

A message may be addressed to ONE peer by id, or to 'all'. A message addressed to a single
agent is delivered to that agent alone -- no one else sees it, so choose the recipient who can
actually act on it. A published interface always reaches everyone.

You also keep PRIVATE notes on your peers: what each one owns, what they have promised you,
what they still owe you, and whether a claim of theirs has actually shown up in the code. No
peer ever sees your notes, and they are shown back to you at the start of every round. Keep
them current and use them to decide whom to ask for what.

These commands are on your PATH alongside the usual shell tools:
  list_agents                         who your peers are and which file each owns
  send_message <agent_id|all> --message '<text>'
                                      message one peer, or all of them
  publish_interface '<signature>' '<description>'
                                      announce a name peers must code against
  update_belief <agent_id> --note '<text>'
                                      private note about a peer; nobody else sees it
  no_op                               end your turn early and wait for a reply
  scoped_submit                       record your patch (you may run it more than once)

Your response must contain exactly ONE bash code block with ONE command (or commands joined by
&& or ||). Put a THOUGHT section before it explaining your reasoning.

<format_example>
Your reasoning here.

```bash
your_command_here
```
</format_example>

The run lasts 10 rounds. Each round you get up to 6 steps (commands). Messages you
send during a round arrive at your peers at the start of the next one, and theirs arrive the
same way -- so ask early, and keep working while you wait. Published interfaces persist and are
reprinted to everyone every round; messages are not, they arrive once and are then gone.

Your file as it stands at the end of the final round is what gets graded. Run `scoped_submit`
whenever your changes are complete; you can edit and submit again if a peer tells you something
that changes your file.
````

## 2.2 instance_template (73c)

`{{problem_statement}}` <- this agent's own `local_issue.md`, which under
`--route-interface` holds the COMPLETE problem statement and only the interface entries for its
own file.

```
The repository is checked out at {{working_dir}}.

{{problem_statement}}
```

## 2.3 comm_docs, spliced in per cell

p2p (+ beliefs):

```
  send_message <agent_id|all> --message '<text>'
                                      message one peer, or all of them
  publish_interface '<signature>' '<description>'
                                      announce a name peers must code against
  update_belief <agent_id> --note '<text>'
                                      private note about a peer; nobody else sees it
```

broadcast -- `send_message` has NO recipient argument at all. The affordance is withheld rather
than refused, because a declared-but-rejected argument would still tell the model that addressing
exists, which is the variable under test:

```
  send_message --message '<text>'      say something to EVERY peer at once
  publish_interface '<signature>' '<description>'
                                      announce a name peers must code against
```

## 2.4 Templates it does NOT set, and therefore inherits from mini

| template | multi-agent | solo (swebp) |
| --- | --- | --- |
| `action_observation_template` | `Observation: {{output}}` (mini default, 23c) | 867c, 10k cap, `<returncode>` |
| `format_error_template` | mini default, 61c | 604c |
| `timeout_template` | mini default, 234c | not set |
| history processor | none | none |
| `step_limit` | `rounds x steps` = 60 | 250 (the paper's call limit) |
| `cost_limit` | 0 -- INERT, see below | 5.0, a real brake |

Two consequences: raw command output enters context untruncated and with no returncode, and
context growth is unbounded. `cost_limit` is 0 because the multi-agent runs export
`MSWEA_COST_TRACKING=ignore_errors`, under which litellm reports $0.00 -- `step_limit` is the only
ceiling there. The solo arm registers real per-token prices instead (CHECKPOINT 14.6).

---

# 3. swe-agent x SINGLE AGENT (the paper's config, not built by this harness)

`SWE-agent/config/tool_use.yaml`, driven by SWE-agent's own `run-batch`. Its header records the
lineage: *"a fork of 250225_anthropic_filemap_simple_review.yaml ... heavily inspired by anthropic
and openhands"*.

No rounds, no peers, no comm tools, no scope guard, no round notice.

## 3.1 system_template (77c)

One sentence. Everything substantive is in the instance template.

```
You are a helpful assistant that can interact with a computer to solve tasks.
```

## 3.2 instance_template (1208c)

`{{working_dir}}` -> the repo root; `{{problem_statement}}` -> the
instance's composed issue text (3.5).

Near-identical in substance to mini's swebp instance template (1.2) -- same `<pr_description>`
framing, same five numbered steps, same "I've already taken care of all changes to any of the test
files" line. Byte-identical: **False**. mini's is longer because it
additionally carries the response-format rules and shell examples that a function-calling scaffold
does not need.

```
<uploaded_files>
{{working_dir}}
</uploaded_files>
I've uploaded a python code repository in the directory {{working_dir}}. Consider the following PR description:

<pr_description>
{{problem_statement}}
</pr_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <pr_description> are met?
I've already taken care of all changes to any of the test files described in the <pr_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Your task is to make the minimal changes to non-tests files in the {{working_dir}} directory to ensure the <pr_description> is satisfied.
Follow these steps to resolve the issue:
1. As a first step, it might be a good idea to find and read code relevant to the <pr_description>
2. Create a script to reproduce the error and execute it with `python <filename.py>` using the bash tool, to confirm the error
3. Edit the source code of the repo to resolve the issue
4. Rerun your reproduce script and confirm that the error is fixed!
5. Think about edgecases and make sure your fix handles them as well
Your thinking should be thorough and so it's fine if it's very long.
```

## 3.3 Per-step templates

`next_step_template`:

```
OBSERVATION:
{{observation}}
```

`next_step_no_output_template`:

```
Your command ran successfully and did not produce any output.
```

## 3.4 Action space -- THREE tools, and a real shell

`enable_bash_tool: True`, `parse_function: function_calling`,
`execution_timeout: 450`.

| bundle | tools |
| --- | --- |
| `tools/registry` | none declared -- support bundle only (`_read_env` / `_write_env`, the cross-tool state registry) |
| `tools/edit_anthropic` | `str_replace_editor` -- one tool with a `command` enum: `view`, `create`, `str_replace`, `insert`, `undo_edit` |
| `tools/submit` | `submit` |
| (built in) | `bash` -- because `enable_bash_tool` is true |

Bundles loaded: `['tools/registry', 'tools/edit_anthropic', 'tools/submit']`.

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

## 3.5 What fills `{{problem_statement}}`

`SWE-agent/data/instances.yaml` -- 731 instances (the full Pro set), each
carrying one pre-composed `problem_statement` field of ~6000c. Measured on the
first instance: contains `Requirements:` **True**, contains
`New interfaces introduced:` **True**, still JSON-escaped (starts with a
quote, literal `\n` throughout) **True**.

So this arm is the three dataset fields concatenated by
`helper_code/create_problem_statement.py`, exactly as mini's paper arm is -- **requirements
INCLUDED**, and undecoded. Our solo arm (section 1) differs on both counts deliberately: it
withholds requirements and decodes the text (CHECKPOINT 14, `solo/README.md`).

## 3.6 The paper's launch command

Reproduced verbatim from `SWE-agent/sweagent_wrapper_configs/example_config.yaml`. Read it as an
example rather than the published run: `--instances.slice :25` and
`--agent.model.per_instance_call_limit 3` are smoke-test values, and the model pinned here is
Claude 3.7 Sonnet.

```yaml
output_dir: sweagent_results/sweagent/swe_bench_pro_test
sweagent_command: |
  sweagent run-batch \
    --config config/tool_use.yaml \
    --output_dir {output_dir} \
    --num_workers 75 \
    --random_delay_multiplier 1 \
    --instances.type file \
    --instances.path data/instances.yaml \
    --instances.slice :25 \
    --instances.shuffle=False \
    --instances.deployment.type=modal \
    --instances.deployment.startup_timeout 1800 \
    --instances.deployment.runtime_timeout 3600 \
    --agent.model.name anthropic/claude-3-7-sonnet-20250219 \
    --agent.model.api_base $OPENAI_BASE_URL \
    --agent.model.api_key $OPENAI_API_KEY \
    --agent.model.per_instance_cost_limit 0 \
    --agent.model.per_instance_call_limit 3
```

---

# 4. swe-agent x MULTI AGENT

Written by `gen_solver_config.py::build_agent_config` (`--scaffold swe-agent`).

## 4.1 system_template -- rendered for `--comm-mode p2p`, rounds=10, steps=6 (1895c)

Substitution is `str.replace`, never `str.format`: the prompt also carries the jinja literal
`{{command_docs}}` that SWE-agent renders later, and `.format()` would silently
collapse it to `{command_docs}` and break tool documentation for every agent.

```
You are one of several software-engineering agents fixing the same GitHub issue in a shared
repository. You own one file in the repository and you may read and edit anything in this file.

Each agent owns one file. You may read and edit anything in the repository except the files
your peers own; those are invisible to you, and your own file is invisible to them. Run
`scoped_list` to see both lists.

Because your peers cannot read your code, they will not discover the names you choose — you
have to tell them, and they have to tell you. Ask for whatever you need.

The problem statement and requirements below are complete and unedited. What you are not
given is the new interfaces your peers introduce: the interface section lists only the entries
for your own file, plus any that name no file. The names a peer invents are not there.

The run lasts 10 rounds. Each round you get up to 6 steps (tool calls). Messages
you send during a round arrive at your peers at the start of the next one, and theirs arrive
the same way.

A message may be addressed to ONE peer by id, or to 'all'. A message addressed to a single
agent is delivered to that agent alone -- no one else sees it, so choose the recipient who can
actually act on it. A published interface always reaches everyone.

When you write a name a peer must call — a function, class, or signature — announce it with
`publish_interface`, using the exact name you actually wrote. Publishing a name you have not
written is refused by the tool. Published interfaces persist and are reprinted to everyone at
the start of every round. Messages are not — they arrive once at the beginning of the round
and then they are gone.

Your team has 10 rounds to fix the issue. You can submit your patch multiple times. Your
patch as it stands at the end of the final round is what gets graded to resolve the issue.

Available tools:
{{command_docs}}
```

## 4.2 instance_template (89c)

```
You are working in the repository checked out at {{working_dir}}.

{{problem_statement}}
```

## 4.3 What `{{command_docs}}` expands to

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

```
OBSERVATION:
{{observation}}
```

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

## COORD_BROADCAST (187c)
```

Every message you send goes to ALL of your peers at once. There is no way to write to just one
of them, and no way to overhear less than everything: whatever anyone says, everyone gets.
```

## COORD_P2P (254c)
```

A message may be addressed to ONE peer by id, or to 'all'. A message addressed to a single
agent is delivered to that agent alone -- no one else sees it, so choose the recipient who can
actually act on it. A published interface always reaches everyone.
```

## COORD_BELIEFS (336c, appended under `--beliefs`)
```

You also keep PRIVATE notes on your peers: what each one owns, what they have promised you,
what they still owe you, and whether a claim of theirs has actually shown up in the code. No
peer ever sees your notes, and they are shown back to you at the start of every round. Keep
them current and use them to decide whom to ask for what.
```

---

# 6. The ROUND NOTICE -- injected every round, both multi-agent scaffolds

`orchestrate.py::build_notice`. Byte-identical for both backends; only the injection mechanics
differ (SWE-agent `_append_history` with `message_type: "user"`, mini `add_message("user", ...)`).
Injected from round 2 on. **This is the entire delivery mechanism** -- there is no tool an agent
could call to fetch any of it. Neither single-agent arm has one.

Order is deliberate: the registry comes FIRST and repeats every round; messages are new-only. A
contract is state, a message is an event.

## 6.1 A working agent's notice, round 2 (1091c)

```
--- Round 2 begins ---

Interface contracts currently published — these are the EXACT names to code against, and the
exact names you are on the hook for. They stay listed here every round:
  agent_3  def prepare_multipart(fields)
      Returns (body_bytes, content_type_header). Raises TypeError if fields is not a Mapping.

Messages your peers sent you in round 1 (you receive these automatically -- there is no
tool to fetch them, and nothing here will be shown to you twice):
  [agent_4 -> you] What exact name did you give the enum?

Anything you post from now on reaches your peers in round 3, not this one. So:
  * a peer gave you what you were waiting for -> apply it and run `scoped_submit`;
  * your file is already complete and nothing above changes that -> run `scoped_submit` again
    to confirm you are finished (the run continues to the final round regardless, and your
    patch as it stands then is what gets graded);
  * you are still missing something only a peer can give you -> `send_message` to ask, then
    `no_op` to end your turn and wait for the reply next round.
```

## 6.2 An already-submitted agent's notice, round 5, with beliefs (1053c)

`NOTICE_SUBMITTED` replaces `NOTICE_WORKING` for an agent that has already submitted. It exists
because agents are never retired on submission -- peers can only reach an agent while it keeps
taking turns.

```
--- Round 5 begins ---

Interface contracts currently published — these are the EXACT names to code against, and the
exact names you are on the hook for. They stay listed here every round:
  agent_3  def prepare_multipart(fields)
      Returns (body_bytes, content_type_header). Raises TypeError if fields is not a Mapping.

No peer sent you anything in round 4.

Your private notes on your peers (nobody else can see these):
  agent_2: owns urls.py; promised prepare_multipart

You already submitted your patch in round 3. You are being given another turn
because your peers may need something from you -- they can only reach you while you keep
taking turns. Decide from what is above:
  * a peer asked you for something (a name, a signature, where something lives) -> answer with
    `send_message`, or `publish_interface` the EXACT names you wrote in your file;
  * a peer told you something that changes your file -> edit it, then `scoped_submit` again;
  * nothing above concerns you -> run `scoped_submit` again to confirm you are still finished.
```

## 6.3 Message expiry

A notice is superseded by the next one, so every earlier notice is pruned. An agent's OWN outgoing
message survives one extra round, because the reply to a question asked in round N-1 only arrives
at the start of round N -- dropping it on the same boundary would show the agent an answer with no
memory of what it asked. Published interfaces are exempt: the registry reprints them every round.
