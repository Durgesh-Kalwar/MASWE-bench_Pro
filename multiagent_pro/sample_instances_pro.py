#!/usr/bin/env python
"""Stage 1 of the SWE-bench **Pro** multi-agent pipeline: sample instances from the
HuggingFace dataset and dump them to disk for the build step.

Loads `ScaleAI/SWE-bench_Pro` (split `test`), filters to the languages enabled in
`LANG_CONFIG` (Python only for now), and writes per instance:

    sampled_pro/<instance_id>/metadata.json   # raw HF fields under their original names
    sampled_pro/raw_sample.jsonl              # combined index for swe_bench_pro_eval.py

`metadata.json` is the sole input to `build_multiagent_pro.py`. `raw_sample.jsonl` is the
`--raw_sample_path` the evaluator consumes; its `fail_to_pass` / `pass_to_pass` /
`selected_test_files_to_run` columns are preserved as the **raw string literals** the HF
dataset stores them as, because the evaluator does `eval(...)` on them, not `json.loads`.

Usage
-----
    python multiagent_pro/sample_instances_pro.py                       # all python instances
    python multiagent_pro/sample_instances_pro.py --instances <id> <id>
    python multiagent_pro/sample_instances_pro.py --repo qutebrowser -n 5
"""

import argparse
import json
import sys
from pathlib import Path

DATASET = "ScaleAI/SWE-bench_Pro"
SPLIT = "test"

# Language policy lives here so other languages flip on later without touching call sites.
# `suffixes` documents the source extension(s) per language (used by the build step's
# distractor matching, which is already suffix-keyed). Only `enabled` gates sampling here.
LANG_CONFIG = {
    "python":     {"suffixes": {".py"},          "enabled": True},
    "javascript": {"suffixes": {".js"},          "enabled": False},
    "typescript": {"suffixes": {".ts", ".tsx"},  "enabled": False},
    "js":         {"suffixes": {".js", ".ts"},   "enabled": False},
    "go":         {"suffixes": {".go"},          "enabled": False},
}

# Raw HF fields carried verbatim into metadata.json (names preserved for downstream parsing).
RAW_FIELDS = [
    "repo", "instance_id", "base_commit", "patch", "test_patch",
    "problem_statement", "requirements", "interface", "repo_language",
    "fail_to_pass", "pass_to_pass", "issue_categories", "issue_specificity",
    "before_repo_set_cmd", "selected_test_files_to_run", "dockerhub_tag",
]

# Columns the evaluator (swe_bench_pro_eval.py) reads from --raw_sample_path, keyed by
# instance_id. Kept lean; the string-literal columns must NOT be json-normalized.
RAW_SAMPLE_FIELDS = [
    "instance_id", "repo", "base_commit", "before_repo_set_cmd",
    "selected_test_files_to_run", "fail_to_pass", "pass_to_pass", "dockerhub_tag",
]


def lang_enabled(repo_language):
    cfg = LANG_CONFIG.get(str(repo_language or "").lower())
    return bool(cfg and cfg["enabled"])


def load_rows():
    """Reuse the HF-loader pattern from explore_swebench_pro.py."""
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Missing dependency. Run:  pip install datasets")
    print(f"Loading {DATASET} (split={SPLIT}) from HuggingFace ...")
    return load_dataset(DATASET, split=SPLIT)


def select_rows(ds, instances, repo, num):
    """Filter to enabled-language rows, optionally restricting by --instances / --repo / -n."""
    want = set(instances) if instances else None
    rows = []
    for r in ds:
        if not lang_enabled(r.get("repo_language")):
            continue
        if want is not None and r["instance_id"] not in want:
            continue
        if repo and repo.lower() not in str(r.get("repo", "")).lower():
            continue
        rows.append(r)
        if num and not want and len(rows) >= num:
            break
    return rows


def write_metadata(row, out_root):
    iid = row["instance_id"]
    inst_dir = out_root / iid
    inst_dir.mkdir(parents=True, exist_ok=True)
    meta = {k: row.get(k) for k in RAW_FIELDS}
    (inst_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return inst_dir


def write_raw_sample(rows, out_path):
    """Write one combined JSONL for the evaluator. fail_to_pass/pass_to_pass/
    selected_test_files_to_run are kept as the raw string literals (eval()'d downstream)."""
    with open(out_path, "w") as f:
        for r in rows:
            rec = {k: r.get(k) for k in RAW_SAMPLE_FIELDS}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="sampled_pro", help="Output folder")
    ap.add_argument("--instances", nargs="*", help="Restrict to these instance ids")
    ap.add_argument("--repo", help="Restrict to instances whose repo matches this substring")
    ap.add_argument("-n", "--num", type=int, default=0,
                    help="Cap on number of instances (ignored when --instances is given)")
    args = ap.parse_args()

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    ds = load_rows()
    rows = select_rows(ds, args.instances, args.repo, args.num)
    if not rows:
        sys.exit("No matching (enabled-language) instances found.")

    by_repo = {}
    for r in rows:
        write_metadata(r, out_root)
        by_repo[r.get("repo")] = by_repo.get(r.get("repo"), 0) + 1

    raw_sample = write_raw_sample(rows, out_root / "raw_sample.jsonl")

    print(f"\nWrote {len(rows)} instance(s) to {out_root}/")
    for repo, n in sorted(by_repo.items()):
        print(f"  {repo:<32} {n}")
    print(f"raw sample -> {raw_sample}")


if __name__ == "__main__":
    main()
