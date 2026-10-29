#!/usr/bin/env python
"""Assemble the belief-analysis outputs from the per-instance records.

Inputs : instances/<instance>.json (analyst records, schema in BELIEF_BRIEF.md), prep_summary.json,
         ../comm_measures/summary.csv and ../comm_measures/requests.csv (existing communication
         measures for the same problems in the P2P and beliefs arms), ../privacy/summary.csv.
Outputs: per_problem_summary.csv   one row per belief-enabled problem: topology, record stats, the three
                                   analyses summarized as label counts, and the matching no-belief and
                                   belief communication/privacy values side by side (descriptive)
         facts.jsonl               one row per shared fact, with its claim timeline
         exchanges.jsonl           one row per message -> belief -> action annotation
         retention.jsonl           one row per retention trace
         aggregates.md             label distributions and the paired descriptive comparison
"""
import csv, json, statistics
from collections import Counter, defaultdict
from pathlib import Path

A = Path(__file__).resolve().parent
ROOT = A.parent
recs = {json.load(open(f))["instance"]: json.load(open(f)) for f in sorted((A / "instances").glob("*.json"))}
prep = {r["instance"]: r for r in json.load(open(A / "prep_summary.json"))}
comm = {(r["arm"], r["instance"]): r for r in csv.DictReader(open(ROOT / "comm_measures" / "summary.csv"))}
reqs = list(csv.DictReader(open(ROOT / "comm_measures" / "requests.csv")))
priv = {(r["arm"], r["instance"]): r for r in csv.DictReader(open(ROOT / "privacy" / "summary.csv"))}
atf = Counter((q["arm"], q["instance"]) for q in reqs if q.get("answered_then_forgotten") in ("True", "true"))
nreq = Counter((q["arm"], q["instance"]) for q in reqs)

FACT = ["correct_initially", "aligned_during_run", "persistent_disagreement_or_uncertainty",
        "stable_incorrect_agreement", "correct_then_unsupported_reversal"]
UPT = ["already_held", "incorporated_missing", "corrected_incorrect", "not_incorporated", "adopted_incorrect_or_stale", "uncertain"]
ACT = ["fits", "no_action_needed", "understood_not_implemented", "not_updated", "uncertain"]
RET = ["never_received", "received_not_incorporated", "incorporated_then_contradicted_or_lost", "retained_not_implemented", "justified_update"]

rows = []
with open(A / "facts.jsonl", "w") as ff, open(A / "exchanges.jsonl", "w") as fe, open(A / "retention.jsonl", "w") as fr:
    for inst, r in recs.items():
        for f in r.get("facts", []): ff.write(json.dumps({"instance": inst, **f}) + "\n")
        for e in r.get("exchanges", []): fe.write(json.dumps({"instance": inst, **e}) + "\n")
        for x in r.get("retention", []): fr.write(json.dumps({"instance": inst, **x}) + "\n")
        fc = Counter(f.get("classification") for f in r.get("facts", []))
        uc = Counter(e.get("uptake") for e in r.get("exchanges", []))
        ac = Counter(e.get("action_alignment") for e in r.get("exchanges", []))
        sc = Counter(e.get("sender_consistency") for e in r.get("exchanges", []))
        rc = Counter(x.get("classification") for x in r.get("retention", []))
        aligned = [f.get("first_round_correct_stable") for f in r.get("facts", []) if f.get("classification") == "aligned_during_run" and isinstance(f.get("first_round_correct_stable"), int)]
        p = prep.get(inst, {})
        cb, cp = comm.get(("p2p_beliefs", inst), {}), comm.get(("p2p", inst), {})
        pb, pp = priv.get(("p2p_beliefs", inst), {}), priv.get(("p2p", inst), {})
        rows.append({
            "instance": inst, "topology": cb.get("topology") or cp.get("topology", ""), "analyst_topology_note": r.get("topology", ""),
            "belief_updates": p.get("belief_updates"), "agents_with_notes": f"{p.get('agents_with_updates')}/{p.get('n_agents')}",
            "notes_shown_next_round": p.get("notes_shown_next_round"),
            **{f"fact_{k}": fc.get(k, 0) for k in FACT},
            "median_round_of_alignment": statistics.median(aligned) if aligned else "N/A",
            "exchanges": sum(uc.values()), **{f"uptake_{k}": uc.get(k, 0) for k in UPT},
            "sender_consistent": sc.get("consistent", 0), "sender_inconsistent": sc.get("inconsistent", 0),
            **{f"action_{k}": ac.get(k, 0) for k in ACT},
            **{f"retention_{k}": rc.get(k, 0) for k in RET},
            # matching runs, existing measures (descriptive only)
            "p2p_redundancy": cp.get("redundancy", "N/A"), "beliefs_redundancy": cb.get("redundancy", "N/A"),
            "p2p_response_fulfillment": cp.get("response_fulfillment", "N/A"), "beliefs_response_fulfillment": cb.get("response_fulfillment", "N/A"),
            "p2p_answered_then_forgotten": f"{atf[('p2p', inst)]}/{nreq[('p2p', inst)]}",
            "beliefs_answered_then_forgotten": f"{atf[('p2p_beliefs', inst)]}/{nreq[('p2p_beliefs', inst)]}",
            "p2p_conversations": cp.get("conversations", "N/A"), "beliefs_conversations": cb.get("conversations", "N/A"),
            "p2p_successful_access": pp.get("successful_access", "N/A"), "beliefs_successful_access": pb.get("successful_access", "N/A"),
            "p2p_disclosures": pp.get("disclosures_delivered", "N/A"), "beliefs_disclosures": pb.get("disclosures_delivered", "N/A")})
with open(A / "per_problem_summary.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

tot = lambda pre, keys: {k: sum(r[f"{pre}_{k}"] for r in rows) for k in keys}
L = [f"# Belief analysis aggregates ({len(rows)} belief-enabled problems)", "",
     f"Belief updates accepted: {sum(r['belief_updates'] or 0 for r in rows)}; notes shown back in the next round: "
     f"{sum(int(r['notes_shown_next_round'].split('/')[0]) for r in rows)}/{sum(int(r['notes_shown_next_round'].split('/')[1]) for r in rows)}", "",
     f"## 1. Shared facts ({sum(tot('fact', FACT).values())}): {tot('fact', FACT)}",
     f"## 2. Exchanges ({sum(r['exchanges'] for r in rows)}): uptake {tot('uptake', UPT)}; action {tot('action', ACT)}; "
     f"sender consistent {sum(r['sender_consistent'] for r in rows)}, inconsistent {sum(r['sender_inconsistent'] for r in rows)}",
     f"## 3. Retention traces ({sum(tot('retention', RET).values())}): {tot('retention', RET)}", "",
     "## Matching no-belief runs (descriptive; one run per problem per arm)", "",
     "| problem | topology | redundancy p2p / beliefs | answered-then-forgotten p2p / beliefs | conversations p2p / beliefs | successful access p2p / beliefs | disclosures p2p / beliefs |",
     "|---|---|---|---|---|---|---|"]
for r in rows:
    L.append(f"| {r['instance'][9:40]} | {r['topology']} | {r['p2p_redundancy']} / {r['beliefs_redundancy']} | {r['p2p_answered_then_forgotten']} / {r['beliefs_answered_then_forgotten']} | "
             f"{r['p2p_conversations']} / {r['beliefs_conversations']} | {r['p2p_successful_access']} / {r['beliefs_successful_access']} | {r['p2p_disclosures']} / {r['beliefs_disclosures']} |")
sumf = lambda k: (sum(int(r[k].split("/")[0]) for r in rows), sum(int(r[k].split("/")[1]) for r in rows))
a, b = sumf("p2p_answered_then_forgotten"), sumf("beliefs_answered_then_forgotten")
L += ["", f"Answered then forgotten, pooled: P2P {a[0]}/{a[1]} requests ({a[0]/a[1]:.0%}); beliefs {b[0]}/{b[1]} ({b[0]/b[1]:.0%})."]
(A / "aggregates.md").write_text("\n".join(L)); print("\n".join(L))
