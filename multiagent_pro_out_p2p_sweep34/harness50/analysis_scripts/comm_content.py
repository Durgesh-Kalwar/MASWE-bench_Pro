#!/usr/bin/env python
"""What the P2P agents talk about, when, and how much of it carries new information.

Reads board.json (+ per-round snapshots) and traj/round_k.json for every finished instance
under --run-root and prints:
  * volume by round (messages, interfaces, edit actions, submits) -- the temporal shape
  * message length distribution and content mix (regex taxonomy, one message may hit several)
  * novelty: share of messages whose code identifiers were ALL already on the board
  * per-agent role split: who talks (definers vs consumers, by realized dependency edges)
  * talk-vs-work: steps spent on comm commands vs edits vs tests vs other, per round
Writes messages_tagged.jsonl (one row per message with tags) for the qualitative pass.
"""
import json, re, sys, collections
from pathlib import Path

root = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
ev = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}

TAX = {  # order matters only for display
 "interface_announce": r"\b(def |class |signature|returns?|->|\(\w+(, ?\w+)*\)|param|kwarg|argument)\b",
 "request": r"\bplease\b|\bcan you\b|\bcould you\b|\?",
 "confirm_ack": r"\bconfirm(ed|s)?\b|\back\b|\bagree(d)?\b|\bthanks\b|\bsounds good\b|\bmatches\b",
 "status_done": r"\b(is|are|now) (done|written|implemented|in place|on disk|complete)|\bimplemented\b|\bdone\b|\bfinished\b|\bsubmitted\b",
 "test_report": r"\d+ passed|\btests? (pass|fail)|\bpytest\b|\bpassed\b|\bfailed\b",
 "correction": r"\bcorrection\b|\bretract|\bI was wrong\b|\bwrongly\b|\bmade .* up\b|\bnever (actually )?(received|got)\b",
 "problem_scope": r"\bguard\b|\brefus(ed|es)\b|\bdenied\b|\bowned by\b|\bcannot (read|edit|see)\b|\bstale\b|\bseparate (view|container)s?\b",
 "upstream_recall": r"\bupstream\b|\bPR ?#?\d|\bissue ?#?\d",
 "plan_assignment": r"\bagent_\d+[:,]? (please|should|needs? to|will|can)\b|\byou (should|need to|must)\b",
}
EDIT_RE = re.compile(r"sed\s+-i|cat\s*>>?\s*(?!/tmp)|tee\s+(?!/tmp)|python3?\s+-\s*<<|open\(.{0,80}['\"]w|git\s+apply|\bpatch\s+-p")
TEST_RE = re.compile(r"pytest|python3? -m unittest|python3? -c|tox\b")
COMM_RE = re.compile(r"\b(send_message|publish_interface|list_agents|update_belief)\b")
IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")

rows, inst_stats = [], []
by_round = collections.defaultdict(lambda: collections.Counter())
for d in sorted(root.glob("instance_*")):
    spec = json.loads((d / "spec.json").read_text())
    if len(list(d.glob("agent_*.patch"))) != spec["num_agents"]: continue
    board = json.loads((d / "board.json").read_text())
    lens, k = [], 1
    while (d / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((d / f"board_after_round_{k}.json").read_text()))); k += 1
    seen_idents = set()
    msgs = [m for m in board if m.get("type") == "message"]
    n_if = sum(1 for m in board if m.get("type") == "interface")
    for i, m in enumerate(board):
        m["round"] = next((r + 1 for r, n in enumerate(lens) if i < n), len(lens))
        if m.get("type") == "interface":
            seen_idents |= set(IDENT.findall(m.get("signature", ""))); by_round[m["round"]]["interfaces"] += 1; continue
        t = m["text"]; tags = [k for k, r in TAX.items() if re.search(r, t, re.I)]
        ids = set(IDENT.findall(t)) - {"agent"}; ids = {x for x in ids if not re.match(r"^(agent_\d+|please|the|and|for|with|that|this|from|your|you|have|will|now|not)$", x, re.I)}
        code_ids = {x for x in ids if "_" in x or re.search(r"[a-z][A-Z]", x) or x.endswith(".py")}
        novel = len(code_ids - seen_idents); seen_idents |= code_ids
        rows.append({"instance": d.name, "from": m["from"], "to": m["to"], "round": m["round"], "chars": len(t),
                     "tags": tags, "n_code_ids": len(code_ids), "n_novel_ids": novel, "text": t})
        by_round[m["round"]]["messages"] += 1; by_round[m["round"]]["directed"] += m["to"] != "all"
    # talk vs work per round from trajectories
    for ad in d.glob("agent_*/"):
        for rf in ad.glob("traj/round_*.json"):
            r = int(rf.stem.split("_")[1])
            for s in json.load(open(rf)):
                a = s.get("action", "")
                if "COMPLETE_TASK_AND_SUBMIT" in a: by_round[r]["submit_steps"] += 1
                elif COMM_RE.search(a) and not EDIT_RE.search(a) and not TEST_RE.search(a): by_round[r]["comm_only_steps"] += 1
                elif EDIT_RE.search(a): by_round[r]["edit_steps"] += 1
                elif TEST_RE.search(a): by_round[r]["test_steps"] += 1
                else: by_round[r]["other_steps"] += 1
    inst_stats.append({"instance": d.name, "agents": spec["num_agents"], "messages": len(msgs), "interfaces": n_if,
                       "resolved": ev.get(d.name), "chars": sum(len(m["text"]) for m in msgs)})

with open(out / "messages_tagged.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
N = len(rows); print(f"# {len(inst_stats)} instances, {sum(i['agents'] for i in inst_stats)} agents, {N} messages, {sum(i['interfaces'] for i in inst_stats)} interfaces\n")
print("## Volume by round (all instances)")
print("| round | messages | directed | interfaces | comm-only steps | edit steps | test steps | other steps | submit-only steps |"); print("|---|---|---|---|---|---|---|---|---|")
for r in sorted(by_round):
    c = by_round[r]; print(f"| {r} | {c['messages']} | {c['directed']} | {c['interfaces']} | {c['comm_only_steps']} | {c['edit_steps']} | {c['test_steps']} | {c['other_steps']} | {c['submit_steps']} |")
cum = 0
for r in sorted(by_round):
    cum += by_round[r]["messages"]
    if cum / N >= 0.5 and "half" not in locals(): half = r
    if cum / N >= 0.9 and "ninety" not in locals(): ninety = r
print(f"\n50% of all messages sent by end of round {half}; 90% by end of round {ninety}.")
L = sorted(r["chars"] for r in rows); print(f"\n## Length: median {L[N//2]} chars, p90 {L[int(N*.9)]}, max {L[-1]}; total {sum(L):,} chars (~{sum(L)//4:,} tokens)")
print("\n## Content mix (share of messages carrying each tag; a message can carry several)")
for k in TAX: print(f"- {k}: {sum(1 for r in rows if k in r['tags'])/N:.0%}")
print(f"- no tag at all: {sum(1 for r in rows if not r['tags'])/N:.0%}")
print("\n## Novelty")
print(f"- messages containing at least one code identifier: {sum(1 for r in rows if r['n_code_ids'])/N:.0%}")
print(f"- of those, messages whose identifiers were ALL already on the board (restatement): {sum(1 for r in rows if r['n_code_ids'] and r['n_novel_ids']==0)/sum(1 for r in rows if r['n_code_ids']):.0%}")
print(f"- messages with no code identifier (pure coordination/ack): {sum(1 for r in rows if not r['n_code_ids'])/N:.0%}")
print("\n## Per instance")
print("| instance | agents | msgs | msgs/agent | interfaces | chars | resolved |"); print("|---|---|---|---|---|---|---|")
for i in inst_stats: print(f"| {i['instance'][9:40]} | {i['agents']} | {i['messages']} | {i['messages']/i['agents']:.1f} | {i['interfaces']} | {i['chars']:,} | {i['resolved']} |")
