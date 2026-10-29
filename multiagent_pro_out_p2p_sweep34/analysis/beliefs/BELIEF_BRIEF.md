# Brief: belief-enabled run analysis (shared by all analysts)

READ-ONLY on run data and harness code. Write only to
`/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_beliefs/instances/<instance>.json`
(scratch in `.../analysis_beliefs/work_<letter>/`). Do not rerun agents.

## What the belief records are (verified in tools/comm/bin/update_belief, lib/board.py, orchestrate.py, prompt dumps)
- Agents record free-text notes **about a peer** (`update_belief <peer> --note '...'`), prompted to cover
  "what each one owns, what they have promised you, what they still owe you, and whether a claim of theirs
  has actually shown up in the code". Notes are about peers only; the tool refuses a note about oneself.
- Each update **replaces** the author's current note on that peer and appends `{round, note}` to that
  peer's `history`. So the current note is a snapshot of the author's belief *about that peer*, written
  selectively (the author chooses what to include); the full revision history survives in `history`.
  **A proposition absent from a newer note is NOT evidence it was forgotten**; only an explicit
  contradiction ("no reply ever arrived", "that was made up") is.
- Timing: an update is a tool call at a known (round, step), so it can be ordered against message
  DELIVERY (start of round r+1 for a message sent in round r) and code edits (steps). The archive
  `beliefs_round_r.json` is the post-turn state going into round r+1.
- Availability: the author's current notes on all peers are rendered into the author's **next-round
  notice** ("Your private notes on your peers"). Verified: 100% of archived notes appear in the next
  round's prompt in all 14 instances. Notes persist across rounds (unlike received messages, which
  expire after one round). Peers never see them.
- So beliefs give (a) persistent memory and (b) a structured place to state what one believes about
  each peer. Separating those two benefits would need a controlled experiment; do not claim it.

## Inputs per instance
`prep/<instance>.json` (this directory): per agent `updates` (round, step, about, note), `edits`,
`availability`, `final_notes`; `events` = time-ordered union of deliveries (round start), belief
updates, edits, submits, sends; `board` with send rounds. Raw data under `run_dir` as usual
(traj, context/messages.jsonl, local_issue.md, patches). Gold slices in
`/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro/multiagent_pro_bench34_noreq/<instance>/agent_k/gold.patch`
(one valid implementation). Gold dependency links + topology:
`/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_comm_measures/prep/p2p_beliefs/<instance>.json` (`graph`).
Existing redundancy / request annotations for the SAME run:
`/home/asurite.ad.asu.edu/ubiswas2/harness50/analysis_comm_measures/annotations/p2p_beliefs/<instance>.json`.
The matching no-belief run: `/home/asurite.ad.asu.edu/ubiswas2/harness50/p2p/mini_swe_agent/claude_opus_5_5/<instance>/`
and its annotations under `.../annotations/p2p/`.

## Analysis 1 — correct and stable convergence
From the task text and gold links, list the **shared facts** the linked agents must hold compatibly
(signature, return type, defaults, error behaviour, ownership, call-site value). Do not limit to facts
they happened to discuss. For each fact, collect every observable **claim**: {agent, object, property,
value, round, step, evidence (board# / belief update / traj), status: requirement | proposal |
commitment | implemented}. Sources: belief notes, messages, publications, thoughts, code edits.
Then classify the fact: `correct_initially` | `aligned_during_run` (give first round of correct stable
alignment) | `persistent_disagreement_or_uncertainty` | `stable_incorrect_agreement` |
`correct_then_unsupported_reversal`. Check requirement claims against the task text; implementation
claims against the owner's code at that time (its patch / edits). Compatible understanding, not
identical wording. If records are sparse, say what the limit is rather than inventing a round.

## Analysis 2 — message → belief → code (for relevant exchanges on gold links)
- **Sender consistency**: does the message match the sender's most recent prior note / thought on
  that proposition? (A consistently communicated wrong belief is consistent but incorrect; say both.)
- **Receiver uptake**: receiver's belief before delivery vs first belief/update after delivery:
  `already_held` | `incorporated_missing` | `corrected_incorrect` | `not_incorporated` |
  `adopted_incorrect_or_stale`. Compare against delivery time (round r+1 start), not send time.
  Check for independent inspection (a grep/test in the trajectory) before attributing a change to
  the message.
- **Action alignment**: does the receiver's later implementation / action fit its recorded belief?
  Distinguish "did not update understanding" from "understood but did not implement". A useful
  confirmation may need no code change.
Compare specific propositions ("f returns bytes" vs "f returns str"), not whole-text similarity.

## Analysis 3 — retention across rounds
Trace: message received → belief recorded → message expires → belief retained / omitted / reversed →
later question or action. Classify: `never_received` | `received_not_incorporated` |
`incorporated_then_contradicted_or_lost` | `retained_not_implemented` | `justified_update`.
Use the record format honestly: omission from a selective note is not forgetting; an explicit "that
reply never arrived" while the history (or the prompt dump) shows it did is. Relate each supported
retention failure to the existing redundancy annotations (repeated questions, false retractions) for
this run, and compare descriptively with the matching no-belief run (did the same agent/link show the
same false retraction there?). Already believing a fact does not make a later confirmation redundant.

## Output `instances/<instance>.json`
```json
{"instance": "...", "topology": "...", "record_summary": {"updates": n, "agents_using": "k/N", "notes_shown_next_round": "x/y",
   "what_recorded": "ownership / promises / verified-in-code / trust ... with counts or examples"},
 "facts": [{"fact_id": "F1", "link": ["agent_1","agent_2"], "object": "...", "property": "...", "required_value": "...",
   "source_of_truth": "task text §… | owner code", "claims": [{"agent": "...", "value": "...", "round": 1, "step": 3,
   "status": "proposal|commitment|implemented|requirement", "evidence": "belief update | board#k | traj ..."}],
   "classification": "correct_initially|aligned_during_run|persistent_disagreement_or_uncertainty|stable_incorrect_agreement|correct_then_unsupported_reversal",
   "first_round_correct_stable": 1, "notes": ""}],
 "exchanges": [{"board_idx": 4, "from": "...", "to": "...", "delivered_round": 2, "proposition": "...",
   "sender_consistency": "consistent|inconsistent|no_prior_belief|uncertain", "sender_evidence": "...",
   "receiver": "...", "belief_before": "...|none", "belief_after": "...|none", "uptake": "already_held|incorporated_missing|corrected_incorrect|not_incorporated|adopted_incorrect_or_stale|uncertain",
   "independent_inspection": "none|traj agent_k rR sS ...", "action_alignment": "fits|understood_not_implemented|not_updated|no_action_needed|uncertain", "evidence": "..."}],
 "retention": [{"agent": "...", "about": "...", "proposition": "...", "received_round": 2, "recorded_round": 2, "later": "retained|omitted|reversed",
   "classification": "never_received|received_not_incorporated|incorporated_then_contradicted_or_lost|retained_not_implemented|justified_update",
   "consequence": "repeated question board#… | false retraction board#… | none", "no_belief_run_comparison": "same agent/link in p2p: … | n/a", "evidence": "..."}],
 "beyond_messages": ["what the notes reveal that messages alone do not (e.g. private doubt, trust, stale-view awareness)"],
 "uncertain": ["..."]}
```
Every claim needs instance, agent ids, round/step and a raw reference. Redact implementation details
that are not needed (describe, don't paste code). Validate with json.load.
