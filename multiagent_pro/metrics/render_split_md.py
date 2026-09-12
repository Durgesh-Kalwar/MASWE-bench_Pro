#!/usr/bin/env python
"""Render ONE markdown file showing, for every built multi-agent instance, the original dataset
text and the exact text each agent receives.

Reads what the pipeline actually produced rather than re-deriving it: each agent's view is its
own `agent_<k>/local_issue.md` (the file SWE-agent substitutes for {{problem_statement}}), and
roles / dependency edges come from the `coupling` key that `tag_coupling.py` writes into
`spec.json`. The original fields come verbatim from `<sampled>/<id>/metadata.json` (only the
dataset's JSON string-encoding is removed).

    python multiagent_pro/metrics/render_split_md.py --bench multiagent_pro_bench50
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                # multiagent_pro/
sys.path.insert(0, str(HERE.parent / "aci"))        # gen_solver_config
from build_multiagent_pro import decode_text  # noqa: E402


def fence(text):
    """A code fence longer than any backtick run inside `text`, so an issue that itself
    contains ``` blocks cannot terminate the fence early and spill into the page."""
    run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, run + 1)
    return f"{ticks}\n{text.rstrip()}\n{ticks}"


def issue_body(local_issue):
    """The issue proper, i.e. what follows the builder's preamble separator."""
    head, sep, body = local_issue.partition("\n---\n")
    return body.strip() if sep else local_issue.strip()


def prompts():
    try:
        import gen_solver_config as g
        return g.SYSTEM_PROMPT, g.INSTANCE_PROMPT
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", default="multiagent_pro_bench50")
    ap.add_argument("--sampled", default="sampled_pro",
                    help="metadata with the ORIGINAL (unpruned) dataset fields")
    ap.add_argument("--out", default=None, help="default: <bench>/top50_split_paths.md")
    args = ap.parse_args()
    bench, sampled = Path(args.bench), Path(args.sampled)
    out = Path(args.out) if args.out else bench / "top50_split_paths.md"

    rows = []
    for d in sorted(p for p in bench.iterdir() if p.name.startswith("instance_")):
        spec = json.loads((d / "spec.json").read_text())
        c = spec.get("coupling") or {}
        rows.append((c.get("agent_pairs", 0), c.get("coupled_agents", 0),
                     len(c.get("edges", [])), d, spec, c))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2], r[3].name))

    L = []
    A = L.append
    A(f"# {bench.name}: original text, and exactly what each agent sees\n")
    A(f"{len(rows)} instances, {sum(r[4]['num_agents'] for r in rows)} agents, ranked by "
      "**unique agent-pair dependency edges** (`pairs`) — how many distinct agent-to-agent "
      "dependencies the problem contains.\n")
    A("**The split (`--route-interface`).** Every agent receives the complete "
      "`problem_statement` and the complete `requirements`, verbatim and unmasked — those are "
      "identical for all agents, so they are printed once per instance below. The `interface` "
      "is routed: each declared entry goes to the agent whose file it names (or whose diff "
      "introduces its symbol), and entries naming no file go to everyone. A peer's new API is "
      "the only thing an agent does not see.\n")
    A("**Fixed files.** Files pruned away from the agents (documentation, changelogs, CI/build "
      "files, comment-only diffs) are not agents. Their gold diffs are kept in `fixed.patch`, "
      "denied to every agent, and appended to the graded patch at merge. With each agent "
      "writing its gold diff, all 50 instances grade 100%.\n")
    A("Originals come verbatim from `sampled_pro/<id>/metadata.json`; each agent's view is its "
      "`agent_<k>/local_issue.md`, reproduced as written.\n")

    system, instance = prompts()
    if system:
        A("## What every agent receives, before its issue text\n")
        A("The system prompt (identical for all agents; `{{command_docs}}` expands to the tool "
          "list):\n")
        A(fence(system) + "\n")
        A("The instance prompt, where `{{problem_statement}}` is that agent's `local_issue.md`:\n")
        A(fence(instance) + "\n")

    A("## Index\n")
    A("| # | pairs | in graph | edges | agents | fixed | instance |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for i, (pairs, ca, ne, d, spec, _) in enumerate(rows, 1):
        A(f"| {i} | {pairs} | {ca} | {ne} | {spec['num_agents']} | "
          f"{len(spec.get('fixed_files') or [])} | `{d.name[:56]}` |")
    A("\n---\n")

    for i, (pairs, ca, ne, d, spec, c) in enumerate(rows, 1):
        iid = d.name
        meta = json.loads((sampled / iid / "metadata.json").read_text())
        ps, req, itf = (decode_text(meta.get(k) or "").strip()
                        for k in ("problem_statement", "requirements", "interface"))
        roles = c.get("per_agent", {})
        fixed = spec.get("fixed_files") or []

        A(f"## {i}. `{iid}`\n")
        A(f"**{pairs} agent pairs** · {ca} agents in the graph · {ne} symbol edges · "
          f"{spec['num_agents']} agents" + (f" · {len(fixed)} fixed file(s)" if fixed else "")
          + "\n")
        A("Agents (one per gold file):\n")
        for a in spec["agents"]:
            A(f"- `{a['id']}` — `{a['gold_file']}` — role "
              f"**{roles.get(a['id'], {}).get('role', '?')}**")
        A("")
        if fixed:
            A("Fixed files (no agent owns them; merged into the final patch as-is): "
              + ", ".join(f"`{f}`" for f in fixed) + "\n")
        if c.get("edges"):
            A("Dependencies (consumer → definer):\n")
            for e in c["edges"]:
                A(f"- `{e['from']}` → `{e['to']}` — {e['kind']} on `{e['symbol']}`")
            A("")
        if (d / "coupling_graph.png").exists():
            A(f"![dependency graph]({iid}/coupling_graph.png)\n")

        A("### ORIGINAL `problem_statement`\n")
        A(fence(ps or "(empty)") + "\n")
        A("### ORIGINAL `requirements`\n")
        A(fence(req or "(empty)") + "\n")
        A("### ORIGINAL `interface`\n")
        A(fence(itf or "(empty)") + "\n")

        A("### THE SPLIT — the interface entries each agent receives\n")
        A("*Problem statement and requirements are identical for every agent: exactly the "
          "originals above. Only the interface differs.*\n")
        for a in spec["agents"]:
            li = (d / a["id"] / "local_issue.md").read_text()
            head, sep, itf = li.partition("## New interfaces introduced")
            itf = (sep + itf).strip()
            A(f"#### {a['id']} — `{a['gold_file']}` · role "
              f"**{roles.get(a['id'], {}).get('role', '?')}**\n")
            A(fence(itf) + "\n" if itf else
              "*No interface section — this instance declares no new interfaces.*\n")
        A("---\n")

    out.write_text("\n".join(L))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(rows)} instances)")


if __name__ == "__main__":
    main()
