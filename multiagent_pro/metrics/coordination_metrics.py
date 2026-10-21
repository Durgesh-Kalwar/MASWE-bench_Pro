#!/usr/bin/env python
"""Coordination and communication metrics for a multiagent_pro run.

Everything is computed from artifacts the run already writes -- board.json and its per-round
snapshots, comm_stats.json, cost_stats.json, traj/round_k.json, context/messages.jsonl (when
--dump-context was on) and the final agent_<k>.patch files -- so it is deterministic and
needs no LLM. Per instance it reports:

  outcome        resolved (from an eval_results.json if given), cost, steps, LLM calls.
  volume         messages (directed / broadcast), interfaces published, per-agent sent+received,
                 and `dup_rate`: share of messages that near-repeat an earlier message by the
                 same sender (word-Jaccard >= 0.7) -- resends are pure overhead.
  dependency     a REALIZED dependency graph built from the final patches: edge consumer->definer
                 whenever a name that one agent's patch introduces (def/class/CONST) is used in
                 another agent's added lines, or the consumer imports the definer's module.
                 This is what the agents actually built, independent of the gold decomposition.
  targeting      contact_recall = share of realized edges whose two agents exchanged at least
                 one directed message (either way) or a broadcast that names the other;
                 directed_precision = share of directed messages that lie on a realized edge.
  interface      agreement = share of (edge, name) pairs where every consumer call's keyword
                 args exist in the definer's FINAL signature and the positional count fits;
                 publish_coverage = share of consumed names that the definer published with
                 publish_interface; publish_drift = published signatures whose parameter set
                 differs from the final def.
  responsiveness requests = messages with a question or a "please <verb>" aimed at a peer;
                 answered_rate = share with any later message from that peer back to the
                 requester (or to all); latency in rounds. Delivery is next-round, so 1 is
                 the floor.
  convergence    per agent: first round it submitted, last round it edited a repo file,
                 post_submit_edit_rounds (edited after first submit), idle rounds (only the
                 submit sentinel). settled_rate = agents with no post-submit edits.
  context        from the dumped prompts: delivered_rate (message present in the recipient's
                 round-r prompt), retained_next_round (still present at round r+1 -- the
                 harness expires mail after one round, so this measures that policy), and
                 uptake_rate = share of delivered messages whose sender is referred to in the
                 recipient's thoughts during the round it was delivered.

A provisional `coord_score` (0-100) averages contact_recall, interface agreement,
answered_rate, 1-dup_rate, uptake_rate and settled_rate; the components matter more than the
composite and are all printed.

Usage:
    python multiagent_pro/metrics/coordination_metrics.py --run-root <run dir>
        [--instances ...] [--eval-results <eval_results.json>] [--out <dir>]
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TEST_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]+\.py$|_test\.py$|conftest\.py$")
EDIT_RE = re.compile(r"sed\s+-i|cat\s*>>?\s*(?!/tmp)|tee\s+(?!/tmp)|python3?\s+-\s*<<|python3?\s+-c\s+[\"'].{0,200}open\(.{0,80}['\"]w|git\s+apply|\bpatch\s+-p|>\s*(?!/tmp|/dev)\S+\.(py|yml|yaml|rst|txt|html|js|less|json)\b")
SUBMIT = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
STOP_NAMES = {"__init__", "main", "setUp", "tearDown", "run", "get", "set", "self", "cls", "args", "kwargs", "data", "name", "path", "value"}


# --------------------------------------------------------------------------- loading
def load(inst_dir):
    spec = json.loads((inst_dir / "spec.json").read_text())
    board = json.loads((inst_dir / "board.json").read_text())
    lens, k = [], 1
    while (inst_dir / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((inst_dir / f"board_after_round_{k}.json").read_text())))
        k += 1
    for i, m in enumerate(board):
        m["round"] = next((r + 1 for r, n in enumerate(lens) if i < n), len(lens) or None)
    comm = json.loads((inst_dir / "comm_stats.json").read_text()) if (inst_dir / "comm_stats.json").exists() else []
    cost = json.loads((inst_dir / "cost_stats.json").read_text()) if (inst_dir / "cost_stats.json").exists() else {}
    agents = {}
    for a in spec["agents"]:
        ad = inst_dir / a["id"]
        steps = []
        for rf in sorted(ad.glob("traj/round_*.json"), key=lambda p: int(p.stem.split("_")[1])):
            r = int(rf.stem.split("_")[1])
            for s in json.load(open(rf)):
                steps.append({"round": r, "step": s.get("step"), "thought": s.get("thought") or "",
                              "action": s.get("action") or "", "obs": s.get("observation") or ""})
        ctx = []
        cf = ad / "context" / "messages.jsonl"
        if cf.exists():
            for line in cf.read_text().splitlines():
                if line.strip():
                    c = json.loads(line)
                    txt = "\n".join(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])
                                    for m in c["messages"])
                    ctx.append({"round": c["round"], "step": c["step_in_round"], "text": txt})
        pf = inst_dir / f"{a['id']}.patch"
        agents[a["id"]] = {"gold": a["gold_file"], "steps": steps, "ctx": ctx,
                           "patch": pf.read_text() if pf.exists() else ""}
    return spec, board, comm, cost, agents, len(lens)


# --------------------------------------------------------------------------- patch analysis
def added_lines(patch, skip_tests=True):
    """[(file, line)] for '+' lines, excluding test files by default."""
    out, cur = [], None
    for line in patch.splitlines():
        m = re.match(r"^diff --git a/(\S+)", line)
        if m:
            cur = m.group(1)
            continue
        if cur and line.startswith("+") and not line.startswith("+++"):
            if skip_tests and TEST_RE.search(cur):
                continue
            out.append((cur, line[1:]))
    return out


def defined_names(patch):
    names = {}
    for f, l in added_lines(patch):
        m = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", l) or re.match(r"\s*class\s+(\w+)", l) \
            or re.match(r"([A-Z][A-Z0-9_]{3,})\s*=", l)
        if m and m.group(1) not in STOP_NAMES and not m.group(1).startswith("test_") and len(m.group(1)) >= 4:
            names.setdefault(m.group(1), f)
    return names


def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def balanced(lines, start_idx, open_at):
    """Join lines from start_idx until the paren opened at open_at closes."""
    buf, depth = "", 0
    for l in lines[start_idx:start_idx + 12]:
        for i, ch in enumerate(l if buf else l[open_at:]):
            buf += ch
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return buf
        buf += "\n"
    return buf


def final_signature(patch, name):
    """Parameters of `def name(...)` in the patch's added lines; None if not defined there."""
    lines = [l for _, l in added_lines(patch)]
    for i, l in enumerate(lines):
        m = re.match(r"\s*(?:async\s+)?def\s+" + re.escape(name) + r"\s*\(", l)
        if m:
            body = balanced(lines, i, m.end() - 1)
            inner = body[1:-1] if body.endswith(")") else body[1:]
            params, star, dstar = [], False, False
            for p in split_args(inner):
                p = p.split(":")[0].split("=")[0].strip()
                if p.startswith("**"):
                    dstar = True
                elif p.startswith("*"):
                    star = True
                elif p and p not in ("self", "cls"):
                    params.append(p)
            return {"params": params, "star": star, "dstar": dstar}
    return None


def calls_of(patch, name):
    """[(file, kwargs, n_positional)] for calls to `name(` in added lines (not the def)."""
    out = []
    by_file = defaultdict(list)
    for f, l in added_lines(patch):
        by_file[f].append(l)
    for f, lines in by_file.items():
        for i, l in enumerate(lines):
            for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"\s*\(", l):   # obj.name( counts
                if re.search(r"\bdef\s+" + re.escape(name) + r"\s*\($", l[:m.end()]):
                    continue
                body = balanced(lines, i, m.end() - 1)
                inner = body[1:-1] if body.endswith(")") else body[1:]
                kw, pos = [], 0
                for a in split_args(inner):
                    if re.match(r"^\w+\s*=(?!=)", a):
                        kw.append(a.split("=")[0].strip())
                    elif a and not a.startswith("*"):
                        pos += 1
                out.append((f, kw, pos))
    return out


def parse_published(text):
    """'Class.method(a, b=1, *c, **d)' -> (method, params, star, dstar); None if no parens."""
    text = re.split(r"\)\s*->", text.strip(), 1)[0] + (")" if re.search(r"\)\s*->", text) else "")
    m = re.search(r"([\w.]+)\s*\((.*)\)\s*$", text.strip(), re.S)
    if not m:
        return None
    name = m.group(1).split(".")[-1]
    params, star, dstar = [], False, False
    for p in split_args(m.group(2)):
        p = p.split(":")[0].split("=")[0].strip()
        if p.startswith("**"):
            dstar = True
        elif p.startswith("*"):
            star = True
        elif p and p not in ("self", "cls"):
            params.append(p)
    return name, params, star, dstar


# --------------------------------------------------------------------------- metrics
def jaccard(a, b):
    A, B = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(A & B) / len(A | B) if A | B else 0.0


def analyze(inst_dir, resolved):
    spec, board, comm, cost, agents, n_rounds = load(inst_dir)
    ids = list(agents)
    msgs = [m for m in board if m.get("type") == "message"]
    ifaces = [m for m in board if m.get("type") == "interface"]
    R = {"instance": inst_dir.name, "n_agents": len(ids), "rounds": n_rounds, "resolved": resolved,
         "cost": round(cost.get("spent", 0.0), 2), "budget": cost.get("instance_budget"),
         "steps": sum(len(a["steps"]) for a in agents.values()),
         "llm_calls": cost.get("total", {}).get("calls")}

    # ---- volume
    directed = [m for m in msgs if m["to"] != "all"]
    R["messages"] = len(msgs)
    R["directed"] = len(directed)
    R["broadcast"] = len(msgs) - len(directed)
    R["interfaces"] = len(ifaces)
    dups = 0
    for i, m in enumerate(msgs):
        if any(x["from"] == m["from"] and jaccard(x["text"], m["text"]) >= 0.7 for x in msgs[:i]):
            dups += 1
    R["dup_rate"] = round(dups / len(msgs), 2) if msgs else 0.0
    R["msgs_per_agent"] = {a: sum(1 for m in msgs if m["from"] == a) for a in ids}

    # ---- realized dependency graph
    defs = {a: defined_names(agents[a]["patch"]) for a in ids}
    edges = {}      # (consumer, definer) -> [names]
    for c in ids:
        added = "\n".join(l for _, l in added_lines(agents[c]["patch"]))
        toks = set(re.findall(r"\w+", added))
        for d in ids:
            if d == c:
                continue
            shared = [n for n in defs[d] if n in toks]
            mod = re.sub(r"^lib/", "", agents[d]["gold"]).replace(".py", "").replace("/", ".")
            if re.search(r"(from|import)\s+" + re.escape(mod) + r"\b", added):
                shared.append(f"<import {mod}>")
            if shared:
                edges[(c, d)] = shared
    R["dep_edges"] = {f"{c}->{d}": v for (c, d), v in edges.items()}
    pairs = {frozenset(e) for e in edges}
    # ---- targeting
    def in_contact(a, b):
        return any((m["from"], m["to"]) in ((a, b), (b, a)) for m in directed) or \
            any(m["from"] == a and m["to"] == "all" and b in m["text"] for m in msgs) or \
            any(m["from"] == b and m["to"] == "all" and a in m["text"] for m in msgs)
    R["contact_recall"] = round(sum(in_contact(*tuple(p)) for p in pairs) / len(pairs), 2) if pairs else None
    R["directed_precision"] = round(sum(frozenset((m["from"], m["to"])) in pairs for m in directed) / len(directed), 2) if directed and pairs else None

    # ---- interface agreement + publication
    checks, ok, mism, published, consumed_names = 0, 0, [], 0, 0
    pub_by_agent = defaultdict(list)
    for m in ifaces:
        p = parse_published(m.get("signature") or m.get("text", ""))
        if p:
            pub_by_agent[m["from"]].append(p)
    for (c, d), names in edges.items():
        for n in names:
            if n.startswith("<import"):
                continue
            consumed_names += 1
            if any(p[0] == n for p in pub_by_agent[d]):
                published += 1
            sig = final_signature(agents[d]["patch"], n)
            if sig is None:          # class / constant: nothing to check
                continue
            for f, kw, pos in calls_of(agents[c]["patch"], n):
                checks += 1
                bad_kw = [k for k in kw if k not in sig["params"] and not sig["dstar"]]
                too_many = pos > len(sig["params"]) and not sig["star"]
                if bad_kw or too_many:
                    mism.append({"consumer": c, "definer": d, "name": n, "file": f, "bad_kwargs": bad_kw,
                                 "positional": pos, "params": sig["params"]})
                else:
                    ok += 1
    R["iface_checks"] = checks
    R["iface_agreement"] = round(ok / checks, 2) if checks else None
    R["iface_mismatches"] = mism
    R["publish_coverage"] = round(published / consumed_names, 2) if consumed_names else None
    drift = []
    for a, pubs in pub_by_agent.items():
        for name, params, star, dstar in pubs:
            sig = final_signature(agents[a]["patch"], name)
            if sig and set(params) != set(sig["params"]):
                drift.append({"agent": a, "name": name, "published": params, "final": sig["params"]})
    R["publish_drift"] = drift

    # ---- responsiveness
    reqs, answered, lat = 0, 0, []
    for m in msgs:
        is_req = "?" in m["text"] or re.search(r"please\s+(\w+\s+)?(confirm|reply|implement|add|change|update|define|expose|tell|let me know|check)", m["text"], re.I)
        if not is_req:
            continue
        targets = [m["to"]] if m["to"] != "all" else sorted(set(re.findall(r"(agent_\d+)[:,]?\s*(?:please|can you|could you|should)", m["text"])) - {m["from"]})
        for t in targets:
            reqs += 1
            reply = next((x for x in msgs if x["from"] == t and x["to"] in (m["from"], "all") and x["ts"] > m["ts"]), None)
            if reply:
                answered += 1
                lat.append(max(1, (reply["round"] or 0) - (m["round"] or 0)))
    R["requests"] = reqs
    R["answered_rate"] = round(answered / reqs, 2) if reqs else None
    R["mean_latency_rounds"] = round(sum(lat) / len(lat), 2) if lat else None

    # ---- convergence
    conv = {}
    for a in ids:
        rows = [r for r in comm if r["agent"] == a]
        first_submit = next((r["round"] for r in rows if r.get("submitted")), None)
        edit_rounds = sorted({s["round"] for s in agents[a]["steps"] if EDIT_RE.search(s["action"]) and "send_message" not in s["action"][:20]})
        idle = sum(1 for r in rows if r["steps"] == 1 and any(s["round"] == r["round"] and SUBMIT in s["action"] for s in agents[a]["steps"]))
        post = [r for r in edit_rounds if first_submit and r > first_submit]
        conv[a] = {"first_submit": first_submit, "last_edit": edit_rounds[-1] if edit_rounds else None,
                   "post_submit_edit_rounds": post, "idle_rounds": idle}
    R["convergence"] = conv
    R["settled_rate"] = round(sum(1 for v in conv.values() if not v["post_submit_edit_rounds"]) / len(ids), 2)
    R["idle_share"] = round(sum(v["idle_rounds"] for v in conv.values()) / (len(ids) * n_rounds), 2) if n_rounds else None
    R["mean_first_submit"] = round(sum(v["first_submit"] or n_rounds for v in conv.values()) / len(ids), 1)

    # ---- context delivery / retention / uptake
    deliv, retained, uptake, n = 0, 0, 0, 0
    for a in ids:
        ctx = agents[a]["ctx"]
        if not ctx:
            continue
        for m in msgs:
            if m["from"] == a or m["to"] not in (a, "all") or not m["round"] or m["round"] >= n_rounds:
                continue
            key = m["text"][:50]
            r_deliv = m["round"] + 1
            p_now = next((c for c in ctx if c["round"] == r_deliv and c["step"] == 1), None)
            p_next = next((c for c in ctx if c["round"] == r_deliv + 1 and c["step"] == 1), None)
            if p_now is None:
                continue
            n += 1
            deliv += key in p_now["text"]
            if p_next is not None:
                retained += key in p_next["text"]
            thoughts = " ".join(s["thought"] for s in agents[a]["steps"] if s["round"] == r_deliv)
            uptake += m["from"] in thoughts
    R["ctx_checked"] = n
    R["delivered_rate"] = round(deliv / n, 2) if n else None
    R["retained_next_round"] = round(retained / n, 2) if n else None
    R["uptake_rate"] = round(uptake / n, 2) if n else None

    comps = [x for x in (R["contact_recall"], R["iface_agreement"], R["answered_rate"],
                         1 - R["dup_rate"], R["uptake_rate"], R["settled_rate"]) if x is not None]
    R["coord_score"] = round(100 * sum(comps) / len(comps)) if comps else None
    return R


def fmt(v):
    return "-" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--instances", nargs="*")
    ap.add_argument("--eval-results", help="eval_results.json from swe_bench_pro_eval.py")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = Path(args.run_root)
    results = json.load(open(args.eval_results)) if args.eval_results else {}
    if args.instances:
        dirs = [root / i for i in args.instances]
    else:
        dirs = [d for d in sorted(root.glob("instance_*")) if (d / "spec.json").exists()
                and len(list(d.glob("agent_*.patch"))) == json.loads((d / "spec.json").read_text())["num_agents"]]
    rows = [analyze(d, results.get(d.name)) for d in dirs]

    cols = ["n_agents", "resolved", "cost", "messages", "directed", "dup_rate", "contact_recall", "directed_precision",
            "iface_checks", "iface_agreement", "publish_coverage", "requests", "answered_rate", "mean_latency_rounds",
            "mean_first_submit", "settled_rate", "idle_share", "delivered_rate", "retained_next_round", "uptake_rate", "coord_score"]
    lines = [f"# Coordination metrics: {len(rows)} instances", "",
             "| instance | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for r in rows:
        lines.append(f"| {r['instance'][9:40]} | " + " | ".join(fmt(r.get(c)) for c in cols) + " |")

    def mean(c):
        v = [r[c] for r in rows if isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool)]
        return round(sum(v) / len(v), 2) if v else None
    lines.append("| **mean** | " + " | ".join(fmt(mean(c)) if c != "resolved" else
                                              f"{sum(1 for r in rows if r['resolved'])}/{sum(1 for r in rows if r['resolved'] is not None)}"
                                              for c in cols) + " |")
    res = [r for r in rows if r["resolved"] is True]
    unres = [r for r in rows if r["resolved"] is False]
    if res and unres:
        lines += ["", "## Resolved vs unresolved (means)", "", "| metric | resolved | unresolved |", "|---|---|---|"]
        for c in cols[2:]:
            def m(rs):
                v = [r[c] for r in rs if isinstance(r.get(c), (int, float))]
                return round(sum(v) / len(v), 2) if v else None
            lines.append(f"| {c} | {fmt(m(res))} | {fmt(m(unres))} |")
    lines += ["", "## Interface mismatches (consumer call vs definer's final signature)", ""]
    for r in rows:
        for x in r["iface_mismatches"]:
            lines.append(f"- {r['instance'][9:40]}: {x['consumer']} calls {x['name']}(bad kwargs={x['bad_kwargs']}, "
                         f"positional={x['positional']}) but {x['definer']} defines params={x['params']}")
    lines += ["", "## Published-vs-final signature drift", ""]
    for r in rows:
        for x in r["publish_drift"]:
            lines.append(f"- {r['instance'][9:40]} {x['agent']} {x['name']}: published {x['published']} -> final {x['final']}")
    lines += ["", "## Realized dependency edges (consumer -> definer: names)", ""]
    for r in rows:
        if r["dep_edges"]:
            lines.append(f"- {r['instance'][9:40]}: " + "; ".join(f"{k}: {', '.join(v[:4])}" for k, v in r["dep_edges"].items()))
    lines += ["", "## Convergence per agent (first_submit / last_edit / post-submit edit rounds / idle rounds)", ""]
    for r in rows:
        lines.append(f"- {r['instance'][9:40]}: " + "; ".join(
            f"{a} {v['first_submit']}/{v['last_edit']}/{v['post_submit_edit_rounds']}/{v['idle_rounds']}" for a, v in r["convergence"].items()))
    report = "\n".join(lines)
    print(report)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        json.dump(rows, open(out / "metrics.json", "w"), indent=1)
        (out / "metrics.md").write_text(report)
        print(f"\nwrote {out}/metrics.json, metrics.md", file=sys.stderr)


if __name__ == "__main__":
    main()
