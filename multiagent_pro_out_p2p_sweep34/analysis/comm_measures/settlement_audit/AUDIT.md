# Settlement audit (P2P arm)

**Question.** Of the 101 P2P links annotated `initially_settled`, how many were really settled
before any message could change a decision? The annotation is a judgment from trajectories; this
audit checks it mechanically and then by hand.

**Result.** One label changed. `7f6b722a` agent_2–agent_6 is now `resolved` (2 messages, round 3).
P2P links are now 100 initially settled, 23 settled through communication and 3 unresolved (were
101 / 22 / 3).

## Method

`settlement_audit.py` finds, for every link, the steps where an endpoint ran a file-writing command
that names one of the link's gold objects, then takes each endpoint's **first** such round.

| Initially settled links (101, before revision) | Count | Meaning |
|---|---|---|
| both endpoints wrote the name in round 1 | 75 | consistent with the label |
| only one endpoint ever writes the name | 13 | the other side uses existing code, a template or the task text; consistent |
| the later endpoint first writes the name in round ≥ 2, **after** a message naming it was delivered | 13 | a message may have supplied the decision: checked by hand below |

The test used for each flagged link: **did a delivered message supply or change either endpoint's
decision?** A decision fixed independently before any delivery (in code, or in the agent's own
round-1 plan or broadcast) counts as initial even when it was implemented later.

The last name-bearing edit is reported in `link_edits.csv` but is not a usable signal: 78 of the
100 initially settled links have one after round 1, and a sample showed these are import moves,
test-file edits, cleanup, or commands that only mention the name in a `grep`.

A first pass that discarded steps whose output showed an error flagged 29 links; 16 of those were
edits that applied before a later command in the same step failed, which annotators had noted
("applied despite shell error"). The script keeps errored steps.

## Verdicts on the 13 flagged links

| Link | Verdict | Reason |
|---|---|---|
| `7f6b722a` 2–6 | **changed to resolved** (2 messages: #2, #15; settled r3) | The contracted API (`build_q_from_params`, `q_to_solr_params`, `facet_rewrites`) is in neither task text. Both endpoints wrote it only after agent_3's `SearchScheme` publication (#2) was delivered in r2 (agent_6 r2 s11, agent_2 r3 s16). The annotation itself gave settled round 2 with an initial label, which the definition does not allow. |
| `b8025ac1` 1–4 | keep | agent_1 announced `open_url(..., ciphers=None)` in its r1 broadcast (#0) before any delivery; its r2 code followed its own plan, and agent_4's r1 call already matched. |
| `25858f9f` 2–3 | keep | agent_2 fixed the exact import list from `openlibrary.solr.utils` in r1 (r1 s6, a send the guard refused); its r2 code followed that independent decision. |
| `25858f9f` 2–4 | keep | `build_subject_doc` already existed in the base `update_work.py`; agent_2 never moved it. |
| `7f6b722a` 6–7 | keep | agent_6's task text gives `WorkSearchScheme`'s name and path; agent_7 coded the import in r1. The later message only asked for confirmation. |
| `7f6b722a` 2–8, 6–8 | keep | agent_8's r1 change to `fully_escape_query` is a behaviour fix with the name unchanged; nothing needed agreeing. |
| `7f6b722a` 4–6, 5–6 | keep | Sibling classes overriding the same base method; `link_real: false`, no contract between them. |
| `7f6b722a` 11–2 | keep | agent_11's r1 template accepted either result shape, so agent_2's r3 `get_results` could not be incompatible. |
| `e5340c44` 1–3 | keep | agent_3 used `ignore_certificate_error`, which agent_1 kept unchanged from base. |
| `e5340c44` 4–7 | keep | agent_4 never adopted the new `certificate_was_accepted`; it kept the base `error.ignore` path. |
| `e5340c44` 2–6 | keep | `link_real: false`: the gold graph attributes the webengine wrapper to this pair, but agent_6 only uses the webkit one. |

## Limits

- Edits are detected from command text; there are no per-step file snapshots. An edit that never
  spells out the name is missed, and a write that only mentions it is counted.
- The 75 "both sides in round 1" links were not opened by hand. They are consistent with the label
  but not proof of it: a round-1 edit could still have been revised later because of a message.
- The verdicts are a single reviewer's, like the original annotations.

## Files

| File | Contents |
|---|---|
| `settlement_audit.py` | the mechanical check; rerun with `python settlement_audit.py` after `build.py` |
| `link_edits.csv` | every P2P link: status, first name-bearing edit per endpoint, last edit round, all edits, check result |
| `needs_check.csv` | initially settled links still flagged (12 after the revision; all kept above) |
