#!/usr/bin/env python
"""Patch-text helpers shared by the analyses (no run data, no judgment).

added_lines(patch)      -> [(file, line)] for '+' lines, test files excluded by default
defined_names(patch)    -> {name: file} for def/class/CONSTANT introduced on added lines
split_args / balanced   -> small parsers for signatures and calls
final_signature(patch, name) -> params of `def name(...)` in the added lines
calls_of(patch, name)   -> [(file, kwargs, n_positional)] for calls to name( in the added lines
"""
import re
from collections import defaultdict
from pathlib import Path

TEST_RE = re.compile(r"(^|/)(tests?|testing)/|(^|/)test_[^/]+\.py$|_test\.py$|conftest\.py$")
EDIT_RE = re.compile(r"sed\s+-i|cat\s*>>?\s*(?!/tmp)|tee\s+(?!/tmp)|python3?\s+-\s*<<|python3?\s+-c\s+[\"'].{0,200}open\(.{0,80}['\"]w|git\s+apply|\bpatch\s+-p|>\s*(?!/tmp|/dev)\S+\.(py|yml|yaml|rst|txt|html|js|less|json)\b")
SUBMIT = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
STOP_NAMES = {"__init__", "main", "setUp", "tearDown", "run", "get", "set", "self", "cls", "args", "kwargs", "data", "name", "path", "value"}


# --------------------------------------------------------------------------- loading
def load(inst_dir):
    spec = json.loads((inst_dir / "spec.json").read_text())
    board = json.loads((inst_dir / "board.json").read_text())
    lens, k = [], 1
    while (inst_dir / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((inst_dir / f"board_after_round_{k}.json").read_text())))
        k += 1
    for i, m in enumerate(board):
        m["round"] = next((r + 1 for r, n in enumerate(lens) if i < n), len(lens) or None)
    comm = json.loads((inst_dir / "comm_stats.json").read_text()) if (inst_dir / "comm_stats.json").exists() else []
    cost = json.loads((inst_dir / "cost_stats.json").read_text()) if (inst_dir / "cost_stats.json").exists() else {}
    agents = {}
    for a in spec["agents"]:
        ad = inst_dir / a["id"]
        steps = []
        for rf in sorted(ad.glob("traj/round_*.json"), key=lambda p: int(p.stem.split("_")[1])):
            r = int(rf.stem.split("_")[1])
            for s in json.load(open(rf)):
                steps.append({"round": r, "step": s.get("step"), "thought": s.get("thought") or "",
                              "action": s.get("action") or "", "obs": s.get("observation") or ""})
        ctx = []
        cf = ad / "context" / "messages.jsonl"
        if cf.exists():
            for line in cf.read_text().splitlines():
                if line.strip():
                    c = json.loads(line)
                    txt = "\n".join(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])
                                    for m in c["messages"])
                    ctx.append({"round": c["round"], "step": c["step_in_round"], "text": txt})
        pf = inst_dir / f"{a['id']}.patch"
        agents[a["id"]] = {"gold": a["gold_file"], "steps": steps, "ctx": ctx,
                           "patch": pf.read_text() if pf.exists() else ""}
    return spec, board, comm, cost, agents, len(lens)


# --------------------------------------------------------------------------- patch analysis
def added_lines(patch, skip_tests=True):
    """[(file, line)] for '+' lines, excluding test files by default."""
    out, cur = [], None
    for line in patch.splitlines():
        m = re.match(r"^diff --git a/(\S+)", line)
        if m:
            cur = m.group(1)
            continue
        if cur and line.startswith("+") and not line.startswith("+++"):
            if skip_tests and TEST_RE.search(cur):
                continue
            out.append((cur, line[1:]))
    return out


def defined_names(patch):
    names = {}
    for f, l in added_lines(patch):
        m = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", l) or re.match(r"\s*class\s+(\w+)", l) \
            or re.match(r"([A-Z][A-Z0-9_]{3,})\s*=", l)
        if m and m.group(1) not in STOP_NAMES and not m.group(1).startswith("test_") and len(m.group(1)) >= 4:
            names.setdefault(m.group(1), f)
    return names


def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def balanced(lines, start_idx, open_at):
    """Join lines from start_idx until the paren opened at open_at closes."""
    buf, depth = "", 0
    for l in lines[start_idx:start_idx + 12]:
        for i, ch in enumerate(l if buf else l[open_at:]):
            buf += ch
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return buf
        buf += "\n"
    return buf


def final_signature(patch, name):
    """Parameters of `def name(...)` in the patch's added lines; None if not defined there."""
    lines = [l for _, l in added_lines(patch)]
    for i, l in enumerate(lines):
        m = re.match(r"\s*(?:async\s+)?def\s+" + re.escape(name) + r"\s*\(", l)
        if m:
            body = balanced(lines, i, m.end() - 1)
            inner = body[1:-1] if body.endswith(")") else body[1:]
            params, star, dstar = [], False, False
            for p in split_args(inner):
                p = p.split(":")[0].split("=")[0].strip()
                if p.startswith("**"):
                    dstar = True
                elif p.startswith("*"):
                    star = True
                elif p and p not in ("self", "cls"):
                    params.append(p)
            return {"params": params, "star": star, "dstar": dstar}
    return None


def calls_of(patch, name):
    """[(file, kwargs, n_positional)] for calls to `name(` in added lines (not the def)."""
    out = []
    by_file = defaultdict(list)
    for f, l in added_lines(patch):
        by_file[f].append(l)
    for f, lines in by_file.items():
        for i, l in enumerate(lines):
            for m in re.finditer(r"(?<!\w)" + re.escape(name) + r"\s*\(", l):   # obj.name( counts
                if re.search(r"\bdef\s+" + re.escape(name) + r"\s*\($", l[:m.end()]):
                    continue
                body = balanced(lines, i, m.end() - 1)
                inner = body[1:-1] if body.endswith(")") else body[1:]
                kw, pos = [], 0
                for a in split_args(inner):
                    if re.match(r"^\w+\s*=(?!=)", a):
                        kw.append(a.split("=")[0].strip())
                    elif a and not a.startswith("*"):
                        pos += 1
                out.append((f, kw, pos))
    return out


