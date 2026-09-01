"""Shared helpers for the comm ACI bundle: the inter-agent message board (blackboard).

The board is a JSON list of messages persisted at COMM_BOARD inside the container. Each
agent writes its own container-local copy; the host orchestrator owns the canonical board
and runs a strict ROUND BARRIER: every agent in a round is handed the identical snapshot
frozen at the round's start, and everything posted during the round is published only once
the round ends.

Delivery is PUSH, not pull. There is no `read_messages` tool: at the start of round r+1 the
host injects each agent's round-r messages straight into its model context (see
orchestrate.py `_notify_round`). So the bins here only ever WRITE to the board -- the host
does all the reading and per-recipient filtering. Two consequences worth knowing:

  * No read cursor is needed. The barrier already partitions messages by round, so every
    message is delivered exactly once to every eligible recipient by construction.
  * Pushed messages are injected with message_type "user", which SWE-agent's
    `last_n_observations` history processor never elides -- a peer's interface can no longer
    be silently lost from context the way it was under the old pull design.

Env vars exported via `agent.tools.env_variables`:

  AGENT_ID        this agent's id (e.g. agent_2)
  COMM_BOARD      path to the board JSON inside the container (default /root/comm/board.json)
  AGENTS_ROSTER   JSON array of {id, gold_file} for all peers (for list_agents)
  COMM_MODE       "broadcast" | "p2p" -- the communication harness for this run

Self-contained: no dependency on SWE-agent's tool libs.
"""
import json
import os
import time
from pathlib import Path


def agent_id() -> str:
    return os.environ.get("AGENT_ID", "agent")


def comm_mode() -> str:
    """"broadcast" (send_message always goes to every peer) or "p2p" (it may be addressed to
    one). Defaults to p2p, which is the strictly more permissive surface."""
    return os.environ.get("COMM_MODE", "p2p").strip().lower() or "p2p"


def board_path() -> Path:
    return Path(os.environ.get("COMM_BOARD", "/root/comm/board.json"))


def round_path() -> Path:
    """Current round number, written by the host at the start of every turn. Only used to
    stamp belief notes -- nothing gates on it."""
    return board_path().parent / ".round"


def current_round():
    """The round number as an int, or None when the host has written no `.round` file
    (offline tooling). Int rather than the raw text so archived belief history sorts."""
    try:
        return int(round_path().read_text().strip())
    except Exception:
        return None


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


# --------------------------------------------------------------------------- #
# Private per-agent beliefs about peers (--beliefs cell only)
# --------------------------------------------------------------------------- #
def beliefs_path() -> Path:
    """This agent's PRIVATE notes on its peers. Kept beside the board but never merged into
    it and never shown to anyone else: the host reads it only to inject the table back into
    this same agent's context each round, and to archive it for analysis. The host never
    writes it, so it survives every round for the container's whole life."""
    return board_path().parent / f".beliefs_{agent_id()}.json"


def load_beliefs() -> dict:
    try:
        data = json.loads(beliefs_path().read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_beliefs(beliefs: dict) -> None:
    p = beliefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(beliefs, indent=2))
