#!/usr/bin/env python
"""Join the deterministic prep with the contextual annotations into the final outputs.

Inputs : prep/<arm>/<instance>.json, annotations/<arm>/<instance>.json, prep_summary.json
Outputs:
  summary.csv               one row per run (arm x problem): topology, participating k/N, density,
                            and the six measures with numerators/denominators;
  by_topology.md            the six measures compared by topology, per arm and overall;
  conversation_labels.csv   every conversation: deterministic matches + redundancy annotation;
  requests.csv              every explicit request with its matched responses and label;
  links.csv                 every gold link: status, messages to resolution, post-resolution,
                            reopenings, evidence;
  validation.md             completeness checks (every conversation annotated once, every link).
Rates are N/A when the denominator is 0. Nothing here adds judgment; labels come from annotations.
"""
import csv, json, statistics
from collections import Counter, defaultdict
from pathlib import Path

A = Path(__file__).resolve().parent
summary = json.load(open(A / "prep_summary.json"))
rate = lambda n, d: round(n / d, 3) if d else None
fmt = lambda v: "N/A" if v is None else v

rows, conv_rows, req_rows, link_rows, problems = [], [], [], [], []
for r in summary["runs"]:
    arm, inst = r["arm"], r["instance"]
    prep = json.load(open(A / "prep" / arm / f"{inst}.json"))
    ap = A / "annotations" / arm / f"{inst}.json"
    if not ap.exists():
        problems.append(f"MISSING annotation: {arm} {inst}"); continue
    an = json.load(open(ap))
    convs = {c["idx"]: c for c in prep["conversations"]}
    labels = {}
    for c in an.get("conversations", []):
        if c["idx"] in labels: problems.append(f"duplicate conversation label {arm} {inst} idx {c['idx']}")
        labels[c["idx"]] = c
    missing = sorted(set(convs) - set(labels)); extra = sorted(set(labels) - set(convs))
    if missing or extra: problems.append(f"{arm} {inst}: conversations unlabelled {missing[:8]} / unknown {extra[:8]}")
    n = len(convs)
    red = Counter(labels[i].get("redundancy") for i in convs if i in labels)
    red_cause = Counter((labels[i].get("cause") or "n/a") for i in convs if i in labels and labels[i].get("redundancy") == "redundant")
    harness_red = sum(v for k, v in red_cause.items() if k.startswith("harness"))
    agent_red = red_cause.get("agent_avoidable", 0)
    reqs = an.get("requests", [])
    rl = Counter(q.get("label") for q in reqs)
    eligible = sum(v for k, v in rl.items() if k != "no_opportunity")
    links = an.get("links", [])
    gold_pairs = {tuple(sorted(L["agents"])) for L in prep["graph"]["links"]}
    ann_pairs = {tuple(sorted(L["agents"])) for L in links}
    if gold_pairs != ann_pairs:
        problems.append(f"{arm} {inst}: link set mismatch missing {sorted(gold_pairs - ann_pairs)} extra {sorted(ann_pairs - gold_pairs)}")
    st = Counter(L.get("status") for L in links)
    mtr = [L.get("messages_to_resolution") or 0 for L in links if L.get("status") in ("initially_settled", "resolved")]
    rows.append({
        "arm": arm, "instance": inst, "topology": r["topology"] + (" (uncertain: " + r["topology_without_flagged_links"] + " without flagged links)" if r["topology_uncertain"] else ""),
        "participating_agents": r["participating"], "density": fmt(r["density"]),
        "conversations": n, "directed": r["directed"], "broadcasts": r["broadcasts"], "publications": r["publications"], "recipient_deliveries": r["deliveries"],
        "directedness": fmt(rate(r["on_link"], n)), "directedness_num_den": f"{r['on_link']}/{n}",
        "directedness_structurally_uninformative": r["directedness_uninformative"],
        "relevance": fmt(rate(r["relevant"], n)), "relevance_num_den": f"{r['relevant']}/{n}",
        "coverage": fmt(rate(r["links_addressed"], r["links_total"])), "coverage_num_den": f"{r['links_addressed']}/{r['links_total']}",
        "redundancy": fmt(rate(red.get("redundant", 0), n)), "redundancy_num_den": f"{red.get('redundant', 0)}/{n}",
        "partly_redundant": red.get("partly_redundant", 0), "redundant_harness": harness_red, "redundant_agent_avoidable": agent_red,
        "response_fulfillment": fmt(rate(rl.get("fully", 0), eligible)), "response_fulfillment_num_den": f"{rl.get('fully', 0)}/{eligible}",
        "requests_partly": rl.get("partly", 0), "requests_incorrect": rl.get("incorrect", 0), "requests_unanswered": rl.get("unanswered", 0),
        "requests_no_opportunity": rl.get("no_opportunity", 0),
        "requests_answered_then_forgotten": sum(1 for q in reqs if q.get("answered_then_forgotten")),
        "median_messages_to_resolution": fmt(statistics.median(mtr) if mtr else None),
        "links_initially_settled": st.get("initially_settled", 0), "links_resolved_by_communication": st.get("resolved", 0),
        "links_unresolved": st.get("unresolved", 0), "links_uncertain": st.get("uncertain", 0),
        "messages_to_resolution_per_link": ";".join(f"{'-'.join(sorted(L['agents']))}={L.get('messages_to_resolution') if L.get('status') in ('initially_settled','resolved') else L.get('status')}" for L in links)})
    for i, c in convs.items():
        l = labels.get(i, {})
        conv_rows.append({"arm": arm, "instance": inst, "idx": i, "round": c["round"], "from": c["from"], "to": c["to"], "kind": c["kind"],
                          "deliveries": c["deliveries"], "on_gold_links": "|".join("-".join(p) for p in c["on_gold_links"]),
                          "gold_objects_named": "|".join(c["gold_objects_named"]), "function": l.get("function"),
                          "redundancy": l.get("redundancy"), "cause": l.get("cause"), "earlier_source": l.get("earlier_source"),
                          "why": l.get("why"), "text": c["text"][:300]})
    for q in reqs:
        req_rows.append({"arm": arm, "instance": inst, **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in q.items()}})
    for L in links:
        link_rows.append({"arm": arm, "instance": inst, **{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in L.items()}})


def write_csv(name, data):
    if not data: return
    keys = list(dict.fromkeys(k for d in data for k in d))
    with open(A / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(data)


write_csv("summary.csv", rows); write_csv("conversation_labels.csv", conv_rows)
write_csv("requests.csv", req_rows); write_csv("links.csv", link_rows)

# ---- by topology (pooled counts, so rates are weighted by conversations / requests / links)
def pooled(rs):
    num = lambda k: sum(int(x[k].split("/")[0]) for x in rs)
    den = lambda k: sum(int(x[k].split("/")[1]) for x in rs)
    mt = [x["median_messages_to_resolution"] for x in rs if x["median_messages_to_resolution"] != "N/A"]
    return {"runs": len(rs), "conversations": sum(x["conversations"] for x in rs),
            "directedness": f"{rate(num('directedness_num_den'), den('directedness_num_den'))} ({num('directedness_num_den')}/{den('directedness_num_den')})",
            "relevance": f"{rate(num('relevance_num_den'), den('relevance_num_den'))} ({num('relevance_num_den')}/{den('relevance_num_den')})",
            "coverage": f"{rate(num('coverage_num_den'), den('coverage_num_den'))} ({num('coverage_num_den')}/{den('coverage_num_den')})",
            "redundancy": f"{rate(num('redundancy_num_den'), den('redundancy_num_den'))} ({num('redundancy_num_den')}/{den('redundancy_num_den')}; harness {sum(x['redundant_harness'] for x in rs)}, agent {sum(x['redundant_agent_avoidable'] for x in rs)}; partly {sum(x['partly_redundant'] for x in rs)})",
            "response_fulfillment": f"{rate(num('response_fulfillment_num_den'), den('response_fulfillment_num_den'))} ({num('response_fulfillment_num_den')}/{den('response_fulfillment_num_den')}; partly {sum(x['requests_partly'] for x in rs)}, incorrect {sum(x['requests_incorrect'] for x in rs)}, unanswered {sum(x['requests_unanswered'] for x in rs)})",
            "messages_to_resolution": f"median of run medians {statistics.median(mt) if mt else 'N/A'}; links: {sum(x['links_initially_settled'] for x in rs)} initially settled, {sum(x['links_resolved_by_communication'] for x in rs)} via communication, {sum(x['links_unresolved'] for x in rs)} unresolved, {sum(x['links_uncertain'] for x in rs)} uncertain"}

L = ["# Six measures by topology", "",
     "Pooled over runs (numerators and denominators summed). Topology labels are the primary label; uncertain labels are counted under their primary label and listed in summary.csv.", ""]
for arm in ["all"] + sorted({x["arm"] for x in rows}):
    rs = [x for x in rows if arm == "all" or x["arm"] == arm]
    L += [f"## {arm} ({len(rs)} runs)", "", "| topology | runs | conversations | directedness | relevance | coverage | redundancy | response fulfillment | messages to resolution |", "|---|---|---|---|---|---|---|---|---|"]
    for topo in ["star", "chain", "tree", "mesh", "disconnected", "no links"]:
        sub = [x for x in rs if x["topology"].split(" (")[0] == topo]
        if sub:
            p = pooled(sub); L.append(f"| {topo} | {p['runs']} | {p['conversations']} | {p['directedness']} | {p['relevance']} | {p['coverage']} | {p['redundancy']} | {p['response_fulfillment']} | {p['messages_to_resolution']} |")
    p = pooled(rs); L += [f"| **overall** | {p['runs']} | {p['conversations']} | {p['directedness']} | {p['relevance']} | {p['coverage']} | {p['redundancy']} | {p['response_fulfillment']} | {p['messages_to_resolution']} |", ""]
(A / "by_topology.md").write_text("\n".join(L))
V = ["# Validation", "", f"runs with annotations: {len(rows)} of {len(summary['runs'])}", f"missing runs (no complete run data): {len(summary['missing'])}", ""] + \
    ([f"- {p}" for p in problems] or ["- no problems: every conversation labelled exactly once and every gold link annotated"])
(A / "validation.md").write_text("\n".join(V))
print("\n".join(V)); print(); print("\n".join(L))
