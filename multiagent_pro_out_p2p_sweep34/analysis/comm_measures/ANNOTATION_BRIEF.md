# Annotation brief: redundancy, response fulfillment, messages to resolution

READ-ONLY on all run data and harness code. Write only to
`/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_comm_measures/annotations/<arm>/<instance>.json`
(scratch scripts may go in `.../analysis_comm_measures/work_<your letter>/`). Do not rerun agents.

## Inputs per run
- `prep/<arm>/<instance>.json` (in this directory). It contains:
  - `run_dir`;
  - `graph` (gold links with agents, objects and flags; participating agents; topology);
  - `conversations` (one per sending action, i.e. board entry), with `idx`, send `round`,
    `deliver_round`, `from`, `to`, `kind` (directed / broadcast / publication), `deliveries`,
    `on_gold_links`, `addresses_links`, `gold_objects_named`, `text`.
- Raw run data under `run_dir`:
  - `board.json`;
  - `agent_k/traj/round_r.json` (thought / action / observation per step);
  - `agent_k/context/messages.jsonl` (the exact prompt before each step: use it to see what an
    agent could see when);
  - `agent_k/local_issue.md` (that agent's task text);
  - `agent_k.patch` (final diff).
  - Beliefs-arm runs also have `agent_k/beliefs_round_r.json`. These are private notes: never a
    conversation.
- Gold reference slices:
  `/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro/multiagent_pro_bench34_noreq/<instance>/agent_k/gold.patch`.
  This is one valid implementation, not the only correct one.
- Test results:
  - P2P arm only: `/home/asurite.ad.asu.edu/ubiswas2/harness50/p2p/mini_swe_agent/claude_opus_5_5/eval_out/`
    (`eval_results.json`; per instance `multiagent_output.json` and logs).
  - Beliefs and no-interface runs are not graded yet: judge correctness from the task text, the code
    and the gold slice.
- Prior evidence. These are leads only; recompute everything.
  - `/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_star_communication/instances/*.json`
    (detailed P2P star records);
  - `/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_communication/per_instance.json`
    (P2P narratives).

## Communication environment (verified in the harness code)
- **Delivery.** A message sent in round r is delivered at the start of round r+1. All agents in a
  round see the same frozen board. A request/response cycle therefore takes at least 2 rounds.
- **Addressing.** A directed message reaches one agent; `all` reaches every peer.
- **Publications.** A publication is delivered like a broadcast, then reprinted in every later
  round's notice. A reprint is NOT a new sending action.
- **Retention.**
  - A received message stays in the recipient's context for ONE round only.
  - The agent's own sent command text and its own thoughts persist.
- **Workspaces.** Agents cannot see peers' edits: peer files are at the base commit. A guard
  refuses commands naming peer-owned paths, and its substring match can also refuse an agent's
  own file.
- **Rounds.** All 10 rounds run. A message sent in round 10 is never delivered.

## Unit: conversation
One sending action = one board entry: a directed message, a broadcast, or a publication.
Annotate every conversation in `prep` (all of them, keyed by `idx`).

## A. Redundancy (per conversation)

Labels:
- `not_redundant`;
- `partly_redundant`: adds something useful AND repeats available information;
- `redundant`: repeats information already available to the recipient(s) and adds no useful
  coordination function.

For `redundant` and `partly_redundant`:
- Cite the **earlier source** that made the information available to the recipient(s): the
  earlier board#, the round it was delivered, a publication reprint, the task text section, or
  the recipient's own code or thought.
- Explain **why** the later exchange added no useful function.

Do NOT automatically label as redundant:
- the same information reaching a NEW recipient;
- a useful acknowledgement of ownership, commitment or readiness;
- a correction or clarification;
- information repeated because it had disappeared from the recipient's context. That is
  harness-induced. Label it `not_redundant` with `cause: harness_expiry` if restoring it served a
  purpose (the recipient needed it and lacked it). Label it `redundant` with
  `cause: harness_expiry` if the recipient no longer needed it, for example because its code was
  already final and compatible.

Cause (required for redundant and partly redundant; optional otherwise):

| Cause | Meaning |
|---|---|
| `harness_expiry` | repetition because a message expired from context |
| `harness_stale_view` | repetition prompted by seeing base-commit peer code |
| `harness_guard` | repetition caused by a guard refusal |
| `harness_delivery_timing` | crossing messages sent before an answer could arrive |
| `agent_avoidable` | the agent repeated information it had, or could have had, in context |

Also record `function`, one of: proposal, request, answer, acknowledgement, commitment, readiness,
correction, clarification, status, restore_after_expiry, stale_report, restatement, other.

## B. Response fulfillment (per explicit request)

**What counts as a request.** A conversation that explicitly asks someone for an action,
information or confirmation: a question, "please X", "confirm Y". One conversation may contain
several distinct requests; list each.

**Linking.** Link each request to its replies, broadcasts or publications.

**Labels:**

| Label | Meaning |
|---|---|
| `fully` | correct and sufficiently complete |
| `partly` | correct but incomplete, or answers only some of what was asked |
| `incorrect` | the answer is wrong for the requirements or code |
| `unanswered` | no response although there was an opportunity |
| `no_opportunity` | e.g. sent in round 10, so never delivered; or the addressee was retired or locked out |

A response that merely mentions the right object does not necessarily answer the question.

**Answered then forgotten.** An answer that was delivered and later forgotten is still
answered: set `answered_then_forgotten: true` with evidence, for example the asker's later
"I never received a reply" while the prompt dump shows the reply was delivered.

**Eligibility.** A request is eligible unless its label is `no_opportunity`.

## C. Messages to resolution (per gold link)

**What to settle.** For each gold link in `prep.graph.links` (undirected agent pair, with its gold
objects), identify the shared contracts or decisions that needed settling: names, signatures,
return types, defaults, behaviour, ownership. Use the task text, messages, publications and the
final code.

**When a link counts as settled.** When both endpoints hold compatible decisions that are correct
for the requirements, and no later change was needed. Agreement on incorrect behaviour is NOT
resolution.

**Statuses:**

| Status | Meaning | messages_to_resolution |
|---|---|---|
| `initially_settled` | the task text, or compatible independent implementation before any message could be delivered (round 1, or before the first relevant delivery), already settled every contract | 0 |
| `resolved` | settled through communication | the number of conversations on this link (use `prep.conversations[*].on_gold_links`; justify any override) up to and including the settling conversation; list their idx |
| `unresolved` | never settled correctly | null; record the conversations observed |
| `uncertain` | insufficient evidence | null |

Also record:
- `post_resolution_messages`: on-link conversations after settlement;
- `reopened`: board refs where a settled contract was reopened;
- `settling_ref`: board# or `traj agent_k rR sS` for the code edit;
- `settled_round`;
- `correctness_evidence`: code, test or requirement.

Flagged links (import-only, template endpoint, sibling same-name methods): still annotate them,
and note whether the link is real.

## Output schema: `annotations/<arm>/<instance>.json`
```json
{
 "arm": "p2p", "instance": "...",
 "conversations": [{"idx": 0, "function": "proposal", "redundancy": "not_redundant|partly_redundant|redundant",
     "cause": "harness_expiry|harness_stale_view|harness_guard|harness_delivery_timing|agent_avoidable|n/a",
     "earlier_source": "board#3 (delivered r2) | task text §… | publication reprint | own code", "why": "<=200 chars"}],
 "requests": [{"request_idx": 5, "sub": "a", "from": "agent_2", "to": "agent_1|all", "round": 2, "asks": "<=150 chars",
     "label": "fully|partly|incorrect|unanswered|no_opportunity", "response_refs": ["board#7"],
     "answered_then_forgotten": false, "evidence": "<=250 chars"}],
 "links": [{"agents": ["agent_1", "agent_2"], "contracts": ["..."], "status": "initially_settled|resolved|unresolved|uncertain",
     "messages_to_resolution": 0, "messages_counted": [], "settling_ref": "...", "settled_round": 1,
     "post_resolution_messages": 4, "reopened": ["board#9"], "correctness_evidence": "...", "link_real": true, "notes": ""}],
 "notes": ["anything a reviewer should know"]
}
```
Every claim needs an evidence reference: board# (0-based idx in board.json), round, agent ids, or
`traj agent_k rR sS`. Quotes must be verbatim and short. Validate the JSON with `json.load` before
finishing.
