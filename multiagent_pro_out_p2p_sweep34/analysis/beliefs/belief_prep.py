#!/usr/bin/env python
"""Belief-enabled runs: deterministic extraction (read-only over run data).

Record semantics (from tools/comm/bin/update_belief, tools/comm/lib/board.py, orchestrate.py):
  * `update_belief <peer> --note '<text>'` REPLACES the author's current note about that peer and
    appends {round, note} to that peer's `history`. The store is one JSON per author
    (/root/comm/.beliefs_<aid>.json in the author's own container).
  * The harness archives the WHOLE store after each turn (beliefs_round_r.json = state going into
    round r+1) and renders every current note into the author's round-(r+1) notice. Peers never
    see it. A missing peer key means "no note recorded about that peer", not "no belief".
  * Because each note replaces the previous one, a belief that disappears from the *note* can
    only be seen in `history`; an omission from a new note is therefore NOT evidence of forgetting
    unless the note explicitly contradicts earlier content.

This script writes, per instance, a timeline with exact step ordering:
  events = union of
    - belief updates (agent, round, step, about, note) from the trajectories' update_belief actions;
    - message deliveries (recipient, round r+1 start, board idx) for every board entry;
    - code edits (agent, round, step, action excerpt);
    - submits;
  plus, per agent, which rounds' notices actually contained each note (availability check against
  context/messages.jsonl), and the final per-peer note.
"""
import json, re, sys
from pathlib import Path

H = Path("/home/asurite.ad.asu.edu/ubiswas2/harness50")
RUN = H / "p2p_beliefs/mini_swe_agent/claude_opus_5_5"
OUT = Path(__file__).resolve().parent
EDIT_RE = re.compile(r"sed\s+-i|cat\s*>>?\s*(?!/tmp)|tee\s+(?!/tmp)|python3?\s+-\s*<<|open\(.{0,80}['\"]w|git\s+apply")
UB = re.compile(r"update_belief\s+(agent_\d+)\s+--note\s+(?P<q>['\"])(?P<note>.*?)(?P=q)(?=\s*(&&|;|\||\n|$))", re.S)

summary = []
for d in sorted(RUN.glob("instance_*")):
    spec = json.loads((d / "spec.json").read_text())
    if not (d / "board.json").exists() or len(list(d.glob("agent_*.patch"))) != spec["num_agents"]:
        continue
    board = json.loads((d / "board.json").read_text())
    lens, k = [], 1
    while (d / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((d / f"board_after_round_{k}.json").read_text()))); k += 1
    events, per_agent = [], {}
    for i, m in enumerate(board):
        r = next((x + 1 for x, n in enumerate(lens) if i < n), len(lens))
        m["round"] = r; m["idx"] = i
        events.append({"kind": "send", "round": r, "step": None, "agent": m["from"], "to": m.get("to"), "board_idx": i,
                       "type": m.get("type"), "text": (m.get("signature", "") + " " + m.get("text", "")).strip()[:300]})
        for a in spec["agents"]:
            if a["id"] != m["from"] and m.get("to") in (a["id"], "all"):
                events.append({"kind": "deliver", "round": r + 1, "step": 0, "agent": a["id"], "from": m["from"], "board_idx": i})
    for a in spec["agents"]:
        aid = a["id"]; updates = []; edits = []
        for rf in sorted((d / aid).glob("traj/round_*.json"), key=lambda p: int(p.stem.split("_")[1])):
            r = int(rf.stem.split("_")[1])
            for s in json.load(open(rf)):
                act = s.get("action") or ""
                for mo in UB.finditer(act):
                    updates.append({"round": r, "step": s.get("step"), "about": mo.group(1), "note": mo.group("note")[:600],
                                    "ok": "Noted about" in (s.get("observation") or "")})
                    events.append({"kind": "belief", "round": r, "step": s.get("step"), "agent": aid, "about": mo.group(1), "note": mo.group("note")[:300]})
                if EDIT_RE.search(act) and "update_belief" not in act.split("&&")[0]:
                    edits.append({"round": r, "step": s.get("step"), "action": act[:200]})
                    events.append({"kind": "edit", "round": r, "step": s.get("step"), "agent": aid, "action": act[:200]})
                if "COMPLETE_TASK_AND_SUBMIT" in act:
                    events.append({"kind": "submit", "round": r, "step": s.get("step"), "agent": aid})
        # archived snapshots + availability in the next round's prompt
        snaps = {}
        for bf in (d / aid).glob("beliefs_round_*.json"):
            snaps[int(bf.stem.split("_")[-1])] = json.load(open(bf))
        ctx = {}
        cf = d / aid / "context" / "messages.jsonl"
        if cf.exists():
            for line in cf.read_text().splitlines():
                c = json.loads(line)
                if c["step_in_round"] == 1:
                    ctx[c["round"]] = "\n".join(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"]) for m in c["messages"])
        avail = []
        for r, st in sorted(snaps.items()):
            for peer, e in st.items():
                note = (e or {}).get("note") or ""
                nxt = ctx.get(r + 1)
                avail.append({"snapshot_round": r, "about": peer, "shown_in_round": r + 1,
                              "present": (note[:60] in nxt) if nxt and note else None})
        final = {p: (e or {}).get("note", "") for p, e in (snaps.get(max(snaps)) if snaps else {}).items()}
        per_agent[aid] = {"gold_file": a["gold_file"], "n_updates": sum(1 for u in updates if u["ok"]), "n_refused_or_failed": sum(1 for u in updates if not u["ok"]), "updates": updates, "edits": edits,
                          "snapshots_rounds": sorted(snaps), "availability": avail, "final_notes": final}
    events.sort(key=lambda e: (e["round"], e["step"] if e["step"] is not None else 99, 0 if e["kind"] == "deliver" else 1))
    pres = [x["present"] for a in per_agent.values() for x in a["availability"] if x["present"] is not None]
    row = {"instance": d.name, "n_agents": spec["num_agents"], "belief_updates": sum(a["n_updates"] for a in per_agent.values()),
           "agents_with_updates": sum(1 for a in per_agent.values() if a["n_updates"]),
           "notes_shown_next_round": f"{sum(pres)}/{len(pres)}", "messages": sum(1 for m in board if m.get("type") == "message"),
           "publications": sum(1 for m in board if m.get("type") == "interface")}
    summary.append(row)
    json.dump({"instance": d.name, "run_dir": str(d), "agents": per_agent, "events": events,
               "board": [{"idx": m["idx"], "round": m["round"], "from": m["from"], "to": m.get("to"), "type": m.get("type"),
                          "text": (m.get("signature", "") + " " + m.get("text", "")).strip()} for m in board]},
              open(OUT / "prep" / f"{d.name}.json", "w"), indent=1)
json.dump(summary, open(OUT / "prep_summary.json", "w"), indent=1)
print(f"{len(summary)} belief-enabled instances")
print("| instance | agents | messages | publications | belief updates | agents using it | notes shown in next round |")
for r in summary:
    print(f"| {r['instance'][9:40]} | {r['n_agents']} | {r['messages']} | {r['publications']} | {r['belief_updates']} | {r['agents_with_updates']}/{r['n_agents']} | {r['notes_shown_next_round']} |")
