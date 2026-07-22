# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

SWE-Bench Pro: a benchmark for evaluating LLM agents on long-horizon software-engineering tasks. Given a codebase + issue, an agent produces a patch; this repo runs that patch inside the instance's prebuilt Docker image, executes the instance's tests, and scores pass/fail. The dataset lives on HuggingFace (`ScaleAI/SWE-bench_Pro`); this repo is the **evaluation harness + reproduction scaffold**, not the dataset itself.

## Submodules

`SWE-agent/` and `mini-swe-agent/` are git submodules (Scale forks, see `.gitmodules`) used to *generate* patches. They are independent agent scaffolds with their own setup. After cloning, run `git submodule update --init --recursive`. Patch *generation* happens there; patch *evaluation* happens in the root scripts.

## End-to-end pipeline

The three stages are run separately, in order:

1. **Generate patches** — run an agent scaffold (SWE-agent / mini-swe-agent submodule) to produce per-instance `.pred` files.
2. **Gather patches** — `helper_code/gather_patches.py` collects scattered `.pred` files into one JSON array of `{instance_id, patch, prefix}`.
3. **Evaluate** — `swe_bench_pro_eval.py` runs each patch and emits `eval_results.json` + per-instance logs.

```bash
# Stage 2: collect .pred files into one JSON
python helper_code/gather_patches.py --directory <pred_dir> --prefix <model_name> --output patches.json

# Stage 3: evaluate (Modal by default)
python swe_bench_pro_eval.py \
    --raw_sample_path=<data>.csv \   # or .jsonl; pandas auto-detects by extension
    --patch_path=patches.json \
    --output_dir=<out_dir> \
    --scripts_dir=run_scripts \
    --num_workers=100 \
    --dockerhub_username=jefzda
```

Useful eval flags: `--use_local_docker` (run via local Docker SDK instead of Modal), `--redo` (re-run even if `{prefix}_output.json` exists), `--block_network` (no network inside the container), `--docker_platform linux/amd64` (forced on Apple Silicon auto-detect).

To run a **single instance**, make a `patches.json` with just that one entry (e.g. extract its gold patch via `helper_code/extract_gold_patches.py`) and point `--patch_path` at it. There is no separate single-test runner — scope is controlled by the contents of the patch JSON.

## How evaluation actually works (the core flow)

`swe_bench_pro_eval.py` is the heart of the repo. Per instance it:

1. Loads three local files keyed by `instance_id`:
   - `run_scripts/{instance_id}/run_script.sh` — sets up the test env and runs the selected tests, emitting JSON test output.
   - `run_scripts/{instance_id}/parser.py` — parses test stdout/stderr into `{"tests": [{"name", "status"}]}`.
   - `dockerfiles/{base,instance}_dockerfile/{instance_id}/Dockerfile` — only its `ENV` lines are scraped and converted to `export`s (the images themselves come from Docker Hub, the Dockerfiles are *not* built here).
2. Builds an `entryscript.sh` (`create_entryscript`) that, inside the container: `git reset/checkout` to `base_commit` → `git apply patch.diff` → run `before_repo_set_cmd` → run `run_script.sh` → run `parser.py` → write `output.json`.
3. Runs that entryscript in a **Modal Sandbox** (`eval_with_modal`) or **local Docker container** (`eval_with_docker`), pulling image `{dockerhub_username}/sweap-images:{tag}`.
4. Scoring (`main`): an instance **passes only if `FAIL_TO_PASS ∪ PASS_TO_PASS ⊆ {tests that PASSED}`** — every required test must pass, not just a subset.

Evaluation is embarrassingly parallel via `ThreadPoolExecutor(max_workers=num_workers)`; each instance is independent. Any failure (missing scripts, container error, no `output.json`) is caught and scored as `False` rather than aborting the run.

### Things that bite

- **Docker tag derivation is special-cased** — `helper_code/image_uri.py::get_dockerhub_image_uri` lowercases `repo`, strips the `-vnan` suffix, truncates to 128 chars, and has explicit one-off handling for `element-hq/element-web`. If an image 404s, suspect this function before anything else.
- **CSV columns are stored as stringified Python literals.** `selected_test_files_to_run`, `fail_to_pass`, `pass_to_pass` are parsed with `eval(...)`, not `json.loads`. New input data must match that format.
- **Patch field fallback:** patch JSON entries are read as `model_patch` first, then `patch`. `.pred` files may be raw text or JSON containing either key (see `gather_patches.py`).
- **Binary diffs are stripped** before applying (`strip_binary_hunks`) — binary hunks won't survive into the container.
- **`instance_id` is the universal join key** across `run_scripts/`, `dockerfiles/`, the CSV index, and patch JSON. The 1000 dirs in `run_scripts/` and 731 in `dockerfiles/base_dockerfile/` are per-instance and must align with the rows in your sample file.

## Setup

```bash
pip install -r requirements.txt          # pandas, tqdm, datasets, modal, docker, huggingface_hub
modal setup                              # default backend; writes ~/.modal.toml. Skip if using --use_local_docker
```
`modal` and `docker` are imported lazily — you only need the one matching your chosen backend.

## Other directories

- `helper_code/` — `extract_gold_patches.py` (gold patches → eval JSON), `generate_sweagent_instances.py`, `create_problem_statement.py`, `sweap_eval_full_v2.jsonl` (sample data).
- `error_analysis/` — CSV outputs of LLM-as-a-judge failure analysis from the paper.
- `traj/`, `swebench_pro_out/` — trajectory / evaluation output artifacts.
- `index.html` — static results page.
