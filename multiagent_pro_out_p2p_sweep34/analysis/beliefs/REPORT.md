# What the belief records reveal (P2P + beliefs arm, 14 problems)

The six communication measures and the three privacy measures are unchanged. This analysis uses
the agents' private belief notes to explain what happened during coordination. There is no belief
score. Nothing was rerun or changed.

Topology of the 14 problems (labels from `comm_measures/`): 11 star, 2 mesh, 1 chain. These are
the only belief-enabled runs that completed before the sweep stopped.

## What the belief records are

Checked in `tools/comm/bin/update_belief`, `tools/comm/lib/board.py`, `orchestrate.py` and the
prompt dumps:

| Question | Answer |
|---|---|
| What are notes about? | A peer, never the author. The prompt asks agents to record what each peer owns, has promised, still owes, and whether its claims "actually showed up in the code". |
| Snapshot or incremental? | Each update replaces the author's current note on that peer and appends to that peer's history. The current note is a selective snapshot, so a fact missing from a newer note is not evidence it was forgotten. Only an explicit contradiction counts. |
| When are they recorded? | At a known round and step, so they can be ordered against message delivery (start of the next round) and code edits. |
| Are they available later? | Yes. Every current note is printed back to its author at the start of every later round: **1147 of 1147** archived notes were found in the next round's prompt. Received messages, by contrast, vanish after one round. Peers never see the notes. |
| How much were they used? | 510 accepted updates across all 14 problems. Every agent used them except one (`949c503f` agent_3, whose combined command was refused by the guard). |

Beliefs therefore add two things at once: **persistent memory** and **a structured place to state
beliefs about each peer**. Separating those two benefits would need a controlled experiment; this
analysis does not claim either one.

## 1. Correct and stable convergence (78 shared facts)

Facts are things linked agents must understand compatibly: signatures, return types, defaults,
error behaviour, ownership, the value each call site passes. They come from the task and gold
links, not only from what agents discussed. Each claim is checked against the task (for
requirements) or the owner's code at that time (for implementation).

| Classification | Facts |
|---|---|
| correct initially | 46 (59%) |
| aligned during the run | 20 (median first round of stable alignment: round 2–3) |
| correct, then an unsupported reversal | 11 |
| persistent disagreement or uncertainty | 1 |
| stable agreement on an incorrect claim | 0 |

- **The contract itself was almost never the problem.** No fact ended in agreement on a wrong
  value.
- **The one persistent case (`b8025ac1`) is about verification, not content.** Peers never accepted
  that the hub's file was saved, because they could not see it, yet all coded correctly against the
  published signature.
- **All 11 reversals concern beliefs about a peer's state, not the contract.** "Did my peer
  implement it? Did my peer reply?" In every case the underlying code was correct and unchanged.
  Example: in `3b823d90`, agent_1's belief about agent_6's fix reversed twice without new evidence
  (r3 s12, r9 s29), and the run ended with agent_1 believing the key fix was "unconfirmed" after six
  confirmations had been delivered.

## 2. Message → belief → code (170 exchanges)

| Relationship | Result |
|---|---|
| Sender consistency | 152 consistent with the sender's prior note; 8 inconsistent; 10 with no prior note |
| Receiver uptake | 72 incorporated missing information; 25 corrected an incorrect belief; 33 already held it; 27 not incorporated; 10 adopted incorrect or stale information; 3 uncertain |
| Action alignment | 75 actions fit the recorded belief; 90 needed no action (a confirmation); 3 not updated; 1 understood but not implemented; 1 uncertain |

Uptake is mostly real, with independent-inspection checks applied before attributing a change to a
message: 97 of 170 exchanges added or corrected a belief.

**Failures of uptake are mostly stale views and false retractions**, not misunderstood contracts.
All 10 cases of adopting incorrect information follow one of two patterns:

- a peer's false correction ("I never received any confirmations; please don't rely on my claims",
  `3b823d90` board#34);
- a stale "every call site still uses the old values" report, built from the base copy of a peer's
  file.

**Notes and actions are tightly aligned.** Only one agent understood a contract and did not
implement it. Where code was wrong it was because the belief was wrong, not because the agent
failed to act on it.

## 3. Retention across rounds (77 traces)

| Classification | Traces |
|---|---|
| incorporated, then contradicted or lost | 37 |
| justified update | 28 (mostly reversals driven by a stale view; the label set has no "evidence-driven but wrong" category, so each entry says so) |
| received, not incorporated | 11 |
| retained, not implemented | 1 |
| never received | 0 |

**The central finding: notes persisted, but agents overrode them.**

- Every false retraction in the beliefs arm happened while the agent's own correct note was on
  screen. The sequence is the same each time:
  1. a message is received;
  2. a correct note is recorded;
  3. the message expires from context the next round;
  4. the agent sees its note but no matching message in the visible transcript, and writes "no reply
     ever arrived" or "my earlier note was wrong".
- Example (`b8025ac1`): agent_2, agent_3 and agent_4 each saw their own round-2 note "agent_1
  announced ciphers" printed in their round-3 prompt, then wrote "no message ever arrived" (r3 s10–11)
  and re-asked (#10, #11, #13).
- Agents treated *"not in the visible messages"* as stronger evidence than *"in my own notes"*. Notes
  keep the content of a fact but not where it came from, so once the source message expired, agents
  doubted their own record.
- **Consequences** of the 37 contradicted-or-lost traces:
  - 18 led to a repeated question;
  - 8 to a false public retraction;
  - 7 had no visible consequence;
  - 4 had other effects.
- In `1be7de78`, agent_4's false correction (#22) was then adopted by agent_3.

**Beliefs backed by a publication survived; beliefs backed only by a message did not.** Publications
are reprinted every round, so the agent could see a source for them.

## Comparison with the matching no-belief runs (descriptive only)

Same 14 problems, one P2P run and one beliefs run each. Per-problem values are in
`per_problem_summary.csv`.

| | P2P | P2P + beliefs |
|---|---|---|
| Requests answered then forgotten | 32/159 (20%) | 17/236 (7%) |
| Redundancy (mean of problems) | 0.23 | 0.23 |
| Conversations per problem | 19.9 | 26.9 |
| Successful unauthorized access (sum) | 53 | 57 |
| Disclosures delivered (sum) | 1 | 14 |

- **Forgetting is lower in the beliefs runs**, which is consistent with better retention. But the
  analysts found the same false retractions on the same links in both arms in many cases. In
  `b8025ac1`, agent_3's round-3 lapse happens in both, so the notes did not prevent it. In some
  other cases the retraction moved to a different agent.
- **Redundancy is unchanged**, and the beliefs runs talked more.
- **More disclosures in the beliefs runs.** The beliefs agents recorded and broadcast "your file
  still has X" verification more often; the notes show agents privately tracking whether peers'
  claims "showed up in the code", which the prompt asks for. That is a plausible link to the extra
  stale-view broadcasts, but not established.
- **None of this is causal.** One run per cell, ungraded beliefs runs, and the persistent interface
  registry exists in both arms.

## What beliefs reveal beyond messages

- **Private evidence grading.** Notes mark how an agent knows each claim ("their claim only", "not
  verified by reading", "trusting the contract"), while its messages state the same claims as fact.
- **Doubt before it is spoken.** Stale-view suspicion and doubts about a peer were often written
  privately a round before they were sent (`395e5e20` agent_3 r2 s6; `3b823d90` agent_1 r2 s9), and
  many agents diagnosed the private-workspace problem in their notes before any message explained it.
- **Wrong beliefs about non-linked peers**, invisible in messages. In `3b823d90`, agents 3 and 4
  believed agent_5 should use `'vaulted'`.
- **The mechanism of false retraction.** Messages alone show "I never got a reply". The notes show
  that the agent *had* recorded the reply and then overrode its own record.

## Limitations

- The records are reported beliefs: free text written by the agents themselves, and selective. The
  analysis checks them against behaviour, but cannot see unrecorded beliefs.
- 14 belief-enabled problems, mostly stars; 20 of 34 did not complete.
- One `a26c325b` note is missed by the parser (29 counted vs 30 recorded); counts of refused notes
  are excluded.
- Contextual labels were single-annotated under one brief.

## Files

| File | Contents |
|---|---|
| `per_problem_summary.csv` | per problem: topology, record stats, label counts for the three analyses, matching no-belief vs belief communication and privacy values |
| `facts.jsonl` | each shared fact with its claim timeline |
| `exchanges.jsonl` | each message → belief → action annotation |
| `retention.jsonl` | each retention trace |
| `instances/*.json` | full records with evidence |
| `aggregates.md` | label distributions and the paired table |
| Scripts | `belief_prep.py` (timelines ordered against delivery and edits; next-round availability), `belief_build.py` (outputs) |
| Brief | `BELIEF_BRIEF.md` (verified record semantics, definitions, labels, schema) |
