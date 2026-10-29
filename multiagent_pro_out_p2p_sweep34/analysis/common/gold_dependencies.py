#!/usr/bin/env python
"""Gold interdependency structure of each multi-agent instance, and whether the run's talk followed it.

For every instance in --bench (the built benchmark, one gold.patch per agent) build the GOLD
dependency graph: edge consumer -> definer whenever a name that the definer's gold slice
introduces (def / class / CONSTANT, or the module itself via import) is used in the consumer's
gold added lines. Report per instance: agents, edges, agents touched by at least one edge,
isolated agents (no edge either way), hub in-degree, and a shape label
(none / pair / star / chain / mesh). Optionally (--run-root, --metrics) compare with the run:
edges the agents actually realized in their patches, and whether each gold edge's two agents
exchanged a message.
"""
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_extract import added_lines, defined_names

IMPORT_RE = r"(from|import)\s+{mod}\b"


def gold_graph(inst_dir):
    spec = json.loads((inst_dir / "spec.json").read_text())
    ids = [a["id"] for a in spec["agents"]]
    gold = {a["id"]: (inst_dir / a["id"] / "gold.patch").read_text() if (inst_dir / a["id"] / "gold.patch").exists() else "" for a in spec["agents"]}
    gfile = {a["id"]: a["gold_file"] for a in spec["agents"]}
    defs = {a: dict(defined_names(gold[a])) for a in ids}
    # Modified existing definitions: the enclosing def/class named in a hunk header counts as a
    # definition the slice changes (USE-ON-CHANGED), even when the `def` line itself is not in
    # the diff (multi-line signatures). Same rule as tag_coupling's DEFS_MOD.
    for a in ids:
        for m in re.finditer(r"^@@[^@]*@@\s*.*?\b(?:def|class)\s+(\w+)", gold[a], re.M):
            n = m.group(1)
            if n not in defs[a] and n not in ("__init__", "main", "setUp") and len(n) >= 4:
                defs[a][n] = "<modified>"
    # Parameter-level coupling: a keyword the definer's slice introduces in a signature
    # (`name=default` / `name: type` on an added line) that a consumer passes as `name=` in a call.
    # The definer is the slice that IMPLEMENTS the parameter (stores it: `self.x = x`, documents
    # it as `:kwarg x`, or resolves it via `x = self._fallback(x`); a consumer PASSES it in a call
    # (`x=<expr>` where the expr is not an argument-spec `dict(`).
    kw_defs = {}
    for a in ids:
        added = "\n".join(l for _, l in added_lines(gold[a]))
        kw_defs[a] = set(re.findall(r"self\.([a-z_][a-z0-9_]{4,})\s*=\s*\1\b", added)) | \
            set(re.findall(r":kwarg\s+([a-z_][a-z0-9_]{4,})", added)) | \
            set(re.findall(r"\b([a-z_][a-z0-9_]{4,})\s*=\s*self\._fallback\(\s*\1\b", added))
    edges = {}
    for c in ids:
        added = "\n".join(l for _, l in added_lines(gold[c]))
        toks = set(re.findall(r"\w+", added))
        kw_used = set(re.findall(r"(?<![\w.])([a-z_][a-z0-9_]{4,})\s*=(?!=)\s*(?!dict\()[\w'\"\[]", added))
        for d in ids:
            if d == c:
                continue
            names = [n + ("*" if defs[d][n] == "<modified>" else "") for n in defs[d] if n in toks]
            if not names:   # fall back to keyword coupling only when no name-level edge exists
                names += [f"kw:{k}" for k in sorted(kw_defs[d] & kw_used - kw_defs[c])]
            mod = re.sub(r"^lib/", "", gfile[d]).replace(".py", "").replace("/", ".")
            if gfile[d].endswith(".py") and re.search(IMPORT_RE.format(mod=re.escape(mod)), added):
                names.append(f"<import {mod.split('.')[-1]}>")
            if names:
                edges[(c, d)] = names
    return spec, ids, gfile, edges


def shape(ids, edges):
    if not edges:
        return "none"
    indeg = defaultdict(int); outdeg = defaultdict(int)
    for c, d in edges:
        indeg[d] += 1; outdeg[c] += 1
    touched = {x for e in edges for x in e}
    if len(edges) == 1:
        return "pair"
    hub, hub_in = max(indeg.items(), key=lambda kv: kv[1])
    if hub_in == len(edges) and len(touched) == len(edges) + 1:
        return "star"
    if all(indeg[x] <= 1 and outdeg[x] <= 1 for x in touched):
        return "chain"
    return "mesh"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", required=True, help="built benchmark dir with <id>/agent_k/gold.patch")
    ap.add_argument("--run-root", help="run dir, to list which gold edges the agents' messages covered")
    ap.add_argument("--metrics", help="coordination metrics.json of the run (realized edges)")
    ap.add_argument("--out")
    args = ap.parse_args()
    run = Path(args.run_root) if args.run_root else None
    realized = {r["instance"]: r for r in json.load(open(args.metrics))} if args.metrics else {}
    rows = []
    for d in sorted(Path(args.bench).glob("instance_*")):
        spec, ids, gfile, edges = gold_graph(d)
        touched = {x for e in edges for x in e}
        indeg = defaultdict(int)
        for c, dd in edges:
            indeg[dd] += 1
        hub = max(indeg.items(), key=lambda kv: kv[1]) if indeg else (None, 0)
        row = {"instance": d.name, "n_agents": len(ids), "n_edges": len(edges), "agents_linked": len(touched),
               "agents_isolated": len(ids) - len(touched), "hub": hub[0], "hub_in_degree": hub[1],
               "shape": shape(ids, edges), "edges": {f"{c}->{dd}": v for (c, dd), v in edges.items()},
               "files": gfile}
        if run and (run / d.name / "board.json").exists():
            board = json.loads((run / d.name / "board.json").read_text())
            msgs = [m for m in board if m.get("type") == "message"]
            def talked(a, b):
                return any((m["from"], m["to"]) in ((a, b), (b, a)) for m in msgs) or \
                    any(m["from"] in (a, b) and m["to"] == "all" and ({a, b} - {m["from"]}).pop() in m["text"] for m in msgs)
            row["gold_edges_with_contact"] = sum(talked(c, dd) for c, dd in edges)
            pairs_talking = {frozenset((m["from"], m["to"])) for m in msgs if m["to"] != "all"}
            gold_pairs = {frozenset(e) for e in edges}
            row["directed_pairs"] = len(pairs_talking)
            row["directed_pairs_on_gold_edge"] = len(pairs_talking & gold_pairs)
            rm = realized.get(d.name)
            if rm:
                rp = {frozenset(k.split("->")) for k in rm["dep_edges"]}
                row["realized_edges"] = len(rm["dep_edges"])
                row["realized_pairs_matching_gold"] = len(rp & gold_pairs)
                row["resolved"] = rm.get("resolved")
        rows.append(row)

    cols = ["n_agents", "n_edges", "agents_linked", "agents_isolated", "hub_in_degree", "shape"]
    extra = ["realized_edges", "realized_pairs_matching_gold", "gold_edges_with_contact", "directed_pairs", "directed_pairs_on_gold_edge", "resolved"]
    have_extra = any("gold_edges_with_contact" in r for r in rows)
    hdr = cols + (extra if have_extra else [])
    lines = [f"# Gold interdependencies: {len(rows)} instances, {sum(r['n_agents'] for r in rows)} agents, {sum(r['n_edges'] for r in rows)} gold edges", "",
             "| instance | " + " | ".join(hdr) + " |", "|---|" + "---|" * len(hdr)]
    for r in rows:
        lines.append(f"| {r['instance'][9:40]} | " + " | ".join(str(r.get(c, "-")) for c in hdr) + " |")
    from collections import Counter
    lines += ["", "## Shapes: " + ", ".join(f"{k}={v}" for k, v in Counter(r["shape"] for r in rows).most_common()),
              f"## Agents: {sum(r['agents_linked'] for r in rows)} linked, {sum(r['agents_isolated'] for r in rows)} isolated "
              f"(no gold dependency either way) of {sum(r['n_agents'] for r in rows)}",
              f"## Edges per instance: mean {sum(r['n_edges'] for r in rows)/len(rows):.2f}, max {max(r['n_edges'] for r in rows)}; "
              f"edges per linked agent {sum(r['n_edges'] for r in rows)/max(1,sum(r['agents_linked'] for r in rows)):.2f}"]
    if have_extra:
        rr = [r for r in rows if "gold_edges_with_contact" in r]
        ge = sum(r["n_edges"] for r in rr); gc = sum(r["gold_edges_with_contact"] for r in rr)
        dp = sum(r["directed_pairs"] for r in rr); dg = sum(r["directed_pairs_on_gold_edge"] for r in rr)
        lines += [f"## Run vs gold ({len(rr)} completed instances): gold edges with at least one message between the two agents: {gc}/{ge} "
                  f"({gc/max(1,ge):.0%}); directed message pairs that lie on a gold edge: {dg}/{dp} ({dg/max(1,dp):.0%})"]
    lines += ["", "## Edge lists (consumer -> definer: names)", ""]
    for r in rows:
        if r["edges"]:
            lines.append(f"- {r['instance'][9:40]} [{r['shape']}]: " + "; ".join(f"{k}: {', '.join(v[:3])}" for k, v in r["edges"].items()))
        else:
            lines.append(f"- {r['instance'][9:40]} [none]: no cross-agent names in the gold slices (agents independent)")
    report = "\n".join(lines); print(report)
    if args.out:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        json.dump(rows, open(out / "gold_dependencies.json", "w"), indent=1); (out / "gold_dependencies.md").write_text(report)


if __name__ == "__main__":
    main()
