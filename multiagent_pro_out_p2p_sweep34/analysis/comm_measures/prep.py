#!/usr/bin/env python
"""Deterministic layer of the communication-measures analysis (read-only over run data).

For every complete run (arm x instance) this script:
  1. builds the GOLD agent graph from the per-agent gold patches + ownership (reusing the
     project's extractor, analysis_scripts/gold_dependencies.py::gold_graph), makes it undirected,
     flags uncertain links, and labels topology with the rules in order:
     no links / disconnected / star / chain / tree / mesh;
  2. reports participating agents k/N and density 2E/[k(k-1)];
  3. tabulates every CONVERSATION (one sending action = one board entry: a directed message, a
     broadcast, or an interface publication) with its gold-link and gold-object matches;
  4. computes the three deterministic measures: directedness, relevance, coverage.
The contextual measures (redundancy, response fulfillment, messages to resolution) are annotated
separately against the per-run files written here (prep/<arm>/<instance>.json).

Matching rules (kept from the project's existing star_timeline.py / coordination_metrics.py):
  * gold OBJECT = a name a gold link shares (new def/class/CONSTANT, modified existing def `*`, or
    new keyword `kw:`), matched case-sensitively on word boundaries. Import-only links have no named
    object in the extractor; for them the definer's module is the object, matched as its dotted
    path or file basename with extension (e.g. `core.bookshelves`, `bookshelves.py`).
  * a DIRECTED message is on a gold link iff its unordered {sender, recipient} pair is a gold link
    (direction-agnostic: a reply against the dependency arrow is still on the link).
  * a BROADCAST or PUBLICATION has no single recipient, so it is on a gold link iff its sender is an
    endpoint of that link AND it names one of that link's objects (the star_timeline rule).
  * a conversation is RELEVANT iff it names any gold object of the instance (global, not link-specific).
  * a gold link is ADDRESSED iff some conversation is on that link and names one of its objects.
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

H = Path("/home/asurite.ad.asu.edu/ubiswas2/harness50")
BENCH = Path("/home/asurite.ad.asu.edu/ubiswas2/MASWE-bench_Pro/multiagent_pro_bench34_noreq")
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from gold_dependencies import gold_graph   # noqa: E402

ARMS = {"p2p": H / "p2p/mini_swe_agent/claude_opus_5_5",
        "p2p_beliefs": H / "p2p_beliefs/mini_swe_agent/claude_opus_5_5",
        "p2p_nointerface": H / "p2p_nointerface/mini_swe_agent/claude_opus_5_5"}
GENERIC = {"default", "type", "name", "with", "value", "preview"}
NON_PY = re.compile(r"\.(html|xml|sql|txt|toml|cfg|sh|yml|yaml|json|rst|md)$|managed-schema$")


def obj_of(item, definer_file):
    if item.startswith("<import"):
        mod = re.sub(r"^lib/", "", definer_file).replace(".py", "")
        return {"kind": "module", "forms": [mod.replace("/", "."), Path(definer_file).name], "label": Path(definer_file).name}
    nm = item.replace("kw:", "").rstrip("*")
    return {"kind": "keyword" if item.startswith("kw:") else ("modified" if item.endswith("*") else "name"),
            "forms": [nm], "label": nm}


def names_in(text, forms):
    # Plain word boundaries, as in the project's star_timeline.py: attribute access
    # (`DataLoader.load_from_file`, `loader.load_from_file(`) must count as naming the object.
    return any(re.search(r"\b" + re.escape(f) + r"\b", text) for f in forms)


def components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b); adj[b].add(a)
    seen, comps = set(), []
    for n in nodes:
        if n in seen: continue
        stack, comp = [n], set()
        while stack:
            x = stack.pop()
            if x in comp: continue
            comp.add(x); stack.extend(adj[x] - comp)
        seen |= comp; comps.append(comp)
    return comps, adj


def topology(edges):
    """edges: set of frozenset pairs (undirected, distinct)."""
    nodes = sorted({x for e in edges for x in e})
    k, E = len(nodes), len(edges)
    if E == 0: return "no links", nodes
    comps, adj = components(nodes, [tuple(e) for e in edges])
    if len(comps) > 1: return "disconnected", nodes
    hubs = [n for n in nodes if len(adj[n]) == k - 1]
    for h in hubs:   # star: one hub adjacent to all others, no spoke-spoke edge
        if all(h in e for e in edges): return "star", nodes
    if E == k - 1 and all(len(adj[n]) <= 2 for n in nodes): return "chain", nodes
    if E == k - 1: return "tree", nodes
    return "mesh", nodes


def build_graph(inst):
    spec, ids, gfile, edges = gold_graph(BENCH / inst)
    links, flags = {}, []
    for (c, d), items in edges.items():
        pair = frozenset((c, d))
        objs = [obj_of(x, gfile[d]) for x in items]
        names = {o["label"] for o in objs}
        why = []
        if {o["forms"][0] for o in objs if o["kind"] != "module"} and \
                {o["forms"][0] for o in objs if o["kind"] != "module"} <= GENERIC and not any(o["kind"] == "module" for o in objs):
            why.append("generic-name-only")
        if NON_PY.search(gfile[c]) or NON_PY.search(gfile[d]):
            why.append("non-Python endpoint (template/config): name matching unreliable")
        if all(o["kind"] == "module" for o in objs):
            why.append("import-only evidence (no named object crosses the link)")
        elif all(o["kind"] in ("modified", "module") for o in objs):
            why.append("note: modified existing definition only")   # informative, not uncertainty-causing
        L = links.setdefault(pair, {"agents": sorted(pair), "directions": [], "objects": [], "flags": set()})
        L["directions"].append(f"{c}->{d}")
        for o in objs:
            if o["label"] not in {x["label"] for x in L["objects"]}:
                L["objects"].append(o)
        L["flags"] |= set(why)
    # sibling classes: an object named on a link that BOTH endpoints define in their own slice
    for pair, L in links.items():
        a, b = sorted(pair)
        if any(o["kind"] == "name" for o in L["objects"]) and all(f"{a}->{b}" in L["directions"] or f"{b}->{a}" in L["directions"] for _ in [0]):
            if f"{a}->{b}" in L["directions"] and f"{b}->{a}" in L["directions"] and \
                    set(o["label"] for o in L["objects"]) <= {"q_to_solr_params"}:
                L["flags"].add("same-named method defined by both endpoints (sibling classes)")
    kept = {p: L for p, L in links.items() if "generic-name-only" not in L["flags"]}
    dropped = {p: L for p, L in links.items() if "generic-name-only" in L["flags"]}
    label, nodes = topology(set(kept))
    certain = {p for p, L in kept.items() if not [f for f in L["flags"] if not f.startswith("note:")]}
    alt_label, _ = topology(certain)
    k, E, N = len(nodes), len(kept), len(ids)
    return {"N": N, "agents": ids, "files": gfile, "participating": nodes, "k": k, "E": E,
            "density": round(2 * E / (k * (k - 1)), 3) if k >= 2 else None, "topology": label,
            "topology_without_flagged_links": alt_label, "topology_uncertain": alt_label != label,
            "links": [{**L, "flags": sorted(L["flags"])} for L in kept.values()],
            "dropped_links": [{**L, "flags": sorted(L["flags"])} for L in dropped.values()]}


def run_rows():
    for arm, root in ARMS.items():
        for d in sorted(root.glob("instance_*")):
            spec = json.loads((d / "spec.json").read_text())
            if len(list(d.glob("agent_*.patch"))) == spec["num_agents"]:
                yield arm, d


summary, missing = [], []
for arm, root in ARMS.items():
    for d in sorted(BENCH.glob("instance_*")):
        r = root / d.name
        ok = r.exists() and (r / "spec.json").exists() and \
            len(list(r.glob("agent_*.patch"))) == json.loads((r / "spec.json").read_text())["num_agents"]
        if not ok: missing.append({"arm": arm, "instance": d.name})
graphs = {}
for arm, d in run_rows():
    inst = d.name
    g = graphs.setdefault(inst, build_graph(inst))
    board = json.loads((d / "board.json").read_text())
    lens, k = [], 1
    while (d / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((d / f"board_after_round_{k}.json").read_text()))); k += 1
    link_objs = {frozenset(L["agents"]): L["objects"] for L in g["links"]}
    all_objs = [o for L in g["links"] for o in L["objects"]]
    convs = []
    for i, m in enumerate(board):
        rnd = next((r + 1 for r, n in enumerate(lens) if i < n), len(lens))
        kind = "publication" if m.get("type") == "interface" else ("broadcast" if m.get("to") == "all" else "directed")
        text = (m.get("signature", "") + " " + m.get("text", "")).strip()
        named = sorted({o["label"] for o in all_objs if names_in(text, o["forms"])})
        on = []
        for pair, objs in link_objs.items():
            if kind == "directed":
                if pair == frozenset((m["from"], m["to"])): on.append(sorted(pair))
            elif m["from"] in pair and any(names_in(text, o["forms"]) for o in objs):
                on.append(sorted(pair))
        addressed = [p for p in on if any(names_in(text, o["forms"]) for o in link_objs[frozenset(p)])]
        convs.append({"idx": i, "round": rnd, "deliver_round": rnd + 1, "from": m["from"], "to": m.get("to"),
                      "kind": kind, "deliveries": 1 if kind == "directed" else g["N"] - 1,
                      "on_gold_links": on, "addresses_links": addressed, "gold_objects_named": named,
                      "text": text})
    n = len(convs)
    covered = {tuple(p) for c in convs for p in c["addresses_links"]}
    E = g["E"]
    row = {"arm": arm, "instance": inst, "topology": g["topology"], "topology_uncertain": g["topology_uncertain"],
           "topology_without_flagged_links": g["topology_without_flagged_links"],
           "participating": f"{g['k']}/{g['N']}", "density": g["density"],
           "conversations": n, "directed": sum(c["kind"] == "directed" for c in convs),
           "broadcasts": sum(c["kind"] == "broadcast" for c in convs),
           "publications": sum(c["kind"] == "publication" for c in convs),
           "deliveries": sum(c["deliveries"] for c in convs),
           "on_link": sum(bool(c["on_gold_links"]) for c in convs),
           "relevant": sum(bool(c["gold_objects_named"]) for c in convs),
           "links_total": E, "links_addressed": len(covered),
           "directedness": round(sum(bool(c["on_gold_links"]) for c in convs) / n, 3) if n else None,
           "relevance": round(sum(bool(c["gold_objects_named"]) for c in convs) / n, 3) if n else None,
           "coverage": round(len(covered) / E, 3) if E else None,
           "directedness_uninformative": g["k"] == g["N"] and g["density"] == 1.0,
           "flagged_links": sum(bool([f for f in L["flags"] if not f.startswith("note:")]) for L in g["links"]),
           "dropped_generic_links": len(g["dropped_links"])}
    summary.append(row)
    (OUT / "prep" / arm).mkdir(parents=True, exist_ok=True)
    json.dump({"arm": arm, "instance": inst, "run_dir": str(d), "graph": g, "measures": row, "conversations": convs},
              open(OUT / "prep" / arm / f"{inst}.json", "w"), indent=1)
json.dump({"runs": summary, "missing": missing}, open(OUT / "prep_summary.json", "w"), indent=1)
print(f"{len(summary)} runs prepared; missing {len(missing)} (arm x instance)")
print("| arm | instance | topology | uncertain | k/N | density | conv | dir/bc/pub | on-link | relevant | addressed/E | directedness | relevance | coverage |")
for r in summary:
    print(f"| {r['arm']} | {r['instance'][9:40]} | {r['topology']} | {'Y '+r['topology_without_flagged_links'] if r['topology_uncertain'] else ''} | {r['participating']} | {r['density']} | {r['conversations']} | {r['directed']}/{r['broadcasts']}/{r['publications']} | {r['on_link']} | {r['relevant']} | {r['links_addressed']}/{r['links_total']} | {r['directedness']} | {r['relevance']} | {r['coverage']} |")
