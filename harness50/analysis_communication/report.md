# What the P2P agents talk about, and how efficient the communication was

Run: 34-instance P2P sweep (mini-swe-agent, Opus 5.5, 10 rounds x 6 steps, $3/agent pooled),
33 instances completed, 177 agents, 667 messages + 141 published interfaces, 29/33 resolved.

Two layers of evidence: (1) deterministic counts over every board and trajectory
(`comm_content.py`, `coordination_metrics.py`); (2) a full read of all 33 conversations by three
independent readers using one fixed message taxonomy, each message assigned exactly one primary
type, plus a 0-10 efficiency score per instance with cited evidence (`per_instance.json`).

## 1. Shape of the conversation over time

| round | messages | interfaces published | edit steps | test steps | submit-only steps |
|---|---|---|---|---|---|
| 1 | 184 | 72 | 196 | 32 | 99 |
| 2 | 109 | 53 | 106 | 92 | 164 |
| 3 | 77 | 5 | 40 | 113 | 171 |
| 4 | 82 | 6 | 24 | 74 | 177 |
| 5-10 | 215 (total) | 5 (total) | 48 (total) | 124 (total) | ~177 per round |

- 50% of all messages are sent by the end of round 3; 89% of interfaces are published in rounds 1-2.
- Editing is essentially over by round 4. From round 3 on, the dominant step in the run is the bare
  `COMPLETE_TASK_AND_SUBMIT` no-op (177 of 177 agents re-submitting every round). The 10-round
  budget bought about 3 rounds of work; 49% of all agent-rounds were idle.
- Delivery is next-round, so every question costs a full round (mean answer latency 1.1 rounds,
  95% of requests answered). Inside a ~3-round working window, one unanswered-until-next-round
  question is a third of the run.

## 2. What the messages are (667 messages, one primary type each)

| type | count | share | what it looks like |
|---|---|---|---|
| STATUS | 128 | 19% | "schemes/subjects.py IS saved on my side"; "still no changes needed" |
| RESTATE | 126 | 19% | repeating a signature/decision already on the board, no new information |
| CONFIRM | 99 | 15% | "confirmed, cache='vaulted' matches" |
| REQUEST | 90 | 13% | "agent_1 please publish the exact signature"; "do you compare types with ==?" |
| PROPOSE_INTERFACE | 84 | 13% | first statement of a name/signature/contract |
| PROBLEM | 59 | 9% | guard refusals, "your edit isn't saved", ImportError in the local sandbox |
| CORRECTION | 46 | 7% | "I never actually received a reply, so that was wrong" |
| TEST_REPORT | 21 | 3% | "41 passed" |
| PLAN | 13 | 2% | assigning who does what |

Supporting counts from the regex pass: 97% of messages name at least one code identifier
(this is not chit-chat), but for 60% of those every identifier was already on the board.
Only 3% of messages carry no code identifier at all. Median message is 353 characters; the
whole sweep's message text is ~64k tokens, under 2% of the ~$165 spend. The cost of
communication is rounds, not tokens.

## 3. What they are actually talking about

**Interface agreement, settled almost immediately.** The substantive content of nearly every
board is one handshake: the owner of the "hub" file states a signature (`DataLoader.load_from_file(
file_name, cache='all', ...)`, `prepare_multipart(fields) -> (content_type, body)`,
`IteratingStates`/`FailedStates`, `scm_archive_collection(...)`, `SubjectSearchScheme`), and the
consumers state how they call it. In 10 of the 11 ansible instances, and in most openlibrary and
qutebrowser ones, every agent independently posted the *upstream* design (same names, defaults,
even changelog fragment names) in round 1 before any peer message had been delivered. The
readers' verdict: convergence by shared prior, not by negotiation. The real ambiguities were
trivial and each took one message: `'vaults'` vs `'vaulted'`; a non-existent `ctx.resolved_fqcn`;
str vs bytes return of `scm_archive_collection`; `set_toc_text(str | None)`.

**Code that changed because of a message.** The readers counted roughly 1-2 per instance,
86 across the sweep. Examples: `a02e22e9` agent_3 switching the offline proxy from raising to
returning `set()` after peer requests; `5640093f` agent_4's `resolved_fqcn` correction forcing a
re-publish; `e40889e7` the `to_bytes` wrap on a str return; `630221a` a primary-key rename;
`77c16d53` None-safe `set_toc_text`; `7f6b722a` agent_12 changing `+ facet_fields` to
`+ list(facet_fields)` after one omnibus broadcast; `46e6839e` moving `parse_version` above a
circular import. Everything else either confirmed what the receiver had already written or was
absorbed by defensive dual-shape coding (accept dict *or* object, try/except import fallbacks,
local fallback implementations) that substitutes for asking.

**The rest is produced by the harness, not the task.** Two mechanisms account for roughly half
of all traffic and nearly all traffic after round 5:

1. *Stale-view storms* (9/11 in group C, every multi-round problem thread in group A). Each agent
   sees the base-commit copy of peers' files. Agents grep/import them, get ImportError/TypeError/
   `hasattr(...) == False`, and tell the owner "your edit isn't saved". Owners reply with line
   numbers and "your view is stale". `qutebrowser-1943fa0`: 37 of 44 messages. `openlibrary-308a35d`:
   11 identical reports to agent_1 over rounds 3-5. The phrase "workspaces appear to be separate"
   first appears at round 4-5 in every affected instance, never up front, because nothing in the
   prompt says so.
2. *Expiry-induced false corrections* (8/11 in group B, 7/11 in group C). Messages leave the
   agent's context after one round. The agent reads a reply, acts on it, then next round sees only
   its own acknowledgement and retracts: "No such reply ever reached me, so that claim was
   unfounded"; "I fabricated them; please disregard" (retracting two TRUE peer reports); "No peer
   message has actually reached me at any point in this run" (after answering a peer in round 4).
   Each retraction triggers a re-ask, a re-answer, and often an apology from the peer whose message
   was in fact delivered. `3b823d90`: agent_1 asked agent_6 the same question in rounds 3, 6 and 9;
   agent_6 answered in rounds 4, 7 and 10. In `openlibrary-d109cc7` a false retraction made
   agent_7 revert a correct template change. Interfaces persist (registry), so they never suffer
   this; messages do.

Smaller patterns: late `publish_interface` triggers "please publish" ask-storms (b8025ac1,
8127abbc); pile-on alerts where four bystanders report the same mismatch the owner is already
fixing (630221a); directed messages re-broadcast verbatim; duplicated helpers accepted as
"harmless" rather than resolved (three `expand_record` copies in 1be7de78); almost no genuine
test coordination (several agents state they ran no tests).

## 4. Efficiency scores (0-10; 10 = every message necessary, nothing missing)

Distribution over 33 instances: 2,2,2,3,3,3,4x8,5x7,6x6,7x5,8. Median 5, mean 4.9.
Resolved instances 5.1, unresolved 3.0. Teams of <=4 agents 5.4 (n=17); teams of >=7 agents
4.3 (n=7). Readers cited 86 necessary, 93 wasted and 36 missing messages.

Best boards (7-8): `a26c325b` (6 messages: three directed requests, one status, one publish),
`8127abbc` (one proposal per owner, two targeted requests, and one agent pre-emptively saying
"please don't touch that test file"), `77c16d53` (7 agents, 12 messages, one each, done in two
rounds), `b8025ac1`, `949c503f`, `d40ec887`.

Worst boards (2-3): `qutebrowser-1943fa0` (resolved, 44 messages, 90% stale-grep nagging),
`395e5e20` (17 of 21 messages stale-view reminders), `30bc73a1` (6 useful messages then 35 of
stale reports, false corrections and a solicited "facts only" status round), and three of the
four failures.

## 5. The four failures, from the board's point of view

| instance | cause | was it a communication failure? |
|---|---|---|
| `ansible-42355d18` | two agents edited the same unowned test file; identical hunks; merged patch does not apply | Yes, and visible: both *announced* the edit (R3, R5); nobody objected. In 8127abbc one "don't touch that test file" message prevented the same thing. |
| `openlibrary-7bf3238` | same collision on `tests/solr/test_update_work.py` | Yes: three direct messages between the two agents ("exactly ONE exists (mine)... leave it") never surfaced that they were describing different copies. Missing message: "we have both edited this file; only one of us may." |
| `openlibrary-4b7ea29` | one test fails: an exception the test expects is swallowed | Yes, by *harmful* advice: the single behaviour-changing message ("wrap the call in try/except") pushed the consumer the wrong way and nothing checked it; 15 messages meanwhile went on three version pins. |
| `openlibrary-630221a` | intra-file bug (`db.get_db()` before a read-status check) | No. The board caught and fixed the one real cross-file mismatch within two rounds; no message could have found this bug. |

## 6. Bottom line on efficiency

- Targeting is good: contact recall 0.95, interface agreement 0.99, duplicate rate 0.01,
  95% of requests answered. Agents say the right things to the right peers.
- Information yield is low: ~13% of messages propose something, ~1-2 messages per instance
  change code, and most agents had already implemented the proposed signature (from the same
  memorised upstream design) before the proposal arrived.
- Time efficiency is poor: all useful exchange happens in rounds 1-3; rounds 4-10 are mostly
  idle submits plus traffic generated by two harness properties (invisible peer edits, one-round
  message expiry) that the agents have to discover for themselves.
- Two harness changes would remove roughly half of all traffic: tell agents up front that peer
  edits are invisible in their sandbox, and keep delivered messages (or a digest) in context
  instead of expiring them after one round. A third would have prevented two of the four
  failures: treat shared test files as owned, or at least warn when two agents announce edits
  to the same unowned file.

Files: `per_instance.json` (narratives, per-type counts, necessary/wasted/missing messages,
scores, quotes for all 33 instances), `messages_tagged.jsonl` (all 667 messages with round,
sender, recipient and regex tags), `comm_content.md` (the deterministic pass output).
