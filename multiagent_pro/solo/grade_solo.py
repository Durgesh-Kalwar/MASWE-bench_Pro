#!/usr/bin/env python
"""Grade the solo arm and emit the solvable-instance filter.

Grading goes through the SAME path as the multi-agent runs -- swe_bench_pro_eval.py against the
instance's own run_scripts/ and parser -- because the whole point of this arm is to decide which
instances survive into the multi-agent grid. A different grader here would confound the filter
with the thing it is filtering for.

WHAT IT WRITES

    <cell>/patches.json         [{instance_id, patch, prefix}] handed to the evaluator
    <cell>/eval_out/            per-instance multiagent_output.json / multiagent_patch.diff
    <cell>/eval_out/eval_results.json
    <cell>/solo_scores.json     per-instance F2P / P2P / resolved / collected-count
    <cell>/solvable.txt         the filter: instance_ids that met the criterion

The prefix is `multiagent` even though nothing here is multi-agent: the evaluator names its
outputs `{prefix}_output.json`, and the dashboard reads `multiagent_output.json`. Changing it
would make solo runs grade fine and then show no tests.

TWO SCORING RULES THAT ARE EASY TO GET WRONG, both learned the hard way (CHECKPOINT 9.5):

1. **Score FAIL_TO_PASS and PASS_TO_PASS separately.** P2P is a DAMAGE gauge, not a score -- an
   empty patch earns ~100% of it. A raw "43/46" is mostly the P2P baseline and says almost
   nothing about whether the feature got built. F2P is the only column that measures that.

2. **An uncollected test is not a missing test, it is a failed one.** Collection happens per
   module at import, so one broken top-level import removes every test in that file as a single
   collection error -- silently shrinking the denominator and making a catastrophic run look
   like a small one ("2/5"). So the collected count is reconciled against the expected total and
   any shortfall is reported, not averaged away.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
PREFIX = "multiagent"


def test_list(v):
    """raw_sample.jsonl stores fail_to_pass / pass_to_pass as STRINGIFIED python lists, not JSON
    arrays -- iterating one directly yields single characters, which silently scores everything
    as a miss."""
    if isinstance(v, list):
        return v
    if not isinstance(v, str) or not v.strip():
        return []
    try:
        out = ast.literal_eval(v)
        return list(out) if isinstance(out, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def instance_dirs(cell: Path, only: list[str] | None) -> list[Path]:
    """Instance dirs in the cell, optionally restricted to `only`.

    A restriction matters for more than speed: grading an instance whose run has not happened
    yet would enter it in patches.json with an empty patch and record a real FAIL for it, which
    then reads identically to an agent that ran and wrote nothing.
    """
    dirs = sorted(p for p in cell.iterdir() if (p / "spec.json").exists())
    if not only:
        return dirs
    keep = {d.name for d in dirs} & set(only)
    missing = set(only) - keep
    for m in sorted(missing):
        print(f"  warning: {m} is not built in this cell -- skipped")
    return [d for d in dirs if d.name in keep]


def gather(cell: Path, only: list[str] | None = None) -> list[dict]:
    """One entry per instance that produced a patch file."""
    entries = []
    for idir in instance_dirs(cell, only):
        pf = idir / "agent_1.patch"
        patch = pf.read_text() if pf.is_file() else ""
        entries.append({"instance_id": idir.name, "patch": patch, "prefix": PREFIX})
        if not patch.strip():
            # Recorded, not skipped: an empty patch is a real result (the agent ran and wrote
            # nothing) and it still needs a grade, since it establishes the P2P baseline.
            print(f"  note: {idir.name[:58]} produced an EMPTY patch")
    return entries


def score(cell: Path, raw: dict, criterion: str,
          only: list[str] | None = None) -> tuple[list[dict], list[str]]:
    evals = json.loads((cell / "eval_out" / "eval_results.json").read_text())
    rows, solvable = [], []
    for idir in instance_dirs(cell, only):
        iid = idir.name
        out_p = cell / "eval_out" / iid / f"{PREFIX}_output.json"
        tests = (json.loads(out_p.read_text()).get("tests") or []) if out_p.is_file() else []
        sample = raw.get(iid, {})
        f2p = set(test_list(sample.get("fail_to_pass")))
        p2p = set(test_list(sample.get("pass_to_pass")))
        passed = {t.get("name") for t in tests if str(t.get("status", "")).upper() == "PASSED"}
        seen = {t.get("name") for t in tests}

        f2p_ok, p2p_ok = len(f2p & passed), len(p2p & passed)
        # Pro's real criterion: every required test must PASS, not merely most of them.
        resolved = bool(f2p | p2p) and (f2p | p2p) <= passed
        missing = sorted((f2p | p2p) - seen)

        stats_p = idir / "solo_stats.json"
        st = json.loads(stats_p.read_text()) if stats_p.is_file() else {}
        spec = json.loads((idir / "spec.json").read_text())

        keep = {"resolved": resolved,
                "f2p_all": bool(f2p) and f2p <= passed,
                "f2p_any": f2p_ok > 0}[criterion]
        if keep:
            solvable.append(iid)

        rows.append({
            "instance_id": iid,
            "arm": spec.get("arm"),
            "coupling": spec.get("coupling"),
            "multiagent_num_agents": spec.get("multiagent_num_agents"),
            "resolved": evals.get(iid, resolved),
            "f2p": [f2p_ok, len(f2p)],
            "p2p": [p2p_ok, len(p2p)],
            "collected": len(seen),
            "expected": len(f2p | p2p),
            # Non-empty means a module failed to import: those tests are absent from output.json
            # and, since scoring requires the union to PASS, absence scores exactly like failure.
            "uncollected": missing[:20],
            "n_uncollected": len(missing),
            "stop_reason": st.get("stop_reason"),
            "steps": st.get("steps"),
            "cost": st.get("cost_gateway") or st.get("cost_litellm"),
            "patch_lines": st.get("patch_lines"),
            "kept": keep,
        })
    return rows, solvable


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="cell root written by build_solo.py")
    ap.add_argument("--raw-sample", default=str(REPO_DIR / "sampled_pro" / "raw_sample.jsonl"))
    ap.add_argument("--criterion", choices=("resolved", "f2p_all", "f2p_any"),
                    default="resolved",
                    help="what 'solvable without requirements' means. resolved (default): full "
                         "Pro criterion, F2P and P2P all pass. f2p_all: every FAIL_TO_PASS "
                         "passes, P2P damage ignored. f2p_any: at least one F2P passes.")
    ap.add_argument("--dockerhub_username", default="jefzda")
    ap.add_argument("--instances", nargs="*",
                    help="restrict to these instance_ids (default: every built instance). Use it "
                         "to avoid grading instances whose run has not happened yet -- an "
                         "ungraded-but-empty patch records a FAIL indistinguishable from a real "
                         "one.")
    ap.add_argument("--skip-eval", action="store_true",
                    help="score an eval_out/ that already exists instead of re-grading")
    ap.add_argument("--redo", action="store_true",
                    help="pass --redo to the evaluator; without it, an instance whose "
                         "multiagent_output.json exists is SKIPPED and its OLD result reported")
    args = ap.parse_args()

    cell = Path(args.root)
    if not cell.is_dir():
        raise SystemExit(f"no such cell: {cell}")

    if not args.skip_eval:
        entries = gather(cell, args.instances)
        if not entries:
            raise SystemExit(f"no instances with spec.json under {cell}")
        (cell / "patches.json").write_text(json.dumps(entries, indent=2) + "\n")
        print(f"{len(entries)} patch(es) -> {cell / 'patches.json'}")

        cmd = [sys.executable, str(REPO_DIR / "swe_bench_pro_eval.py"),
               "--raw_sample_path", args.raw_sample,
               "--patch_path", str(cell / "patches.json"),
               "--output_dir", str(cell / "eval_out"),
               "--scripts_dir", "run_scripts",
               "--dockerhub_username", args.dockerhub_username,
               "--use_local_docker"]
        if args.redo:
            cmd.append("--redo")
        print(" ".join(cmd))
        subprocess.run(cmd, check=True, cwd=str(REPO_DIR))

    raw = {}
    with open(args.raw_sample) as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                raw[d["instance_id"]] = d

    rows, solvable = score(cell, raw, args.criterion, args.instances)
    (cell / "solo_scores.json").write_text(json.dumps(
        {"criterion": args.criterion, "rows": rows}, indent=2) + "\n")
    # Only rewrite the filter when the WHOLE cell was scored; a partial run must not silently
    # shrink the list the multi-agent phase reads.
    filt = cell / ("solvable_partial.txt" if args.instances else "solvable.txt")
    filt.write_text("".join(i + "\n" for i in solvable))

    print(f"\n{'instance':<40} {'F2P':>8} {'P2P':>9} {'coll':>9} {'steps':>6} {'cost':>7}  keep")
    for r in rows:
        f2p = f"{r['f2p'][0]}/{r['f2p'][1]}"
        p2p = f"{r['p2p'][0]}/{r['p2p'][1]}"
        coll = f"{r['collected']}/{r['expected']}"
        flag = "!" if r["n_uncollected"] else " "
        cost = f"${r['cost']:.2f}" if r["cost"] else "-"
        print(f"{r['instance_id'][:40]:<40} {f2p:>8} {p2p:>9} {coll:>8}{flag} "
              f"{str(r['steps'] or '-'):>6} {cost:>7}  {'KEEP' if r['kept'] else '.'}")

    n = len(rows)
    print(f"\ncriterion={args.criterion}: {len(solvable)}/{n} kept -> {filt}")
    if n:
        print(f"F2P total {sum(r['f2p'][0] for r in rows)}/{sum(r['f2p'][1] for r in rows)}   "
              f"P2P total {sum(r['p2p'][0] for r in rows)}/{sum(r['p2p'][1] for r in rows)}")
    bad = [r for r in rows if r["n_uncollected"]]
    if bad:
        print(f"\n{len(bad)} instance(s) with UNCOLLECTED tests (a broken import removes a whole "
              f"module; absence scores as failure):")
        for r in bad:
            print(f"  {r['instance_id'][:58]}: {r['n_uncollected']} missing, "
                  f"e.g. {r['uncollected'][:2]}")


if __name__ == "__main__":
    main()
