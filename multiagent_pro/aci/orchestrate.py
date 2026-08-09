#!/usr/bin/env python
"""Stage W3d — round-based orchestrator for the multi-agent scoped ACI.

Drives N file-scoped agents over ONE SWE-bench Pro instance, lets them coordinate through a
shared message board, then integrates their disjoint scoped diffs and grades the result with
the unchanged Pro harness.

Container model (per the design): each agent runs in its OWN container started from the same
Pro image at the same base_commit (SWE-agent's DockerDeployment always starts a fresh
container, and the registry/state files are hardcoded single paths, so agents cannot safely
co-tenant). The comm board is owned here on the host and synced into/out of every container
each round, so messages propagate at the round barrier.

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

    envs, agents, done = {}, {}, {}
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
        envs[aid], agents[aid], done[aid] = env, agent, False
        print(f"  started {aid}")

    board = []
    for r in range(rounds):
        print(f"  -- round {r + 1}/{rounds} --")
        for a in spec["agents"]:
            aid = a["id"]
            if done[aid]:
                continue
            env, agent = envs[aid], agents[aid]
            env.write_file(COMM_BOARD_IN_IMAGE, json.dumps(board))   # sync board IN
            round_steps = []
            for _ in range(steps_per_round):
                out = agent.step()
                record = _step_record(len(agent.trajectory), out)
                round_steps.append(record)
                print(f"    [{aid}] step {record['step']}: {_format_tool_calls(record['tool_calls'])}")
                if getattr(out, "done", False):
                    done[aid] = True
                    break
            traj_dir = inst_dir / aid / "traj"
            traj_dir.mkdir(parents=True, exist_ok=True)
            (traj_dir / f"round_{r + 1}.json").write_text(json.dumps(round_steps, indent=2))
            try:                                                    # collect new msgs OUT
                new_board = merge_board(board, json.loads(env.read_file(COMM_BOARD_IN_IMAGE)))
            except Exception:
                new_board = board
            for m in new_board[len(board):]:
                print(f"    [board] {m.get('from')} -> {m.get('to', 'all')}: {m.get('text')}")
            board = new_board
        (inst_dir / f"board_after_round_{r + 1}.json").write_text(json.dumps(board, indent=2))
        if all(done.values()):
            print("  all agents submitted")
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
