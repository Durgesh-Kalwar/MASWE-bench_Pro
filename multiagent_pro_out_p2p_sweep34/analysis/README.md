# Analysis of the multi-agent SWE-bench Pro runs

This folder measures **how the agents communicated** in our multi-agent runs. Each run puts several
agents on one GitHub issue; each agent owns one file and the agents coordinate only by messages.

Everything here is computed after the fact from the saved run data. Nothing reruns an agent or
changes the harness.

| Folder | What it contains | Status |
|---|---|---|
| `comm_measures/` | Six communication measures for every run, plus a topology label for every problem | done |
| `privacy/` | Three privacy measures: access attempts, successful access, disclosure | in progress |
| `beliefs/` | What the private belief notes reveal about convergence, uptake and retention | in progress |
| `lib/` | Shared code: building the "who depends on whom" graph from the reference patches | done |

Runs covered (48 complete runs, all Claude Opus 5.5, 10 rounds × 6 steps):

| Run configuration ("arm") | Complete runs | Raw data |
|---|---|---|
| P2P (directed or broadcast messages, persistent interface publications) | 33 of 34 | `~/harness50/p2p/...` |
| P2P + beliefs (each agent also keeps private notes about its peers) | 14 of 34 | `~/harness50/p2p_beliefs/...` |
| P2P without `publish_interface` | 1 of 34 | `~/harness50/p2p_nointerface/...` |

The beliefs and no-interface sweeps stopped early when the API budget ran out.

---

## Part 1: What the metrics mean

### Building blocks

**Gold link.** Two agents are linked if, in the reference (gold) solution, one agent's file uses
something the other agent's file introduces or changes: a new function or class, a changed
function signature, a new keyword argument, or an import of the other file. Links describe what the
task *requires* agents to agree on. They come from the reference patches, never from what agents
actually said. Links are undirected.

**Participating agent.** An agent with at least one gold link. Agents with no link (for example the
owner of an HTML template nobody calls) can still talk, but nothing they own needs agreement.

**Gold object.** A name that crosses a gold link: the function, class, keyword or module that the
two agents must agree on.

**Conversation.** One sending action: one directed message, one broadcast to everyone, or one
interface publication. A publication is shown again at the top of every later round, but that
reprint is **not** a new conversation. Number of recipients is recorded separately and never used in
a rate.

### Topology label (one per problem)

Draw the participating agents and their gold links, then apply these rules in order:

| Label | Rule |
|---|---|
| no links | no agent has any gold link |
| disconnected | the linked agents form two or more separate groups |
| star | one agent (the hub) is linked to every other participating agent, and no two others are linked |
| chain | the agents form a single path (and it was not already a star) |
| tree | connected, no cycles, but not a path |
| mesh | connected and containing a cycle (it does not have to be fully connected) |

A label is marked **uncertain** when it would change if links supported only by an import were
removed. Three problems are uncertain this way.

### Graph descriptions (two per problem)

- **Participating agents `k/N`**: k linked agents out of N assigned agents.
- **Graph density `2E / [k(k−1)]`**: E distinct links divided by the number of possible links among
  the k participating agents. 1.0 means every participating pair is linked. N/A when k < 2.

### The six communication measures

| # | Measure | Plain meaning | Formula |
|---|---|---|---|
| 1 | **Directedness** | Did messages go between agents who actually depend on each other? | conversations on a gold link ÷ all conversations |
| 2 | **Relevance** | Did messages talk about things that actually needed agreeing? | conversations naming a gold object ÷ all conversations |
| 3 | **Coverage** | Was every required dependency talked about at least once? | gold links addressed ÷ all gold links |
| 4 | **Redundancy** | How much of the talk repeated what the recipient already had, without serving a purpose? | conversations labelled *redundant* ÷ all conversations |
| 5 | **Response fulfillment** | When an agent asked for something, did it get a correct and complete answer? | requests answered *fully* ÷ requests that could be answered |
| 6 | **Messages to resolution** | How many messages did it take to settle each dependency correctly? | per link: number of messages on that link up to the one that settled it |

Details that matter for reading the numbers:

1. **Directedness.** A directed message counts if its sender and recipient are linked, in either
   direction (a reply against the dependency still counts). A broadcast or publication has no single
   recipient, so it counts if its sender is on a link *and* it names that link's object.
2. **Relevance** is problem-wide: a message counts if it names *any* gold object of the problem, not
   just one belonging to the link it was sent on.
3. **Coverage.** A link counts as addressed if at least one conversation is on that link and names
   one of its objects.
4. **Redundancy** is judged by reading each conversation in context. Labels:
   - *not redundant*;
   - *partly redundant*: added something useful and repeated something; counted separately, not as
     waste;
   - *redundant*: repeated information the recipient already had, with no useful function.

   Each redundant conversation records the earlier source of the information and a **cause**:

   | Cause | Meaning |
   |---|---|
   | harness: expiry | the recipient lost a received message after one round, so it had to be repeated |
   | harness: stale view | the sender saw the unedited copy of a peer's file and reported a problem that wasn't there |
   | harness: delivery timing | sent before an answer could possibly have arrived |
   | harness: guard | caused by a refused command |
   | agent-avoidable | the information was available in the agent's own context |

   **Not** automatically redundant: the same fact reaching a new recipient, a useful acknowledgement
   of ownership or readiness, a correction, or restoring information the recipient had genuinely
   lost and needed.
5. **Response fulfillment.** Every explicit request (a question, "please do X", "confirm Y") is
   linked to its replies and labelled:

   | Label | Meaning |
   |---|---|
   | fully | correct and sufficiently complete |
   | partly | correct but incomplete |
   | incorrect | the answer was wrong for the requirements or code |
   | unanswered | no response although there was an opportunity |
   | no opportunity | e.g. sent in the last round, or to an agent who could not act |

   Requests with no opportunity are left out of the denominator. A request whose answer arrived and
   was later forgotten by the asker still counts as answered, and is flagged *answered then
   forgotten*.
6. **Messages to resolution.** For each gold link, decide what had to be agreed (names, signature,
   return type, defaults, behaviour, ownership) and when both sides held compatible, correct
   decisions:

   | Status | Meaning | Messages counted |
   |---|---|---|
   | initially settled | the task text, or both agents' independent round-1 code, already agreed before any message could arrive | 0 |
   | resolved | settled through communication | messages on the link up to and including the settling one |
   | unresolved | never correctly settled (agreement on wrong behaviour is not resolution) | undefined |
   | uncertain | not enough evidence | undefined |

   The problem-level value is the median over resolved links (zeros included), reported next to the
   number of unresolved and uncertain links. Messages after settlement are recorded separately.

   This is a count of communication **effort**, not time, and a higher count is not automatically
   worse: a harder dependency can need several useful messages.

### What the harness does to communication (verified in the code)

These rules explain much of the redundancy, so the measures report them as causes:

| Rule | Effect |
|---|---|
| Next-round delivery | A message sent in round r arrives at the start of round r+1, so any question-and-answer takes at least two rounds. |
| One-round memory of received messages | A received message stays in the recipient's context for one round only. The agent's own sent messages and thoughts stay for good. |
| Persistent publications | Publications are reprinted every round, so they are never forgotten. |
| Private workspaces | An agent sees only its own edits; peers' files sit at their original, unedited version. |
| Text guard | A guard refuses commands that name a peer's file. It also sometimes refuses an agent's own file whose name contains a peer's file name. |

---

## Part 2: How each metric is implemented

### Pipeline

```
reference patches ──► lib/gold_dependencies.py ──► comm_measures/prep.py ──► prep/<arm>/<problem>.json
run boards + prompts ─────────────────────────────►        │               (graph, topology, conversations,
                                                            │                directedness, relevance, coverage)
                                                            ▼
                         7 annotators, one shared brief (ANNOTATION_BRIEF.md)
                                                            ▼
                                       annotations/<arm>/<problem>.json
                                       (redundancy, requests, link resolution)
                                                            ▼
                                       comm_measures/build.py ──► summary.csv, by_topology.md,
                                                                  conversation_labels.csv, requests.csv,
                                                                  links.csv, validation.md
```

Measures 1–3, the topology label and the graph descriptions are **deterministic**: rerunning the
scripts gives the same numbers. Measures 4–6 need judgment, so they come from **contextual
annotation** of the raw records under one written brief, then the script counts the labels.

### `lib/patch_extract.py`

Small parsers over patch text. `added_lines(patch)` returns the `+` lines (test files excluded).
`defined_names(patch)` returns the functions, classes and constants a patch introduces.

### `lib/gold_dependencies.py`

`gold_graph(instance_dir)` reads each agent's reference slice
(`multiagent_pro_bench34_noreq/<problem>/agent_k/gold.patch`) and draws a link from agent A to agent
B when one of the following holds:

| Evidence | Recorded as |
|---|---|
| A name B's slice introduces appears in A's added lines | the name |
| A function whose definition B's slice changes (taken from B's hunk headers) is used by A | the name, marked `*` (modified) |
| A keyword argument that B's slice implements (`self.x = x`, `:kwarg x`, or `x = self._fallback(x`) is passed by A | `kw:x` |
| A imports B's module | `<import module>` |

### `comm_measures/prep.py`

| Function | What it does |
|---|---|
| `build_graph(problem)` | Calls `gold_graph`, merges both directions of a link into one undirected link, and attaches the link's objects. Flags uncertain evidence (import-only, non-Python endpoint such as a template, sibling classes defining the same method name). Drops links whose only shared name is a generic word (`default`, `type`, `name`, `with`, `value`). |
| `topology(edges)` | Applies the label rules above in order; returns the label and the participating agents. Then recomputes without flagged links; if the label changes, the problem is marked uncertain. |
| density | `2E / [k(k−1)]` from the kept links. |
| `names_in(text, forms)` | Word-boundary match of an object name (so `DataLoader.load_from_file` counts as naming `load_from_file`). Import-only links match the module's dotted path or file name. |
| conversation table | Reads `board.json` and the per-round snapshots `board_after_round_k.json` (to get each message's round). For every board entry it records kind, sender, recipient, deliveries, which gold links it is on (the rules in Part 1), which links it addresses, and which gold objects it names. |
| measures 1–3 | Directedness, relevance and coverage are counted from that table. |

Outputs: `prep/<arm>/<problem>.json` and `prep_summary.json`, which also lists missing runs.

### `comm_measures/ANNOTATION_BRIEF.md`

The written rules the annotators followed: the environment facts above, the exact label sets for
redundancy, requests and link status, what counts as evidence, and the output format. Each
annotator read every board entry, the agents' trajectories (`agent_k/traj/round_r.json`: thought,
command, output per step), and, whenever the question was "could the recipient see this at that
moment?", the exact prompts the model received (`agent_k/context/messages.jsonl`). That last check
is what separates *expired from context* from *ignored*, and *answered then forgotten* from
*unanswered*.

Outputs: `annotations/<arm>/<problem>.json`. Every conversation, request and gold link carries a
label and an evidence reference (`board#k`, round, agent, or `traj agent_k rR sS`).

### `comm_measures/build.py`

Joins the prep files with the annotations and:

1. **Validates.** Every conversation must be labelled exactly once, and the annotated links must
   equal the gold links. Problems go to `validation.md` (currently none).
2. **Computes measures 4–6** per run:
   - redundancy = redundant ÷ all conversations, with partly-redundant and the harness/agent split
     alongside;
   - response fulfillment = fully ÷ (all requests − no opportunity);
   - messages to resolution = median over resolved and initially-settled links, with unresolved and
     uncertain counts alongside.
3. **Writes the results.**

| File | Contents |
|---|---|
| `summary.csv` | one row per run: topology, k/N, density, the six measures, each with its numerator/denominator |
| `by_topology.md` | the six measures pooled by topology, per arm and overall |
| `conversation_labels.csv` | every conversation with its matches and redundancy label |
| `requests.csv` | every request with its responses and label |
| `links.csv` | every gold link with its status, message counts and evidence |

`N/A` marks any rate whose denominator is 0.

### Rerunning

```bash
cd multiagent_pro_out_p2p_sweep34/analysis/comm_measures
python3 prep.py     # rebuilds graphs, topology, conversation table, measures 1-3
python3 build.py    # recomputes measures 4-6 from the annotations and rewrites the CSVs
```

`prep.py` reads the run data from `~/harness50/<arm>/mini_swe_agent/claude_opus_5_5/` and the
reference patches from `multiagent_pro_bench34_noreq/`. The annotations are inputs, not regenerated.

### Known limitations

See `comm_measures/REPORT.md` §5. The most important one: the gold graph misses some real links
(where the shared call sits on an unchanged line of the reference patch) and contains a few spurious
ones. The graph is kept fixed rather than corrected from the conversations, which would make
directedness and coverage circular; the known cases and their direction of bias are listed in the
report.

---

## Results so far

`comm_measures/REPORT.md` has the findings. In one line: coverage was nearly complete (0.98) and
almost every request was answered correctly (0.97). But 132 of 163 dependencies were settled before
any message could matter, and about a quarter of the talk was redundant, 88% of it caused by the
harness (forgotten messages, unedited peer files, crossing messages) rather than by the agents.
