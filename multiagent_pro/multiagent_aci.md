# A multi-agent Agent–Computer Interface (ACI) for SWE-bench Pro

This document describes the **multi-agent ACI** built on top of SWE-agent for the SWE-bench
Pro multi-agent reformulation, the **inter-agent communication interface** that goes with it,
and the **design decisions** behind both. It complements [`README.md`](README.md) (the task
formulation) and lives alongside the implementation under [`aci/`](aci/).

SWE-agent gives a *single* agent an ACI — a small, LM-friendly command set for searching,
viewing, editing, and running code (see `SWE-agent/docs/background/aci.md`). Our setting is
different: **N agents**, each restricted to **its own slice of the repository**, that must
**collaborate** to produce one coherent patch. So we need two things SWE-agent does not have:
per-agent **file scoping** and an **inter-agent communication channel**. This is the prototype
of both.

---

## 1. What "multi-agent" changes about the ACI

In the [formulation](README.md), one Pro instance becomes `M(x) = (A, scope, local,
integrate, grade)`: one agent per gold-patched file, each owning `scope(a_i)` = its gold file
+ K distractor siblings. The single-agent ACI assumes the agent can read and write the whole
repo. Two properties must now hold instead:

1. **Strict scoping** — an agent may read and write *only* the files in its scope; every other
   file is invisible (chosen in planning over "read-any, write-scope"). This is what makes the
   problem genuinely distributed: an agent cannot peek at the file a peer is editing.
2. **Coordination** — because each agent is blind to its peers' files, anything shared across
   files (an interface one agent defines and another must call) has to travel over an explicit
   **communication channel**, not through the filesystem.

`integrate` and `grade` are unchanged: concatenate the disjoint scoped diffs into one
`model_patch` and run it through `swe_bench_pro_eval.py`.

---

## 2. ACI design decisions

### 2.1 Where scope is enforced — tool layer, not the filesystem

SWE-agent enforces nothing about *which* files a tool may touch; its only gate is
`ToolHandler.should_block_action`, which blocks a few interactive shells. We considered three
enforcement boundaries:

| Option | How | Verdict |
| --- | --- | --- |
| **Tool layer** (chosen) | Every file tool checks the path against an allowlist before acting | Faithful to "the restriction is part of the ACI", keeps the full repo intact for clean `git diff`, simple |
| Filesystem isolation | Materialize only scope files (sparse checkout / per-agent worktree) | Heavier; complicates `git diff` and running code; the repo state diverges from grade-time |
| Container per file-set | One container exposing only the scope | Wasteful; still needs tool cooperation for new files |

We enforce at the **tool layer**: a set of `scoped_*` tools that consult the agent's allowlist
and refuse out-of-scope paths. The repo stays whole on disk, so each agent's contribution is
just `git diff -- <scope files>` at the end.

### 2.2 Closing the bash escape hatch

A path-checking file tool is pointless if the agent also has raw `bash` (it could `cat`/`sed`
anything). So the solver config sets **`enable_bash_tool: false`**, which SWE-agent only
permits with the `function_calling` (or `json`) parser. With bash gone and only our registered
function tools available, **the model can reach the filesystem solely through the scoped
tools** — the allowlist becomes a hard boundary, not a suggestion. `should_block_action` is
kept only as a belt-and-suspenders net; it cannot do path scoping itself.

### 2.3 The scoped tool surface (`aci/tools/scoped_fs/`)

A compact, self-contained ACI mirroring SWE-agent's primitives, every one funneling its path
argument(s) through `require_scope()`:

| Tool | Role | Scope rule |
| --- | --- | --- |
| `scoped_list` | list the files you may edit (+ line counts) | shows the allowlist; in full mode shows the primary file + the peer-owned deny list |
| `scoped_view <path> [start] [end]` | windowed, line-numbered file view (100-line window) | denies out-of-scope paths |
| `scoped_str_replace <path> <old_str> <new_str>` | unique exact-match edit | denies; refuses non-unique/0 matches; **rejected (unapplied) if it breaks `.py` syntax** |
| `scoped_insert <path> <line> <text>` | insert after a line | denies out-of-scope; **rejected (unapplied) if it breaks `.py` syntax** |
| `scoped_create <path> <file_text>` | create a NEW in-scope file (e.g. a gold-added module) | path must still be in the allowlist; **rejected if `file_text` has a `.py` syntax error** |
| `scoped_search <term> [path]` | literal-substring search over scope files (whole repo minus denied files in full mode) | never lists out-of-scope / peer-owned files |
| `scoped_submit` | end the episode, emit the diff (writes `/root/model.patch`) | with `SUBMIT_GATE`: refused until the agent has read the board **once** and announced any public-symbol removal (see §2.5) |
| `no_op` | pass: end this agent's turn for the CURRENT round without submitting | prints `###MULTIAGENT-NO-OP###`; the orchestrator stops stepping the agent for the round and brings it back next round |
| `exit_forfeit` | give up and end the episode without submitting | — |

Two enforcement subtleties: paths are `Path.resolve()`d before comparison, so `../` and
absolute-path escapes normalize to a non-allowlisted path and are denied; and `scoped_search`
*post-filters to scope*, so an agent can't enumerate hidden files by grepping.

**Lint-on-write syntax check (added after the first real solve-mode run):** the first time an
agent's collected patch actually reached the Pro evaluator, it scored 0% because `scoped_insert`
had spliced a `def` into the middle of an existing `try:`/`except:` block, producing an
`IndentationError` that broke the module's import entirely — every test in the file failed to
even collect. SWE-agent's own single-agent toolset has exactly this safety net
(`edit_linting`/`windowed_edit_linting`: run flake8 after every edit, reject it if new errors
appear), but per §2.4 its underlying `flake8_utils.py`/`windowed_file.py` don't exist in this
checkout, so nothing was portable as-is. `aci/tools/scoped_fs/lib/scoped.py` now has
`check_syntax(path, text)` — a dependency-free `.py`-only check via stdlib `compile()` (not
flake8: it's after syntax-breaking edits specifically, not style) — wired into
`scoped_str_replace`/`scoped_insert`/`scoped_create`. A syntax-breaking edit is rejected before
ever touching disk: the model sees the exact `SyntaxError`/`IndentationError` and the file is
left untouched. Verified against a real Pro image container by reproducing the exact failing
edit above (correctly rejected) and confirming a valid edit on the same file still succeeds.

**`exit_forfeit` (added alongside the syntax check):** SWE-agent's own repeated-format/error
templates unconditionally tell the model "please run `exit_forfeit` (if available) or submit"
— this text ships with SWE-agent itself, independent of what we bundle. Without the tool
bundled, that instruction was a dead end. `aci/tools/scoped_fs/bin/exit_forfeit` just emits the
literal token SWE-agent's run loop watches for (`agents.py`'s `EXIT_FORFEIT_TOKEN`); it needs no
scope awareness since it ends the episode without touching any file.

### 2.4 Why self-contained (no delegation to SWE-agent's own tools)

The plan originally delegated to SWE-agent's real `open`/`str_replace_editor` bins (hidden via
`hidden_tools`). During implementation we found this fork's tool bundles import library
modules (`registry.py`, `windowed_file.py`, `flake8_utils.py`) from `tools/*/lib/` that are
**absent from the checkout** — so the stock bins would crash. The scoped bundle is therefore
**fully self-contained**: it implements its own windowed view/edit/search in pure Python and
reads its configuration from shell env vars, depending on nothing under `tools/*/lib/`.

### 2.5 How an agent learns its scope — env vars, not the registry

SWE-agent's registry (`_read_env`) also needs the missing `lib/`, so we avoid it. Instead the
per-agent values are injected as **`agent.tools.env_variables`**, which SWE-agent `export`s
into the persistent bash session before the first action; the bins read `os.environ`:

| Var | Meaning |
| --- | --- |
| `SCOPE_FILES` | JSON array of the agent's allowlist (gold file + distractors); in full mode, just its primary file |
| `SCOPE_MODE` | `allow` (default; `SCOPE_FILES` is a strict allowlist) or `full` (denylist — see below) |
| `SCOPE_DENY` | full mode only: JSON array of files the agent may NOT touch (peers' gold files); empty otherwise |
| `SUBMIT_GATE` | `"1"` when configs were generated with `--submit-gate`, else `""` (gate off) |
| `REPO_ROOT` | repo checkout dir in the image — **`/app` on Pro images, not `/testbed`** |
| `AGENT_ID` | this agent's id (`agent_2`) |
| `COMM_BOARD` | path to the message board inside the container |
| `AGENTS_ROSTER` | JSON `[{id, gold_file}]` of all peers |

**Full-access mode (`--distractors -1`).** When the build is run with `--distractors -1`,
scoping inverts from allowlist to **denylist**: `SCOPE_MODE=full` and `SCOPE_DENY` lists the
other agents' gold files. `require_scope()` then permits any path **inside the repo** that is
not in `SCOPE_DENY` (and denies paths outside the repo). The tool surface adapts: `scoped_list`
prints "full access except (peer-owned): …", `scoped_search` walks the **whole repo** (skipping
`.git/` and denied files) instead of only the scope, and `scoped_submit` emits an **unscoped**
whole-repo diff. Correspondingly, `orchestrate.py` collects each agent's final patch as an
unscoped `git diff` (the agent's `scope` is no longer the edit boundary). Since agents may now
edit the same non-gold file, `merge` warns on overlapping file paths and the concatenated patch
may fail `git apply` — surfaced honestly, not reconciled.

**Lockstep rounds + `no_op` (orchestrator, always on).** The board is frozen at the start of
each round: every agent in that round is handed the identical snapshot, and everything posted
during the round is published only at the round barrier. So an agent reads peers' messages
from **previous rounds only** — turn order within a round confers no information advantage
(previously the board was merged after *each* agent's turn, so later agents saw earlier ones'
same-round messages).

**Delivery is push, not pull — there is no read tool.** At the barrier the host computes, per
agent, which of the round's new messages that agent is entitled to (`visible_to`: peer-authored
and addressed to it or broadcast) and injects them into its model context before its next turn,
as part of the round notice (`orchestrate.py::build_notice` / `_notify_round`). Because the
barrier already partitions messages by round, each one is delivered exactly once to each
eligible recipient **by construction** — no read cursor exists any more. Two consequences:
receiving costs no step, so what differs between communication harnesses (§2.7) is topology
rather than tool-call discipline; and the injected turn is `message_type: "user"`, which
`last_n_observations` never elides, so the loss described in §2.6 can no longer happen to a
peer's message.

**Contracts are state, messages are events.** The notice therefore has two parts. Messages are
new-only. Interface contracts are re-rendered in FULL every round — an always-current registry
(`interface_registry`, newest-wins per author+symbol) listing every contract anyone has
published, the agent's own marked `<- yours`. Retention was never the problem here (an agent's
own actions and pushed deliveries are both elision-exempt); *salience* was: a contract announced
in round 1 sits dozens of turns back by round 4, which is exactly the state §9.4 recorded when an
agent that held an interface invented its own anyway. Re-publishing a corrected signature
supersedes the old row, so peers see one current contract instead of two contradictory messages.
An interface still arrives as an ordinary message the round it is published, so the transcript
keeps showing *when* each contract appeared.

Every agent gets a turn **every round, including agents that already submitted**, so a peer's
later question can still be answered; the run stops once every still-active agent submits
within the *same* round. An agent ends its turn by `scoped_submit`, by `no_op` (a pass — "I'm
missing information only a peer can give me"; it returns next round), or by exhausting its
step budget. Only `exit_status` starting with `submitted` counts as a submission — the ~10
other causes of SWE-agent's `done` (`exit_cost`, `exit_context`, `exit_format`,
`exit_command_timeout`, `exit_forfeit`, `exit_error`, …) retire the agent permanently instead,
and `agent.step()` is wrapped so a re-raised `TotalCostLimitExceededError` can't abort the run
before diff collection.

**Partitioned issue text (`--partition-issue`, build-time).** The default local info makes
cooperation optional (every agent holds the full issue, which spells out the whole cross-file
contract — measured: zero comm-tool calls across full qwen/gpt-4o-mini runs). With
`--partition-issue`, each `local_issue.md` holds only that agent's exclusively-routed slice
(definer-priority routing: units naming symbols an agent's gold diff *introduces* go to that
definer, so consumers must ask over the board for the names), plus symbol-free shared context.
Pure build-time change — no runtime env var; the solver sees it only as different
problem-statement content.

**Submit gate (`--submit-gate` at config-gen, OFF by default).** When `SUBMIT_GATE` is set,
`scoped_submit` runs `scoped_fs/lib/submit_gate.py` before any git work and REFUSES (prints
the reason, exits 0, emits **no** submission markers and **no** `/root/model.patch`, so the
episode continues) until:
**Publish-check** — any public `def`/`class` deleted by the agent's edits (HEAD vs
   worktree, `ast`-parsed, `_`-prefixed names exempt) has been announced in one of the
   agent's own board messages (name match against its `publish_interface`/`send_message`
   texts). Deleting a whole class also flags its public methods — one message naming all of
   them satisfies the check. Targets the observed contract-break failures (`HostState`,
   `_is_fqcn`).

*Superseded:* the gate also used to require that the agent had run `read_messages` (once ever,
then once per round). Push delivery leaves nothing for an agent to fail to check and no tool it
could run to satisfy such a gate, so that half was deleted rather than relaxed — keyed on
sidecar files only `read_messages` wrote, it would have become an unconditional block.

The check is a pure refusal — the harness never calls a comm tool on the agent's behalf;
the refusal text says exactly what to run. Internal gate errors fail OPEN (submission
proceeds) so the gate can never strand an agent. Escape hatch: `exit_forfeit`.

### 2.6 Context management — `--last-n-observations`

Mechanism is SWE-agent's, unchanged: the solver config carries a `last_n_observations` history
processor, plus SWE-agent's per-observation truncation. The scoped windowed view keeps
individual observations small, exactly as the single-agent ACI intends. What *is*
multi-agent-specific is the choice of N, which `gen_solver_config.py --last-n-observations N`
exposes (default 5, the SWE-agent 0.7 default).

**What the processor actually does.** It is applied at *query* time in `DefaultAgent.messages`
(`agents.py:534-546`) and never mutates `self.history` — the trajectory on disk is always
complete; only what the model sees is trimmed. All but the newest N entries with
`message_type == "observation"` have their text replaced by `Old environment output: (K lines
omitted)`. Three properties matter here:

- **Actions and thoughts are never elided** — the agent always remembers what it *did* and
  said, only what the tools *replied* is dropped.
- **The first observation is never elided** — it is the instance template
  (`history_processors.py::_get_omit_indices` slices `[1:...]`).
- **The window spans the whole run, not a round.** SWE-agent has no notion of rounds; N=5 with
  `--steps-per-round 25` means an agent starts round 2 having lost every observation from
  round 1 but the first.

**Historical hazard, now structural.** Under the old *pull* design this window also elided
`read_messages` output — and because `read_messages` was **unread-only** (per-agent
content-digest cursor), a peer's message that scrolled out could **never be retrieved again**.
Observed on `b748edea` at N=5: `agent_4` received `agent_3`'s `prepare_multipart` interface,
lost it to elision mid-round, and re-invented a competing `prepare_multipart_payload`
(CHECKPOINT §9.4). Push delivery removes this by construction — peer messages arrive as
`message_type: "user"`, and `_get_omit_indices` only ever selects entries typed `"observation"`.

N therefore now bounds only the agent's **own** file views. **Rule of thumb: N ≥
`--steps-per-round`,** so a full previous round of them survives. Note that N never fixed
*adoption* — an agent holding an interface may still invent its own (§9.4) — and that a large N
is not free: it raises per-step prompt size, so `--per-instance-cost-limit` must rise with it.

The default stays 5.

---

### 2.7 Communication harnesses — the study variable

Coordination behaviour is what this scaffold exists to measure, so the *shape* of the
communication channel is a selectable cell rather than a fixed design (`gen_solver_config.py
--comm-mode {broadcast,p2p} [--beliefs]`). Three cells are currently studied:

| cell | `send_message` reaches | `publish_interface` | private peer notes |
| --- | --- | --- | --- |
| `broadcast` | every peer; the tool has **no recipient argument** | every peer | — |
| `p2p` | one named peer (that agent alone) or `all` | every peer | — |
| `p2p --beliefs` | as p2p | every peer | `update_belief`, replayed each round |

**Why the affordance is withheld, not just refused.** In broadcast mode the model must not see
a `to` parameter at all — a declared-but-rejected argument still tells the model that addressing
is a thing, which is precisely the variable under test. SWE-agent builds function schemas from
`<bundle>/config.yaml` at a fixed path, so the bundle cannot be switched at run time; instead
`gen_solver_config.py` **materializes** `<id>/_comm_bundle/` per instance, containing only that
cell's declarations (selected from `comm/tool_defs.yaml`) and only the matching bins. Bin
selection and declaration selection have to move together: a tool declared with no bin
hard-fails at `agent.setup()` (`tools.py::_check_available_commands`). `send_message` still
re-forces `to = "all"` from `COMM_MODE` in broadcast mode, so the topology holds even if a model
somehow supplies one. Materializing also archives the exact harness beside the run, and
`<id>/comm_mode.json` records the cell so `orchestrate.py` reads it from one source of truth
rather than a flag that could disagree with the bundle the agents are running.

**Beliefs are a mechanism, not a prompt.** `update_belief <peer> --note` writes
`/root/comm/.beliefs_<AGENT_ID>.json` — never merged into the board, never shown to a peer. The
host replays the current table into each round notice (consistent with there being no read tool)
and archives it as `<id>/<agent>/beliefs_round_N.json`, keeping every revision, so belief
accuracy and drift are scoreable against ground truth afterwards. The no-belief cell must infer
whom to address from the message stream itself.

**Known confound.** Broadcast and p2p differ in *context volume* as well as topology: a
broadcast agent receives every message, a p2p agent only what is addressed to it plus
interfaces. `<id>/comm_stats.json` records per agent per round the messages received, sent
(directed vs broadcast), interfaces published and **refused**, `no_op`s and belief updates —
report those alongside the grade rather than the grade alone.

**Not a property of the cells:** peer *identity*. `list_agents` is present in every cell, so a
broadcast agent can still write "agent_3: I need X" into a message body. Broadcast means no
addressed *delivery*, not anonymity.

## 3. Communication interface design decisions

Because scope is strict, coordination needs its own channel. It is a second tool bundle,
`aci/tools/comm/`.

### 3.1 Topology — host-mediated blackboard

We chose a **shared message board (blackboard)** over directed point-to-point sockets or a
central coordinator agent: it is the simplest model that supports both broadcast (an interface
everyone may need) and addressed messages, and it leaves a complete, inspectable transcript
(`board.json`). Each container holds a local copy at `COMM_BOARD`; the **host orchestrator owns
the canonical board** and syncs it in/out each round (§4). A coordinator-agent topology was
rejected as overkill for a prototype; directed sockets were rejected because agents live in
separate containers with no shared network namespace.

Agents only ever **write** to their local copy. The host does all the reading, computing each
recipient's mail at the barrier and pushing it into that agent's context (§2.5) — which is what
lets the delivery *topology* be varied per cell (§2.7) without changing the transport. The board
in the container is still written back in each round because the bins append to it and
`--submit-gate`'s publish-check needs the agent's own past announcements.

### 3.2 Message content — structured, not just freeform

Deliberately including a *structured* contract primitive, so the most important cross-file fact
(a signature) is first-class rather than buried in prose. There is **no read tool** — messages
are pushed (§2.5) — and the exact tool set depends on the communication harness (§2.7):

| Tool | Cells | Purpose |
| --- | --- | --- |
| `list_agents` | all | see every peer and the file it owns (whom to ask) |
| `send_message <message>` | broadcast | freeform message to every peer; no recipient argument exists |
| `send_message <to> <message>` | p2p | freeform message to ONE peer by id, or `all` |
| `publish_interface <signature> <description>` | all | **broadcast a contract** you own — a signature peers must code against. Refused if the symbol does not exist in a file you own. Unlike a message, it is re-listed in every later round notice |
| `update_belief <about> <note>` | `--beliefs` | PRIVATE per-peer note, never posted; replayed to you each round |

`publish_interface` is the dynamic counterpart to the static `interface` field: when the Pro
dataset declares a new public interface, `--include-interface` seeds the board / coordination
note with it; agents can also negotiate/announce one at runtime when the dataset declares none.

### 3.3 Synchronization — round-based barrier

Messages propagate at a **round barrier**, not instantly. Within a round each agent runs a
bounded number of `step()`s against the board **frozen at the start of that round** — every
agent in the round gets byte-identical state — and the orchestrator only merges everyone's new
messages into the canonical board once the round ends. So a message is delivered exactly one
round after it is posted, regardless of who posted it or in what order agents run — and exactly
once, since the barrier itself partitions messages by round (there is no read cursor). This
gives
deterministic, debuggable turn-taking, removes any turn-order information advantage, and avoids
racing on a shared file. The merge de-duplicates by `(from, ts, to, text, signature)`.

(Earlier revisions merged the board after *each agent's turn*, so agent *k* saw agents
1…*k*−1's same-round messages while agent 1 saw none — turn order silently decided who knew
what. That is fixed; see §2.5.)

---

## 4. Container model & the round loop

**One container per agent.** SWE-agent's `DockerDeployment` always starts a fresh,
uniquely-named container, and its registry/state live at hardcoded single paths — so agents
cannot safely co-tenant one container. Each agent therefore gets its own container from the
**same Pro image at the same `base_commit`**; the board is the only shared state, mediated by
the host.

`aci/orchestrate.py` drives it:

```
for each agent: start SWEEnv from its solver.yaml (env.start)            # one container each
board, deliveries = [], []                        # `deliveries` = last round's new messages
for round in 1..R:
    frozen = board                                # FROZEN: identical for every agent
    submitted, pending = {}, []
    for each agent not permanently retired:       # includes agents that already submitted
        env.write_file(COMM_BOARD, frozen)        # bins append here; publish-gate reads it
        mine = [m for m in deliveries if visible_to(m, aid)]    # THIS agent's mail
        beliefs = read_beliefs(env, aid)                        # --beliefs cell only
        notify_round(agent, mine, beliefs)        # PUSHED into context -- there is no read tool
        run up to `steps_per_round` of agent.step()
            # turn ends on: no_op marker (pass, returns next round)
            #             | done + exit_status "submitted*"  -> submitted[aid]
            #             | done otherwise (exit_cost/context/format/...) -> retire agent
        pending += messages this container added on top of `frozen`
        archive <agent>/beliefs_round_N.json       # --beliefs cell only
        comm_stats row: received / sent_directed / sent_broadcast / published / refused / no_op
    board = merge(board, pending)                 # PUBLISH once, at the round barrier
    deliveries = board[len(frozen):]              # exactly this round's new messages
    stop if every still-active agent submitted THIS round
for each agent: agent.patch = env.communicate("git diff ... | base64 -w0")   # scoped diff
# integrate + grade (unchanged):
build_multiagent_pro.py --mode merge  ->  patches.json  ->  swe_bench_pro_eval.py
```

Delivery is **exactly-once by construction**: `deliveries` holds precisely the messages published
at the previous barrier, so each one is offered to each eligible recipient in exactly one round
and never again. That is why no read cursor exists — the barrier itself is the cursor.

The per-agent `git diff -- <scope>` guarantees each contribution is scope-clean even if a
distractor was touched, and the integrate→grade path is byte-for-byte the existing one.

---

## 5. Usage

```bash
# 0) Stage 1/2 (see README): sample + build the multi-agent specs (offline docker distractors)
python multiagent_pro/sample_instances_pro.py --instances <id>
python multiagent_pro/build_multiagent_pro.py --mode build --instances <id> \
    --distractor-source docker --distractors 3 --include-interface --emit-gold

# 1) Generate one SWE-agent solver config per agent (+ roster.json, comm_mode.json,
#    _comm_bundle/). The COMMUNICATION HARNESS is chosen HERE, not at run time -- it decides
#    which comm tools exist in the bundle and what the system prompt says, so switching cells
#    means regenerating solver.yaml. Give each cell its own --output root (see README 2.1).
python multiagent_pro/aci/gen_solver_config.py --instances <id> --model claude-sonnet-4-6 \
    --comm-mode broadcast              # send_message reaches everyone; NO recipient argument
python multiagent_pro/aci/gen_solver_config.py --instances <id> --model claude-sonnet-4-6 \
    --comm-mode p2p                    # (default) may address ONE peer by id, or 'all'
python multiagent_pro/aci/gen_solver_config.py --instances <id> --model claude-sonnet-4-6 \
    --comm-mode p2p --beliefs          # p2p + private per-peer notes (update_belief)
#    Full per-cell recipe, incl. keys, grading and how to read comm_stats.json: README 2.1.

# 2a) Validate the configs without starting anything. NOTE this only checks that solver.yaml
#     parses under RunSingleConfig -- it never reaches agent.setup(), so it does NOT catch a
#     declared-tool/missing-bin mismatch in the generated bundle.
python multiagent_pro/aci/orchestrate.py --mode dry --instances <id>

# 2b) Offline end-to-end check (no LLM): apply each agent's gold patch in-image, scope-diff,
#     integrate, and grade through the Pro harness
python multiagent_pro/aci/orchestrate.py --mode gold --instances <id> --grade

# 2c) Real multi-agent solving (needs model API keys). orchestrate builds the swe-rex
#     runtime image automatically on first use; this pre-builds it explicitly if you want.
python multiagent_pro/aci/build_runtime_image.py <pro_base_image>
python multiagent_pro/aci/orchestrate.py --mode agents --instances <id> \
    --rounds 4 --steps-per-round 6 --grade
```

### The swe-rex runtime image (why `agents` mode needs a derived image)

SWE-agent boots each agent with **SWE-ReX**, which must run a `swerex-remote` server *inside*
the container. Both of SWE-ReX's stock ways to get one fail on the Pro images:

- With `python_standalone_dir` set, SWE-ReX compiles a standalone CPython 3.11 on
  `python:3.11-slim` (**glibc 2.36**) and copies it into the base image. The Pro images are
  Ubuntu 20.04 (**glibc 2.31**), so the copied binary can't even run `--version` — this was the
  original `RUN .../python3 --version` boot crash.
- With `python_standalone_dir: None`, SWE-ReX uses the image's own `python3`. Pro images ship
  **Python 3.9.5**, but `swe-rex` needs **≥ 3.10**, so that path can't run it either.

`multiagent_pro/aci/build_runtime_image.py` resolves this by baking a swe-rex server into a
**derived image, once per Pro base**: it drops in a portable
[python-build-standalone](https://github.com/astral-sh/python-build-standalone) CPython 3.11
(built for glibc 2.17+, so it runs on 2.31), `pip install`s `swe-rex==1.2.0` into it (via
`--index-url https://pypi.org/simple`, because the Pro images pin an offline mirror at
`127.0.0.1:9876`), and symlinks `swerex-remote` onto `PATH`. The derived tag is content-addressed
(`swerex-runtime:<sha16>` of base+version+tarball) and cached — rebuilt only when an input
changes. `gen_solver_config.py` then emits `deployment: {image: <derived tag>,
python_standalone_dir: null, pull: never}`, so at solve time SWE-ReX simply execs the
pre-installed `swerex-remote` — **no per-run compile, no in-container network**. The base image's
own Python 3.9.5 (which the tool bins and the repo use) is left untouched.

Artifacts (added to the per-instance tree from the README):

```
multiagent_pro_out/<id>/
├── roster.json                 # [{id, gold_file}] surfaced by list_agents
├── board.json                  # (agents mode) full message transcript
└── agent_<k>/
    ├── solver.yaml             # generated SWE-agent config (bash off, scoped+comm bundles)
    ├── local_issue.md          # full issue + this agent's focus highlight
    ├── gold.patch              # oracle (only with --emit-gold)
    ├── agent_<k>.patch         # this agent's scoped diff (orchestrator output) -> merge
    └── traj/                   # SWE-agent trajectory (agents mode)
```

---

## 6. Verification performed

- **Scope enforcement (host + real image).** `scoped_*` tools allow in-scope reads/edits and
  **deny** out-of-scope paths, including `../` and absolute-path escapes. Verified both on the
  host and **inside the real Pro image** (Python 3.9.5, repo at `/app`): the owned 451-line
  file is viewable; a peer's file is denied.
- **Communication.** Delivery partition over a synthetic multi-round board: peer-only,
  addressing respected, each message delivered exactly once per recipient, no self-delivery.
  In the real Pro image: broadcast `send_message` writes `to: "all"` even when handed a peer
  id; p2p rejects unknown recipients and self-sends; `publish_interface` refuses a symbol
  absent from the agent's files and accepts one present (and fails open on a non-Python scope
  or an unparseable signature); `update_belief` round-trips with per-round history;
  `list_agents` shows the roster.
- **Config validity.** Every generated `solver.yaml` parses under SWE-agent's own
  `RunSingleConfig`: bash disabled, `scoped_fs` plus the selected `comm` tools exposed (the
  model-visible function schemas were asserted per cell: no `read_messages` anywhere,
  `send_message` carries a `to` property only in p2p, `update_belief` only with `--beliefs`),
  every declared tool has a matching bin, bundles
  resolved by absolute path, `submit_command: scoped_submit`.
- **End-to-end integrate→grade (gold mode).** Per-agent scoped diffs are captured **inside the
  real container** (`git diff -- <scope>` after applying the gold hunks at `base_commit`),
  merged, and graded **`true` / accuracy 1.0** through `swe_bench_pro_eval.py --use_local_docker`
  for `instance_ansible__ansible-f327e65d…` — confirming the multi-agent pipeline grades
  identically to the single-agent gold, with no evaluator change.
- **swe-rex boot + tool install (agents mode, no LLM).** The derived runtime image boots a real
  agent env in ~1 s (`env.start()` → `swerex-remote` up, repo reset to `base_commit` at `/app`),
  and `agent.setup()` installs both bundles into it. Exercised without any model call:
  `scoped_list`/`scoped_view` allow the owned file and **deny** an out-of-scope path, `SCOPE_FILES`
  propagates, and `list_agents` shows the roster — the entire `agents` path minus the paid
  `agent.step()`.

---

## 7. Limitations & open runtime spikes

- **`agents` mode boots (swe-rex spike resolved).** `env.start()` + tool install are now verified
  end-to-end on the derived runtime image (see §5 and the runtime-image note in §2); the only thing
  a real run still adds is (a) model API keys and (b) the paid `agent.step()` loop. Note the
  generated `solver.yaml` defaults to `claude-sonnet-4-6`; if only `OPENAI_API_KEY` is set, pass
  `--model gpt-4o-mini` (or similar) to `gen_solver_config.py`.
- **Missing SWE-agent tool libs.** This fork lacks `tools/*/lib/`; our bundles are
  self-contained to sidestep that. If you later restore those libs you could swap in SWE-agent's
  richer windowed editor (with flake8 lint-gating) behind the same scoped wrappers.
- **Distractors are still solution-aware.** Scope contains the gold file (plus decoys); a
  module/dir-based, solution-agnostic scoping variant remains future work (a non-goal here).
- **Coordination quality is emergent.** The board enables coordination but does not enforce it;
  whether agents actually converge on a shared interface is exactly what this harness is for
  measuring. Round count and steps-per-round are the main knobs.
- **One container per agent** is simple but N× the memory/boot cost. A shared-container variant
  (one deployment, per-agent bash sessions, namespaced registry/state) is possible but needs
  changes to SWE-agent's hardcoded `/root/.swe-agent-env` and `/root/state.json` paths.
