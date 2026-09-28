#!/usr/bin/env python
"""Run the solo (single-agent) mini-swe-agent arm, logging everything the dashboard needs.

One agent, the whole repository, no communication, no scope guard. This is the control that
decides which instances are solvable once the `requirements` spec is withheld; only those go on
to the multi-agent grid.

WHY NOT orchestrate.py. That script owns the coordination harness -- round barrier, board,
pushed notices, interface registry, beliefs, comm_stats -- none of which exists in a solo run,
and its round loop is built around N agents taking turns. Reusing it would mean threading a
"pretend there are no peers" flag through every one of those systems. Instead this drives mini's
DefaultAgent directly, the way MiniScaffold does, and writes the SAME artifacts so the existing
dashboard reads solo runs with no changes:

    <instance>/agent_1/context/messages.jsonl   one snapshot of the whole message list per call
    <instance>/agent_1/traj/round_1.json        the action each call produced
    <instance>/agent_1.patch                    the evaluated diff

ALIGNMENT IS POSITIONAL, and that constrains the loop. dashboard/build_dashboard.py pairs
snapshot k with trajectory step k by POSITION, not by the logged step numbers, then verifies the
pairing (snapshot k's trailing message must contain step k-1's observation). So this writes
exactly one snapshot and exactly one trajectory record per model call -- including for a
FormatError, where the model was called and the parse then failed. Skipping either side for any
step would silently shift every later pair.

SCOPE GUARD IS ABSENT ON PURPOSE. ScopedDockerEnvironment exists to stop an agent reading a
peer's file. A solo agent has no peers and is supposed to see the whole repo, so plain
DockerEnvironment is used and no scope_violations.jsonl is written.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
ACI_DIR = REPO_DIR / "multiagent_pro" / "aci"
sys.path.insert(0, str(REPO_DIR / "mini-swe-agent" / "src"))
sys.path.insert(0, str(ACI_DIR))               # scaffolds.StepResult, for one record shape

from scaffolds import StepResult                                        # noqa: E402


def _command_name(action: str) -> str:
    """First word of a bash command, so the dashboard's per-step tool label works the same way
    it does for SWE-agent tool names."""
    action = (action or "").strip()
    if not action:
        return ""
    try:
        parts = shlex.split(action)
    except ValueError:
        parts = action.split()
    return os.path.basename(parts[0]) if parts else ""


def _gateway_cost(resp: dict) -> float | None:
    """The gateway's OWN billed cost for one response, if litellm preserved it.

    The CreateAI gateway returns metadata.usage_metric.total_token_cost, which is authoritative
    -- it is what the monthly budget is debited by. litellm's ModelResponse may or may not carry
    unknown top-level fields through model_dump(), so this is best-effort and the litellm-computed
    cost (from the registered per-token prices) remains the primary figure.
    """
    try:
        return float(resp["metadata"]["usage_metric"]["total_token_cost"])
    except (KeyError, TypeError, ValueError):
        return None


class SoloRunner:
    def __init__(self, idir: Path, *, dump_context: bool = True):
        self.idir = idir
        self.adir = idir / "agent_1"
        self.dump_context = dump_context
        self.ctx_path = self.adir / "context" / "messages.jsonl"
        self.traj_path = self.adir / "traj" / "round_1.json"
        self.agent = None
        self.env = None
        self.records: list[dict] = []
        self.gateway_cost = 0.0
        self.tokens_in = self.tokens_out = 0

    # -- lifecycle ---------------------------------------------------------- #
    def start(self) -> None:
        import yaml
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.environments.docker import DockerEnvironment
        from minisweagent.models import get_model

        cfg = yaml.safe_load((self.adir / "mini.yaml").read_text())
        self.env = DockerEnvironment(**(cfg.get("environment") or {}))
        model = get_model(config=dict(cfg.get("model") or {}))
        self.agent = DefaultAgent(model, self.env, **(cfg.get("agent") or {}))

        # DefaultAgent.run() seeds these before its own while-loop; we drive step() directly, so
        # do it here. `problem_statement` is the composed issue text built by build_solo.py --
        # jinja runs with StrictUndefined, so a missing variable is a hard error, not a blank
        # prompt (a bug that cost a whole run once; see CHECKPOINT 13.4).
        issue = (self.adir / "local_issue.md").read_text()
        self.agent.extra_template_vars |= {"task": "", "problem_statement": issue}
        self.agent.add_message(
            "system", self.agent.render_template(self.agent.config.system_template))
        self.agent.add_message(
            "user", self.agent.render_template(self.agent.config.instance_template))

    def close(self) -> None:
        if self.env is not None:
            try:
                self.env.cleanup()
            except Exception:
                pass

    # -- logging ------------------------------------------------------------ #
    def _dump_context(self, step_no: int) -> None:
        """Append the EXACT message list the imminent call will send.

        mini has no history processor, so this is simply the full conversation -- which is the
        point: it answers "what did the agent see before it decided", recoverable from neither
        the trajectory (what tools returned) nor the patch (what it ended up writing).
        Best-effort: a logging failure must never take down a paid run.
        """
        if not self.dump_context:
            return
        try:
            msgs = self.agent.messages
            self.ctx_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                # Solo runs have no rounds; round 1 keeps the dashboard's round->step tree valid.
                "round": 1,
                "step_in_round": step_no,
                "global_step": step_no,
                "n_messages": len(msgs),
                "chars": sum(len(str(m.get("content", ""))) for m in msgs),
                "messages": msgs,
            }
            with self.ctx_path.open("a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception as e:
            print(f"    (context dump skipped: {type(e).__name__}: {e})")

    def _write_traj(self) -> None:
        """Rewrite the whole trajectory array after every step.

        A JSON array appended to incrementally is invalid JSON until closed, so a killed run
        would lose everything (the dashboard's read_json would fall back to []). Rewriting costs
        nothing next to an LLM call and means a run can be interrupted at any point and still be
        readable -- the same reason comm_stats.json is rewritten every round.
        """
        try:
            self.traj_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.traj_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.records, indent=1, default=str))
            tmp.replace(self.traj_path)
        except Exception as e:
            print(f"    (traj write skipped: {type(e).__name__}: {e})")

    def _account(self) -> None:
        """Pull token counts and the gateway's own cost off the message just produced.

        Scans BACKWARDS for the last assistant message carrying `extra`, rather than reading
        messages[-1]: by the time a step returns, mini has already appended the observation as a
        user turn, so the last message is not the one the model produced. Reading [-1] silently
        accounted zero for every step.
        """
        try:
            resp = {}
            for m in reversed(self.agent.messages):
                if m.get("role") == "assistant" and (m.get("extra") or {}).get("response"):
                    resp = m["extra"]["response"]
                    break
            usage = resp.get("usage") or {}
            self.tokens_in += int(usage.get("prompt_tokens") or 0)
            self.tokens_out += int(usage.get("completion_tokens") or 0)
            if (c := _gateway_cost(resp)) is not None:
                self.gateway_cost += c
        except Exception:
            pass

    # -- the loop ----------------------------------------------------------- #
    def step(self, step_no: int) -> StepResult:
        """One model call plus its action, normalized. Mirrors MiniScaffold.step so solo and
        multi-agent trajectories have identical record shapes."""
        from minisweagent.agents.default import (
            NonTerminatingException,
            Submitted,
            TerminatingException,
        )
        t0 = time.time()
        try:
            out = self.agent.step()
        except NonTerminatingException as e:
            # The model WAS called and the parse then failed; run() feeds the error back as a
            # user turn and continues, so this still counts as one step for alignment. The
            # thought is recorded even though there is no valid action -- on a format error it is
            # the only evidence of what the model was trying to do.
            self._account()
            thought = self._last_thought()
            self.agent.add_message("user", str(e))
            return StepResult(step=step_no, thought=thought, observation=str(e),
                              exit_status="format_error", execution_time=time.time() - t0)
        except TerminatingException as e:
            self._account()
            # Capture thought/action BEFORE appending the termination notice: the model did issue
            # a command on this step (the submit sentinel, or whatever tripped the limit), and
            # without this the final step renders in the dashboard with an empty action.
            thought, action = self._last_thought(), self._last_action()
            self.agent.add_message("user", str(e))
            return StepResult(step=step_no, thought=thought, action=action,
                              observation=str(e), exit_status=type(e).__name__,
                              tool_calls=[{"name": _command_name(action),
                                           "args": {"command": action}}] if action else [],
                              done=True, submitted=isinstance(e, Submitted),
                              execution_time=time.time() - t0)
        except Exception as e:                       # never let one step kill the run
            return StepResult(step=step_no, observation=f"{type(e).__name__}: {e}",
                              exit_status=type(e).__name__, done=True,
                              execution_time=time.time() - t0)
        self._account()
        action = self._last_action()
        return StepResult(
            step=step_no,
            thought=self._last_thought(),
            action=action,
            observation=str(out.get("output", "")),
            # mini has no tool schema -- the bash command IS the action. Recorded under the same
            # key so the dashboard labels each step the same way for both scaffolds.
            tool_calls=[{"name": _command_name(action), "args": {"command": action}}],
            execution_time=time.time() - t0,
        )

    def _last_assistant(self) -> str:
        for m in reversed(self.agent.messages):
            if m.get("role") == "assistant":
                return str(m.get("content", ""))
        return ""

    def _last_action(self) -> str:
        m = re.search(r"```bash\n(.*?)\n```", self._last_assistant(), re.S)
        return m.group(1).strip() if m else ""

    def _last_thought(self) -> str:
        return re.split(r"```bash", self._last_assistant(), maxsplit=1)[0].strip()

    def collect_patch(self) -> str:
        """Whole-repo diff. `git add -A` first so files the agent CREATED are included, and
        base64 through the transport because a raw diff can lose trailing blank context lines --
        which makes `git apply` reject the entire patch as corrupt (CHECKPOINT 6)."""
        r = self.env.execute(
            'cd "${ROOT:-/app}" && git add -A && '
            'git --no-pager diff --cached | base64 -w0', timeout=180)
        return base64.b64decode("".join(str(r.get("output", "")).split())).decode(
            "utf-8", errors="replace")

    def run(self, *, max_steps: int, wall_limit: float, cost_ceiling: float) -> dict:
        t_start = time.time()
        stop = "step_limit"
        for i in range(1, max_steps + 1):
            self._dump_context(i)
            res = self.step(i)
            self.records.append(res.as_record())
            self._write_traj()

            litellm_cost = float(getattr(self.agent.model, "cost", 0.0) or 0.0)
            billed = self.gateway_cost or litellm_cost
            label = _command_name(res.action) or res.exit_status or "-"
            print(f"  step {i:>3}/{max_steps}  {label:<16} "
                  f"ctx={len(self.agent.messages):>3}msg "
                  f"tok_in={self.tokens_in:>9,} ${billed:>7.3f}  {res.execution_time:>5.1f}s")

            if res.done:
                stop = "submitted" if res.submitted else (res.exit_status or "done")
                break
            # Two brakes mini does not provide. Its own cost_limit is checked BEFORE a call, so
            # it can overshoot by one very large call; this catches the overshoot. The wall clock
            # guards against a run that is neither spending nor finishing.
            if billed >= cost_ceiling:
                stop = "cost_ceiling"
                print(f"  STOP: billed ${billed:.2f} >= ceiling ${cost_ceiling:.2f}")
                break
            if time.time() - t_start > wall_limit:
                stop = "wall_limit"
                print(f"  STOP: wall clock {time.time() - t_start:.0f}s > {wall_limit:.0f}s")
                break

        patch = ""
        try:
            patch = self.collect_patch()
        except Exception as e:
            print(f"  patch collection FAILED: {type(e).__name__}: {e}")
        (self.idir / "agent_1.patch").write_text(patch)

        litellm_cost = float(getattr(self.agent.model, "cost", 0.0) or 0.0)
        stats = {
            "instance_id": self.idir.name,
            "stop_reason": stop,
            "steps": len(self.records),
            "max_steps": max_steps,
            "n_model_calls": int(getattr(self.agent.model, "n_calls", 0) or 0),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_litellm": round(litellm_cost, 6),
            # None when litellm dropped the gateway's metadata; then cost_litellm is all we have.
            "cost_gateway": round(self.gateway_cost, 6) or None,
            "wall_seconds": round(time.time() - t_start, 1),
            "patch_bytes": len(patch),
            "patch_lines": patch.count("\n"),
        }
        stats |= extrapolate(stats)
        (self.idir / "solo_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
        return stats


def extrapolate(stats: dict) -> dict:
    """Project the cost of a longer run from a short calibration one.

    Cost is quadratic in steps, not linear: mini keeps the FULL history with no elision, and this
    gateway does not honour prompt caching (measured: an identical 28.9k-token prefix reported
    cached_tokens=0 three times running), so every call re-sends and re-pays for the whole
    conversation. With per-step growth d, cumulative input over n steps is

        sum_{k=1..n} (s0 + k*d)  =  n*s0 + d*n*(n+1)/2

    so fitting d from a short run predicts a long one. That is the whole point of calibrating:
    measuring d costs ~$2 at 25 steps, whereas discovering it at 250 steps costs the full run.
    """
    n, tin = stats["steps"], stats["tokens_in"]
    if n < 2 or not tin:
        return {}
    # Average context per call, and the implied per-step growth, from the closed form above.
    d = 2.0 * tin / (n * (n + 1))
    in_rate = 4e-06                       # Opus 5.5 input $/token
    out_rate = 20e-06
    out_per_step = (stats["tokens_out"] / n) if n else 0.0
    proj = {}
    for target in (60, 125, 250):
        toks = d * target * (target + 1) / 2
        proj[f"proj_{target}_steps_usd"] = round(toks * in_rate + out_per_step * target * out_rate, 2)
        proj[f"proj_{target}_tokens_in"] = int(toks)
    return {"growth_tokens_per_step": round(d, 1), **proj}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True,
                    help="cell root: <harness50>/<harness>/mini_swe_agent/<model>")
    ap.add_argument("--instances", nargs="*", help="instance_ids (default: all in the cell)")
    ap.add_argument("--max-steps", type=int, default=None,
                    help="override the step budget in mini.yaml. Use a small value (e.g. 25) to "
                         "CALIBRATE cost cheaply before committing to a 250-step run.")
    ap.add_argument("--cost-ceiling", type=float, default=6.0,
                    help="abort an instance once billed cost reaches this. Backstop for mini's "
                         "own cost_limit, which is checked before a call and so can overshoot "
                         "by one large call.")
    ap.add_argument("--wall-limit", type=float, default=7200,
                    help="seconds per instance before abandoning it")
    ap.add_argument("--no-dump-context", action="store_true",
                    help="skip context/messages.jsonl. It re-serialises the whole conversation "
                         "every step, so it grows quadratically (~100MB for a 250-step run) -- "
                         "but it is what the dashboard's context explorer reads, so it is ON by "
                         "default.")
    args = ap.parse_args()

    root = Path(args.root)
    idirs = ([root / i for i in args.instances] if args.instances
             else sorted(p for p in root.iterdir() if (p / "spec.json").exists()))
    if not idirs:
        raise SystemExit(f"no <id>/spec.json under {root} -- run build_solo.py first")

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is unset. For the CreateAI gateway:\n"
                         "  eval \"$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)\"\n"
                         "  export OPENAI_API_KEY=\"$CREATEAI_API_KEY\"")

    all_stats = []
    for idir in idirs:
        spec = json.loads((idir / "spec.json").read_text())
        max_steps = args.max_steps or spec.get("step_limit") or 250
        print(f"\n=== {idir.name}")
        print(f"    arm={spec.get('arm')} requirements={spec.get('requirements_included')} "
              f"steps={max_steps} model={spec.get('model')}")
        runner = SoloRunner(idir, dump_context=not args.no_dump_context)
        try:
            runner.start()
            st = runner.run(max_steps=max_steps, wall_limit=args.wall_limit,
                            cost_ceiling=args.cost_ceiling)
            all_stats.append(st)
            print(f"    -> {st['stop_reason']} after {st['steps']} steps, "
                  f"${st['cost_gateway'] or st['cost_litellm']:.2f}, "
                  f"{st['patch_lines']} patch lines")
            if "proj_250_steps_usd" in st:
                print(f"    projected at 250 steps: ${st['proj_250_steps_usd']:.2f} "
                      f"(growth {st['growth_tokens_per_step']:.0f} tok/step)")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
        finally:
            runner.close()

    if all_stats:
        tot = sum(s["cost_gateway"] or s["cost_litellm"] for s in all_stats)
        print(f"\n{len(all_stats)} instance(s), ${tot:.2f} total")
        proj = [s.get("proj_250_steps_usd") for s in all_stats if s.get("proj_250_steps_usd")]
        if proj:
            mean = sum(proj) / len(proj)
            print(f"mean projected cost per instance at 250 steps: ${mean:.2f}  "
                  f"-> ${mean * 50:,.0f} for 50 instances")


if __name__ == "__main__":
    main()
