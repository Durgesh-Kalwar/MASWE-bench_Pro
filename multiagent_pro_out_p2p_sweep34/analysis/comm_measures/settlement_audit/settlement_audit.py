#!/usr/bin/env python
"""Mechanical audit of the `initially_settled` link labels (P2P arm only; read-only over run data).

A link is initially settled when both endpoints held compatible, correct decisions before any
message could change them. The audit checks that against the trajectories:

  * an EDIT that names a link object = a file-writing command (python write, sed -i, heredoc,
    tee, git apply, ...) whose text contains one of the link's gold-object forms. Errored steps are
    kept: annotators found edits that applied before a later command in the same step failed;
  * per endpoint, the FIRST round of such an edit. If the later endpoint first writes the name in
    round >= 2 AND had already been delivered a message naming a link object, a message may have
    supplied the decision, so the label needs a manual check (`needs_check`).

The LAST name-bearing edit is reported too but is not used: agents keep editing their files long
after a contract is fixed (imports, tests, cleanup), so it says little about settlement.

Edits are detected from command text because the harness saves no per-step file snapshots: an
edit that never spells out the name (e.g. a line-number sed) is missed, and a write that merely
mentions the name is counted. Manual verdicts on every flagged link are in AUDIT.md.

Outputs (this folder): link_edits.csv (every P2P link), needs_check.csv (flagged initially-settled links).
"""
import csv, json, re
from collections import Counter
from pathlib import Path

A = Path(__file__).resolve().parent
CM = A.parent
RUNS = CM.parent.parent          # multiagent_pro_out_p2p_sweep34/<instance>/agent_k/traj/round_r.json
WRITE = re.compile(r"sed -i|perl -[a-z]*i|\bcat\s*>|\btee\b|open\([^)]*['\"][wa]['\"]|write_text|\.write\(|git apply|patch -p")


def named(text, forms):
    return any(re.search(r"\b" + re.escape(f) + r"\b", text) for f in forms)


def edits(inst, aid):
    out = []
    for f in (RUNS / inst / aid / "traj").glob("round_*.json"):
        r = int(f.stem.split("_")[1])
        out += [(r, s["step"], s.get("action") or "") for s in json.load(open(f)) if WRITE.search(s.get("action") or "")]
    return sorted(out)


labels = {(r["instance"], tuple(sorted(json.loads(r["agents"])))): r
          for r in csv.DictReader(open(CM / "links.csv")) if r["arm"] == "p2p"}
rows = []
for f in sorted((CM / "prep/p2p").glob("*.json")):
    d = json.load(open(f)); inst = d["instance"]
    conv = d["conversations"]
    for L in d["graph"]["links"]:
        pair = tuple(sorted(L["agents"]))
        forms = [x for o in L["objects"] for x in o["forms"]]
        hits = {a: [(r, s) for r, s, act in edits(inst, a) if named(act, forms)] for a in pair}
        first = {a: min(h)[0] for a, h in hits.items() if h}
        allh = [h for a in pair for h in hits[a]]
        lab = labels[(inst, pair)]
        row = {"instance": inst, "pair": "-".join(a.split("_")[1] for a in pair), "status": lab["status"],
               "settled_round": lab["settled_round"], "objects": "|".join(o["label"] for o in L["objects"]),
               "first_edit_by_side": " ".join(f"{a.split('_')[1]}:r{first.get(a, '-')}" for a in pair),
               "last_edit_round": max(allh)[0] if allh else "",
               "edits": " ".join(f"{a.split('_')[1]}:r{r}s{s}" for a in pair for r, s in hits[a]),
               "prior_msgs": "", "check": ""}
        if len(first) < 2:
            row["check"] = "one side never writes the name"
        elif max(first.values()) == 1:
            row["check"] = "both sides wrote it in r1"
        else:
            late = max(pair, key=lambda a: first[a]); rr = first[late]
            prior = [c for c in conv if c["deliver_round"] <= rr and c["from"] != late
                     and c["to"] in ("all", late) and named(c["text"], forms)]
            row["prior_msgs"] = " ".join(f"#{c['idx']}(r{c['round']}->{c['deliver_round']},{c['from'].split('_')[1]})" for c in prior)
            row["check"] = "needs_check: later side first writes it r%d after a message naming it" % rr if prior \
                else "later side first writes it r%d, no prior message naming it" % rr
        rows.append(row)

with open(A / "link_edits.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
flag = [r for r in rows if r["status"] == "initially_settled" and r["check"].startswith("needs_check")]
with open(A / "needs_check.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(flag)
init = [r for r in rows if r["status"] == "initially_settled"]
print(f"P2P links {len(rows)}; initially settled {len(init)}")
for k, v in Counter(re.sub(r" r\d+", " rN", r["check"]) for r in init).most_common(): print(f"  {v:3d}  {k}")
lb = Counter("r1" if r["last_edit_round"] == 1 else "r2-3" if r["last_edit_round"] in (2, 3) else "r4+" if r["last_edit_round"] else "none" for r in init)
print("  last name-bearing edit (not used):", dict(lb))
