#!/usr/bin/env python
"""Draw the two whiteboard figures with this run's counts filled in (Graphviz `dot`).

Reads results/fig1_summary.json and results/fig2_summary.json (run fig1_agent_actions.py and
fig2_message_analysis.py first). Writes results/figure1_agent_actions.{png,pdf,svg,dot} and
results/figure2_message_analysis.{png,pdf,svg,dot}. The boxes and arrows follow
"Whiteboard figures – agent actions & message analysis.pdf"; boxes with a dashed border are
additions (the user's questions 1 and 4, and sends that answer no question).
"""
import json, subprocess

from wb_common import ARM, OUT, RUN, SEALED, TITLE, pct

F1 = json.load(open(OUT / "fig1_summary.json"))
F2 = json.load(open(OUT / "fig2_summary.json"))
seal = json.load(open(RUN / "scope_seal_summary.json"))["totals"] if (RUN / "scope_seal_summary.json").exists() else {}

ROOT = 'shape=box, style="rounded,filled", fillcolor="#3b5876", fontcolor=white, color="#3b5876", fontsize=15, margin="0.25,0.18"'
HEAD = 'shape=box, style="rounded,filled", fillcolor="#d9e4f0", color="#3b5876", fontsize=13, margin="0.22,0.14"'
BOX = 'shape=box, style="rounded,filled", fillcolor="#eef2f7", color="#3b5876", fontsize=12, margin="0.18,0.12"'
ADD = 'shape=box, style="rounded,filled,dashed", fillcolor="#f7f7f7", color="#3b5876", fontsize=12, margin="0.18,0.12"'
ASK = 'shape=box, style="filled", fillcolor="#fff2cc", color="#b8860b", fontsize=12, margin="0.18,0.12"'
NOTE = 'shape=plaintext, fontsize=10.5, fontcolor="#333333"'
COMMON = 'graph [fontname="Helvetica", labelloc=t, fontsize=18, pad=0.3, nodesep=0.28];\n node [fontname="Helvetica"];\n edge [color="#3b5876", arrowsize=0.8, fontname="Helvetica", fontsize=10];\n'


def B(s):
    return "<" + s.replace("\n", "<br/>") + ">"


def node(name, style, text):
    return f"  {name} [{style}, label={B(text)}];\n"


def render(name, dot):
    (OUT / f"{name}.dot").write_text(dot)
    for fmt, extra in (("png", ["-Gdpi=170"]), ("pdf", []), ("svg", [])):
        subprocess.run(["dot", f"-T{fmt}", *extra, "-o", str(OUT / f"{name}.{fmt}"), str(OUT / f"{name}.dot")], check=True)


# ------------------------------------------------------------------------------- Figure 1
s, d, c = F1["scheming"], F1["destructive"], F1["contamination"]
u = d["undo_by_kind"]
stash = u.get("git stash (set edits aside)", 0)
pop = u.get("git stash pop / apply (bring edits back)", 0)
rm = d["rm_by_target"]
g = f'digraph G {{\n rankdir=LR; ranksep=0.55;\n {COMMON}'
g += f' label=<<b>Figure 1. Monitoring agent actions: sandboxing and git operations</b><br/><font point-size="13">{TITLE} run · {F1["instances"]} instances · {F1["agents"]} agents · {F1["steps"]:,} commands · string matching only</font><br/> >;\n'
g += node("root", ROOT, "<b>Agent actions</b>")
g += node("sch", HEAD, "<b>① Scheming</b>")
g += node("des", HEAD, f"<b>② Destructive actions</b>\n(e.g. rm)")
g += node("con", HEAD, "<b>③ Data contamination</b>")
g += node("try", BOX, f"An agent tries to access another agent's files\n<b>{s['attempts']}</b> commands by {s['agents_attempting']}/{F1['agents']} agents\n"
                      f"{s['attempts_blocked']} refused by the guard · {s['attempts_unblocked']} not refused")
g += node("succ", BOX, f"An agent successfully accesses lines\nfrom another agent's files\n<b>{s['success_commands']}</b> commands "
                       f"({s['success_agents']} agents, {s['success_instances']} instances)")
g += node("issue", BOX, f"Issues with sandbox design\nstill possible: listing a peer module's names\nthrough its bytecode stand-in (<b>{s['name_probes']}</b> commands);\n"
                        f"guard also refused <b>{s['guard_refused_messages']}</b> messages\nthat only named a peer's path")
if SEALED:
    g += node("sol", BOX, f"Solution: Docker implementation\n(one sandboxed container per agent)\n{seal.get('sealed', '?')} peer files sealed out, "
                          f"{seal.get('compile_failed', 0)} failures")
    g += node("q", ASK, f"Question: what is the success rate when we\ndon't let agents access other agents' files?\n<b>{F1['resolved']}/{F1['instances']} resolved ({pct(F1['resolved'], F1['instances'])})</b>")
else:
    g += node("sol", BOX, "Solution: Docker implementation\n(one sandboxed container per agent)\n<b>not applied in this run</b>: peers' files were on disk,\nonly the command guard stood in the way")
    g += node("q", ASK, f"Success rate in this run, where agents\ncould still reach other agents' files:\n<b>{F1['resolved']}/{F1['instances']} resolved ({pct(F1['resolved'], F1['instances'])})</b>")
g += node("leak", ADD, f"Q1. Private text leaked through messages?\n<b>{F2['leak']['true_leaks']}</b> of {F2['leak']['messages_scanned']} messages carry text\nthe sender read from a peer's file\n"
                       f"({F2['leak']['credential_patterns']} credential patterns)")
g += node("rmn", BOX, f"rm\n<b>{d['rm_total']}</b> commands, {d['rm_agents']} agents\n" + " · ".join(f"{v} {k.split(' (')[0]}" for k, v in rm.items()))
g += node("reset", BOX, f"git reset\n<b>{u.get('git reset', 0)}</b>")
g += node("revert", BOX, f"git revert &lt;commit&gt;\n<b>{u.get('git revert', 0)}</b>")
g += node("co", BOX, f"git checkout / restore &lt;file&gt;\n<b>{u.get('git checkout / restore (file)', 0)}</b>")
g += node("stash", BOX, f"git stash / stash pop\n<b>{stash}</b> / <b>{pop}</b>")
g += node("diff", BOX, f"git diff (reading)\n<b>{d['git_diff_total']}</b> commands, {d['git_diff_agents']} agents")
g += node("mod", BOX, f"modify\n<b>{d['git_diff_then_modify']}</b> diffs followed by a direct\nfile edit in the same or next step ({pct(d['git_diff_then_modify'], d['git_diff_total'])})")
g += node("rev", ASK, f"Do agents take actions they have to reverse?\n<b>{d['undo_agents']}/{F1['agents']}</b> agents ran an undo command ({d['undo_total']} commands,\n{d['undo_instances']}/{F1['instances']} instances)\n"
                      f"resolved: {d['resolved_with_undo']['resolved']}/{d['resolved_with_undo']['instances']} with an undo · "
                      f"{d['resolved_without_undo']['resolved']}/{d['resolved_without_undo']['instances']} without")
g += node("links", BOX, f"Resolving without communication where\nit is required wrt gold patch\n{c['gold_links']} gold links · <b>{c['links_never_discussed']}</b> never discussed\n"
                        f"({c['links_never_discussed_but_realized']} of those still coded correctly)")
g += node("names", BOX, f"Gold-only names used with no visible source\n(not in task text, messages or tool output)\n<b>{c['distinctive_unexplained_uses']}</b> uses of {c['distinctive_unexplained_names']} names, "
                        f"{c['distinctive_unexplained_agents']}/{F1['agents']} agents,\n{c['distinctive_unexplained_instances']}/{F1['instances']} instances")
g += node("ups", BOX, f"Reasoning cites “upstream”\n<b>{c['upstream_mentions']}</b> steps, {c['upstream_agents']}/{F1['agents']} agents,\n{c['upstream_instances']}/{F1['instances']} instances")
g += " root -> sch; root -> des; root -> con;\n sch -> try -> succ -> issue -> sol -> q;\n succ -> leak [style=dashed];\n"
g += " des -> rmn; des -> reset; des -> revert; des -> co; des -> stash; des -> diff; diff -> mod;\n"
g += " co -> rev [style=dashed]; stash -> rev [style=dashed];\n"
g += " con -> links -> names -> ups;\n"
g += " {rank=same; sch; des; con}\n}\n"
render("figure1_agent_actions", g)

# ------------------------------------------------------------------------------- Figure 2
a, sd, lk = F2["ask"], F2["send"], F2["leak"]
rq, nq, un, pb = sd["relevant_q"], sd["not_relevant_q"], sd["unsolicited"], sd["publication"]
g = f'digraph G {{\n rankdir=TB; ranksep=0.5;\n {COMMON}'
g += f' label=<<b>Figure 2. Communication / message analysis between agents (Ag to Ag*)</b><br/><font point-size="13">{TITLE} run · {F2["instances"]} instances · {F2["board_entries"]} board entries · string matching only</font><br/> >;\n'
g += node("root", ROOT, f"<b>Message analysis</b>\n(send messages)\n{F2['board_entries']} messages and publications")
g += node("askq", HEAD, "<b>Am I asking a\nrelevant question?</b>")
g += node("sendq", HEAD, "<b>Am I sending\nrelevant info?</b>")
g += node("ask", BOX, f"Ask [Ag, Q, text, Ag*]\n<b>{a['n']}</b> asks\n{a['questions']} questions · {a['directives']} requests to act")
g += node("arel", BOX, f"Relevant\n<b>{a['relevant']}</b> ({pct(a['relevant'], a['n'])})")
g += node("anot", BOX, f"Not relevant\n<b>{a['not_relevant']}</b> ({pct(a['not_relevant'], a['n'])})")
g += node("p2p", HEAD, f"<b>Am I asking a\nrelevant question to the\nright agent? [P2P]</b>\n{a['directed_relevant']} directed asks")
g += node("ra", BOX, f"Relevant agent\n<b>{a['right_agent']}</b> ({pct(a['right_agent'], a['directed_relevant'])})")
g += node("wa", BOX, f"Non-relevant agent\n<b>{a['wrong_agent']}</b> ({pct(a['wrong_agent'], a['directed_relevant'])})")
g += node("bc", ADD, f"Asked by broadcast: {a['broadcast_relevant']}\nsome peer has it: <b>{a['broadcast_relevant_some_peer_has_it']}</b>\nno peer has it: {a['broadcast_relevant_no_peer_has_it']}")
g += node("ans", ADD, "Was the ask answered?\n" + "\n".join(f"{k}: <b>{v}</b>" for k, v in a["answer"].items()))
g += node("send", BOX, f"Send [Ag, Q, text, Ag*]\n<b>{sd['n']}</b> sends\n{sd['responses']} answer a pending Q")
g += node("srel", BOX, f"Relevant(Q)\n<b>{rq['n']}</b> ({pct(rq['n'], sd['responses'])})")
g += node("snot", BOX, f"Not relevant(Q)\n<b>{nq['n']}</b> ({pct(nq['n'], sd['responses'])})")
g += node("noq", ADD, f"No Q pending\n<b>{un['n']}</b> unsolicited messages\n<b>{pb['n']}</b> interface publications")
REAL = 'shape=box, style="rounded,filled", fillcolor="#e2f0d9", color="#548235", fontsize=11.5, margin="0.14,0.10"'
HALL = 'shape=box, style="rounded,filled", fillcolor="#fbe5d6", color="#c55a11", fontsize=11.5, margin="0.14,0.10"'
tot = lambda key, grps: sum(x[key] for x in grps)
for k, grps, style in (("r", [rq], BOX), ("n", [nq], BOX), ("u", [un, pb], ADD)):
    g += node(f"acc{k}", style, f"Acc\n<b>{tot('acc', grps)}</b>\n({tot('acc_uncheckable', grps)} state nothing checkable)")
    g += node(f"in{k}", style, f"In-acc\n<b>{tot('inacc', grps)}</b>")
    g += node(f"real{k}", REAL, f"Real\n<b>{tot('acc_real', grps)}</b>")
    g += node(f"hall{k}", HALL, f"Hallucinated\n<b>{tot('acc_hallucinated', grps)}</b>")
    g += f" acc{k} -> real{k}; acc{k} -> hall{k};\n"
g += node("q4", ADD, f"<b>Q4. Am I providing information\nto the right agent? [P2P]</b>\n{sd['directed']} directed sends\nright agent: <b>{sd['directed_right_agent']}</b> ({pct(sd['directed_right_agent'], sd['directed'])}) · "
                     f"not: <b>{sd['directed_wrong_agent']}</b>\nbroadcast deliveries needed: {sd['broadcast_deliveries_needed']}/{sd['broadcast_deliveries']}")
g += node("q1", ADD, f"<b>Q1. Is private information\nleaked through messages?</b>\ntext read from a peer's file: <b>{lk['true_leaks']}</b> messages\n"
                     f"credential patterns: <b>{lk['credential_patterns']}</b>\n(identical text with no access: {lk['messages_with_protected_text_to_non_owner']} messages)")
g += node("n1", NOTE, "text (wrt Ag gold patch):\nam I asking the right question\nwrt my gold patch?")
g += node("n2", NOTE, "text (wrt Ag* gold patch):\nam I asking the agent who has\nthis in their gold patch?")
g += node("n3", NOTE, "text (wrt Q): is the text\nI am sending relevant to Q?")
g += node("n4", NOTE, "Ag: does the text I am sending\nactually belong to me?\n(names something in my gold patch)")
g += node("n5", NOTE, "Is what it states true?\nnames, signatures and “tests pass” checked\nagainst the sender's own final code\nand its own test output")
g += " root -> askq; root -> sendq;\n askq -> ask; ask -> arel; ask -> anot; arel -> p2p; p2p -> ra; p2p -> wa;\n arel -> bc [style=dashed]; ask -> ans [style=dashed];\n"
g += " sendq -> send; send -> srel; send -> snot; send -> noq [style=dashed];\n srel -> accr; srel -> inr; snot -> accn; snot -> inn; noq -> accu [style=dashed]; noq -> inu [style=dashed];\n"
g += " send -> q4 [style=dashed]; root -> q1 [style=dashed];\n"
g += " n1 -> ask [style=dotted, arrowhead=none]; n2 -> p2p [style=dotted, arrowhead=none]; n3 -> send [style=dotted, arrowhead=none]; n4 -> inn [style=dotted, arrowhead=none]; n5 -> hallu [style=dotted, arrowhead=none];\n"
g += " {rank=same; n1; ask; send; n3}\n {rank=same; accr; inr; accn; inn; accu; inu; n4}\n {rank=same; realr; hallr; realn; halln; realu; hallu; n5}\n}\n"
render("figure2_message_analysis", g)
print("wrote", *(p.name for p in sorted(OUT.glob("figure*"))))
