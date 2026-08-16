"""Shared helpers for the scoped_fs ACI bundle: per-agent file-scope enforcement.

This is the enforcement boundary of the multi-agent ACI. An agent may only read and write
the files in its scope; everything else is invisible. The allowlist and repo root are read
from shell env vars that the SWE-agent ToolHandler exports from `agent.tools.env_variables`:

  SCOPE_FILES   JSON array of repo-relative paths the agent owns (gold file + distractors)
  REPO_ROOT     repo checkout dir inside the container (Pro images use /app, not /testbed)

Deliberately self-contained: it does NOT import SWE-agent's own tool libs (registry /
windowed_file), which are absent in this fork's checkout. Every scoped_* bin funnels its
path argument(s) through `require_scope()` before touching the filesystem.
"""
# The Pro images ship Python 3.9.5 (tool bins run in-repo, not in our py3.11 swe-rex runtime
# layer) -- `str | None` annotations need this to defer evaluation (PEP 563), else importing
# this module raises `TypeError: unsupported operand type(s) for |` at def-time on 3.9/3.8.
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WINDOW = 100  # default file-view window (mirrors SWE-agent's ACI viewer)


def repo_root() -> Path:
    """The repo checkout dir. Prefer an explicit REPO_ROOT, then SWE-agent's exported
    ROOT, then the Pro image default /app."""
    return Path(os.environ.get("REPO_ROOT") or os.environ.get("ROOT") or "/app")


def _env_paths(var: str) -> list:
    """Parse a repo-relative path list from env var `var` (JSON array; falls back to an
    os.pathsep-separated list)."""
    raw = os.environ.get(var, "[]")
    try:
        vals = json.loads(raw)
        if isinstance(vals, list):
            return [str(v) for v in vals]
    except Exception:
        pass
    return [x for x in raw.split(os.pathsep) if x]


def scope_files() -> list:
    """The agent's allowlist (repo-relative paths) from SCOPE_FILES. In full mode this is
    just the agent's primary/assigned file (enforcement is by the deny_files() denylist)."""
    return _env_paths("SCOPE_FILES")


def scope_mode() -> str:
    """"allow" (default) = SCOPE_FILES is a strict allowlist; "full" = denylist: any in-repo
    path is editable except deny_files()."""
    return os.environ.get("SCOPE_MODE", "allow")


def deny_files() -> list:
    """In full mode, the repo-relative paths this agent may NOT touch (other agents' gold
    files). Empty in allow mode."""
    return _env_paths("SCOPE_DENY")


def _resolve(path: str) -> Path:
    p = Path(path)
    return (p if p.is_absolute() else repo_root() / p).resolve()


def _allowed() -> set:
    root = repo_root()
    return {str((root / f).resolve()) for f in scope_files()}


def _denied() -> set:
    root = repo_root()
    return {str((root / f).resolve()) for f in deny_files()}


def _within_repo(p: Path) -> bool:
    root = repo_root().resolve()
    return p == root or root in p.parents


def in_scope(path: str) -> bool:
    p = _resolve(path)
    if scope_mode() == "full":
        # Denylist: any path inside the repo is fair game except peers' gold files.
        return _within_repo(p) and str(p) not in _denied()
    return str(p) in _allowed()


def require_scope(path: str) -> Path:
    """Return the absolute path if it is in scope; otherwise print a denial and exit
    non-zero (the model sees this as the tool observation)."""
    if not in_scope(path):
        if scope_mode() == "full":
            p = _resolve(path)
            if not _within_repo(p):
                print(f"DENIED: '{path}' is outside the repository — you may only edit "
                      "files inside the repo.")
            else:
                print(f"DENIED: '{path}' is owned by another agent — you may edit any "
                      "other file, but not this one.")
                print("Files owned by peers (off-limits to you):")
                for f in sorted(deny_files()):
                    print(f"  {f}")
                print("To have one of these changed, coordinate with send_message / "
                      "read_messages.")
        else:
            print(f"DENIED: '{path}' is outside your file scope — you cannot read or edit it.")
            print("Your scope (the only files you may touch):")
            for f in sorted(scope_files()):
                print(f"  {f}")
            print("To use anything outside your scope (e.g. an interface another agent "
                  "owns), coordinate with send_message / read_messages.")
        sys.exit(1)
    return _resolve(path)


def rel(path) -> str:
    try:
        return str(Path(path).resolve().relative_to(repo_root()))
    except Exception:
        return str(path)


def check_syntax(path: Path, text: str) -> str | None:
    """For .py files, return a message describing the SyntaxError in `text`, or None if it
    parses cleanly (or the file isn't Python). Stdlib-only (compile()), not flake8: the goal
    is catching edits that make the file fail to import at all -- e.g. a `def` spliced into
    the middle of a try/except block (IndentationError) -- not style/lint nits.
    """
    if path.suffix != ".py":
        return None
    try:
        compile(text, str(path), "exec")
    except SyntaxError as e:
        pointer = ""
        if e.text:
            pointer = "\n" + e.text.rstrip("\n") + "\n" + " " * max(0, (e.offset or 1) - 1) + "^"
        return f"{type(e).__name__} at line {e.lineno}: {e.msg}{pointer}"
    return None
