"""Shared helpers for the comm ACI bundle: the inter-agent message board (blackboard).

The board is a JSON list of messages persisted at COMM_BOARD inside the container. Each
agent reads/writes its own container-local copy; the host orchestrator owns the canonical
board and runs a strict ROUND BARRIER: every agent in a round is handed the identical
snapshot frozen at the round's start, and everything posted during the round is published
only once the round ends. So an agent reads peers' messages from PREVIOUS rounds only --
nothing it posts (and nothing a peer posts) becomes visible until the next round.

Reads are peer-only and incremental: `visible_to` excludes the agent's own messages, and a
per-agent read cursor (`.read_<AGENT_ID>`, see mark_read/unread) means read_messages shows
each peer message exactly once, ever -- not the whole board on every call.

Env vars exported via `agent.tools.env_variables`:

  AGENT_ID        this agent's id (e.g. agent_2)
  COMM_BOARD      path to the board JSON inside the container (default /root/comm/board.json)
  AGENTS_ROSTER   JSON array of {id, gold_file} for all peers (for list_agents)

Self-contained: no dependency on SWE-agent's tool libs.
"""
import hashlib
import json
import os
import time
from pathlib import Path


def agent_id() -> str:
    return os.environ.get("AGENT_ID", "agent")


def msg_digest(msg: dict) -> str:
    """Stable per-message identity for the read cursor. Content-based (not positional) so it
    survives the host rewriting board.json every round in a different JSON formatting."""
    return hashlib.sha256(json.dumps(msg, sort_keys=True).encode()).hexdigest()[:16]


def read_marker_path() -> Path:
    """Per-agent read cursor, kept beside the board. The host only ever rewrites board.json,
    so this file persists for the container's whole life (i.e. across every round). Its mere
    EXISTENCE is what the optional submit gate checks -- see scoped_fs/lib/submit_gate.py."""
    return board_path().parent / f".read_{agent_id()}"


def round_path() -> Path:
    """Current round number, written by the host at the start of every turn."""
    return board_path().parent / ".round"


def current_round() -> str:
    try:
        return round_path().read_text().strip()
    except Exception:
        return ""


def mark_round_read() -> None:
    """Record that this agent checked the board in the CURRENT round. The submit gate requires
    this every round (not just once ever): an agent that had already finished would otherwise
    submit straight through a board holding a peer's question addressed to it."""
    try:
        cur = current_round()
        if not cur:
            return                    # no round file (offline tooling) -> nothing to record
        p = board_path().parent / f".read_round_{agent_id()}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(cur)
    except Exception:
        pass


def _read_keys() -> set:
    try:
        data = json.loads(read_marker_path().read_text())
        return set(data.get("read", [])) if isinstance(data, dict) else set()
    except Exception:
        return set()


def unread(msgs: list) -> list:
    """The subset of `msgs` this agent has not been shown before."""
    seen = _read_keys()
    return [m for m in msgs if msg_digest(m) not in seen]


def mark_read(msgs: list) -> None:
    """Record `msgs` as delivered so they are never shown twice, and (as a side effect of the
    file existing at all) record that this agent has checked the board at least once. Called
    even when there is nothing new, so a read of an empty board still satisfies the submit
    gate. Best-effort -- a marker failure must never break read_messages."""
    try:
        p = read_marker_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        keys = _read_keys() | {msg_digest(m) for m in msgs}
        p.write_text(json.dumps({"read": sorted(keys)}, indent=2))
    except Exception:
        pass


def board_path() -> Path:
    return Path(os.environ.get("COMM_BOARD", "/root/comm/board.json"))


def load_board() -> list:
    p = board_path()
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_board(msgs: list) -> None:
    p = board_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(msgs, indent=2))


def append(msg: dict) -> None:
    msgs = load_board()
    msg.setdefault("ts", time.time())
    msg.setdefault("from", agent_id())
    msgs.append(msg)
    save_board(msgs)


def roster() -> list:
    try:
        data = json.loads(os.environ.get("AGENTS_ROSTER", "[]"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def visible_to(msg: dict, me: str) -> bool:
    """A message is visible to `me` if a PEER addressed it to me or broadcast it. An agent's
    own messages are deliberately excluded: re-showing them wastes context and (before the
    read cursor existed) made agents echo their own phrasing back onto the board."""
    return msg.get("from") != me and msg.get("to") in (me, "all")
