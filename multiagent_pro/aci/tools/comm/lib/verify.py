"""Existence check for `publish_interface`: does the symbol an agent is announcing actually
exist in a file that agent owns?

Motivation (CHECKPOINT.md 9.5, "false attestation" -- the top-ranked defect class): on
b748edea run 7, agent_3's two edits were both refused by scoped's syntax guard, it gave up,
submitted an empty diff, and then announced across three rounds that `prepare_multipart` was
implemented. A peer relayed the signature onward, and four of five agents coordinated around
a function that does not exist. Adoption WORKING is what made it harmful.

Push delivery makes this strictly worse than it was: under the old pull design a peer could
simply never read a false claim, whereas now every peer is guaranteed to receive it. So the
check lands with the push harness rather than after it.

This is the mirror of scoped_fs/lib/submit_gate.py's delete-announcement check, and follows
the same rule: FAIL OPEN. Any error, any unparseable file, any non-Python scope -> allow the
publish. A guard that strands an agent through no fault of its own is worse than the defect
it prevents.

Tool bins run on the Pro images' Python 3.9 -- keep annotations deferred (PEP 563).
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

# `def foo(...)`, `async def foo(...)`, `class Foo(...)`, or a bare `foo(...)` / `foo`.
_SIG_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)"
    r"|^\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:\(|=|:|$)"
)


def symbol_name(signature: str) -> str | None:
    """The bare name an agent is claiming to have written. Returns None when the signature is
    too freeform to pin down a name -- which fails the check open, by design."""
    m = _SIG_RE.match(signature or "")
    if not m:
        return None
    name = m.group(1) or m.group(2)
    if not name:
        return None
    # "Class.method" -> the check should look for `method`, which is what a peer will call.
    return name.split(".")[-1]


def defined_symbols(source: str) -> set:
    """Every def/class name in `source` at ANY nesting depth, plus module-level assignment
    targets. Deliberately generous: the point is to catch symbols that exist NOWHERE, not to
    police where they live, and a false refusal costs an agent a whole round."""
    names = set()
    try:
        tree = ast.parse(source)
    except Exception:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _repo_root() -> str:
    return os.environ.get("REPO_ROOT") or os.environ.get("ROOT") or "/app"


def owned_python_files() -> list:
    """The .py files this agent could plausibly have written the symbol into: its declared
    scope plus everything it has actually touched. The union covers both scope modes -- an
    allowlist agent only edits SCOPE_FILES, but a scope_mode="full" agent may have written
    the symbol into any non-denied file, which only the git diff reveals."""
    root = Path(_repo_root())
    files = set()
    try:
        scope = json.loads(os.environ.get("SCOPE_FILES", "[]"))
        files |= {f for f in scope if isinstance(f, str)}
    except Exception:
        pass
    try:
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        ).stdout.splitlines()
        files |= set(changed)
    except Exception:
        pass
    return [f for f in sorted(files) if f.endswith(".py") and (root / f).exists()]


def missing(signature: str) -> str | None:
    """The symbol name if it is announced but absent from every file this agent owns;
    None if it is present, unidentifiable, or unverifiable (fail open)."""
    try:
        name = symbol_name(signature)
        if not name:
            return None                       # can't pin a name -> allow
        files = owned_python_files()
        if not files:
            return None                       # nothing Python in scope -> not our business
        root = Path(_repo_root())
        for f in files:
            try:
                src = (root / f).read_text(errors="replace")
            except Exception:
                continue
            if name in defined_symbols(src):
                return None
        return name
    except Exception:
        return None                           # fail open, always
