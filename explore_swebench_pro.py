#!/usr/bin/env python3
"""
Explore a SWE-bench Pro instance.

Loads the public SWE-bench Pro dataset from HuggingFace and dumps one full
instance (all fields, including the gold patch and tests) into readable files
so you can inspect exactly what an agent is given and graded on.

Setup:
    pip install datasets

Usage:
    # dump the first instance
    python explore_swebench_pro.py

    # list available instance ids / repos (first 40)
    python explore_swebench_pro.py --list

    # dump a specific instance by id
    python explore_swebench_pro.py --instance-id <instance_id>

    # dump the Nth instance (0-based)
    python explore_swebench_pro.py --index 5

    # pick the first instance from a given repo
    python explore_swebench_pro.py --repo openlibrary

Output goes to ./swebench_pro_out/<instance_id>/
"""

import argparse
import json
import os
import sys
import textwrap

DATASET = "ScaleAI/SWE-bench_Pro"
SPLIT = "test"

# Fields that are long blobs -> written to their own files instead of inline.
BLOB_FIELDS = {
    "patch": "gold_patch.diff",
    "test_patch": "test_patch.diff",
    "problem_statement": "problem_statement.md",
    "requirements": "requirements.md",
    "interface": "interface.md",
    "fail_to_pass": "fail_to_pass.txt",
    "pass_to_pass": "pass_to_pass.txt",
}


def load_rows():
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Missing dependency. Run:  pip install datasets")
    print(f"Loading {DATASET} (split={SPLIT}) from HuggingFace ...")
    return load_dataset(DATASET, split=SPLIT)


def pick_row(ds, args):
    if args.instance_id:
        for r in ds:
            if r["instance_id"] == args.instance_id:
                return r
        sys.exit(f"instance_id not found: {args.instance_id}")
    if args.repo:
        for r in ds:
            if args.repo.lower() in str(r.get("repo", "")).lower():
                return r
        sys.exit(f"No instance found for repo containing: {args.repo}")
    return ds[args.index]


def maybe_json_list(value):
    """fail_to_pass / pass_to_pass are often JSON-encoded lists of test names."""
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return "\n".join(str(x) for x in parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    return value


def dump(row, outroot):
    iid = row["instance_id"]
    outdir = os.path.join(outroot, iid)
    os.makedirs(outdir, exist_ok=True)

    # 1) full raw row as JSON
    with open(os.path.join(outdir, "instance_full.json"), "w") as f:
        json.dump(dict(row), f, indent=2, ensure_ascii=False)

    # 2) each big field as its own readable file
    for field, fname in BLOB_FIELDS.items():
        if field not in row or row[field] is None:
            continue
        content = maybe_json_list(row[field]) if field.endswith("_to_pass") else row[field]
        with open(os.path.join(outdir, fname), "w") as f:
            f.write(str(content))

    # 3) a human-readable summary
    def short(v, n=300):
        if v is None:
            return "(null)"
        s = str(v)
        return s if len(s) <= n else s[:n] + f"  ... [{len(s)} chars total]"

    ftp = maybe_json_list(row.get("fail_to_pass"))
    ptp = maybe_json_list(row.get("pass_to_pass"))
    n_ftp = len([x for x in str(ftp).splitlines() if x.strip()])
    n_ptp = len([x for x in str(ptp).splitlines() if x.strip()])

    lines = [
        "=" * 70,
        f"INSTANCE: {iid}",
        "=" * 70,
        f"repo:            {row.get('repo')}",
        f"repo_language:   {row.get('repo_language')}",
        f"base_commit:     {row.get('base_commit')}",
        f"dockerhub_tag:   {row.get('dockerhub_tag')}",
        f"  docker image:  jefzda/sweap-images:{row.get('dockerhub_tag')}",
        f"issue_categories:{row.get('issue_categories')}",
        f"issue_specificity:{row.get('issue_specificity')}",
        "",
        f"fail_to_pass tests (must go fail->pass): {n_ftp}",
        f"pass_to_pass tests (must stay passing):  {n_ptp}",
        f"selected_test_files_to_run: {short(row.get('selected_test_files_to_run'))}",
        "",
        "gold patch size:    %d chars" % len(str(row.get("patch") or "")),
        "test patch size:    %d chars" % len(str(row.get("test_patch") or "")),
        "",
        "-" * 70,
        "PROBLEM STATEMENT (preview):",
        "-" * 70,
        textwrap.fill(short(row.get("problem_statement"), 800), width=88),
        "",
        "-" * 70,
        "REQUIREMENTS (preview):",
        "-" * 70,
        textwrap.fill(short(row.get("requirements"), 800), width=88),
        "",
        "Files written to: " + outdir,
        "  - instance_full.json   (all fields)",
        "  - problem_statement.md (what the agent is asked)",
        "  - requirements.md      (human-authored specifics)",
        "  - interface.md         (expected signatures, may be empty)",
        "  - gold_patch.diff      (reference human solution - hidden from agent)",
        "  - test_patch.diff      (the verifier tests)",
        "  - fail_to_pass.txt / pass_to_pass.txt",
    ]
    summary = "\n".join(lines)
    with open(os.path.join(outdir, "SUMMARY.txt"), "w") as f:
        f.write(summary + "\n")
    print("\n" + summary)


def list_instances(ds, n=40):
    print(f"{'#':>4}  {'repo':<22} {'lang':<6} instance_id")
    print("-" * 80)
    for i in range(min(n, len(ds))):
        r = ds[i]
        print(f"{i:>4}  {str(r.get('repo','')):<22} {str(r.get('repo_language','')):<6} {r['instance_id']}")
    print(f"\nTotal instances: {len(ds)}")


def main():
    p = argparse.ArgumentParser(description="Explore a SWE-bench Pro instance.")
    p.add_argument("--list", action="store_true", help="list first 40 instances and exit")
    p.add_argument("--instance-id", help="dump a specific instance by id")
    p.add_argument("--repo", help="dump the first instance whose repo matches this substring")
    p.add_argument("--index", type=int, default=0, help="dump the Nth instance (0-based)")
    p.add_argument("--out", default="swebench_pro_out", help="output directory root")
    args = p.parse_args()

    ds = load_rows()
    print(f"Loaded {len(ds)} instances. Columns: {ds.column_names}\n")

    if args.list:
        list_instances(ds)
        return

    row = pick_row(ds, args)
    dump(row, args.out)


if __name__ == "__main__":
    main()