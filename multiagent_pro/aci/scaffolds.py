"""Scaffold adapters: one round loop, two agent frameworks.

`orchestrate.py` owns the coordination harness -- the round barrier, the board, the pushed
notices, the interface registry, beliefs and comm_stats. None of that is specific to how an
individual agent thinks or edits files. This module isolates the parts that ARE, so
SWE-agent and mini-swe-agent can be swapped underneath an otherwise byte-identical harness.

That sharing is the whole point: "scaffold" is a study variable, so anything the two backends
do not share silently confounds the comparison. Keep harness logic in orchestrate.py and
framework logic here.

The two frameworks differ in three ways that matter, all normalized by `StepResult`:

  * how a step is reported -- SWE-agent returns a StepOutput object with tool_calls; mini
    returns a dict with raw bash output and no tool concept at all;
  * how a submission is signalled -- SWE-agent sets exit_status "submitted (...)"; mini raises
    Submitted when a command's FIRST output line is its sentinel;
  * what "done" means -- SWE-agent's `done` covers ~10 outcomes of which only one is a real
    submission, so `done` and `submitted` are separate fields here rather than one flag.
"""
# Python 3.10+ on the host (the tool BINS run on the images' 3.9; this module never does).
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class StepResult:
    """One agent step, normalized across frameworks.

    `done` means the agent cannot usefully continue (submitted, out of budget, fatal error).
    `submitted` means specifically that it finished its work -- the caller retires a `done`
    agent that did NOT submit, but keeps giving turns to one that did, since peers can only
    reach it while it keeps stepping.
    """
    step: int
    thought: str = ""
    action: str = ""
    observation: str = ""
    tool_calls: list = field(default_factory=list)
    execution_time: float = 0.0
    exit_status: str = ""
    done: bool = False
    submitted: bool = False

    def as_record(self) -> dict:
        """The per-step dict written to <agent>/traj/round_<n>.json."""
        return {
            "step": self.step,
            "thought": self.thought,
            "tool_calls": self.tool_calls,
            "action": self.action,
            "observation": self.observation,
            "execution_time": self.execution_time,
            "done": self.done,
            "exit_status": self.exit_status,
        }


# --------------------------------------------------------------------------- #
# Message expiry (shared semantics, per-framework access)
# --------------------------------------------------------------------------- #
NOTICE_MARK = "--- Round "
# Exactly what tools/comm/bin/send_message prints on success. Matched on the tool's OWN
# output rather than on the message text, so an agent quoting its message elsewhere is
# untouched, and a failed send (unknown recipient, self-addressed) is left in view as the
# error it is.
SENT_MARKS = ("] message sent.", "receive it at the start of the next round")


def prune_history(entries: list, is_notice, is_own_send, cutoff: int) -> int:
    """Expire mail older than one round, in place. Returns how many entries were dropped.

    Retention is deliberately asymmetric, because the two kinds expire for different reasons:

      * a round NOTICE is superseded -- the notice about to be injected carries this round's
        mail, so every earlier one is stale by construction and all of them go;
      * an agent's OWN outgoing message survives one extra round, because the reply to a
        question asked in round N-1 only arrives at the start of round N. Dropping it on the
        same boundary would show the agent an answer with no memory of what it asked.

    Both scaffolds must apply the SAME rule or "scaffold" stops being a controlled variable --
    only the per-entry access differs (SWE-agent keys on message_type, mini on role), which is
    why the predicates are injected.
    """
    keep = [e for i, e in enumerate(entries)
            if not (is_notice(e) or (is_own_send(e) and i < cutoff))]
    dropped = len(entries) - len(keep)
    if dropped:
        entries[:] = keep
    return dropped


class Scaffold(Protocol):
    """What the round loop needs from an agent framework, and nothing more."""

    def start(self) -> None: ...
    def inject(self, text: str) -> None: ...
    def step(self) -> StepResult: ...
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def collect_diff(self, pathspec: str) -> str: ...
    def prune_expired(self) -> int: ...
    def close(self) -> None: ...

    @property
    def messages(self) -> list: ...
    @property
    def n_steps(self) -> int: ...


# --------------------------------------------------------------------------- #
# SWE-agent
# --------------------------------------------------------------------------- #
def _summarize_tool_calls(out) -> list:
    """[{name, args}] from a StepOutput's tool_calls (litellm's
    ChatCompletionMessageToolCall.to_dict() shape: {"function": {"name", "arguments"}}).
    `agent.trajectory` drops tool_calls entirely, so this is the only place the structured
    tool name + args are available."""
    calls = []
    for tc in (out.tool_calls or []):
        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
        raw_args = fn.get("arguments", "")
        try:
            args = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError):
            args = raw_args
        calls.append({"name": fn.get("name", ""), "args": args})
    return calls


class SweAgentScaffold:
    """The original backend. Behaviour here must stay byte-identical to the pre-adapter code
    so previously recorded SWE-agent runs remain reproducible."""

    name = "swe-agent"

    def __init__(self, inst_dir, aid: str, image: str):
        self.inst_dir, self.aid, self.image = inst_dir, aid, image
        self.env = None
        self.agent = None
        self._prev_round_start = 0     # index where the PREVIOUS round's entries begin

    def start(self) -> None:
        import yaml
        from sweagent.agent.agents import get_agent_from_config
        from sweagent.environment.swe_env import SWEEnv
        from sweagent.run.run_single import RunSingleConfig
        from model_pricing import ensure_registered
        from pathlib import Path

        cfg = RunSingleConfig(
            **yaml.safe_load((self.inst_dir / self.aid / "solver.yaml").read_text()))
        # litellm's model_cost table is process-local, so a fresh orchestrate.py run has to
        # re-register any custom pricing gen_solver_config.py saved.
        ensure_registered(cfg.agent.model.name)
        self.env = SWEEnv.from_config(cfg.env)
        self.env.start()
        self.agent = get_agent_from_config(cfg.agent)
        self.agent.setup(env=self.env, problem_statement=cfg.problem_statement,
                         output_dir=Path(cfg.output_dir))

    def inject(self, text: str) -> None:
        """Push the round notice in as a plain user turn.

        Two SWE-agent constraints pin the dict shape: `_append_history` splats it into
        `on_query_message_added(**item)` so no extra keys are allowed, and the `messages`
        property does an unguarded `entry["agent"]` so that key is mandatory. message_type
        "user" (not "observation") is what keeps delivered messages permanently in context --
        LastNObservations only ever elides entries typed "observation".
        """
        self.agent._append_history({
            "role": "user",
            "content": text,
            "agent": getattr(self.agent, "name", "primary"),
            "message_type": "user",
        })

    def step(self) -> StepResult:
        out = self.agent.step()
        done = bool(getattr(out, "done", False))
        # `done` covers ~10 outcomes, only one of which is a real submission (agents.py sets
        # exit_status "submitted"/"submitted (...)"). Everything else -- exit_cost,
        # exit_context, exit_format, exit_command_timeout, exit_forfeit, ... -- means the
        # agent cannot usefully continue.
        return StepResult(
            step=len(self.agent.trajectory),
            thought=out.thought,
            action=out.action,
            observation=out.observation,
            tool_calls=_summarize_tool_calls(out),
            execution_time=out.execution_time,
            exit_status=out.exit_status,
            done=done,
            submitted=done and str(out.exit_status or "").startswith("submitted"),
        )

    def prune_expired(self) -> int:
        """Expire last round's mail from SWE-agent's history.

        Keys on `message_type`: notices are injected as "user", and a send's result arrives
        as an "observation". Best-effort -- a pruning failure must never take down a paid run.
        """
        def is_notice(e):
            return (e.get("message_type") == "user"
                    and NOTICE_MARK in str(e.get("content") or "")[:40])

        def is_own_send(e):
            if e.get("message_type") != "observation":
                return False
            c = str(e.get("content") or "")
            return all(mark in c for mark in SENT_MARKS)

        try:
            hist = getattr(self.agent, "history", None)
            if not isinstance(hist, list):
                return 0
            dropped = prune_history(hist, is_notice, is_own_send, self._prev_round_start)
            # This round's entries start here; the next call uses it as the cutoff, which is
            # what makes an outgoing message live exactly one round longer than a notice.
            self._prev_round_start = len(hist)
            return dropped
        except Exception as e:
            print(f"    (message pruning skipped: {type(e).__name__}: {e})")
            return 0

    def read_file(self, path: str) -> str:
        return self.env.read_file(path)

    def write_file(self, path: str, content: str) -> None:
        self.env.write_file(path, content)

    def collect_diff(self, pathspec: str) -> str:
        import base64
        # base64 -w0 the diff instead of capturing it raw: env.communicate runs in a pty,
        # which (a) CRLF-mangles every line and (b) can eat trailing blank/whitespace context
        # lines -- observed truncating a hunk 2 lines short of its @@ header count, making
        # `git apply` reject the ENTIRE merged patch as "corrupt patch". A single base64 line
        # survives the pty byte-exact. --no-pager keeps git from invoking $PAGER in the pty.
        out = self.env.communicate(
            f'cd "${{ROOT:-/app}}" && git add -A{pathspec} && '
            f'git --no-pager diff --cached{pathspec} | base64 -w0', timeout=120)
        return base64.b64decode("".join(out.split())).decode("utf-8", errors="replace")

    def close(self) -> None:
        if self.env is not None:
            self.env.close()

    @property
    def messages(self) -> list:
        return self.agent.messages

    @property
    def n_steps(self) -> int:
        return len(self.agent.trajectory)
