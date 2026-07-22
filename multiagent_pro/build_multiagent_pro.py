#!/usr/bin/env python
"""Reformulate a SWE-bench **Pro** instance as a multi-agent problem.

Port of `SWE-bench/scripts/build_multiagent.py` to the Pro dataset + harness. Each
gold-patched source file becomes one agent. Every agent gets:
  * a *scope* of files it may read/write = its gold file + K distractor siblings
    (oracle + distractors: the real target is hidden among decoys so localization
    isn't trivially leaked, while every needed file is still owned by someone),
  * a *local* slice of the issue text routed by the symbols its gold hunks change
    (local-only: there is no shared global copy). `problem_statement` is always routed;
    `--include-requirements` additionally routes the Pro `requirements` field,
  * optionally a shared coordination note built from the Pro `interface` field
    (`--include-interface`): the explicit signatures of any new public interface the
    gold solution couples through.

N = number of distinct files the gold patch touches; N=1 collapses to the degenerate case.

Integration is a clean concatenation of each agent's scoped diff into a single
`model_patch`. Grading uses the Pro evaluator `swe_bench_pro_eval.py`, which consumes a
JSON **list** of `{instance_id, model_patch, prefix}` via `--patch_path` (NOT the upstream
swebench harness). The hidden test_patch / fail_to_pass / pass_to_pass are untouched.

Modes
-----
build   Read sampled_pro/<id>/metadata.json -> emit multiagent_pro_out/<id>/ specs.
merge   Concatenate multiagent_pro_out/<id>/agent_*.patch into one model_patch and write
        multiagent_pro_out/patches.json (a JSON list) for swe_bench_pro_eval.py.

Usage
-----
    python multiagent_pro/build_multiagent_pro.py --mode build --distractors 3 \
        --include-requirements --include-interface
    python multiagent_pro/build_multiagent_pro.py --mode merge --instances <id>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from unidiff import PatchSet

# Reuse the evaluator's image-URI derivation so docker-based distractor enumeration pulls
# the exact same image the Pro harness grades against.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "helper_code"))
try:
    from image_uri import get_dockerhub_image_uri
except Exception:  # pragma: no cover - only the docker distractor source needs it
    get_dockerhub_image_uri = None

# Pro has no swebench dependency; hardcode the prediction keys the Pro evaluator reads.
KEY_INSTANCE_ID = "instance_id"
KEY_MODEL_PATCH = "model_patch"   # swe_bench_pro_eval.py prefers this over "patch"
KEY_PREFIX = "prefix"

NO_INTERFACE_SENTINEL = "No new interfaces are introduced"


def decode_text(value):
    """Unwrap Pro's text fields. `problem_statement` / `requirements` / `interface` are
    stored as JSON-encoded strings (wrapped in quotes, with `\\n` escapes); strip that one
    layer when present. `patch` and already-plain text pass through unchanged."""
    if not isinstance(value, str):
        return value or ""
    if value.strip()[:1] == '"':
        try:
            decoded = json.loads(value)
            if isinstance(decoded, str):
                return decoded
        except (json.JSONDecodeError, TypeError):
            pass
    return value

# Identifiers worth routing on (skip 1-2 char noise and pure-numeric tokens).
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# Enclosing def/class names that unidiff exposes in the hunk "@@ ... @@" section header.
# Python-leaning; a future per-language hook would extend this (e.g. add `function`).
_SECTION_SYMBOL = re.compile(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


# --------------------------------------------------------------------------- #
# Gold-patch decomposition
# --------------------------------------------------------------------------- #
def split_gold_by_file(gold_patch):
    """Return {file_path: file_diff_text} for every source file in the gold patch."""
    patch = PatchSet(gold_patch)
    out = {}
    for pf in patch:
        # target_file looks like "b/lib/ansible/foo.py"; pf.path strips the b/ prefix.
        out[pf.path] = str(pf)
    return out


# Generic programming tokens that would mis-route everything if used as anchors.
_NOISE = {
    "self", "from", "import", "return", "None", "True", "False", "def",
    "class", "the", "and", "for", "not", "isinstance", "args", "kwargs",
    "value", "type", "object", "result", "other", "with", "this", "that",
}


def code_symbols(file_diff_text):
    """Identifiers an agent's gold hunks actually change + enclosing def/class names.
    Used only for issue routing here (the Pro contract comes from the interface field)."""
    symbols = set()
    for pf in PatchSet(file_diff_text):
        for hunk in pf:
            for m in _SECTION_SYMBOL.finditer(hunk.section_header or ""):
                symbols.add(m.group(1))
            for line in hunk:
                if line.is_added or line.is_removed:
                    symbols.update(_IDENT.findall(line.value))
    return {s for s in symbols if s not in _NOISE}


def anchor_symbols(code_syms, file_path):
    """Routing anchors: code symbols + the file's basename/module path tokens. Broader
    than code_symbols (path tokens help route prose that names a file/module)."""
    symbols = set(code_syms)
    symbols.add(Path(file_path).stem)
    for part in Path(file_path).with_suffix("").parts:
        if len(part) > 2:
            symbols.add(part)
    return {s for s in symbols if s not in _NOISE}


# --------------------------------------------------------------------------- #
# Local-only issue split
# --------------------------------------------------------------------------- #
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`])")


def segment_issue(text):
    """Split issue text into routable units. Fenced code blocks stay intact as one unit;
    prose is split into sentences (and per-line) so local-only routing can distribute
    fine-grained context. Order is preserved so each agent's slice reads naturally."""
    units, buf, in_fence = [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if in_fence:                       # closing fence -> flush whole code block
                buf.append(line)
                units.append("\n".join(buf))
                buf = []
            else:                              # opening fence -> flush pending prose first
                if buf:
                    units.append("\n".join(buf))
                    buf = []
                buf.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            buf.append(line)
            continue
        if line.strip() == "":                 # paragraph break -> flush prose
            if buf:
                units.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        units.append("\n".join(buf))

    out = []
    for u in units:
        if u.lstrip().startswith("```"):
            out.append(u)
            continue
        for line in u.splitlines():
            for sent in _SENTENCE_SPLIT.split(line):
                if sent.strip():
                    out.append(sent.strip())
    return out


def focus_units(text, agent, cap=15):
    """Select issue units (sentences / code blocks) that mention THIS agent's anchor
    symbols — a per-agent *highlight* over the shared issue text, not a partition. Ranked
    by symbol-overlap, capped, then restored to reading order. Returns a list of strings."""
    if not text:
        return []
    scored = []
    for i, block in enumerate(segment_issue(text)):
        tokens = _IDENT.findall(block)
        score = sum(1 for t in tokens if t in agent["symbols"])
        if score > 0:
            scored.append((i, score, block))
    scored.sort(key=lambda x: (-x[1], x[0]))            # best matches first
    chosen = sorted(scored[:cap], key=lambda x: x[0])    # back to original order
    return [b for _, _, b in chosen]


def _render_focus_units(units):
    """Render selected focus units: code fences verbatim, prose as blockquotes."""
    out = []
    for u in units:
        if u.lstrip().startswith("```"):
            out += ["", u]
        else:
            out.append(f"> {u}")
    return out


def build_local_info(meta, agents, include_requirements):
    """Assemble each agent's local_issue.md body (returns {agent_idx0: markdown}).

    Limited information is enforced by file *scope*, not by withholding issue text: EVERY
    agent receives the FULL problem statement (and full requirements when
    include_requirements). A generated `## Your focus` section then highlights the passages
    that mention this agent's gold file / symbols, plus a responsibility note, so the agent
    knows where to act. No agent is ever handed an empty slice."""
    problem = decode_text(meta.get("problem_statement")).strip()
    requirements = (decode_text(meta.get("requirements")).strip()
                    if include_requirements else "")

    bodies = {}
    for i, ag in enumerate(agents):
        sections = ["## Problem statement", "", problem or "(none provided)"]
        if include_requirements:
            sections += ["", "## Requirements", "", requirements or "(none provided)"]

        sections += ["", f"## Your focus (file: {ag['gold_file']})", "",
                     f"You are responsible for **`{ag['gold_file']}`**. You may only read "
                     f"and write the files listed in your SCOPE.txt; for anything outside "
                     f"that scope (e.g. an interface another agent owns), use the messaging "
                     f"tools to coordinate."]
        # Display only code-like symbols (has `_` or an uppercase letter): drops prose
        # words harvested from comments/docstrings while keeping real identifiers.
        syms = sorted(s for s in ag["symbols"]
                      if "_" in s or any(c.isupper() for c in s))
        if syms:
            sections += ["", "Key symbols in your file: "
                         + ", ".join(f"`{s}`" for s in syms) + "."]
        focus = focus_units(problem, ag)
        if include_requirements:
            focus += focus_units(requirements, ag)
        if focus:
            sections += ["", "Issue passages that mention your file / symbols:"]
            sections += _render_focus_units(focus)
        bodies[i] = "\n".join(sections)
    return bodies


# --------------------------------------------------------------------------- #
# Cross-scope contract: the Pro `interface` field (signatures only)
# --------------------------------------------------------------------------- #
def parse_interface(interface_field):
    """Parse the Pro `interface` field into a contract dict for coordination.md.

    Returns {"has_contract": bool, "raw": str, "signatures": [str], "note": str}.
    The sentinel "No new interfaces are introduced" (or empty) -> has_contract=False.
    Otherwise the raw text is preserved and `signatures` is a best-effort line split for
    nicer rendering (the raw text is always authoritative)."""
    raw = decode_text(interface_field).strip()
    if not raw or raw == NO_INTERFACE_SENTINEL:
        return {
            "has_contract": False,
            "raw": raw,
            "signatures": [],
            "note": ("The dataset declares no new public interface for this instance. "
                     "Agents must discover any cross-file coupling themselves."),
        }
    signatures = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return {"has_contract": True, "raw": raw, "signatures": signatures, "note": ""}


# --------------------------------------------------------------------------- #
# Build mode
# --------------------------------------------------------------------------- #
def enumerate_siblings_docker(image, base_commit, dirs):
    """List the files in each repo directory at base_commit by running `git ls-tree`
    inside the instance's Pro image (the repo is baked into the image). The repo root is
    auto-detected with `git rev-parse --show-toplevel` from the image WORKDIR (Pro images
    use /app, others /testbed), so this works regardless of the checkout path. Returns
    {dir: [repo_relative_paths]}; {} if docker/the image is unavailable. Fully offline —
    no GitHub token. One container lists every directory."""
    dirs = sorted({d for d in dirs})
    if not dirs or not image:
        return {}
    # Detect the repo root once, then delimit per-directory output with sentinel lines.
    listings = " ; ".join(
        f'echo "@@DIR {d}@@"; '
        f'git -C "$REPO" ls-tree --name-only {base_commit} -- "{d}/" 2>/dev/null'
        for d in dirs
    )
    script = (
        'REPO=$(git rev-parse --show-toplevel 2>/dev/null); '
        '[ -z "$REPO" ] && REPO=/testbed; '
        + listings
    )
    cmd = ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception:
        return {}
    if not proc.stdout:
        return {}
    result, cur = {}, None
    for line in proc.stdout.splitlines():
        if line.startswith("@@DIR ") and line.endswith("@@"):
            cur = line[len("@@DIR "):-2]
            result[cur] = []
        elif cur is not None and line.strip():
            result[cur].append(line.strip())
    return result


def _list_dirs_github(repo, base_commit, dirs):
    """GitHub contents API fallback: {dir: [file_paths]} at base_commit; {} on failure."""
    try:
        from ghapi.core import GhApi
    except Exception:
        return {}
    try:
        owner, name = repo.split("/")
    except ValueError:
        return {}
    api = GhApi(token=os.environ.get("GITHUB_TOKEN"))
    out = {}
    for d in sorted(dirs):
        try:
            contents = api.repos.get_content(owner, name, d, ref=base_commit)
            out[d] = [c["path"] for c in contents if c.get("type") == "file"]
        except Exception:
            out[d] = []
    return out


def fetch_distractors(repo, base_commit, gold_files, k, gold_set,
                      source="docker", image=None):
    """Return {gold_file: [distractor_paths]} — up to K sibling files per gold file,
    disjoint across agents and matching the gold file's suffix. Siblings are enumerated at
    base_commit from `source`:
      docker  - `git ls-tree` inside the Pro image (offline, no token) [default]
      github  - GitHub contents API via ghapi (needs network/token)
      oracle  - none (pure-oracle scoping)
    docker falls back to github, then to pure-oracle, if enumeration yields nothing."""
    if k <= 0 or source == "oracle":
        return {gf: [] for gf in gold_files}

    parents = {str(Path(gf).parent) for gf in gold_files}
    dir_listing = {}
    if source == "docker":
        dir_listing = enumerate_siblings_docker(image, base_commit, parents)
    if not dir_listing:                       # docker failed, or source == github
        dir_listing = _list_dirs_github(repo, base_commit, parents)

    assigned = set(gold_set)                  # gold files are never their own decoys
    result = {gf: [] for gf in gold_files}
    for gf in gold_files:
        parent = str(Path(gf).parent)
        suffix = Path(gf).suffix
        for cand in sorted(dir_listing.get(parent, [])):
            if len(result[gf]) >= k:
                break
            if cand in assigned or not cand.endswith(suffix):
                continue
            result[gf].append(cand)
            assigned.add(cand)
    return result


def build_instance(meta, out_dir, k_distractors, include_requirements,
                   include_interface, emit_gold=False,
                   distractor_source="docker", dockerhub_username="jefzda"):
    instance_id = meta[KEY_INSTANCE_ID]
    gold = meta["patch"]
    repo = meta["repo"]
    base_commit = meta["base_commit"]

    gold_by_file = split_gold_by_file(gold)
    gold_files = list(gold_by_file.keys())
    gold_set = set(gold_files)
    image = None
    if distractor_source == "docker" and get_dockerhub_image_uri is not None:
        try:
            image = get_dockerhub_image_uri(instance_id, dockerhub_username, repo)
        except Exception:
            image = None
    distractors = fetch_distractors(repo, base_commit, gold_files, k_distractors, gold_set,
                                    source=distractor_source, image=image)

    agents = []
    for idx, gf in enumerate(gold_files, start=1):
        diff_text = gold_by_file[gf]
        gold_lines = sum(
            1 for ln in diff_text.splitlines()
            if (ln.startswith("+") or ln.startswith("-")) and not ln.startswith(("+++", "---"))
        )
        csyms = code_symbols(diff_text)
        agents.append({
            "idx": idx,
            "gold_file": gf,
            "gold_diff": diff_text,
            "gold_lines": gold_lines,
            "distractors": distractors.get(gf, []),
            "scope": [gf] + distractors.get(gf, []),
            "code_symbols": csyms,
            "symbols": anchor_symbols(csyms, gf),
        })

    local = build_local_info(meta, agents, include_requirements)
    interface = parse_interface(meta.get("interface"))

    # ---- write folders ----
    inst_dir = out_dir / instance_id
    inst_dir.mkdir(parents=True, exist_ok=True)

    spec = {
        KEY_INSTANCE_ID: instance_id,
        "repo": repo,
        "base_commit": base_commit,
        "num_agents": len(agents),
        "degenerate": len(agents) == 1,
        "include_requirements": include_requirements,
        "include_interface": include_interface,
        "shared_contract": interface["raw"] if (include_interface and interface["has_contract"]) else None,
        "agents": [],
        "integration": "concatenate agent_<k>.patch in agent index order -> single model_patch",
        "grade_cmd": (
            f"python multiagent_pro/build_multiagent_pro.py --mode merge --instances {instance_id} "
            f"--output {out_dir} && "
            f"python swe_bench_pro_eval.py "
            f"--raw_sample_path sampled_pro/raw_sample.jsonl "
            f"--patch_path {out_dir}/patches.json "
            f"--output_dir {out_dir}/eval_out --scripts_dir run_scripts "
            f"--dockerhub_username jefzda --use_local_docker"
        ),
    }

    for ag in agents:
        adir = inst_dir / f"agent_{ag['idx']}"
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "SCOPE.txt").write_text(
            "# Files this agent may READ and WRITE (everything else is invisible).\n"
            f"# Target (gold) file is hidden among {len(ag['distractors'])} distractor(s).\n"
            + "\n".join(ag["scope"]) + "\n"
        )
        (adir / "local_issue.md").write_text(
            f"# Issue context for agent_{ag['idx']}\n"
            f"# (full issue text + your focus — limited information is enforced by file "
            f"SCOPE, not by withholding the issue)\n\n"
            + local[ag["idx"] - 1] + "\n"
        )
        if emit_gold:
            # Oracle reference solution for this agent's scope — used to sanity-check
            # that integrate(agent patches) -> grade reproduces the gold result.
            (adir / "gold.patch").write_text(ag["gold_diff"])
        spec["agents"].append({
            "id": f"agent_{ag['idx']}",
            "gold_file": ag["gold_file"],
            "scope": ag["scope"],
            "distractors": ag["distractors"],
            "anchor_symbols": sorted(ag["symbols"]),
            "gold_changed_lines": ag["gold_lines"],
        })

    # Shared contract: emitted only when --include-interface (else agents discover coupling).
    if include_interface:
        (inst_dir / "shared").mkdir(parents=True, exist_ok=True)
        (inst_dir / "shared" / "coordination.md").write_text(
            render_coordination(instance_id, agents, interface))
    (inst_dir / "spec.json").write_text(json.dumps(spec, indent=2))
    (inst_dir / "README.md").write_text(
        render_readme(instance_id, repo, agents, interface,
                      include_requirements, include_interface, out_dir))
    return spec


def render_coordination(instance_id, agents, interface):
    lines = [
        f"# Coordination protocol — {instance_id}",
        "",
        f"Agents: {len(agents)} (one per gold-patched file). Scopes are disjoint; each agent",
        "edits only files in its own SCOPE.txt. The final patch is the concatenation of all",
        "`agent_<k>.patch` files.",
        "",
        "## Cross-scope interface contract (from dataset `interface`)",
    ]
    if interface["has_contract"]:
        lines += [
            "The gold solution introduces the public interface below. Agents must agree on",
            "these exact signatures (one agent defines, others call):",
            "",
            "```",
            interface["raw"],
            "```",
        ]
    else:
        lines.append(f"_{interface['note']}_")
    lines += ["", "## File ownership"]
    for ag in agents:
        lines.append(f"- **agent_{ag['idx']}** owns `{ag['gold_file']}` "
                     f"(+{len(ag['distractors'])} distractor(s))")
    return "\n".join(lines) + "\n"


def render_readme(instance_id, repo, agents, interface,
                  include_requirements, include_interface, out_dir):
    n = len(agents)
    verdict = ("degenerate single-agent (N=1) — identical to standard single-agent Pro"
               if n == 1 else f"genuine {n}-agent decomposition")
    local_fields = ("full problem_statement"
                    + (" + requirements" if include_requirements else "")
                    + " + per-file focus highlight")
    if not include_interface:
        contract = "none emitted (--include-interface off; agents discover coupling)"
    elif interface["has_contract"]:
        contract = "interface signatures (see shared/coordination.md)"
    else:
        contract = "no new interfaces declared by the dataset"
    lines = [
        f"# Multi-agent setup — {instance_id}",
        "",
        f"- **Repo:** {repo}",
        f"- **Agents (N):** {n}  →  _{verdict}_",
        f"- **Local info included:** {local_fields}",
        f"- **Shared contract:** {contract}",
        "",
        "| Agent | Owns (gold) | Distractors | Changed lines |",
        "| --- | --- | --- | --- |",
    ]
    for ag in agents:
        lines.append(
            f"| agent_{ag['idx']} | `{ag['gold_file']}` | "
            f"{len(ag['distractors'])} | {ag['gold_lines']} |"
        )
    lines += [
        "",
        "## Layout",
        "- `agent_<k>/SCOPE.txt` — files this agent may read/write (gold target + distractors)",
        "- `agent_<k>/local_issue.md` — full issue text + this agent's per-file focus highlight",
        "- `shared/coordination.md` — the interface contract (only if --include-interface)",
        "- `spec.json` — machine-readable spec (scopes, symbols, integration, grade command)",
        "",
        "## Solve & grade",
        "Each agent writes its diff to `agent_<k>.patch` (scoped to its files), then:",
        "```bash",
        f"python multiagent_pro/build_multiagent_pro.py --mode merge --instances {instance_id} --output {out_dir}",
        "python swe_bench_pro_eval.py \\",
        "    --raw_sample_path sampled_pro/raw_sample.jsonl \\",
        f"    --patch_path {out_dir}/patches.json \\",
        f"    --output_dir {out_dir}/eval_out --scripts_dir run_scripts \\",
        "    --dockerhub_username jefzda --use_local_docker",
        "```",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Merge mode
# --------------------------------------------------------------------------- #
def merge_instance(inst_dir, prefix="multiagent"):
    """Concatenate agent_*.patch into one model_patch. Returns a single patch entry
    {instance_id, model_patch, prefix} for the Pro evaluator's --patch_path list."""
    instance_id = inst_dir.name
    parts = sorted(inst_dir.glob("agent_*.patch"))
    if not parts:
        # also look one level down: agent_<k>/agent_<k>.patch or agent_<k>/solution.patch
        parts = sorted(inst_dir.glob("agent_*/*.patch"))
    if not parts:
        raise SystemExit(
            f"No agent_*.patch files found under {inst_dir}. "
            "Each agent must write its scoped diff to agent_<k>.patch first."
        )
    merged = ""
    seen_files = {}          # repo path -> first agent patch that touched it
    for p in parts:
        text = p.read_text()
        if text and not text.endswith("\n"):
            text += "\n"
        merged += text
        # Naive concatenation is correct only when scopes are disjoint. If two agents
        # both touch the same file, their hunks duplicate and the combined patch fails
        # `git apply`, which the evaluator silently scores as a wrong answer. Surface it.
        for m in re.finditer(r'^diff --git a/(\S+) b/\S+', text, re.MULTILINE):
            f = m.group(1)
            if f in seen_files:
                print(f"  WARNING: {instance_id}: file '{f}' is modified by both "
                      f"{seen_files[f].name} and {p.name} -- overlapping scopes produce "
                      "duplicate hunks; the merged patch will likely fail to apply.")
            else:
                seen_files[f] = p
    print(f"  merged {len(parts)} patch(es) for {instance_id}")
    return {KEY_INSTANCE_ID: instance_id, KEY_MODEL_PATCH: merged, KEY_PREFIX: prefix}


def write_patches_json(entries, out_path):
    """Write the JSON LIST (not JSONL) consumed by swe_bench_pro_eval.py --patch_path."""
    out_path.write_text(json.dumps(entries, indent=2))
    return out_path


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["build", "merge"], default="build")
    ap.add_argument("--input", default="sampled_pro", help="Folder of sampled instances (build mode)")
    ap.add_argument("--output", default="multiagent_pro_out", help="Output folder")
    ap.add_argument("--instances", nargs="*", help="Restrict to these instance ids")
    ap.add_argument("--distractors", type=int, default=3, help="Distractor siblings per agent (0 = pure oracle)")
    ap.add_argument("--distractor-source", choices=["docker", "github", "oracle"], default="docker",
                    help="How to enumerate sibling files: docker (offline, via the Pro image) "
                         "[default], github (contents API), or oracle (none)")
    ap.add_argument("--dockerhub_username", default="jefzda",
                    help="Docker Hub user for the Pro image (docker distractor source)")
    ap.add_argument("--include-requirements", action="store_true",
                    help="Also route the Pro `requirements` field into each agent's local slice")
    ap.add_argument("--include-interface", action="store_true",
                    help="Emit shared/coordination.md from the Pro `interface` field (the contract)")
    ap.add_argument("--emit-gold", action="store_true",
                    help="Also write each agent's gold.patch (oracle solution) for grade sanity-checks")
    ap.add_argument("--prefix", default="multiagent", help="Prefix namespacing eval output (merge mode)")
    args = ap.parse_args()

    out_dir = Path(args.output)

    if args.mode == "build":
        in_dir = Path(args.input)
        metas = sorted(in_dir.glob("*/metadata.json"))
        if args.instances:
            metas = [m for m in metas if m.parent.name in set(args.instances)]
        if not metas:
            raise SystemExit(f"No metadata.json found under {in_dir}/")
        print(f"Building multi-agent specs for {len(metas)} instance(s) -> {out_dir}/\n")
        for m in metas:
            meta = json.loads(m.read_text())
            spec = build_instance(meta, out_dir, args.distractors,
                                  include_requirements=args.include_requirements,
                                  include_interface=args.include_interface,
                                  emit_gold=args.emit_gold,
                                  distractor_source=args.distractor_source,
                                  dockerhub_username=args.dockerhub_username)
            tag = "N=1 (degenerate)" if spec["degenerate"] else f"N={spec['num_agents']}"
            contract = "yes" if spec["shared_contract"] else "no"
            print(f"  {spec[KEY_INSTANCE_ID]:<70} {tag:<16} contract={contract}")
        print(f"\nDone. Specs under {out_dir}/")
    else:
        targets = [out_dir / i for i in args.instances] if args.instances else \
            [p for p in out_dir.iterdir() if p.is_dir()]
        print(f"Merging agent patches for {len(targets)} instance(s)\n")
        entries = [merge_instance(t, prefix=args.prefix) for t in targets]
        out = write_patches_json(entries, out_dir / "patches.json")
        print(f"\nWrote {len(entries)} prediction(s) -> {out}")


if __name__ == "__main__":
    main()
