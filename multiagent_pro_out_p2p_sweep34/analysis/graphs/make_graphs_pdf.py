"""Render the sweep34 P2P gold dependency graphs (one panel per problem) to a shareable PDF.

Reads the graphs from ../comm_measures/prep/p2p/*.json and resolved status from ../../eval_out/eval_results.json.

Usage (from this folder):
    python make_graphs_pdf.py [out.pdf]        # default: sweep34_gold_graphs.pdf
"""
import json
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

HERE = Path(__file__).resolve().parent
OUT = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "sweep34_gold_graphs.pdf")


def load():
    ev = json.load(open(HERE.parent.parent / "eval_out" / "eval_results.json"))
    out = []
    for f in sorted((HERE.parent / "comm_measures" / "prep" / "p2p").glob("*.json")):
        d = json.load(open(f)); g = d["graph"]; inst = d["instance"]
        out.append({"id": inst.replace("instance_", ""), "resolved": ev.get(inst), "N": g["N"], "agents": g["agents"],
                    "files": g["files"], "part": g["participating"], "k": g["k"], "E": g["E"], "density": g["density"],
                    # every kept link is treated as certain: no flagged styling, no "uncertain" topology
                    "topo": g["topology"], "alt": None,
                    "links": [{"a": L["agents"][0], "b": L["agents"][1], "dirs": L["directions"],
                               "objs": [o["label"] for o in L["objects"]],
                               "flags": []} for L in g["links"]],
                    "dropped": [{"a": L["agents"][0], "b": L["agents"][1], "objs": [o["label"] for o in L["objects"]]}
                                for L in g.get("dropped_links", [])]})
    return out


DATA = load()
ORDER = ["star", "chain", "tree", "mesh", "disconnected"]
RULE = {"star": "E = k-1, density = 2/k", "chain": "E = k-1, density = 2/k", "tree": "E = k-1, density = 2/k",
        "mesh": "E >= k, 2/(k-1) <= density <= 1", "disconnected": "density varies"}
DEF = {"star": "one hub linked to every other linked agent; no spoke-spoke links",
       "chain": "the linked agents form a single path",
       "tree": "connected, no cycles, but not a path or star",
       "mesh": "connected and containing at least one cycle",
       "disconnected": "the linked agents split into two or more separate groups"}
INK, LINK, FLAG, GHOST, MUTED, OK, BAD = "#1b2230", "#2f5bd3", "#c27a12", "#a3abb9", "#5d6779", "#1f8a4c", "#c0392b"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "pdf.fonttype": 42})
W, H = 11, 8.5     # landscape letter


def num(a):
    return a.replace("agent_", "")


def short(p):
    repo = p["id"].split("__")[1].split("-")[0]
    return f"{repo} {p['id'].split('-')[1][:8]}"


def base(f):
    return f.split("/")[-1]


def layout(p):
    G = nx.Graph()
    G.add_nodes_from(p["part"])
    G.add_edges_from((l["a"], l["b"]) for l in p["links"])
    nodes, k = p["part"], len(p["part"])
    if p["topo"] == "star":
        hub = next(n for n in nodes if all(n in (l["a"], l["b"]) for l in p["links"]))
        rest = [n for n in nodes if n != hub]
        if len(rest) == 1:
            return {hub: (-0.8, 0), rest[0]: (0.8, 0)}
        if len(rest) == 2:      # a V instead of a straight line, so labels don't hide the arrowheads
            return {hub: (0, 0.55), rest[0]: (-0.9, -0.55), rest[1]: (0.9, -0.55)}
        pos = {hub: (0, 0)}
        pos.update(nx.circular_layout(rest))
        return pos
    if p["topo"] == "chain":
        path = [next(n for n in nodes if G.degree(n) == 1)]
        while len(path) < k:
            path.append(next(m for m in G[path[-1]] if m not in path))
        return {n: (-1 + 2 * i / (k - 1), 0.25 if i % 2 else -0.25) for i, n in enumerate(path)}
    if p["topo"] == "tree":
        root = min(nodes, key=lambda n: max(nx.single_source_shortest_path_length(G, n).values()))
        depth = nx.single_source_shortest_path_length(G, root)
        kids = {n: [m for m in G[n] if depth[m] == depth[n] + 1] for n in nodes}
        leaves = lambda n: sum(leaves(m) for m in kids[n]) or 1
        total, pos, x = leaves(root), {}, [0]
        dmax = max(depth.values())

        def place(n):
            if not kids[n]:
                pos[n] = (-1 + 2 * x[0] / max(total - 1, 1), 0); x[0] += 1
            else:
                for m in kids[n]:
                    place(m)
                xs = [pos[m][0] for m in kids[n]]
                pos[n] = ((min(xs) + max(xs)) / 2, 0)
            pos[n] = (pos[n][0], 1 - 2 * depth[n] / max(dmax, 1))
        place(root)
        return pos
    return nx.kamada_kawai_layout(G) if nx.is_connected(G) else nx.spring_layout(G, seed=3, k=1.2 / k ** 0.5)


def edge_label(l, dense):
    n = 1 if dense else 2
    s = ", ".join(l["objs"][:n]) + (f" +{len(l['objs']) - n}" if len(l["objs"]) > n else "")
    return "\n".join(textwrap.wrap(s, 30)[:2])


def draw(ax, p):
    ax.set_axis_off()
    pos = layout(p)
    xs = [v[0] for v in pos.values()]; ys = [v[1] for v in pos.values()]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sc = 1 / max(max(xs) - min(xs), max(ys) - min(ys), 1e-6) * 1.6
    pos = {n: ((x - cx) * sc, (y - cy) * sc) for n, (x, y) in pos.items()}
    ghosts = [a for a in p["agents"] if a not in p["part"]]
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-1.45 if ghosts else -1.1, 1.35)
    labels_on = p["E"] <= 8
    for l in p["links"]:
        (x1, y1), (x2, y2) = pos[l["a"]], pos[l["b"]]
        flag = bool(l["flags"])
        fwd, back = f"{l['a']}->{l['b']}" in l["dirs"], f"{l['b']}->{l['a']}" in l["dirs"]
        style = "<|-|>" if fwd and back else ("-|>" if fwd else "<|-")   # arrow points consumer -> definer
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=10, shrinkA=9, shrinkB=9,
                                     color=FLAG if flag else LINK, lw=1.0 + 0.5 * min(len(l["objs"]), 5),
                                     linestyle=(0, (4, 3)) if flag else "-", zorder=1))
        if labels_on:
            # stars: slide the label toward the spoke so labels don't pile up at the hub
            t = 0.5 if p["topo"] != "star" or p["k"] < 3 else (0.62 if all(l["a"] in (m["a"], m["b"]) for m in p["links"]) else 0.38)
            ax.text(x1 + t * (x2 - x1), y1 + t * (y2 - y1), edge_label(l, p["E"] > 4), fontsize=5.6, color=FLAG if flag else LINK,
                    ha="center", va="center", zorder=3,
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.85))
    for n, (x, y) in pos.items():
        ax.scatter([x], [y], s=260, color=INK, zorder=4)
        ax.text(x, y, num(n), color="white", fontsize=7.5, ha="center", va="center", weight="bold", zorder=5)
        ax.text(x, y - 0.11, base(p["files"][n]), fontsize=5.2, color=MUTED, ha="center", va="top", zorder=0.5,
                bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none", alpha=0.8))
    if ghosts:
        ax.text(-1.22, -1.33, "no link:", fontsize=5.5, color=GHOST, va="center")
        step = min(0.24, 1.9 / len(ghosts))
        for i, a in enumerate(ghosts):
            x = -0.92 + i * step
            ax.scatter([x], [-1.33], s=120, facecolors="none", edgecolors=GHOST, linestyle="--", lw=0.8)
            ax.text(x, -1.33, num(a), fontsize=5.5, color=GHOST, ha="center", va="center")
    res = p["resolved"]
    ax.set_title(short(p), fontsize=9, weight="bold", loc="left", color=INK, pad=3)
    ax.text(1.0, 1.0, "resolved" if res else "unresolved", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7, weight="bold", color=OK if res else BAD)
    sub = f"k/N {p['k']}/{p['N']}   E {p['E']}   density {p['density']:.3f}"
    if not labels_on:
        sub += "   (shared names: see appendix)"
    if p["alt"]:
        sub += f"\nuncertain: becomes {p['alt']} without flagged links"
    ax.text(0, 0.99, sub, transform=ax.transAxes, fontsize=6.5, color=MUTED, va="top", linespacing=1.5)


def legend(fig, y):
    h = [Line2D([], [], color=LINK, lw=2.2, marker=">", markevery=[1], markersize=6,
                label="gold link A -> B: A uses a name B defines/changes (thicker = more names)"),
         Line2D([], [], marker="o", color="w", markerfacecolor=INK, markersize=9, label="linked agent (in k), label = its gold file"),
         Line2D([], [], marker="o", color="w", markerfacecolor="none", markeredgecolor=GHOST, markersize=8, label="agent with no gold link (in N only)")]
    fig.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, y), ncol=2, frameon=False, fontsize=7)


def footer(fig, page):
    fig.text(0.5, 0.015, f"Sweep34 P2P gold dependency graphs  |  page {page}", ha="center", fontsize=6.5, color=MUTED)


with PdfPages(OUT) as pdf:
    page = 1
    # ---- cover / summary
    fig = plt.figure(figsize=(W, H))
    fig.text(0.06, 0.92, "Gold dependency graphs: P2P sweep34 (33 problems)", fontsize=18, weight="bold", color=INK)
    intro = ("Each problem's agent graph is built from the per-agent gold patches and file ownership, not from the "
             "conversations. Two agents are linked when one agent's gold slice uses a name the other's slice introduces or "
             "modifies (new def/class/CONSTANT, modified def, new keyword argument) or imports its module. Both directions and "
             "all shared names between a pair merge into ONE undirected link (counted once in E); arrows only show direction: "
             "A -> B means A's slice uses a name B's slice defines or changes. Links whose only shared name is a generic word are "
             "dropped. k = agents with at least one link, N = agents assigned, E = distinct linked pairs, "
             "density = 2E / [k(k-1)]. Star, chain and tree all have E = k-1, so their density is exactly 2/k.")
    fig.text(0.06, 0.885, "\n".join(textwrap.wrap(intro, 150)), fontsize=8.5, color=INK, va="top", linespacing=1.5)
    rows = []
    for t in ORDER:
        ps = [p for p in DATA if p["topo"] == t]
        if not ps:
            continue
        ks = sorted(p["k"] for p in ps)
        rows.append([t, str(len(ps)), RULE[t], f"{min(ks)}-{max(ks)}",
                     ", ".join(f"{d:.3g}" for d in sorted({p['density'] for p in ps}, reverse=True)),
                     f"{sum(p['density'] for p in ps) / len(ps):.2f}",
                     f"{sum(1 for p in ps if p['resolved'])}/{len(ps)}"])
    rows.append(["all", str(len(DATA)), "", f"{min(p['k'] for p in DATA)}-{max(p['k'] for p in DATA)}", "",
                 f"{sum(p['density'] for p in DATA) / len(DATA):.2f}", f"{sum(1 for p in DATA if p['resolved'])}/{len(DATA)}"])
    ax = fig.add_axes([0.06, 0.45, 0.88, 0.32]); ax.set_axis_off()
    tb = ax.table(cellText=rows, colLabels=["topology", "runs", "rule", "k range", "density values seen", "mean density",
                                            "resolved"],
                  loc="upper left", cellLoc="left", colWidths=[0.12, 0.07, 0.28, 0.09, 0.22, 0.11, 0.11])
    tb.auto_set_font_size(False); tb.set_fontsize(8.5); tb.scale(1, 1.7)
    for (r, c), cell in tb.get_celld().items():
        cell.set_edgecolor("#dde1e8")
        if r == 0:
            cell.set_text_props(weight="bold"); cell.set_facecolor("#eceff4")
        if r == len(rows):
            cell.set_text_props(weight="bold")
    notes = ["Four stars have only 2 linked agents (a single link), so their density is 1.0 by construction.",
             "All kept links are drawn and counted as certain, including import-only, non-Python-endpoint and sibling-class links.",
             "The beliefs and no-interface arms run the same problems, so their graphs are identical to these.",
             "Known issue: prep.py drops a whole link when only ONE direction shares a generic word. This wrongly drops "
             "ansible cb94c0cc 2-3",
             "  (shares add_tasknoplay_options; fixed: star 3/4, density 0.667) and openlibrary 6fdbbeee 3-6 (import of models.py; fixed: mesh 5/6,",
             "  density 0.5). Graphs here follow the analysis as committed.",
             "Source: multiagent_pro_out_p2p_sweep34/analysis/comm_measures/prep/p2p/*.json; resolved from eval_out/eval_results.json."]
    fig.text(0.06, 0.40, "\n".join("- " + n for n in notes), fontsize=8, color=MUTED, va="top", linespacing=1.6)
    legend(fig, 0.06)
    footer(fig, page); pdf.savefig(fig); plt.close(fig); page += 1

    # ---- graph pages: 2 x 3 panels, grouped by topology
    for t in ORDER:
        ps = sorted([p for p in DATA if p["topo"] == t], key=lambda p: (p["k"], p["N"], p["id"]))
        per = 6 if t in ("star", "chain") else 4
        for start in range(0, len(ps), per):
            chunk = ps[start:start + per]
            fig, axes = plt.subplots(2, per // 2, figsize=(W, H))
            fig.subplots_adjust(left=0.04, right=0.96, top=0.86, bottom=0.1, wspace=0.12, hspace=0.32)
            part = f" ({start // per + 1}/{(len(ps) + per - 1) // per})" if len(ps) > per else ""
            fig.text(0.04, 0.94, f"{t.capitalize()}{part}", fontsize=15, weight="bold", color=INK)
            fig.text(0.04, 0.915, f"{len(ps)} problems  |  {RULE[t]}  |  {DEF[t]}", fontsize=8.5, color=MUTED)
            for ax, p in zip(axes.flat, chunk):
                draw(ax, p)
            for ax in list(axes.flat)[len(chunk):]:
                ax.set_axis_off()
            legend(fig, 0.025)
            footer(fig, page); pdf.savefig(fig); plt.close(fig); page += 1

    # ---- appendix: link table
    lines = []
    for t in ORDER:
        for p in sorted([p for p in DATA if p["topo"] == t], key=lambda p: (p["k"], p["N"], p["id"])):
            lines.append(("h", f"{short(p)}  [{t}{', uncertain -> ' + p['alt'] if p['alt'] else ''}]  k/N {p['k']}/{p['N']}, "
                               f"E {p['E']}, density {p['density']:.3f}, {'resolved' if p['resolved'] else 'UNRESOLVED'}"))
            files = ", ".join(f"{num(a)}={base(p['files'][a])}" for a in p["agents"])
            for w in textwrap.wrap("agents: " + files, 175):
                lines.append(("f", w))
            for l in p["links"]:
                fwd, back = f"{l['a']}->{l['b']}" in l["dirs"], f"{l['b']}->{l['a']}" in l["dirs"]
                arrow = "<->" if fwd and back else ("->" if fwd else "<-")
                s = f"{num(l['a'])} {arrow} {num(l['b'])}: {', '.join(l['objs'])}" + (f"   [flag: {'; '.join(l['flags'])}]" if l["flags"] else "")
                for i, w in enumerate(textwrap.wrap(s, 170)):
                    lines.append(("fl" if l["flags"] else "l", ("    " if i else "") + w))
            for l in p["dropped"]:
                lines.append(("f", f"dropped (generic name only) {num(l['a'])}-{num(l['b'])}: {', '.join(l['objs'])}"))
            lines.append(("s", ""))
    per = 62
    for start in range(0, len(lines), per):
        fig = plt.figure(figsize=(W, H))
        fig.text(0.04, 0.95, "Appendix: links and shared names per problem", fontsize=13, weight="bold", color=INK)
        y = 0.915
        for kind, s in lines[start:start + per]:
            style = {"h": dict(weight="bold", color=INK, fontsize=7), "f": dict(color=MUTED, fontsize=6),
                     "l": dict(color=LINK, fontsize=6), "fl": dict(color=FLAG, fontsize=6), "s": dict(fontsize=4)}[kind]
            fig.text(0.04, y, s, family="DejaVu Sans Mono" if kind in ("l", "fl") else "DejaVu Sans", va="top", **style)
            y -= 0.0135
        footer(fig, page); pdf.savefig(fig); plt.close(fig); page += 1

print("pages", page - 1)
