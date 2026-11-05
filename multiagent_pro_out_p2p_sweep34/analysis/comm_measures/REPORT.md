# Communication measures across all available runs

One topology label, two graph descriptions and six communication measures per problem, recomputed
from the raw boards, trajectories and prompt dumps. 48 runs: 33 P2P, 14 P2P+beliefs, 1 P2P without
`publish_interface`. No agents were rerun and nothing in the harness was changed.

## 1. Definitions

**Agent graph.** Built from the per-agent gold patches and file ownership, never from the
conversations. A link joins two agents when one agent's gold slice uses a name the other's slice
introduces or modifies (new `def`/`class`/CONSTANT, modified existing `def`, new keyword argument,
or an import of the peer's module). Links are undirected for classification; an agent with no link
is set aside. Labels applied in order: **no links**, **disconnected** (several components), **star**
(one hub adjacent to every other participant, no spoke-spoke link), **chain** (connected path),
**tree** (connected, acyclic), **mesh** (connected with a cycle). A label is flagged *uncertain*
when it changes once links resting only on import evidence are removed. Links whose only shared
name is a generic word (`default`, `type`, `name`, `with`, `value`) are dropped before labelling.

- **Participating agents** `k/N`: agents with at least one link / all assigned agents.
- **Density** `2E / [k(k-1)]`, E = distinct undirected links; N/A when k < 2.

**Conversation.** One sending action = one board entry: a directed message, a broadcast (`all`), or
an interface publication. A publication is delivered once and then *reprinted* in every later
round's notice; reprints are not new actions. Recipient deliveries (directed = 1, broadcast or
publication = N−1) are reported separately and are not used in any rate.

**Gold-link / gold-object matching** (kept from the project's `star_timeline.py`):
- a *gold object* is a name a gold link shares; import-only links use the definer's module path or
  basename;
- a **directed** message is *on a gold link* iff its unordered {sender, recipient} pair is a link.
  Direction is ignored, so a reply against the dependency arrow is on the link;
- a **broadcast or publication** is on a link iff its sender is an endpoint and the text names one
  of that link's objects (it has no single recipient);
- a conversation is **relevant** iff it names any gold object of the problem. This is global
  relevance, deliberately not link-specific;
- a link is **addressed** iff some conversation is on it and names one of its objects.

| Measure | Numerator / denominator | Source |
|---|---|---|
| Directedness | conversations on a gold link / all conversations | deterministic |
| Relevance | conversations naming a gold object / all conversations | deterministic |
| Coverage | gold links addressed / all gold links | deterministic |
| Redundancy | conversations labelled `redundant` / all conversations; `partly_redundant` reported separately; each redundant one carries a cause (harness expiry, stale view, delivery timing, guard; or agent-avoidable) and the earlier source | contextual |
| Response fulfillment | requests labelled `fully` / eligible requests (all explicit requests except `no_opportunity`, e.g. sent in round 10 or to a locked-out agent) | contextual |
| Messages to resolution | per gold link: 0 if the task text or compatible round-1 implementation settled every contract before any delivery; otherwise on-link conversations up to the settling one; `unresolved` if never correctly settled (agreement on incorrect behaviour is not resolution). Problem value = median over resolved links including zeros; unresolved/uncertain counted alongside | contextual |

Contextual labels were produced by seven annotators reading every board entry, trajectory and,
where ordering or visibility mattered, the exact prompt dumps, under one brief
(`ANNOTATION_BRIEF.md`). `validation.md` confirms every conversation was labelled exactly once and
every gold link annotated in all 48 runs.

## 2. Coverage

| | Count |
|---|---|
| Problems selected | 34 |
| Runs analyzed | 48 (P2P 33, P2P+beliefs 14, P2P no-interface 1) |
| Missing runs (no complete run data) | 54 arm×problem cells: P2P 1 (`qutebrowser-f7753550`), beliefs 20, no-interface 33. The beliefs and no-interface sweeps stopped when the API project's monthly budget ran out; two instances whose agents were retired mid-run by budget refusals were excluded as invalid. |
| Graded | P2P only (29/33 resolved). Beliefs and no-interface runs are ungraded; correctness there was judged from task text, code and gold slice. |

Topology of the 34 problems (P2P labels): star 18, mesh 7, chain 3, tree 2, disconnected 3,
`f7753550` star (not run). Three labels are uncertain because they rest on import-only links
(`8127abbc` chain→disconnected, `630221ab` mesh→star, `6fdbbeee` disconnected→star).

## 3. Results by topology (pooled counts; full per-run values in `summary.csv`)

**P2P arm, 33 runs**

| Topology | Runs | Conv. | Directedness | Relevance | Coverage | Redundancy | Response fulfillment | Links: settled initially / via comm. / unresolved | Median msgs to resolution |
|---|---|---|---|---|---|---|---|---|---|
| star | 18 | 360 | 0.63 (226/360) | 0.73 (262/360) | 1.00 (41/41) | 0.24 (86/360) | 0.98 (180/184) | 38 / 1 / 2 | 0 |
| chain | 3 | 67 | 0.64 (43/67) | 0.79 (53/67) | 0.89 (8/9) | 0.33 (22/67) | 0.94 (49/52) | 7 / 2 / 0 | 0 |
| tree | 2 | 84 | 0.65 (55/84) | 0.89 (75/84) | 1.00 (12/12) | 0.48 (40/84) | 1.00 (60/60) | 11 / 1 / 0 | 0 |
| mesh | 7 | 229 | 0.78 (178/229) | 0.87 (198/229) | 1.00 (55/55) | 0.27 (62/229) | 0.96 (134/140) | 36 / 18 / 1 | 0 |
| disconnected | 3 | 68 | 0.59 (40/68) | 0.68 (46/68) | 0.78 (7/9) | 0.22 (15/68) | 0.95 (19/20) | 8 / 1 / 0 | 0 |
| **all** | 33 | 808 | 0.67 (542/808) | 0.79 (634/808) | 0.98 (123/126) | 0.28 (225/808) | 0.97 (442/456) | 100 / 23 / 3 | 0 |

**P2P + beliefs arm, 14 runs**: directedness 0.69 (261/376), relevance 0.84 (317/376), coverage
1.00 (35/35), redundancy 0.25 (94/376), response fulfillment 0.97 (222/230), links 29 settled
initially / 6 via communication / 0 unresolved, median messages to resolution 0.

**P2P without interface, 1 run** (`395e5e20`): directedness 0.95 (20/21), relevance 1.00,
coverage 1.00 (2/2), redundancy 0.19 (4/21), response fulfillment 0.93 (13/14), both links settled
initially. One run supports no comparison.

### What the measures show

**Coverage is saturated.** 160 of 163 gold links were addressed. The three misses are in
disconnected graphs (`72321288`, `b112069e`) and in `8127abbc`, where an import-only link may not
be real. Coverage does not distinguish topologies.

**Directedness is highest in meshes (0.78) and lowest in disconnected graphs (0.59).** In a mesh
most agent pairs are linked, so most directed messages land on a link by construction. The measure
is strictly uninformative only when every participant is linked to every other (k = N, density 1);
no run meets that. But in seven runs the graph is a single pair inside a larger team
(`5640093f`, `a02e22e9`, `cb94c0cc`, `4b7ea297`: 2 participants of 4–8), where density is 1.0 and
directedness mostly measures how much the non-participating agents talked. In `4b7ea297` the one
gold link carried 5 of 36 conversations (directedness 0.14) while six unlinked agents coordinated
version pins and other real but non-gold work.

**Relevance tracks directedness** (0.79 overall) because off-link talk is usually also off-object.
Trees and meshes are highest (0.89, 0.87): their shared objects are more numerous, so more messages
name one.

**Redundancy is 0.27 overall and does not separate topologies**, except the two trees (0.48), driven
by `qutebrowser-1943fa07` (26 of 46 conversations redundant). Of the 323 redundant conversations,
**284 (88%) have a harness cause** and 39 are agent-avoidable:

| Cause of redundant conversations | Count |
|---|---|
| message expired from the recipient's context after one round | 129 |
| stale view: peer file seen at the base commit, so a done edit looked missing | 106 |
| delivery timing: re-ask sent before the answer could arrive | 49 |
| agent-avoidable (information was in context) | 39 |

A further 241 conversations were *partly* redundant (they added something and repeated something);
their causes split more evenly (agent-avoidable 94, timing 56, stale view 56, expiry 34).
By function, redundant conversations are mostly repeated requests (90), stale reports (80),
repeated answers (48) and corrections (34).

**Response fulfillment is high everywhere: 0.97 (677/700 eligible requests fully answered).** Only 5
requests were answered incorrectly and 5 went unanswered. But **123 fully answered requests were
answered and then forgotten** by the asker: the reply was delivered (visible in the prompt dump),
acknowledged, and later denied ("I never received a reply"). That is 99 of 476 requests in P2P
(21%), 17 of 236 in the beliefs arm (7%), 7 of 16 in the no-interface run.

**Messages to resolution is 0 for 131 of 163 links.** The task text or an identical round-1
implementation settled them before any message could arrive. 29 links were settled through
communication, in 1–5 messages (median 2); meshes account for 22 of them. In P2P that is 100
initially settled and 23 resolved, with resolved links taking 1–4 messages (median 2), all
settled in round 2 or 3.

The initial labels were audited (`settlement_audit/AUDIT.md`). For every P2P link the audit finds
each endpoint's first edit naming the shared object. In 75 of the 101 initially settled links both
endpoints wrote it in round 1; in 13 only one endpoint ever writes it. In the other 13 the later
endpoint first writes it after a message naming it was delivered. Checked by hand, one of those 13
was settled by a message and is now `resolved` (`7f6b722a` agent_2–agent_6: the shared API came
from agent_3's `SearchScheme` publication, #2). The other 12 were decided independently, existed in
base code, or are not real links.

Many initially settled links still carry later messages (median 6 per P2P link after
settlement), mostly confirmation of what the code already did; the 0 counts messages needed, not
messages sent. Three links were never
correctly settled, all in P2P:

| Link | Why unresolved |
|---|---|
| `4b7ea297` agent_2–agent_3 | both agreed to swallow `AuthorRemoteIdConflictError`; agent_3's advice "Wrap the call in try/except" (R2) was followed and is wrong for the requirement; the graded test expects the error to propagate |
| `7bf32385` agent_4–agent_6 | each described its *own* copy of an unowned test stub as "exactly one" and they agreed to keep both; two conflicting edits shipped and the merged patch did not apply |
| `e57b6e0e` agent_2–agent_3 | contract agreed verbally, never implemented: the guard locked agent_2 out of its own file for all 10 rounds |

Agreement on incorrect behaviour therefore occurred twice; both were graded failures.

### Arms compared on the same 14 problems (descriptive; one run each, ungraded beliefs)

| Measure | P2P | P2P + beliefs |
|---|---|---|
| directedness | 0.73 | 0.70 |
| relevance | 0.85 | 0.85 |
| coverage | 1.00 | 1.00 |
| redundancy | 0.23 | 0.23 |
| response fulfillment | 0.96 | 0.97 |
| conversations per run | 19.9 | 26.9 |
| requests answered then forgotten | 21% of requests | 7% of requests |

The five rates are indistinguishable. The beliefs arm talked more and forgot far fewer delivered
answers; whether that reflects the persistent notes is examined in the belief analysis
(`../analysis_beliefs/`), not claimed here.

## 4. Representative conversations

- **Resolved through communication, 2 messages** (`e40889e7`, P2P, link agent_2–agent_4):
  agent_4 published the archive helper with its return type in R1 (board#5); agent_2 asked about
  str vs bytes in R2 and wrapped the result the next round (traj agent_2 r3). Post-resolution: 3
  messages.
- **Expiry-driven redundancy** (`3b823d90`, P2P, board#17, R9, agent_1→agent_6): *"I have never
  received a reply from you."* Replies were delivered in R5 and R8 and acknowledged in agent_1's
  thoughts (traj r5 s14, r8 s20). Labelled redundant, cause `harness_expiry`; the request is
  "fully answered, answered-then-forgotten".
- **Stale-view redundancy** (`0d2afd58`, P2P, board#9, R4): *"qobj_repr is published but NOT
  present in qtutils.py yet"*, about a function that had existed in the hub's copy since R1.
- **Agent-avoidable redundancy** (`395e5e20`, P2P, board#1): a broadcast repeating, in the same
  round, the tuple shape already stated in a directed message (#0) to agents with no dependency on
  it.
- **Incorrect answer that was followed** (`4b7ea297`, P2P, board#13, R2, agent_3→agent_2): the
  try/except advice above; labelled `fully` for compliance and `incorrect` for content, and the
  link `unresolved`.
- **Correct agreement on a wrong shared state** (`7bf32385`, P2P, board#22/#26): *"exactly ONE…
  leave it"* said about two different files.

## 5. Limitations

- **Gold graph misses, reported by annotators and kept as-is.** The extractor misses links whose
  shared call sits on an unchanged context line (`5640093f` agents 1–3 and 1–4; `42355d18` agents
  1–2, the `variable_manager` argument where the failure occurred; `a02e22e9` 1–2 and 2–4;
  `8127abbc` 1–2, 1–6, 2–4; `b748edea` 3–4; `cb94c0cc` 2–3; `e40889e7` 1–2; `e5340c44` 5–6), and
  lists a few links that are not real (`8127abbc` 1–5; `630221ab` 4–6; `6fdbbeee` 1–6;
  `e5340c44` 2–6 and 4–5; `e57b6e0e` partly). Where links are missing, directedness and coverage
  are understated (in `1943fa07`, 15 on-topic conversations count as off-link); where spurious,
  coverage is overstated. The graph was kept fixed because re-deriving it from the conversations
  would make directedness and coverage circular.
- **Small graphs.** 7 runs have two participants; their density is 1 by construction and
  directedness there mostly reflects the unlinked agents' traffic.
- **One model, one run per cell.** Opus 5.5 recalls these upstream fixes, which is why 131 of 163
  links were settled initially; a model without that recall would raise messages to resolution.
- **Ungraded arms.** Beliefs and no-interface correctness was judged from requirements and code.
- **Contextual labels** are single-annotated under a shared brief; counts of conversations and
  links were validated mechanically, the labels were not double-coded. The P2P `initially_settled`
  labels were additionally audited against the trajectories (one revised); the beliefs-arm labels
  and the other contextual labels were not.

## Files

`summary.csv` (one row per run: topology, k/N, density, six measures with numerators and
denominators), `by_topology.md`, `conversation_labels.csv` (1205 rows), `requests.csv` (728),
`links.csv` (163), `validation.md`, `prep_summary.json`, `prep/<arm>/<instance>.json`,
`annotations/<arm>/<instance>.json`, `ANNOTATION_BRIEF.md`, scripts `prep.py`, `build.py`;
`settlement_audit/` (`AUDIT.md`, `settlement_audit.py`, `link_edits.csv`, `needs_check.csv`).
