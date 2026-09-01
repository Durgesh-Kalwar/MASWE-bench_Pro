#!/usr/bin/env python
"""Tag each multi-agent Pro instance with a dependency graph BETWEEN agent slices.

Following the def-use approach of commit-untangling work (ClusterChanges, SmartCommit):
each agent's slice of the gold patch is analyzed for the definitions it INTRODUCES
(DEFS_NEW), the existing definitions it MODIFIES (DEFS_MOD), and the names its ADDED
lines USE. A directed edge consumer -> definer is drawn cross-agent when:

  DEF-USE             agent j's added lines use a name agent i's slice introduces.
  USE-USE-ON-CHANGED  agent j's added lines use a name agent i's slice modifies.

An instance whose graph has >= 1 cross-agent edge is labeled "coupled"; otherwise
"decomposable". Results are written ADDITIVELY as spec["coupling"] in each built
instance's spec.json (existing keys untouched); ambiguous name matches are logged to a
review file instead of silently linked.

Method (per agent slice)
------------------------
1. Fetch the PRE-patch content of the agent's gold file (docker `git show` inside the
   Pro image when available, else GitHub raw at base_commit; cached on disk so reruns
   are offline). Apply the slice with `git apply` to obtain the POST-patch file.
2. ast-parse both; a "definition" is a module/class-level def / class / attribute
   assignment (enum members and `name = str.isidentifier`-style module assigns count),
   qualified as Class.member. DEFS_NEW = post defs - pre defs. DEFS_MOD = defs in both
   whose pre span intersects the slice's removed lines or whose post span intersects
   its added lines.
3. USES = Name(Load)/Attribute/imported names on the slice's ADDED lines in the post
   AST (class bases and call targets are covered by the Name/Attribute walk).
   Attribute uses are recorded as (receiver_hint, attr_name).
4. Matching (disambiguation): an Attribute use whose receiver names a class defined by
   exactly one agent matches that class's member directly; otherwise a bare / attr name
   matches only if it is defined exactly ONCE across all agents' files (pre+post) --
   except that when the extra candidates are DELETED pre-patch defs and exactly one
   agent still defines the name post-patch, the use resolves to that live definition
   (the moved-symbol pattern: `init` moved from log.py to qtlog.py). A name the
   consumer's POST-patch file defines resolves locally (no edge). Remaining
   multi-definer names are appended to the review file, never silently linked.

Validation (--validate, OFF by default -- it costs container runs)
------------------------------------------------------------------
Leave-one-out grading through the UNMODIFIED Pro evaluator: one patches.json holding
the full gold merge plus N variants each missing one agent's slice (same instance_id,
distinct `prefix` -> distinct {prefix}_output.json), fed to swe_bench_pro_eval.py once.
F_i = required tests that pass with the full gold patch but fail without slice i.
Non-empty F_i ∩ F_j (i != j) is empirical evidence that agents i and j are coupled;
the report compares these empirical pairs against the static edges.

Usage
-----
    python multiagent_pro/metrics/tag_coupling.py                       # all built instances
    python multiagent_pro/metrics/tag_coupling.py --instances <id> ...
    python multiagent_pro/metrics/tag_coupling.py --pre-source github   # skip docker
    python multiagent_pro/metrics/tag_coupling.py --validate            # + leave-one-out runs

Creates/updates (data only, no code touched):
    multiagent_pro_out/<id>/spec.json            -- additive "coupling" key
    multiagent_pro_out/<id>/coupling.json        -- only if the instance has no spec.json
    multiagent_pro_out/<id>/.coupling_cache/     -- cached pre/post file contents
    multiagent_pro_out/coupling_review.jsonl     -- ambiguous matches for human review
    multiagent_pro_out/coupling_summary.json     -- cross-instance summary
    multiagent_pro_out/coupling_validation/      -- --validate eval artifacts
"""

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from ast import literal_eval
from pathlib import Path

# REUSE the builder's gold-patch decomposition + text/noise/image helpers rather than
# reimplementing them (they define what an "agent slice" is in the first place).
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))            # multiagent_pro/
sys.path.insert(0, str(_HERE.parent.parent.parent / "helper_code"))
from build_multiagent_pro import (  # noqa: E402
    KEY_INSTANCE_ID,
    _NOISE,
    decode_text,
    split_gold_by_file,
)

try:
    from image_uri import get_dockerhub_image_uri
except Exception:  # pragma: no cover - only the docker pre-source needs it
    get_dockerhub_image_uri = None

from unidiff import PatchSet  # noqa: E402

EDGE_DEF_USE = "DEF-USE"
EDGE_USE_USE = "USE-USE-ON-CHANGED"


# --------------------------------------------------------------------------- #
# Pre-patch file content (docker -> github raw -> cache), post via `git apply`
# --------------------------------------------------------------------------- #
def _cache_path(cache_dir, rel_path, side):
    safe = rel_path.replace("/", "__")
    return cache_dir / f"{side}__{safe}"


def fetch_pre_docker(image, base_commit, paths):
    """`git show base_commit:path` inside the instance's Pro image (offline, no token).
    One container; each file is base64-wrapped so content can never collide with the
    sentinel lines. Returns {path: text} for the files that exist; {} on any failure."""
    if not image or not paths:
        return {}
    script = 'REPO=$(git rev-parse --show-toplevel 2>/dev/null); [ -z "$REPO" ] && REPO=/testbed; '
    script += " ; ".join(
        f'echo "@@FILE {p}@@"; git -C "$REPO" show {base_commit}:"{p}" 2>/dev/null | base64; echo "@@END@@"'
        for p in paths
    )
    cmd = ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except Exception:
        return {}
    if not proc.stdout:
        return {}
    out, cur, buf = {}, None, []
    for line in proc.stdout.splitlines():
        if line.startswith("@@FILE ") and line.endswith("@@"):
            cur, buf = line[len("@@FILE "):-2], []
        elif line == "@@END@@" and cur is not None:
            if buf:
                import base64
                try:
                    out[cur] = base64.b64decode("".join(buf)).decode("utf-8", "replace")
                except Exception:
                    pass
            cur = None
        elif cur is not None:
            buf.append(line.strip())
    return out


def fetch_pre_github(repo, base_commit, path):
    """GitHub raw fallback (needs network, no token). Returns text or None."""
    url = f"https://raw.githubusercontent.com/{repo}/{base_commit}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def get_pre_contents(meta, gold_files, cache_dir, pre_source, dockerhub_username, notes):
    """{path: pre_text} for every gold file ("" for files the patch creates). 
    We get what the file was before anything was modified or added. 
    Chain: on-disk cache -> docker image -> github raw. Every fetch is cached."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    new_files = set()
    for pf in PatchSet(meta["patch"]):
        if pf.is_added_file:
            new_files.add(pf.path)

    result, missing = {}, []
    for p in gold_files:
        if p in new_files:
            result[p] = ""
            continue
        cp = _cache_path(cache_dir, p, "pre") # cache path should exist for each file from which we extract the pre-version after running the script once. coupling.cache for each instance is created
        if cp.exists():
            result[p] = cp.read_text()
        else:
            missing.append(p) # else (before first run), we have to extract from git/docker

    if missing and pre_source in ("auto", "docker"):
        image = None
        if get_dockerhub_image_uri is not None:
            try:
                image = get_dockerhub_image_uri(meta[KEY_INSTANCE_ID], dockerhub_username, meta["repo"])
            except Exception:
                image = None
        fetched = fetch_pre_docker(image, meta["base_commit"], missing)
        for p, text in fetched.items():
            _cache_path(cache_dir, p, "pre").write_text(text)
            result[p] = text
        missing = [p for p in missing if p not in result]
        if fetched:
            notes.append(f"pre-patch content for {len(fetched)} file(s) from docker image")

    # most of the instances are from github.
    if missing and pre_source in ("auto", "github"):
        got = 0
        for p in list(missing):
            # extract from base_commit which occurs right before the gold patch commit for Pro instances
            text = fetch_pre_github(meta["repo"], meta["base_commit"], p)
            if text is not None:
                _cache_path(cache_dir, p, "pre").write_text(text)
                result[p] = text
                missing.remove(p)
                got += 1
        if got:
            notes.append(f"pre-patch content for {got} file(s) from GitHub raw (docker unavailable)")

    for p in missing:
        notes.append(f"UNRESOLVED pre-patch content for {p}; agent analyzed as isolated")
    #from this, we get the contents of the files that gold patch changed, the original (pre-commit) contents
    return result


def apply_slice(pre_text, slice_diff, rel_path):
    """Apply one agent's file-slice with `git apply` in a scratch dir -> post text.
    Returns None (and lets the caller log it) if the slice does not apply."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if pre_text:
            target.write_text(pre_text)
        diff_file = root / "slice.diff"
        text = slice_diff if slice_diff.endswith("\n") else slice_diff + "\n"
        diff_file.write_text(text)
        proc = subprocess.run(
            ["git", "apply", "--unsafe-paths", str(diff_file)],
            cwd=root, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        return target.read_text() if target.exists() else ""  # "" = file deleted


# --------------------------------------------------------------------------- #
# AST: definitions and uses
# --------------------------------------------------------------------------- #
def collect_defs(src):
    """{qualname: (kind, start_line, end_line)} for module/class-level definitions:
    def / async def / class, class attributes (incl. enum members), and module-level
    NAME = ... assigns (catches `is_python_identifier = str.isidentifier`). Descends
    through Try/If/With/For/While at module/class level (py2-compat try/except defs are
    real module-level definitions) but NOT into function bodies (locals aren't part of
    any cross-file surface). Returns {} if the source doesn't parse."""
    # we get classes, attributes of classes and definitions within them
    try:
        tree = ast.parse(src or "")
    except SyntaxError:
        return None  # caller logs and falls back to isolated

    defs = {}

    def visit_block(body, stack, in_class):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = ".".join(stack + [node.name])
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                defs[q] = ("def", start, node.end_lineno)
            elif isinstance(node, ast.ClassDef):
                q = ".".join(stack + [node.name])
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                defs[q] = ("class", start, node.end_lineno)
                visit_block(node.body, stack + [node.name], True)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        q = ".".join(stack + [t.id])
                        kind = "attr" if in_class else "assign"
                        defs[q] = (kind, node.lineno, node.end_lineno)
            elif isinstance(node, (ast.Try, ast.If, ast.With, ast.For, ast.While)):
                for field in ("body", "orelse", "finalbody"):
                    visit_block(getattr(node, field, []) or [], stack, in_class)
                for h in getattr(node, "handlers", []) or []:
                    visit_block(h.body, stack, in_class)

    visit_block(tree.body, [], False)
    return defs


def slice_line_sets(slice_diff):
    """(added_target_lines, removed_source_lines) line-number sets for one file slice."""
    added, removed = set(), set()
    for pf in PatchSet(slice_diff):
        for hunk in pf:
            for line in hunk:
                if line.is_added and line.target_line_no:
                    added.add(line.target_line_no)
                elif line.is_removed and line.source_line_no:
                    removed.add(line.source_line_no)
    return added, removed


def collect_uses(post_src, added_lines):
    """Names USED on the slice's added lines, from the post-patch AST.
    Returns a list of (receiver_hint_or_None, name). Covers Name(Load), Attribute
    (recorded as (receiver_hint, attr)), and import / from-import names; class bases
    and call targets are Name/Attribute nodes and need no special casing."""
    if not added_lines:
        return []
    try:
        tree = ast.parse(post_src or "")
    except SyntaxError:
        return None

    def on_added(node):
        end = getattr(node, "end_lineno", None) or node.lineno
        return any(ln in added_lines for ln in range(node.lineno, end + 1))

    uses = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.lineno in added_lines and node.id not in _NOISE:
                uses.append((None, node.id))
        elif isinstance(node, ast.Attribute):
            if node.lineno in added_lines and node.attr not in _NOISE:
                recv = node.value.id if isinstance(node.value, ast.Name) else None
                uses.append((recv, node.attr))
        elif isinstance(node, ast.Call) and on_added(node):
            # A multi-line call where only an ARGUMENT line was added (e.g. threading a
            # new kwarg into `fetch_url(...)`): the callee Name sits on an unchanged
            # line, but the slice still participates in that def-use relation.
            f = node.func
            if isinstance(f, ast.Name) and f.id not in _NOISE:
                uses.append((None, f.id))
            elif isinstance(f, ast.Attribute) and f.attr not in _NOISE:
                recv = f.value.id if isinstance(f.value, ast.Name) else None
                uses.append((recv, f.attr))
        elif isinstance(node, (ast.Import, ast.ImportFrom)) and on_added(node):
            for alias in node.names:
                name = alias.name.split(".")[-1]
                if name not in _NOISE and name != "*":
                    uses.append((None, name))
    return uses


# --------------------------------------------------------------------------- #
# Per-instance analysis
# --------------------------------------------------------------------------- #
def analyze_agent(agent_id, rel_path, slice_diff, pre_text, notes):
    """Compute {defs_pre, defs_post, defs_new, defs_mod, uses} for one agent slice.
    Non-Python files (changelog fragments, configs) carry no def-use surface for this
    analysis and are treated as isolated -- a documented judgment call."""
    blank = {"defs_pre": {}, "defs_post": {}, "defs_new": set(), "defs_mod": set(),
             "uses": [], "analyzed": False}
    # guards
    if not rel_path.endswith(".py"):
        notes.append(f"{agent_id}: non-Python file {rel_path} -> isolated (no AST def-use)")
        return blank
    if pre_text is None:
        return blank  # unresolved pre content, already logged

    # now we get the contents after the patch
    post_text = apply_slice(pre_text, slice_diff, rel_path)
    if post_text is None:
        notes.append(f"{agent_id}: slice failed to `git apply` onto fetched pre content -> isolated")
        return blank

    defs_pre = collect_defs(pre_text)
    defs_post = collect_defs(post_text)
    if defs_pre is None or defs_post is None:
        notes.append(f"{agent_id}: {rel_path} does not ast-parse (pre or post) -> isolated")
        return blank

    added, removed = slice_line_sets(slice_diff)
    defs_new = set(defs_post) - set(defs_pre)
    defs_mod = set()
    for q in set(defs_pre) & set(defs_post):
        _, ps, pe = defs_pre[q]
        _, ts, te = defs_post[q]
        if any(ln in removed for ln in range(ps, pe + 1)) or \
           any(ln in added for ln in range(ts, te + 1)):
            defs_mod.add(q)

    uses = collect_uses(post_text, added)
    if uses is None:
        notes.append(f"{agent_id}: post-patch {rel_path} unparseable for uses -> no outgoing edges")
        uses = []
    return {"defs_pre": defs_pre, "defs_post": defs_post, "defs_new": defs_new,
            "defs_mod": defs_mod, "uses": uses, "analyzed": True}


def _last(qualname):
    return qualname.rsplit(".", 1)[-1]


def build_edges(agents, analyses, instance_id, review_entries):
    """Directed cross-agent edges consumer -> definer with disambiguation.

    Matching order per use:
      1. Attribute use whose receiver names a class defined by exactly one agent ->
         match that class's member directly (preferred, receiver-scoped).
      1.5 Attribute use whose receiver names exactly one agent's gold-file MODULE stem
         (`qtlog.init` -> qtlog.py's `init`) -> resolve there conclusively, never
         falling back to bare-name matching.
      2. Bare/attr name -> match only if defined exactly once across ALL agents' files
         (pre + post), or if exactly one POST-patch (live) definition remains after
         dropping deleted pre-patch candidates (moved-symbol pattern). A name defined
         in the consumer's own POST-patch file resolves locally.
      3. Remaining multi-definer names -> review log, no edge.
    An edge is drawn only if the matched definition is in the definer's DEFS_NEW
    (DEF-USE) or DEFS_MOD (USE-USE-ON-CHANGED); a use of a definition the definer's
    slice does NOT touch is not a dependency on the change."""
    # Global indexes over pre+post defs of every agent.
    by_last = {}          # last component -> [(agent_id, qualname)]
    class_owner = {}      # class name -> set(agent_id) that define a class of that name
    stem_owner = {}       # gold-file stem -> set(agent_id); `qtlog.init` names MODULE qtlog
    for ag, an in zip(agents, analyses):
        alldefs = set(an["defs_pre"]) | set(an["defs_post"])
        for q in alldefs:
            by_last.setdefault(_last(q), []).append((ag["id"], q))
        for q, meta_ in list(an["defs_pre"].items()) + list(an["defs_post"].items()):
            if meta_[0] == "class":
                class_owner.setdefault(_last(q), set()).add(ag["id"])
        if ag["gold_file"].endswith(".py"):
            stem_owner.setdefault(Path(ag["gold_file"]).stem, set()).add(ag["id"])

    idx_of = {a["id"]: i for i, a in enumerate(agents)}
    edges, seen_amb = set(), set()
    for ag, an in zip(agents, analyses):
        # Local resolution consults POST defs only: uses are extracted from the
        # post-patch file, so a def the consumer's own slice DELETED must not shadow
        # a cross-file use of its moved replacement (e.g. log.py deletes `init` and
        # now calls qtlog.init -- pre-based shadowing silently dropped that edge).
        own_last = {_last(q) for q in an["defs_post"]}
        for recv, name in an["uses"]:
            # 1. receiver-scoped attribute match (preferred): the receiver names a class
            #    defined by exactly one agent AND that class defines the attr. If the
            #    class doesn't define it (e.g. inherited), fall through to the bare rule.
            if recv and recv in class_owner and len(class_owner[recv]) == 1:
                definer = next(iter(class_owner[recv]))
                d_an = analyses[[a["id"] for a in agents].index(definer)]
                member = next((q for q in (set(d_an["defs_pre"]) | set(d_an["defs_post"]))
                               if _last(q) == name and q.startswith(recv + ".")), None)
                if member is not None:
                    if definer != ag["id"]:
                        if member in d_an["defs_new"]:
                            edges.add((ag["id"], definer, EDGE_DEF_USE, member))
                        elif member in d_an["defs_mod"]:
                            edges.add((ag["id"], definer, EDGE_USE_USE, member))
                    continue

            # 1.5 module-receiver match: the receiver names exactly one agent's gold
            #     MODULE (file stem), e.g. `qtlog.init(args)` -> the def `init` in
            #     qtlog.py. Conclusive either way: an explicit module receiver must
            #     never fall back to bare-name matching (which local shadowing could
            #     wrongly suppress -- log.py keeping its own `init` while calling
            #     qtlog.init is still a cross-agent dependency).
            if recv and recv in stem_owner and len(stem_owner[recv]) == 1:
                definer = next(iter(stem_owner[recv]))
                if definer != ag["id"]:
                    d_an = analyses[[a["id"] for a in agents].index(definer)]
                    if name in d_an["defs_new"]:
                        edges.add((ag["id"], definer, EDGE_DEF_USE, name))
                    elif name in d_an["defs_mod"]:
                        edges.add((ag["id"], definer, EDGE_USE_USE, name))
                continue

            # 2. bare-name / unscoped-attr match: exactly-once rule
            if name in own_last:
                continue  # resolves locally in the consumer's own file
            cands = by_last.get(name, [])
            if not cands:
                continue
            if len(cands) > 1:
                # Moved-symbol resolution: if the extra candidates are DELETED pre-patch
                # defs and exactly ONE agent still defines the name post-patch, the use
                # can only refer to that live definition (a deleted def cannot be used).
                live = [(a, q) for a, q in cands
                        if q in analyses[idx_of[a]]["defs_post"]]
                if len(live) == 1:
                    cands = live
                elif not live:
                    continue  # every definition was deleted; nothing to depend on
            if len(cands) > 1:
                # defined more than once across the agents' files -> ambiguous: log, don't link
                key = (ag["id"], name)
                if key not in seen_amb:
                    seen_amb.add(key)
                    review_entries.append({
                        "instance_id": instance_id, "consumer": ag["id"],
                        "receiver_hint": recv, "name": name,
                        "candidates": [{"agent": a, "qualname": q} for a, q in cands],
                        "reason": "name defined more than once across agents' files (pre+post)",
                    })
                continue
            definer, qual = cands[0]
            d_an = analyses[[a["id"] for a in agents].index(definer)]
            if qual in d_an["defs_new"]:
                edges.add((ag["id"], definer, EDGE_DEF_USE, qual))
            elif qual in d_an["defs_mod"]:
                edges.add((ag["id"], definer, EDGE_USE_USE, qual))

    return sorted(edges)


def coupling_for_instance(meta, spec, cache_dir, pre_source, dockerhub_username, review_entries):
    """Build the "coupling" dict for one instance. Returns (coupling, notes)."""
    notes = []
    instance_id = meta[KEY_INSTANCE_ID]
    gold_by_file = split_gold_by_file(meta["patch"])

    # Agent identity comes from spec.json when built (ids must match agent_<k> dirs);
    # otherwise derive on the fly exactly like the builder (one agent per gold file,
    # patch order).
    if spec is not None:
        agents = [{"id": a["id"], "gold_file": a["gold_file"]} for a in spec["agents"]]
    else:
        agents = [{"id": f"agent_{i}", "gold_file": gf}
                  for i, gf in enumerate(gold_by_file, start=1)]

    pre = get_pre_contents(meta, [a["gold_file"] for a in agents], cache_dir,
                           pre_source, dockerhub_username, notes)

    analyses = []
    #for each agent given their id, the pre and the patch they have, get the analysis
    for ag in agents:
        slice_diff = gold_by_file.get(ag["gold_file"], "")
        analyses.append(analyze_agent(ag["id"], ag["gold_file"], slice_diff,
                                      pre.get(ag["gold_file"]), notes))

    edges = build_edges(agents, analyses, instance_id, review_entries)

    per_agent = {}
    for ag in agents:
        outd = sum(1 for e in edges if e[0] == ag["id"])
        ind = sum(1 for e in edges if e[1] == ag["id"])
        role = ("both" if ind and outd else "definer" if ind
                else "consumer" if outd else "isolated")
        per_agent[ag["id"]] = {"in_degree": ind, "out_degree": outd, "role": role}

    coupling = {
        "method": "static def-use over per-agent gold slices (ClusterChanges/SmartCommit-style)",
        "edges": [{"from": f, "to": t, "kind": k, "symbol": s} for f, t, k, s in edges],
        "label": "coupled" if edges else "decomposable",
        "per_agent": per_agent,
        "notes": notes,
        "per_agent_defs": {
            ag["id"]: {"defs_new": sorted(an["defs_new"]), "defs_mod": sorted(an["defs_mod"])}
            for ag, an in zip(agents, analyses)
        },
    }
    return coupling, notes


_ROLE_FILL = {"definer": "#c8e6c9", "consumer": "#bbdefb",
              "both": "#e1bee7", "isolated": "#eeeeee"}


def render_graph_svg(coupling, gold_files):
    """Self-contained SVG digraph (circle layout) — viewable directly in VS Code and
    embeddable in markdown preview with no extensions. Nodes are colored by role;
    solid arrows = DEF-USE, dashed = USE-USE-ON-CHANGED. EVERY edge is drawn and
    labeled with its own symbol: parallel edges between the same pair fan out as
    separately-curved arrows instead of being collapsed."""
    import math
    aids = list(coupling["per_agent"].keys())
    grouped = {}                                    # (from, to) -> [edge, ...]
    for e in coupling["edges"]:
        grouped.setdefault((e["from"], e["to"]), []).append(e)
    max_k = max((len(es) for es in grouped.values()), default=1)

    # Column layout by role -- consumers left, definers right, both middle, isolated
    # along the bottom -- so edge fans run left-to-right in parallel instead of
    # crossing each other (these graphs are usually stars around one definer).
    cols = {"consumer": [], "both": [], "definer": [], "isolated": []}
    for aid in aids:
        cols[coupling["per_agent"][aid]["role"]].append(aid)
    vspace = max(150, 26 * max_k + 90)              # room for the widest fan
    n_rows = max(len(cols["consumer"]), len(cols["both"]), len(cols["definer"]), 1)
    W = 1080 if cols["both"] else 900
    H = n_rows * vspace + 120 + (100 if cols["isolated"] else 0)
    pos = {}
    xs = {"consumer": 170, "both": W / 2, "definer": W - 170}
    for role in ("consumer", "both", "definer"):
        col = cols[role]
        top = (H - (100 if cols["isolated"] else 0)) / 2 - (len(col) - 1) * vspace / 2
        for i, aid in enumerate(col):
            pos[aid] = (xs[role], top + i * vspace)
    for i, aid in enumerate(cols["isolated"]):      # bottom row, spread horizontally
        step = W / (len(cols["isolated"]) + 1)
        pos[aid] = (step * (i + 1), H - 70)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11">',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
           'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           '<path d="M 0 0 L 10 5 L 0 10 z" fill="#444"/></marker></defs>',
           f'<rect width="{W}" height="{H}" fill="white"/>']
    for (f, t), es in grouped.items():
        (x1, y1), (x2, y2) = pos[f], pos[t]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1
        # shorten both ends so arrows start/stop at the node boxes, not their centers
        sx, sy = x1 + dx / d * 78, y1 + dy / d * 78
        ex, ey = x2 - dx / d * 78, y2 - dy / d * 78
        px, py = -dy / d, dx / d                    # unit perpendicular, for the fan
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        k = len(es)
        for i, e in enumerate(sorted(es, key=lambda e: e["symbol"])):
            off = 26 * (i - (k - 1) / 2)            # symmetric offsets around straight line
            cxq, cyq = mx + px * 2 * off, my + py * 2 * off   # Bezier passes at ~off
            dash = '' if e["kind"] == EDGE_DEF_USE else ' stroke-dasharray="6,4"'
            svg.append(f'<path d="M {sx:.0f} {sy:.0f} Q {cxq:.0f} {cyq:.0f} '
                       f'{ex:.0f} {ey:.0f}" fill="none" stroke="#444" '
                       f'stroke-width="1.5" marker-end="url(#arr)"{dash}/>')
            # Label staggered ALONG its own curve (each edge gets a different t), then
            # pushed a little to the curve's bulge side -- parallel labels no longer
            # pile up at the shared midpoint.
            t_ = 0.5 if k == 1 else 0.2 + 0.6 * i / (k - 1)
            bx = (1 - t_) ** 2 * sx + 2 * (1 - t_) * t_ * cxq + t_ ** 2 * ex
            by = (1 - t_) ** 2 * sy + 2 * (1 - t_) * t_ * cyq + t_ ** 2 * ey
            side = 1 if off >= 0 else -1
            svg.append(f'<text x="{bx + px * side * 8:.0f}" y="{by + py * side * 8 - 3:.0f}" '
                       f'text-anchor="middle" fill="#333" font-style="italic">'
                       f'{e["symbol"]}</text>')
    for aid, (x, y) in pos.items():
        role = coupling["per_agent"][aid]["role"]
        gf = Path(gold_files.get(aid, "")).name
        svg.append(f'<rect x="{x - 75:.0f}" y="{y - 30:.0f}" width="150" height="60" '
                   f'rx="10" fill="{_ROLE_FILL[role]}" stroke="#555"/>')
        svg.append(f'<text x="{x:.0f}" y="{y - 10:.0f}" text-anchor="middle" '
                   f'font-weight="bold">{aid}</text>')
        svg.append(f'<text x="{x:.0f}" y="{y + 6:.0f}" text-anchor="middle">{gf}</text>')
        svg.append(f'<text x="{x:.0f}" y="{y + 22:.0f}" text-anchor="middle" '
                   f'fill="#666" font-style="italic">{role}</text>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n"




# --------------------------------------------------------------------------- #
# Validation mode: leave-one-out grading through the unmodified Pro evaluator
# --------------------------------------------------------------------------- #
def required_tests(meta):
    f2p = literal_eval(meta["fail_to_pass"]) if isinstance(meta["fail_to_pass"], str) else meta["fail_to_pass"]
    p2p = literal_eval(meta["pass_to_pass"]) if isinstance(meta["pass_to_pass"], str) else meta["pass_to_pass"]
    return set(f2p) | set(p2p)


def _passed_tests(output_json_path):
    if not output_json_path.exists():
        return None
    try:
        data = json.loads(output_json_path.read_text())
        return {t["name"] for t in data["tests"] if t["status"] == "PASSED"}
    except Exception:
        return None


def validate_instances(targets, out_dir, raw_sample_path, scripts_dir,
                       dockerhub_username, num_workers, use_modal):
    """Grade the gold merge and each leave-one-out variant, then compare the empirical
    coupling pairs against the static edges. Returns {instance_id: validation_dict}."""
    val_dir = out_dir / "coupling_validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for meta, spec, coupling in targets:
        if spec is None or len(spec["agents"]) < 2:
            continue
        gold_by_file = split_gold_by_file(meta["patch"])
        slices = {a["id"]: gold_by_file.get(a["gold_file"], "") for a in spec["agents"]}

        def _merge(texts):
            return "".join(t if t.endswith("\n") else t + "\n" for t in texts if t)

        entries.append({KEY_INSTANCE_ID: meta[KEY_INSTANCE_ID],
                        "model_patch": _merge(slices.values()), "prefix": "coupval-full"})
        for aid in slices:
            entries.append({KEY_INSTANCE_ID: meta[KEY_INSTANCE_ID],
                            "model_patch": _merge(v for k, v in slices.items() if k != aid),
                            "prefix": f"coupval-wo-{aid}"})
    if not entries:
        print("--validate: no multi-agent instances to validate.")
        return {}

    patches_path = val_dir / "patches.json"
    patches_path.write_text(json.dumps(entries, indent=2))
    eval_out = val_dir / "eval_out"
    cmd = [sys.executable, str(_HERE.parent.parent.parent / "swe_bench_pro_eval.py"),
           f"--raw_sample_path={raw_sample_path}", f"--patch_path={patches_path}",
           f"--output_dir={eval_out}", f"--scripts_dir={scripts_dir}",
           f"--num_workers={num_workers}", f"--dockerhub_username={dockerhub_username}"]
    if not use_modal:
        cmd.append("--use_local_docker")
    print(f"--validate: running {len(entries)} grading job(s) via swe_bench_pro_eval.py "
          f"(cached {'{prefix}'}_output.json files are reused automatically)...")
    proc = subprocess.run(cmd, cwd=_HERE.parent.parent.parent)
    if proc.returncode != 0:
        print("--validate: evaluator exited non-zero; using whatever outputs exist.")

    results = {}
    for meta, spec, coupling in targets:
        if spec is None or len(spec["agents"]) < 2:
            continue
        iid = meta[KEY_INSTANCE_ID]
        req = required_tests(meta)
        base = _passed_tests(eval_out / iid / "coupval-full_output.json")
        if base is None:
            results[iid] = {"status": "no baseline output"}
            continue
        baseline_ok = req <= base
        broken = {}  # agent_id -> sorted list of required tests its removal breaks
        for a in spec["agents"]:
            aid = a["id"]
            wo = _passed_tests(eval_out / iid / f"coupval-wo-{aid}_output.json")
            if wo is None:
                broken[aid] = None
                continue
            broken[aid] = sorted((req & base) - wo)

        emp_pairs = {}
        aids = [a["id"] for a in spec["agents"]]
        for i, ai in enumerate(aids):
            for aj in aids[i + 1:]:
                if broken.get(ai) and broken.get(aj):
                    shared = sorted(set(broken[ai]) & set(broken[aj]))
                    if shared:
                        emp_pairs[f"{ai}<->{aj}"] = shared

        static_pairs = {tuple(sorted((e["from"], e["to"]))) for e in coupling["edges"]}
        empirical = {tuple(k.split("<->")) for k in emp_pairs}
        results[iid] = {
            "status": "ok",
            "baseline_all_required_pass": baseline_ok,
            "tests_broken_by_removing": broken,
            "empirical_coupled_pairs": emp_pairs,
            "agreement": {
                "static_and_empirical": sorted("<->".join(p) for p in static_pairs & empirical),
                "static_only": sorted("<->".join(p) for p in static_pairs - empirical),
                "empirical_only": sorted("<->".join(p) for p in empirical - static_pairs),
            },
        }
    return results


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="sampled_pro", help="Folder of sampled instances (metadata.json)")
    ap.add_argument("--output", default="multiagent_pro_out", help="Built-instance folder (spec.json)")
    ap.add_argument("--instances", nargs="*", help="Restrict to these instance ids")
    ap.add_argument("--pre-source", choices=["auto", "docker", "github"], default="auto",
                    help="Where to fetch pre-patch file content (auto = cache -> docker -> github)")
    ap.add_argument("--dockerhub_username", default="jefzda")
    ap.add_argument("--graphs-dir", default=None,
                    help="Also collect every instance's dependency-graph SVG into this "
                         "flat folder as <instance_id>.svg (pushable without the "
                         "per-instance data/caches)")
    ap.add_argument("--validate", action="store_true",
                    help="ALSO grade gold with one agent slice removed at a time through the "
                         "unmodified Pro evaluator and compare against the static edges. "
                         "OFF by default: costs (N+1) container runs per instance.")
    ap.add_argument("--use-modal", action="store_true",
                    help="--validate backend: Modal instead of local Docker")
    ap.add_argument("--num-workers", type=int, default=4, help="--validate eval parallelism")
    ap.add_argument("--raw-sample-path", default="sampled_pro/raw_sample.jsonl")
    ap.add_argument("--scripts-dir", default="run_scripts")
    args = ap.parse_args()

    in_dir, out_dir = Path(args.input), Path(args.output)
    metas = sorted(in_dir.glob("*/metadata.json"))
    if args.instances:
        metas = [m for m in metas if m.parent.name in set(args.instances)]
    if not metas:
        raise SystemExit(f"No metadata.json found under {in_dir}/")

    review_entries, targets, rows = [], [], []
    for m in metas:
        meta = json.loads(m.read_text())
        iid = meta[KEY_INSTANCE_ID]
        inst_dir = out_dir / iid
        spec_path = inst_dir / "spec.json"
        spec = json.loads(spec_path.read_text()) if spec_path.exists() else None
        cache_dir = inst_dir / ".coupling_cache"

        coupling, notes = coupling_for_instance(
            meta, spec, cache_dir, args.pre_source, args.dockerhub_username, review_entries)
        targets.append((meta, spec, coupling))

        # ADDITIVE write: spec.json keeps every existing key and gains "coupling".
        if spec is not None:
            spec["coupling"] = coupling
            spec_path.write_text(json.dumps(spec, indent=2))
            where = "spec.json"
        else:
            inst_dir.mkdir(parents=True, exist_ok=True)
            (inst_dir / "coupling.json").write_text(json.dumps(coupling, indent=2))
            where = "coupling.json (instance not built; no spec.json to extend)"

        # Human-viewable per-instance dependency graph (self-contained SVG).
        if spec is not None:
            gold_files = {a["id"]: a["gold_file"] for a in spec["agents"]}
        else:
            gold_files = {f"agent_{i}": gf
                          for i, gf in enumerate(split_gold_by_file(meta["patch"]), start=1)}
        svg = render_graph_svg(coupling, gold_files)
        (inst_dir / "coupling_graph.svg").write_text(svg)
        # PNG twin: VS Code (and most viewers) preview PNGs natively, while .svg files
        # open as XML source without an extension. Skipped silently if cairosvg is absent.
        png = None
        try:
            import cairosvg
            png = cairosvg.svg2png(bytestring=svg.encode(), scale=2.0)
            (inst_dir / "coupling_graph.png").write_bytes(png)
        except ImportError:
            pass
        if args.graphs_dir:
            gdir = Path(args.graphs_dir)
            gdir.mkdir(parents=True, exist_ok=True)
            (gdir / f"{iid}.svg").write_text(svg)
            if png is not None:
                (gdir / f"{iid}.png").write_bytes(png)

        n_agents = len(coupling["per_agent"])
        rows.append({
            "instance_id": iid, "num_agents": n_agents, "label": coupling["label"],
            "edges": len(coupling["edges"]),
            "def_use": sum(1 for e in coupling["edges"] if e["kind"] == EDGE_DEF_USE),
            "use_use_on_changed": sum(1 for e in coupling["edges"] if e["kind"] == EDGE_USE_USE),
        })
        print(f"\n== {iid}  (N={n_agents}, {coupling['label']}) -> {where}")
        for e in coupling["edges"]:
            print(f"   {e['from']} -> {e['to']}  [{e['kind']}]  {e['symbol']}")
        for aid, pa in coupling["per_agent"].items():
            print(f"   {aid}: in={pa['in_degree']} out={pa['out_degree']} role={pa['role']}")
        for n in notes:
            print(f"   note: {n}")

    if review_entries:
        review_path = out_dir / "coupling_review.jsonl"
        with review_path.open("a") as f:
            for e in review_entries:
                f.write(json.dumps(e) + "\n")
        print(f"\n{len(review_entries)} ambiguous match(es) logged to {review_path} (NOT linked)")

    validation = {}
    if args.validate:
        validation = validate_instances(targets, out_dir, args.raw_sample_path,
                                        args.scripts_dir, args.dockerhub_username,
                                        args.num_workers, args.use_modal)
        for meta, spec, coupling in targets:
            iid = meta[KEY_INSTANCE_ID]
            if iid not in validation:
                continue
            spec_path = out_dir / iid / "spec.json"
            if spec_path.exists():
                spec = json.loads(spec_path.read_text())
                spec["coupling"]["validation"] = validation[iid]
                spec_path.write_text(json.dumps(spec, indent=2))
            print(f"\n== validation {iid}: {json.dumps(validation[iid], indent=2)}")

    # Cross-instance summary table
    summary = {
        "instances": rows,
        "totals": {
            "coupled": sum(1 for r in rows if r["label"] == "coupled"),
            "decomposable": sum(1 for r in rows if r["label"] == "decomposable"),
            "edges_def_use": sum(r["def_use"] for r in rows),
            "edges_use_use_on_changed": sum(r["use_use_on_changed"] for r in rows),
        },
    }
    (out_dir / "coupling_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n| instance | N | label | edges | DEF-USE | USE-USE-ON-CHANGED |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print(f"| {r['instance_id'][:60]} | {r['num_agents']} | {r['label']} | "
              f"{r['edges']} | {r['def_use']} | {r['use_use_on_changed']} |")
    t = summary["totals"]
    print(f"\ncoupled: {t['coupled']}  decomposable: {t['decomposable']}  "
          f"DEF-USE: {t['edges_def_use']}  USE-USE-ON-CHANGED: {t['edges_use_use_on_changed']}")
    print(f"summary -> {out_dir / 'coupling_summary.json'}")


if __name__ == "__main__":
    main()
