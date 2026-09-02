#!/usr/bin/env python3
"""Reciprocity metrics for a communication-harness sweep: when a peer asks a question, does
anyone answer -- and does answering depend on the responder having already submitted?

Motivation. Agents were originally told to answer a peer only in NOTICE_SUBMITTED, which the
host delivers ONLY to agents that have already submitted. Responsiveness was therefore a
function of submission timing rather than of the communication topology under study. The
`before/after submit` split below is the direct measurement of that confound: it should be
roughly flat once the instruction applies to working agents too.

TWO ADDRESSING CRITERIA, always reported side by side. They disagree, and each is unfair to
one harness, so picking one silently would manufacture a ranking:

  addressed  -- the reply sets `to` = the asker, OR names the asker in its text.
                Gives every harness credit for whatever addressing it actually has.
  named      -- the reply names the asker in its TEXT only.
                Identical test everywhere, but under-counts p2p, which addresses with the
                `to` field and so has no reason to name anyone in the body.

In the v1 sweep these two orderings were opposite (broadcast 14%/14%, p2p 42%/2%), which is
why both are printed and neither is called "the" answer rate.

Everything is additionally split by the coupling label from metrics/tag_coupling.py: a
harness cannot matter on a `decomposable` instance by construction.

Rounds are reconstructed from the `board_after_round_<n>.json` snapshots -- board.json alone
carries no round stamp.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CELLS = [("broadcast", "out_broadcast"), ("p2p", "out_p2p"), ("p2p+beliefs", "out_p2p_beliefs")]
ROLES = ("definer", "consumer", "both", "isolated")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def rounds_of(inst_dir: Path) -> list:
    """[(round, message)] in publication order, from the per-round board snapshots."""
    snaps = sorted(inst_dir.glob("board_after_round_*.json"),
                   key=lambda p: int(re.search(r"_(\d+)\.json$", p.name).group(1)))
    prev, out = 0, []
    for s in snaps:
        try:
            b = json.load(open(s))
        except Exception:
            continue
        r = int(re.search(r"_(\d+)\.json$", s.name).group(1))
        out.extend((r, m) for m in b[prev:])
        prev = len(b)
    return out


def submitted_rounds(inst_dir: Path) -> dict:
    """agent -> first round in which comm_stats recorded it as submitted."""
    try:
        rows = json.load(open(inst_dir / "comm_stats.json"))
    except Exception:
        return {}
    out = {}
    for x in rows:
        if isinstance(x, dict) and x.get("submitted") and x.get("agent") not in out:
            out[x["agent"]] = x.get("round")
    return out


def agent_roles(built_dir: Path, iid: str) -> dict:
    """agent -> definer|consumer|both|isolated, from tag_coupling's spec.json annotation.
    Empty when tag_coupling.py has not been run against this built-instance folder."""
    try:
        c = json.load(open(built_dir / iid / "spec.json")).get("coupling") or {}
    except Exception:
        return {}
    return {a: v.get("role") for a, v in (c.get("per_agent") or {}).items()}


def coupling_labels(built_dir: Path) -> dict:
    idx = REPO / "multiagent_pro_out" / "coupling_index.json"
    if idx.exists():
        d = json.load(open(idx))
        rows = d.get("instances", d) if isinstance(d, dict) else d
        out = {r["instance_id"]: r.get("label") for r in rows if r.get("instance_id")}
        if out:
            return out
    out = {}
    for spec in built_dir.glob("*/spec.json"):
        try:
            c = json.load(open(spec)).get("coupling") or {}
        except Exception:
            continue
        if c.get("label"):
            out[spec.parent.name] = c["label"]
    return out


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def is_question(m: dict) -> bool:
    return m.get("type") == "message" and "?" in (m.get("text") or "")


def names(text: str, aid: str) -> bool:
    return bool(re.search(rf"\b@?{re.escape(aid)}\b", text or ""))


def analyse_instance(inst_dir: Path, roles: dict) -> dict:
    """Per-instance counters. One dict so the caller can just sum them."""
    msgs = rounds_of(inst_dir)
    sub = submitted_rounds(inst_dir)
    acc = {"questions": 0, "addressed": 0, "named": 0, "reask": 0,
           "latency": [], "ans_before": 0, "ans_after": 0,
           "by_role_q": {r: 0 for r in ROLES}, "by_role_a": {r: 0 for r in ROLES}}

    for r, m in msgs:
        if not is_question(m):
            continue
        acc["questions"] += 1
        src, to = m.get("from"), m.get("to")
        tgt = None if to == "all" else to          # broadcast question: any peer may answer

        # who is on the hook for this question -- used for the role breakdown
        on_hook = [tgt] if tgt else [a for a in roles if a != src]
        for a in on_hook:
            if roles.get(a) in acc["by_role_q"]:
                acc["by_role_q"][roles[a]] += 1

        hit_addr = hit_named = None
        for rr, x in msgs:
            if rr <= r or x.get("type") != "message" or x.get("from") == src:
                continue
            if tgt and x.get("from") != tgt:
                continue
            txt = x.get("text") or ""
            if names(txt, src):
                hit_named = hit_named or (rr, x)
            if x.get("to") == src or names(txt, src):
                hit_addr = hit_addr or (rr, x)
        if hit_addr:
            acc["addressed"] += 1
            acc["latency"].append(hit_addr[0] - r)
            responder = hit_addr[1].get("from")
            if roles.get(responder) in acc["by_role_a"]:
                acc["by_role_a"][roles[responder]] += 1
        if hit_named:
            acc["named"] += 1

        # did the asker give up and repeat itself?
        for rr, x in msgs:
            if rr > r and is_question(x) and x.get("from") == src and difflib.SequenceMatcher(
                    None, (m.get("text") or "")[:200], (x.get("text") or "")[:200]).ratio() > 0.6:
                acc["reask"] += 1
                break

    # THE CONFOUND METRIC: answer-shaped (non-question) messages, split by whether the sender
    # had already submitted when it sent them.
    for r, m in msgs:
        if m.get("type") != "message" or "?" in (m.get("text") or ""):
            continue
        s = sub.get(m.get("from"))
        acc["ans_after" if (s is not None and r >= s) else "ans_before"] += 1
    return acc


def merge(a: dict, b: dict) -> dict:
    for k, v in b.items():
        if isinstance(v, list):
            a[k].extend(v)
        elif isinstance(v, dict):
            for kk, vv in v.items():
                a[k][kk] += vv
        else:
            a[k] += v
    return a


def blank() -> dict:
    return {"questions": 0, "addressed": 0, "named": 0, "reask": 0, "latency": [],
            "ans_before": 0, "ans_after": 0,
            "by_role_q": {r: 0 for r in ROLES}, "by_role_a": {r: 0 for r in ROLES}}


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def report(title: str, per_cell: dict) -> None:
    ids_n = {c: per_cell[c] for c, _ in CELLS}
    print(f"\n===== {title} =====")
    print(f"{'':26s}" + "".join(f"{c:>16s}" for c, _ in CELLS))
    print("-" * (26 + 16 * len(CELLS)))

    def line(label, fn):
        print(f"{label:26s}" + "".join(f"{fn(ids_n[c]):>16s}" for c, _ in CELLS))

    def pct(n, d):
        return f"{n} ({100*n/d:.0f}%)" if d else "n/a"

    line("questions asked", lambda d: str(d["questions"]))
    line("  answered [addressed]", lambda d: pct(d["addressed"], d["questions"]))
    line("  answered [named]", lambda d: pct(d["named"], d["questions"]))
    line("  re-asked by the asker", lambda d: pct(d["reask"], d["questions"]))
    line("median rounds to answer", lambda d: f"{statistics.median(d['latency']):.1f}"
         if d["latency"] else "n/a")
    print()
    line("answer-shaped messages", lambda d: str(d["ans_before"] + d["ans_after"]))
    line("  sent BEFORE submitting", lambda d: pct(d["ans_before"], d["ans_before"] + d["ans_after"]))
    line("  sent AFTER submitting", lambda d: pct(d["ans_after"], d["ans_before"] + d["ans_after"]))
    if any(sum(d["by_role_q"].values()) for d in ids_n.values()):
        print("\n  answer rate by responder's coupling role (definers are who peers must ask):")
        for r in ROLES:
            line(f"    {r}", lambda d, r=r: pct(d["by_role_a"][r], d["by_role_q"][r]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="/media/data/dkalwar/maswe_bench_v2",
                    help="sweep root holding ids20.txt")
    ap.add_argument("--model", default=None,
                    help="per-model subdirectory under --base (omit for the flat v1 layout)")
    ap.add_argument("--output", default=str(REPO / "multiagent_pro_bench20"),
                    help="built-instance folder, read for per-agent coupling roles")
    ap.add_argument("--instances", nargs="*", help="restrict to these instance ids")
    a = ap.parse_args()

    base = Path(a.base)
    root = base / a.model if a.model else base
    built = Path(a.output)
    ids = a.instances or [l.strip() for l in open(base / "ids20.txt") if l.strip()]
    labels = coupling_labels(built)

    strata = {"COUPLED": [i for i in ids if labels.get(i) == "coupled"],
              "DECOMPOSABLE": [i for i in ids if labels.get(i) == "decomposable"],
              "ALL POOLED": ids}

    print(f"\n{'#'*66}\n# reciprocity: {root}\n{'#'*66}")
    have_roles = False
    for title, sub in strata.items():
        if not sub:
            continue
        per_cell = {}
        for cell, d in CELLS:
            acc = blank()
            for i in sub:
                inst = root / d / i
                if not inst.exists():
                    continue
                roles = agent_roles(built, i)
                have_roles = have_roles or bool(roles)
                merge(acc, analyse_instance(inst, roles))
            per_cell[cell] = acc
        report(f"{title}  (n={len(sub)})", per_cell)

    if not have_roles:
        print("\nNOTE: no per-agent coupling roles found under", built,
              "\n      -> the role breakdown is omitted. To enable it, run:",
              f"\n      python multiagent_pro/metrics/tag_coupling.py --output {built}")


if __name__ == "__main__":
    main()
