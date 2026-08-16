"""Optional coordination gate for scoped_submit (enabled by the SUBMIT_GATE env var, wired
from `gen_solver_config.py --submit-gate`; OFF by default).

Both checks are pure REFUSALS: the gate never calls a comm tool on the agent's behalf — it
blocks the submission and tells the model exactly which tool to run itself, so comm-tool
usage remains the model's own decision/action.

  1. Read-gate  — the agent must have checked the board at least ONCE, ever: `read_messages`
     writes a per-agent cursor file next to the board (comm/lib/board.py mark_read), and this
     gate only asks whether that file exists. Deliberately not "has read the CURRENT board":
     an earlier version compared a content hash of the whole board, which the agent's OWN
     send_message/publish_interface silently invalidated (they mutate the board and never
     mark_read), so publishing an interface forced a redundant re-read before every submit.
     Reading an empty board counts -- the point is that the agent looked, not what it found.
  2. Publish-check — if the agent's edits DELETE a public def/class (present at HEAD =
     base_commit, absent in the worktree, name not starting with "_"), it must first have
     posted a board message naming that symbol (publish_interface / send_message). Targets
     the observed cross-module contract breaks (deleted `HostState`, dangling `_is_fqcn`).

Exit status: 0 = submission may proceed; 1 = blocked (message already printed to stdout,
which is the model-visible tool observation). Any internal error fails OPEN (exit 0) — the
gate must never be able to strand an agent that cannot satisfy it through no fault of its
own. The marker PATH formula is intentionally duplicated with comm/lib/board.py: the two tool
bundles are deliberately self-contained (precedent: the COMM_BOARD default path).
"""
# Tool bins run on the Pro images' Python 3.9 -- keep annotations deferred (PEP 563).
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path


def board_path() -> Path:
    return Path(os.environ.get("COMM_BOARD", "/root/comm/board.json"))


def agent_id() -> str:
    return os.environ.get("AGENT_ID", "agent")


def _load_board() -> list:
    try:
        data = json.loads(board_path().read_text())
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def check_read_gate(msgs: list) -> str | None:
    """Blocked until the agent has run `read_messages` in the CURRENT round.

    Round-scoped, not once-ever: an agent that finished early would otherwise submit straight
    past a board holding a peer's question for it (observed -- the definer re-submitted in one
    step for two rounds while two peers sat blocked asking for its enum names). Still NOT a
    content comparison, so the agent's own send_message/publish_interface can never re-block
    its submission the way the old board-hash gate did -- reading once per round is enough.

    Falls back to read-once-ever when the host writes no `.round` file (offline tooling, gold
    mode). Mirrors comm/lib/board.py's path formulas; the two bundles are deliberately
    self-contained, so those formulas live in both files."""
    comm = board_path().parent
    try:
        cur = (comm / ".round").read_text().strip()
    except Exception:
        cur = ""
    if cur:
        try:
            seen = (comm / f".read_round_{agent_id()}").read_text().strip()
        except Exception:
            seen = ""
        if seen == cur:
            return None
        return (
            "SUBMISSION BLOCKED (coordination gate): you have not read the message board in "
            f"this round (round {cur}).\n"
            "Run `read_messages` now -- a peer may be blocked waiting on an answer only you "
            "can give -- then run `scoped_submit` again."
        )
    if (comm / f".read_{agent_id()}").exists():
        return None
    return (
        "SUBMISSION BLOCKED (coordination gate): you have not checked the message board yet.\n"
        "Run `read_messages`, act on anything relevant, then run `scoped_submit` again."
    )


def _public_symbols(source: str) -> set:
    """All def/class names in `source` (module- and class-level) not starting with '_'."""
    names = set()
    try:
        tree = ast.parse(source)
    except Exception:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
    return names


def check_publish_gate(msgs: list) -> str | None:
    root = os.environ.get("REPO_ROOT") or os.environ.get("ROOT") or "/app"
    try:
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=60,
        ).stdout.splitlines()
    except Exception:
        return None                                   # fail open
    removed = set()
    for f in changed:
        if not f.endswith(".py"):
            continue
        new_path = Path(root) / f
        if not new_path.exists():
            continue                                  # whole-file deletion: out of gate scope
        try:
            old_src = subprocess.run(
                ["git", "show", f"HEAD:{f}"],
                cwd=root, capture_output=True, text=True, timeout=60,
            ).stdout
            new_src = new_path.read_text(errors="replace")
        except Exception:
            continue
        removed |= _public_symbols(old_src) - _public_symbols(new_src)
    if not removed:
        return None

    me = agent_id()
    announced = " ".join(
        f"{m.get('signature', '')} {m.get('text', '')}"
        for m in msgs if m.get("from") == me
    )
    silent = sorted(s for s in removed if s not in announced)
    if not silent:
        return None
    listing = "\n".join(
        f'  publish_interface "{s}" "<what replaces it / why it was removed>"'
        for s in silent
    )
    return (
        "SUBMISSION BLOCKED (coordination gate): your changes REMOVE public symbol(s) that "
        "peers (or their tests) may depend on, and you have not announced the removal on "
        f"the board: {', '.join(silent)}.\n"
        "Announce each one first, e.g.:\n" + listing + "\n"
        "then run `scoped_submit` again."
    )


def main() -> int:
    try:
        msgs = _load_board()
        for check in (check_read_gate, check_publish_gate):
            problem = check(msgs)
            if problem:
                print(problem)
                return 1
        return 0
    except Exception:
        return 0                                      # fail open: never strand the agent


if __name__ == "__main__":
    sys.exit(main())
