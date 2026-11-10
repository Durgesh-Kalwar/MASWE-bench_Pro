#!/usr/bin/env python
"""Shared loaders and string-matching helpers for the whiteboard analysis of one sealed run.

No model is called anywhere in this folder: every label is produced by the regular expressions
and set operations defined here and in fig1_agent_actions.py / fig2_message_analysis.py.

Inputs (all relative to this file):
  ..                              the run folder (instance_*/board.json, traj, patches, eval_out)
  ../../multiagent_pro_bench34_noreq   per-agent gold patches (<instance>/<agent>/gold.patch)
  base_files/<instance>.json      base-commit text of every owned / fixed file of the instance
"""
import json, re
from collections import defaultdict
from pathlib import Path

A = Path(__file__).resolve().parent
RUN = A.parent
REPO = RUN.parent
BENCH = REPO / "multiagent_pro_bench34_noreq"
BASE = A / "base_files"
OUT = A / "results"
ARM = RUN.name.replace("multiagent_pro_out_", "")

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
AGENT_ID = re.compile(r"\bagent_\d+\b")
COMM_TOOLS = r"(?:send_message|publish_interface|update_belief)"
EDIT_RE = re.compile(r"sed\s+-i|cat\s*>>?\s*(?!/tmp)|cat\s*<<.*?>\s*(?!/tmp)|tee\s+(?!/tmp)|python3?\s+-\s*<<|python3?\s+-c\s+[\"'].{0,200}open\(.{0,80}['\"]w|git\s+apply|\bpatch\s+-p|>\s*(?!/tmp|/dev)\S+\.(py|yml|yaml|rst|txt|html|js|less|json)\b|\.write_text\(|open\([^)]*['\"][wa]['\"]", re.S)
TRIVIAL = re.compile(r"^(import |from |return$|pass$|else:$|try:$|except.*:$|finally:$|[\]\)\}]+,?$|#.*|\"\"\"|'''|@\w+$)")

# Words that are ordinary English as well as identifiers. A plain lowercase word only counts as a
# gold term when it is NOT in this list; names with an underscore or an inner capital always count.
COMMON = set("""
self none true false return import from class with that this then else elif while for pass raise
except finally lambda yield async await print name names value values data type types path paths
file files line lines text test tests error errors list dict tuple string strings result results
default defaults config option options args kwargs item items key keys index count size length
update updates create delete remove insert append extend check checks parse parser load loads
save read write open close start stop init main run call calls make build send message messages
agent agents round rounds note notes todo only none must exact same done warning json html http
yaml null fixme info debug level user users request response status state states code module
modules function method object objects base common utils util helper helpers model models view
views core plugin plugins action actions task tasks host hosts handler handlers field fields
format output input source target context content contents entry entries record records query
search filter sort order group table column row rows page pages title label description version
change changes changed edit edits work works book books author authors need needs using used
uses does done have will should would could when where which what there their them they also
been being both each into more most other some such than these those very after before first
last next prev true false legacy future should means here still just like since until unless
""".split())


def codelike(t):
    """An identifier that cannot be mistaken for prose: snake_case, camelCase/PascalCase with an
    inner capital, or ALL_CAPS of 4+ characters."""
    core = t.strip("_")
    if len(core) < 4 or core.lower() in COMMON:
        return False
    return "_" in core or bool(re.search(r"[a-z][A-Z]", core)) or (core.isupper() and len(core) >= 4)


def plain_ok(t):
    return len(t) >= 5 and t.lower() not in COMMON and not t.isdigit()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def distinctive_lines(text):
    """Lines long and specific enough that an exact match is evidence of a copy."""
    out = set()
    for l in (text or "").splitlines():
        s = norm(l)
        if len(s) >= 24 and not TRIVIAL.match(s):
            out.add(s)
    return out


def added_lines(patch):
    """[(file, line)] for the '+' lines of a unified diff."""
    out, cur = [], None
    for line in (patch or "").splitlines():
        m = re.match(r"^diff --git a/(\S+)", line)
        if m:
            cur = m.group(1)
        elif cur and line.startswith("+") and not line.startswith("+++"):
            out.append((cur, line[1:]))
    return out


DEF_RE = re.compile(r"\s*(?:async\s+)?def\s+(\w+)\s*\(|\s*class\s+(\w+)|([A-Z][A-Z0-9_]{3,})\s*=(?!=)")


def defs_in(lines):
    names = set()
    for l in lines:
        m = DEF_RE.match(l)
        if m:
            n = m.group(1) or m.group(2) or m.group(3)
            if codelike(n) or plain_ok(n):
                names.add(n)
    return names


def gold_vocab(gold_patch, base_text):
    """(has, new_defs, owns) for one agent.
    has      = identifiers on the changed (+/-) lines of its gold patch, plus the def/class named in
               each hunk header ("has this in their gold patch", the whiteboard's wording);
    new_defs = def / class / CONSTANT names the gold patch introduces on '+' lines;
    owns     = new_defs + modified defs (hunk headers) + every def/class already in the agent's
               own file at the base commit (stricter: "this is defined in my file")."""
    has, hdr, plus = set(), set(), []
    for line in (gold_patch or "").splitlines():
        if line.startswith(("+++", "---", "diff ", "index ")):
            continue
        if line.startswith("@@"):
            m = re.search(r"@@[^@]*@@\s*.*?\b(?:def|class)\s+(\w+)", line)
            if m and (codelike(m.group(1)) or plain_ok(m.group(1))):
                hdr.add(m.group(1))
        elif line[:1] in "+-":
            if line[0] == "+":
                plus.append(line[1:])
            has |= {t for t in IDENT.findall(line[1:]) if codelike(t)}
    new_defs = defs_in(plus)
    owns = new_defs | hdr | defs_in((base_text or "").splitlines())
    return has | hdr | new_defs, new_defs, owns


def file_forms(path, all_paths):
    """Strings that name this file in prose: the full path, the shortest path suffix that is unique
    among the agents' files, and the dotted module path. Returned as (substring forms, word forms)."""
    parts = Path(path).parts
    k = 2 if Path(path).stem == "__init__" else 1
    while k < len(parts) and sum(1 for p in all_paths if Path(p).parts[-k:] == parts[-k:]) > 1:
        k += 1
    sub = {path, "/".join(parts[-k:])}
    words = set()
    if path.endswith(".py"):
        mod = re.sub(r"^(lib|src)/", "", path)[:-3].replace("/", ".")
        mod = re.sub(r"\.__init__$", "", mod)
        sub.add(mod)
        if mod.count(".") >= 1:
            sub.add(".".join(mod.split(".")[-2:]))
    stem = Path(path).stem
    if stem != "__init__" and (codelike(stem) or plain_ok(stem)) and \
            sum(1 for p in all_paths if Path(p).stem == stem) == 1:
        words.add(stem)
    return sub, words


def strip_comm_payload(action):
    """Remove the text handed to send_message / publish_interface / update_belief, so words inside
    a message ('rm', 'git reset', a peer's file name) are not read as shell commands."""
    return re.sub(COMM_TOOLS + r"\b.*?(?=(?:&&|\|\||;|\n)\s*(?:cd|git|echo|python3?|pytest|grep|sed|cat|ls|rm|nl|find|head|tail)\b|\Z)",
                  " COMM_TOOL ", action or "", flags=re.S)


def segments(action):
    """Shell command split on && || ; | and newlines; each segment with leading env assignments
    and `cd X` removed. Good enough to find the command word of each part."""
    out = []
    for seg in re.split(r"&&|\|\||;|\||\n", strip_comm_payload(action)):
        seg = seg.strip()
        seg = re.sub(r"^(?:\w+=\S+\s+)+", "", seg)
        seg = re.sub(r"^\(+\s*", "", seg)
        if seg:
            out.append(seg)
    return out


def gold_graph(inst):
    """Gold dependency edges consumer -> definer with the names that cross, same rules as
    multiagent_pro_out_p2p_sweep34/analysis/common/gold_dependencies.py::gold_graph."""
    d = BENCH / inst
    spec = json.loads((d / "spec.json").read_text())
    ids = [a["id"] for a in spec["agents"]]
    gold = {a: (d / a / "gold.patch").read_text() if (d / a / "gold.patch").exists() else "" for a in ids}
    gfile = {a["id"]: a["gold_file"] for a in spec["agents"]}
    STOP = {"__init__", "main", "setUp", "tearDown", "run", "get", "set", "self", "cls", "args", "kwargs", "data", "name", "path", "value"}
    defs = {}
    for a in ids:
        defs[a] = {}
        for _, l in added_lines(gold[a]):
            m = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", l) or re.match(r"\s*class\s+(\w+)", l) or re.match(r"([A-Z][A-Z0-9_]{3,})\s*=", l)
            if m and m.group(1) not in STOP and not m.group(1).startswith("test_") and len(m.group(1)) >= 4:
                defs[a].setdefault(m.group(1), "new")
        for m in re.finditer(r"^@@[^@]*@@\s*.*?\b(?:def|class)\s+(\w+)", gold[a], re.M):
            n = m.group(1)
            if n not in defs[a] and n not in ("__init__", "main", "setUp") and len(n) >= 4:
                defs[a][n] = "modified"
    kw_defs = {}
    for a in ids:
        added = "\n".join(l for _, l in added_lines(gold[a]))
        kw_defs[a] = set(re.findall(r"self\.([a-z_][a-z0-9_]{4,})\s*=\s*\1\b", added)) | \
            set(re.findall(r":kwarg\s+([a-z_][a-z0-9_]{4,})", added)) | \
            set(re.findall(r"\b([a-z_][a-z0-9_]{4,})\s*=\s*self\._fallback\(\s*\1\b", added))
    edges = {}
    for c in ids:
        added = "\n".join(l for _, l in added_lines(gold[c]))
        toks = set(re.findall(r"\w+", added))
        kw_used = set(re.findall(r"(?<![\w.])([a-z_][a-z0-9_]{4,})\s*=(?!=)\s*(?!dict\()[\w'\"\[]", added))
        for dd in ids:
            if dd == c:
                continue
            objs = [{"name": n, "kind": defs[dd][n], "forms": [n]} for n in defs[dd] if n in toks]
            if not objs:
                objs += [{"name": k, "kind": "keyword", "forms": [k]} for k in sorted(kw_defs[dd] & kw_used - kw_defs[c])]
            mod = re.sub(r"^lib/", "", gfile[dd]).replace(".py", "").replace("/", ".")
            if gfile[dd].endswith(".py") and re.search(r"(from|import)\s+" + re.escape(mod) + r"\b", added):
                objs.append({"name": Path(gfile[dd]).name, "kind": "module", "forms": [mod, Path(gfile[dd]).name]})
            if objs:
                edges[(c, dd)] = objs
    return edges


def names_in(text, forms):
    return any(re.search(r"\b" + re.escape(f) + r"\b", text) for f in forms)


def load(d):
    """Everything the two figure scripts need about one instance folder."""
    inst = d.name
    spec = json.loads((d / "spec.json").read_text())
    board = json.loads((d / "board.json").read_text())
    lens, k = [], 1
    while (d / f"board_after_round_{k}.json").exists():
        lens.append(len(json.loads((d / f"board_after_round_{k}.json").read_text())))
        k += 1
    ids = [a["id"] for a in spec["agents"]]
    for i, m in enumerate(board):
        m["idx"] = i
        m["round"] = next((r + 1 for r, n in enumerate(lens) if i < n), len(lens) or None)
        m["kind"] = "publication" if m.get("type") == "interface" else ("broadcast" if m.get("to") == "all" else "directed")
        m["body"] = (m.get("signature", "") + " " + m.get("text", "")).strip() if m["kind"] == "publication" else m.get("text", "")
        m["recipients"] = [m["to"]] if m["kind"] == "directed" else [a for a in ids if a != m["from"]]
    base = json.loads((BASE / f"{inst}.json").read_text()) if (BASE / f"{inst}.json").exists() else {}
    all_paths = [a["gold_file"] for a in spec["agents"]]
    owner = {a["gold_file"]: a["id"] for a in spec["agents"]}
    fixed_patch = (d / "fixed.patch").read_text() if (d / "fixed.patch").exists() else ""
    agents = {}
    for a in spec["agents"]:
        aid, ad = a["id"], d / a["id"]
        steps = []
        for rf in sorted(ad.glob("traj/round_*.json"), key=lambda p: int(p.stem.split("_")[1])):
            r = int(rf.stem.split("_")[1])
            for s in json.load(open(rf)):
                steps.append({"round": r, "step": s.get("step"), "thought": s.get("thought") or "",
                              "action": s.get("action") or "", "obs": s.get("observation") or ""})
        for g, s in enumerate(steps):
            s["g"] = g
        viol = []
        vf = ad / "scope_violations.jsonl"
        if vf.exists():
            viol = [json.loads(l) for l in vf.read_text().splitlines() if l.strip()]
        gp = BENCH / inst / aid / "gold.patch"
        gold = gp.read_text() if gp.exists() else ""
        pf = d / f"{aid}.patch"
        has, new_defs, owns = gold_vocab(gold, base.get(a["gold_file"]) or "")
        sub, words = file_forms(a["gold_file"], all_paths)
        agents[aid] = {"gold_file": a["gold_file"], "deny": a.get("deny") or [], "steps": steps,
                       "violations": viol, "gold": gold, "patch": pf.read_text() if pf.exists() else "",
                       "issue": (ad / "local_issue.md").read_text() if (ad / "local_issue.md").exists() else "",
                       "seal": json.loads((ad / "scope_seal.json").read_text()) if (ad / "scope_seal.json").exists() else {},
                       "has": has, "new_defs": new_defs, "owns": owns, "file_sub": sub, "file_words": words}
    res_f = RUN / "eval_out" / "eval_results.json"
    resolved = json.loads(res_f.read_text()).get(inst) if res_f.exists() else None
    return {"inst": inst, "spec": spec, "ids": ids, "board": board, "agents": agents, "base": base,
            "owner": owner, "fixed_patch": fixed_patch, "n_rounds": len(lens), "resolved": bool(resolved)}


def instances():
    return sorted(p for p in RUN.glob("instance_*") if (p / "spec.json").exists())


def short(inst):
    m = re.match(r"instance_(?:[^_]+__)?(.+?)-([0-9a-f]{8})", inst)
    return f"{m.group(1)}-{m.group(2)}" if m else inst[:40]


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "n/a"


# ------------------------------------------------------------------ truth checks (Figure 2, Acc)
def apply_patch(base_text, patch, path):
    """Final text of `path` after the agent's patch. Hunks are applied by their old line numbers;
    returns (text, exact) where exact is False if a hunk did not line up and the result is the
    base text with the added lines appended (enough for name and signature look-ups)."""
    lines = (base_text or "").splitlines()
    out, pos, cur, exact, hunks = [], 0, None, True, []
    for line in (patch or "").splitlines():
        m = re.match(r"^diff --git a/(\S+)", line)
        if m:
            cur = m.group(1)
            continue
        if cur != path:
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", line)
        if m:
            hunks.append([int(m.group(1)), []])
        elif hunks and line and line[0] in " +-" and not line.startswith(("+++ ", "--- ")):
            hunks[-1][1].append(line)
        elif hunks and line == "":
            hunks[-1][1].append(" ")
    for start, body in hunks:
        start = max(start - 1, 0)
        if start < pos:
            exact = False
            break
        out += lines[pos:start]
        pos = start
        for l in body:
            if l[0] == "+":
                out.append(l[1:])
            else:
                if pos >= len(lines) or lines[pos].rstrip() != l[1:].rstrip():
                    exact = False
                elif l[0] == " ":
                    out.append(lines[pos])
                pos += 1
    if not exact:
        return "\n".join(lines + [l for f, l in added_lines(patch) if f == path]), False
    return "\n".join(out + lines[pos:]), True


def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def balanced(text, open_at, limit=600):
    """Text between the parenthesis at open_at and its match (None if it does not close)."""
    depth = 0
    for i in range(open_at, min(len(text), open_at + limit)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
    return None


def parse_params(inner):
    params, dstar = [], False
    inner = re.sub(r"#[^\n]*", "", inner)      # `arg,  # type: str` comments inside a signature
    for p in split_args(inner):
        if p.startswith("**"):
            dstar = True
        elif p.startswith("*") or p in ("/", ""):
            continue
        else:
            p = p.split(":")[0].split("=")[0].strip()
            if p and p not in ("self", "cls"):
                params.append(p)
    return {"params": params, "dstar": dstar}


def def_signatures(code):
    """{name: [ {params, dstar}, ... ]} for every def in the code; a class name maps to the
    parameters of its __init__ (when it has one)."""
    sigs = {}
    for m in re.finditer(r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\(", code, re.M):
        inner = balanced(code, m.end() - 1)
        if inner is not None:
            sigs.setdefault(m.group(1), []).append(parse_params(inner))
    for m in re.finditer(r"^class\s+(\w+)", code, re.M):
        nxt = re.search(r"^class\s+\w+", code[m.end():], re.M)
        block = code[m.end(): m.end() + nxt.start()] if nxt else code[m.end():]
        mi = re.search(r"def\s+__init__\s*\(", block)
        if mi:
            inner = balanced(block, mi.end() - 1)
            if inner is not None:
                sigs.setdefault(m.group(1), []).append(parse_params(inner))
    return sigs
