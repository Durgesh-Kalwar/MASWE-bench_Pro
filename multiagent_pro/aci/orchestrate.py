#!/usr/bin/env python
"""Stage W3d — round-based orchestrator for the multi-agent scoped ACI.

Drives N file-scoped agents over ONE SWE-bench Pro instance, lets them coordinate through a
shared message board, then integrates their disjoint scoped diffs and grades the result with
the unchanged Pro harness.

Container model (per the design): each agent runs in its OWN container started from the same
Pro image at the same base_commit (SWE-agent's DockerDeployment always starts a fresh
container, and the registry/state files are hardcoded single paths, so agents cannot safely
co-tenant). The comm board is owned here on the host.

Round model (strict lockstep): at the start of a round the board is FROZEN, and every agent
in that round is handed the identical snapshot. Whatever the agents post is collected but
published only once the round ends, so an agent can only ever read what peers said in
PREVIOUS rounds -- turn order within a round carries no information advantage. Every agent
gets a turn every round, including agents that already submitted (so a peer's later question
can still be answered); the run stops once every agent submits within the SAME round. An
agent ends its turn by submitting, by `no_op` (a pass: "I'm missing information a peer must
give me" -- it returns next round), or by exhausting its step budget.

Modes
-----
gold    No LLM. For each agent, apply its gold.patch inside the image, capture
        `git diff -- <scope>`, write agent_<k>.patch. Verifies the container + scoped-diff
        + integrate + grade path end-to-end, fully offline. (Requires --emit-gold at build.)
agents  Real LLM solving: start one SWEEnv per agent, drive DefaultAgent.step() in bounded
        rounds with board sync between rounds, then collect scoped diffs. Needs model API
        keys and a working swe-rex boot on the Pro image (see notes at bottom).
dry     Validate every solver.yaml parses and print the plan; start nothing.

After either solving mode, runs `build_multiagent_pro.py --mode merge` and (optionally) the
Pro evaluator.
"""
import argparse
import base64
import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = REPO_DIR / "multiagent_pro" / "build_multiagent_pro.py"
COMM_BOARD_IN_IMAGE = "/root/comm/board.json"
# Current round number, rewritten into every container at the start of each turn. The submit
# gate compares it against the round the agent last ran read_messages in, which is what makes
# "read the board once per round" enforceable (a read-once-ever gate let an agent that had
# finished sail past questions posted for it in later rounds).
ROUND_FILE_IN_IMAGE = "/root/comm/.round"
# Emitted by tools/scoped_fs/bin/no_op. Matched as a SUBSTRING of the step observation: the
# swe-rex pty appends CRLF, so equality/line comparisons would miss it.
NOOP_MARKER = "###MULTIAGENT-NO-OP###"


# --------------------------------------------------------------------------- #
# Board helpers (host-side canonical board)
# --------------------------------------------------------------------------- #
def _msg_key(m):
    return (m.get("from"), round(float(m.get("ts", 0)), 6), m.get("to"), m.get("text"),
            m.get("signature"))


def merge_board(canonical, incoming):
    seen = {_msg_key(m) for m in canonical}
    out = list(canonical)
    for m in incoming:
        if _msg_key(m) not in seen:
            seen.add(_msg_key(m))
            out.append(m)
    return out


# --------------------------------------------------------------------------- #
# Per-step / per-round trajectory logging (agents mode)
# --------------------------------------------------------------------------- #
def _summarize_tool_calls(out):
    """Pull [{name, args}] out of a StepOutput's tool_calls (litellm's
    ChatCompletionMessageToolCall.to_dict() shape: {"function": {"name", "arguments"}, ...}).
    `agent.trajectory` (SWE-agent's own record) drops tool_calls entirely -- this is the only
    place the structured tool name + args are available, so we capture it here instead.
    """
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


def _step_record(step_idx, out):
    return {
        "step": step_idx,
        "thought": out.thought,
        "tool_calls": _summarize_tool_calls(out),
        "action": out.action,
        "observation": out.observation,
        "execution_time": out.execution_time,
        "done": bool(getattr(out, "done", False)),
        "exit_status": out.exit_status,
    }


def _format_tool_calls(calls):
    if not calls:
        return "(no tool call)"
    return ", ".join(f"{c['name']}({c['args']})" for c in calls)


ROUND_NOTICE = """\
--- Round {n} begins ---
The message board has just been updated with everything your peers posted in round {prev}.
Anything you post from now on reaches them in round {next}, not this one.

Start by running `read_messages` (it shows only what is new, and never your own messages).
Then:
  * if a peer gave you what you were waiting for, apply it and run `scoped_submit`;
  * if your file is already complete and nothing has changed for you, run `scoped_submit`
    again to confirm you are finished -- the run ends once every agent submits in the same
    round;
  * if you are still missing something only a peer can give you, `send_message` to ask, then
    `no_op` to end your turn and wait for their reply next round.

You must run `read_messages` in EVERY round before `scoped_submit` -- a peer may be blocked
waiting on an answer only you can give.
"""

SUBMITTED_NOTICE = """\
--- Round {n} begins ---
You already submitted your patch in round {submitted_in}. You are being given another turn
because your peers may need something from you -- they can only reach you while you keep
taking turns.

The board now carries everything your peers posted in round {prev}. Run `read_messages`
FIRST, then decide from what you actually find there:
  * a peer asked you for something (a name, a signature, where something lives) -> answer
    with `send_message`, or `publish_interface` the EXACT names you wrote in your file;
  * a peer told you something that changes your file -> edit it, then `scoped_submit` again;
  * nothing on the board concerns you -> run `scoped_submit` again to confirm you are still
    finished (the run ends once every agent submits in the same round).

You must run `read_messages` in EVERY round before `scoped_submit`, including this one.
"""


def _notify_round(agent, r, submitted_in=None):
    """Tell an agent a new round started. Without this, an agent re-invoked after submitting
    just sees its own last observation and has no idea why it is being stepped again, so it
    can neither answer a peer's new question nor confirm it is finished (which is what ends
    the run). Agents that already submitted get a notice naming the round they submitted in,
    since "why am I running again?" is exactly their question. Injected as a plain user turn
    -- valid after a step because function-calling observations are appended with role "tool"
    (agents.py _add_templated_messages_to_history). Best-effort: the round loop must never die
    over a prompt nicety."""
    if r == 0:
        return
    tmpl = SUBMITTED_NOTICE if submitted_in else ROUND_NOTICE
    try:
        agent._append_history({
            "role": "user",
            "content": tmpl.format(n=r + 1, prev=r, next=r + 2, submitted_in=submitted_in),
            "agent": getattr(agent, "name", "primary"),
            "message_type": "user",
        })
    except Exception as e:
        print(f"    (round notice skipped: {type(e).__name__}: {e})")


# --------------------------------------------------------------------------- #
# gold mode (offline, no LLM)
# --------------------------------------------------------------------------- #
def docker_apply_and_diff(image, base_commit, patch_text, scope_files):
    """Inside the image: reset to base_commit, apply patch_text, emit `git diff -- scope`."""
    scope_args = " ".join(shlex.quote(f) for f in scope_files)
    b64 = base64.b64encode(patch_text.encode()).decode()
    script = (
        'REPO=$(git rev-parse --show-toplevel 2>/dev/null); [ -z "$REPO" ] && REPO=/app; '
        'cd "$REPO" || exit 1; '
        f'git reset --hard {base_commit} >/dev/null 2>&1; '
        f'echo {b64} | base64 -d > /tmp/agent.patch; '
        'git apply --whitespace=nowarn /tmp/agent.patch 2>/tmp/apply.err '
        '|| { echo "APPLY_FAILED"; cat /tmp/apply.err; exit 3; }; '
        'git add -A; '
        f'git diff --cached -- {scope_args}'
    )
    cmd = ["docker", "run", "--rm", "--entrypoint", "bash", image, "-lc", script]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"docker scoped-diff failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def run_gold(inst_dir, spec):
    base_commit = spec["base_commit"]
    image = spec["image"]
    for agent in spec["agents"]:
        aid = agent["id"]
        gold = inst_dir / aid / "gold.patch"
        if not gold.exists():
            raise SystemExit(f"{gold} missing — rebuild with --emit-gold for gold mode.")
        diff = docker_apply_and_diff(image, base_commit, gold.read_text(), agent["scope"])
        (inst_dir / f"{aid}.patch").write_text(diff)
        print(f"  {aid}: scoped diff captured ({len(diff.splitlines())} lines) "
              f"-> {aid}.patch")


# --------------------------------------------------------------------------- #
# agents mode (real LLM, round-based)
# --------------------------------------------------------------------------- #
def run_agents(inst_dir, spec, rounds, steps_per_round):
    import yaml
    sys.path.insert(0, str(Path(__file__).resolve().parent))     # for build_runtime_image
    sys.path.insert(0, str(REPO_DIR / "SWE-agent"))
    from build_runtime_image import ensure_runtime_image
    from model_pricing import ensure_registered
    from sweagent.agent.agents import get_agent_from_config
    from sweagent.environment.swe_env import SWEEnv
    from sweagent.run.run_single import RunSingleConfig

    # Bake swe-rex into a derived image once (all agents share the same Pro base). The
    # solver.yaml files already point at this deterministic tag with pull=never.
    ensure_runtime_image(spec["image"])

    envs, agents, retired = {}, {}, {}
    for a in spec["agents"]:
        aid = a["id"]
        cfg = RunSingleConfig(**yaml.safe_load((inst_dir / aid / "solver.yaml").read_text()))
        # Re-register any custom-model pricing gen_solver_config.py saved -- litellm's
        # model_cost table is process-local, so a fresh orchestrate.py run needs this too.
        ensure_registered(cfg.agent.model.name)
        env = SWEEnv.from_config(cfg.env)
        env.start()
        agent = get_agent_from_config(cfg.agent)
        agent.setup(env=env, problem_statement=cfg.problem_statement,
                    output_dir=Path(cfg.output_dir))
        envs[aid], agents[aid], retired[aid] = env, agent, False
        print(f"  started {aid}")

    board = []
    submitted_round = {}              # aid -> round it FIRST submitted in (for the notice)
    for r in range(rounds):
        print(f"  -- round {r + 1}/{rounds} --")
        frozen = list(board)          # every agent this round sees the SAME board state
        frozen_keys = {_msg_key(m) for m in frozen}
        submitted, pending = {}, []
        for a in spec["agents"]:
            aid = a["id"]
            if retired[aid]:          # terminal failure only -- NOT "already submitted"
                continue
            env, agent = envs[aid], agents[aid]
            env.write_file(COMM_BOARD_IN_IMAGE, json.dumps(frozen))   # identical for everyone
            env.write_file(ROUND_FILE_IN_IMAGE, str(r + 1))   # arms the per-round read gate
            _notify_round(agent, r, submitted_round.get(aid))
            round_steps = []
            for _ in range(steps_per_round):
                try:
                    out = agent.step()
                except Exception as e:
                    # SWE-agent turns most failures into done-steps, but re-raises
                    # TotalCostLimitExceededError -- unguarded that would abort run_agents
                    # entirely and skip the diff collection below, losing EVERY agent's work.
                    print(f"    [{aid}] step raised {type(e).__name__}: {e} -- retiring agent")
                    retired[aid] = True
                    break
                record = _step_record(len(agent.trajectory), out)
                round_steps.append(record)
                print(f"    [{aid}] step {record['step']}: {_format_tool_calls(record['tool_calls'])}")
                if NOOP_MARKER in (out.observation or ""):
                    print(f"    [{aid}] passed this round (no_op)")
                    break             # turn over for this round; agent is NOT done
                if getattr(out, "done", False):
                    # `done` covers ~10 outcomes, only one of which is a real submission
                    # (agents.py sets exit_status "submitted"/"submitted (...)"). The rest --
                    # exit_cost, exit_context, exit_format, exit_command_timeout, exit_forfeit,
                    # exit_error, ... -- mean the agent cannot usefully continue, so retire it
                    # instead of burning a wasted step on it every remaining round.
                    if str(out.exit_status or "").startswith("submitted"):
                        submitted[aid] = True
                        submitted_round.setdefault(aid, r + 1)
                    else:
                        print(f"    [{aid}] ended: {out.exit_status} -- retiring agent")
                        retired[aid] = True
                    break
            traj_dir = inst_dir / aid / "traj"
            traj_dir.mkdir(parents=True, exist_ok=True)
            (traj_dir / f"round_{r + 1}.json").write_text(json.dumps(round_steps, indent=2))
            try:            # stage this agent's new messages; do NOT publish them yet
                posted = json.loads(env.read_file(COMM_BOARD_IN_IMAGE))
                if not isinstance(posted, list):
                    posted = []
            except Exception:
                posted = []
            pending.extend(m for m in posted
                           if isinstance(m, dict) and _msg_key(m) not in frozen_keys)
        board = merge_board(board, pending)          # publish once, at the round barrier
        for m in board[len(frozen):]:
            print(f"    [board] {m.get('from')} -> {m.get('to', 'all')}: "
                  f"{m.get('signature') or m.get('text')}")
        (inst_dir / f"board_after_round_{r + 1}.json").write_text(json.dumps(board, indent=2))
        active = [a["id"] for a in spec["agents"] if not retired[a["id"]]]
        if active and all(submitted.get(aid) for aid in active):
            print("  all agents submitted in the same round")
            break
        if not active:
            print("  no agents left to run")
            break

    for a in spec["agents"]:
        aid = a["id"]
        env = envs[aid]
        full = a.get("scope_mode") == "full"
        # In "full" (denylist) mode the agent could edit ANY file except peers' gold files, so
        # a["scope"] (= just its own gold file) is NOT the edit boundary -- scoping the diff to
        # it would drop every edit to other files. Diff the whole repo instead; enforcement
        # guarantees the agent never wrote a denied file, so the diff holds only allowed edits.
        # In allow mode, stage only this agent's scope: `git add -A` walks the entire worktree,
        # which on large repos (ansible) exceeds the default 25s timeout; the diff was already
        # restricted to `scope`, so staging beyond it was never needed.
        pathspec = "" if full else " -- " + " ".join(shlex.quote(f) for f in a["scope"])
        try:
            # base64 -w0 the diff instead of capturing it raw: env.communicate runs in a pty,
            # which (a) CRLF-mangles every line and (b) can eat trailing blank/whitespace
            # context lines -- observed truncating a hunk 2 lines short of its @@ header
            # count, making `git apply` reject the ENTIRE merged patch as "corrupt patch"
            # (graded as if the agents did nothing). A single base64 line survives the pty
            # byte-exact. --no-pager still needed so git never invokes $PAGER in the pty.
            out = env.communicate(f'cd "${{ROOT:-/app}}" && git add -A{pathspec} && '
                                  f'git --no-pager diff --cached{pathspec} | base64 -w0',
                                  timeout=120)
            diff = base64.b64decode("".join(out.split())).decode("utf-8", errors="replace")
            (inst_dir / f"{aid}.patch").write_text(diff)
            print(f"  {aid}: scoped diff -> {aid}.patch ({len(diff.splitlines())} lines)")
        except Exception as e:
            # Never let one agent's collection failure strand the other agents'
            # containers -- that leaks disk until the next manual cleanup.
            print(f"  {aid}: diff collection FAILED: {e}")
        finally:
            env.close()
    (inst_dir / "board.json").write_text(json.dumps(board, indent=2))


# --------------------------------------------------------------------------- #
def merge_and_grade(inst_dir, output_root, prefix, grade, dockerhub_username):
    inst_id = inst_dir.name
    subprocess.run([sys.executable, str(BUILD_SCRIPT), "--mode", "merge",
                    "--instances", inst_id, "--output", str(output_root),
                    "--prefix", prefix], check=True)
    if not grade:
        print(f"\nMerged. To grade:\n  python swe_bench_pro_eval.py "
              f"--raw_sample_path sampled_pro/raw_sample.jsonl "
              f"--patch_path {output_root}/patches.json "
              f"--output_dir {output_root}/eval_out --scripts_dir run_scripts "
              f"--dockerhub_username {dockerhub_username} --use_local_docker")
        return
    subprocess.run([sys.executable, str(REPO_DIR / "swe_bench_pro_eval.py"),
                    "--raw_sample_path", "sampled_pro/raw_sample.jsonl",
                    "--patch_path", str(output_root / "patches.json"),
                    "--output_dir", str(output_root / "eval_out"),
                    "--scripts_dir", "run_scripts",
                    "--dockerhub_username", dockerhub_username,
                    "--use_local_docker"], check=True, cwd=str(REPO_DIR))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["gold", "agents", "dry"], default="gold")
    ap.add_argument("--output", default="multiagent_pro_out",
                    help="Build-output root with <id>/spec.json + solver.yaml")
    ap.add_argument("--instances", nargs="*", help="Restrict to these instance ids")
    ap.add_argument("--rounds", type=int, default=4, help="(agents mode) coordination rounds")
    ap.add_argument("--steps-per-round", type=int, default=6,
                    help="(agents mode) agent.step() calls per agent per round")
    ap.add_argument("--prefix", default="multiagent")
    ap.add_argument("--grade", action="store_true", help="Run the Pro evaluator after merge")
    ap.add_argument("--dockerhub_username", default="jefzda")
    args = ap.parse_args()

    root = Path(args.output)
    inst_dirs = ([root / i for i in args.instances] if args.instances
                 else [p for p in root.iterdir() if (p / "spec.json").exists()])
    if not inst_dirs:
        raise SystemExit(f"No <id>/spec.json under {root}/. Build + gen_solver_config first.")

    import yaml
    sys.path.insert(0, str(REPO_DIR / "helper_code"))
    from image_uri import get_dockerhub_image_uri

    for inst_dir in inst_dirs:
        spec = json.loads((inst_dir / "spec.json").read_text())
        spec.setdefault("image", get_dockerhub_image_uri(
            spec["instance_id"], args.dockerhub_username, spec["repo"]))
        print(f"\n=== {inst_dir.name} ({spec['num_agents']} agents, mode={args.mode}) ===")

        if args.mode == "dry":
            from sweagent.run.run_single import RunSingleConfig
            for a in spec["agents"]:
                RunSingleConfig(**yaml.safe_load(
                    (inst_dir / a["id"] / "solver.yaml").read_text()))
                if a.get("scope_mode") == "full":
                    access = f"full access (deny {len(a.get('deny', []))} peer file(s))"
                else:
                    access = f"scope={len(a['scope'])} files"
                print(f"  {a['id']}: solver.yaml OK | owns {a['gold_file']} | {access}")
            continue
        if args.mode == "gold":
            run_gold(inst_dir, spec)
        else:
            run_agents(inst_dir, spec, args.rounds, args.steps_per_round)
        merge_and_grade(inst_dir, root, args.prefix, args.grade, args.dockerhub_username)


if __name__ == "__main__":
    main()
