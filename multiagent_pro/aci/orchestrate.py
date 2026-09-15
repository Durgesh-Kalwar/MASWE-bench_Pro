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
published only once the round ends -- turn order within a round carries no information
advantage. Every agent gets a turn every round, including agents that already submitted (so
a peer's later question can still be answered); every one of the --rounds rounds runs, since
submitting does not end the run (unless --stop-when-all-submitted). An agent ends its turn by
submitting, by `no_op` (a pass: "I'm missing information a peer must give me" -- it returns
next round), or by exhausting its step budget.

Delivery is PUSH: there is no read tool. At the round barrier this host computes, per agent,
which of the round's new messages that agent is entitled to, and INJECTS them into its model
context before its next turn (`_notify_round`). Two things follow. Receiving costs no step,
so what differs between communication harnesses is topology rather than tool-call discipline;
and because the injected turn is message_type "user", `last_n_observations` can never elide a
peer's interface out of context the way it could when messages arrived as tool output.

Communication harness (the study variable, chosen at gen_solver_config time and read here
from <id>/comm_mode.json):

  broadcast   every send_message reaches every peer; the tool has no recipient argument.
  p2p         send_message may be addressed to one peer (delivered to that agent alone) or
              to 'all'. publish_interface broadcasts in both.
  + beliefs   agents additionally keep PRIVATE per-peer notes (`update_belief`) that no peer
              ever sees; the host replays them into each round notice and archives them per
              round as <id>/<agent>/beliefs_round_N.json.

Per-round communication counts land in <id>/comm_stats.json.

Modes
-----
gold    No LLM. For each agent, apply its gold.patch inside the image, capture
        `git diff -- <scope>`, write agent_<k>.patch. Verifies the container + scoped-diff
        + integrate + grade path end-to-end, fully offline. (Requires --emit-gold at build.)
agents  Real LLM solving: start one container per agent, drive the configured scaffold's
        step() (SWE-agent or mini-swe-agent -- see scaffolds.py) in bounded
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
# Reuse the comm bundle's signature parser rather than re-deriving it here: the interface
# registry below has to agree with what publish_interface accepted, and two regexes that must
# stay in sync are two regexes that will not. Pure stdlib, no import side effects.
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools" / "comm" / "lib"))
from verify import symbol_name
COMM_BOARD_IN_IMAGE = "/root/comm/board.json"
# Current round number, rewritten into every container at the start of each turn. Nothing
# gates on it; `update_belief` reads it to stamp each note so belief drift is recoverable
# from the archive.
ROUND_FILE_IN_IMAGE = "/root/comm/.round"
# Per-agent PRIVATE belief store (--beliefs cell). Written only by the agent's own
# update_belief; the host reads it to replay into the round notice and to archive it.
BELIEFS_FILE_IN_IMAGE = "/root/comm/.beliefs_{aid}.json"
# Emitted by tools/scoped_fs/bin/no_op. Matched as a SUBSTRING of the step observation: the
# swe-rex pty appends CRLF, so equality/line comparisons would miss it.
NOOP_MARKER = "###MULTIAGENT-NO-OP###"


# --------------------------------------------------------------------------- #
# Board helpers (host-side canonical board)
# --------------------------------------------------------------------------- #
def _msg_key(m):
    return (m.get("from"), round(float(m.get("ts", 0)), 6), m.get("to"), m.get("text"),
            m.get("signature"))


def visible_to(msg, me):
    """A message is delivered to `me` if a PEER addressed it to me or broadcast it. An agent
    never receives its own messages back. Verbatim from the old comm/lib/board.py: it moved
    host-side when delivery became push, since the host is now the only reader."""
    return msg.get("from") != me and msg.get("to") in (me, "all")


def render_messages(msgs, me):
    """Render delivered messages for injection. Same two shapes the old `read_messages` tool
    printed -- an interface line carries its signature, a plain message its text -- with the
    recipient shown as "you" so a directed message is visibly distinct from a broadcast (the
    difference between the harnesses is only legible if the agent can see it)."""
    lines = []
    for m in msgs:
        sender = m.get("from", "?")
        to = m.get("to", "?")
        addr = "you" if to == me else to
        if m.get("type") == "interface":
            lines.append(f"  [{sender} -> {addr}] INTERFACE: {m.get('signature', '')}")
            if m.get("text"):
                lines.append(f"      {m['text']}")
        else:
            lines.append(f"  [{sender} -> {addr}] {m.get('text', '')}")
    return "\n".join(lines)


def interface_registry(board):
    """The interface contracts currently in force, newest-wins per (author, symbol).

    An interface is not really a message -- it is standing state that stays true after the
    round it was announced in. Delivered once and never repeated, a contract from round 1 is
    buried dozens of turns deep by round 4: still in context (pushed messages are never
    elided), but no longer salient. That is the failure §9.4 actually recorded -- an agent
    holding an interface still invented its own -- so the registry is re-rendered into EVERY
    round notice instead. Re-publishing a corrected signature supersedes the old one here, so
    peers see one current contract rather than two contradictory messages.
    """
    current = {}
    for m in board:
        if m.get("type") != "interface":
            continue
        sig = m.get("signature") or ""
        # Fall back to the raw signature when no name can be parsed, so an unparseable
        # contract is still listed (just never deduped against anything).
        key = (m.get("from"), symbol_name(sig) or sig)
        current[key] = m
    return list(current.values())


def render_registry(entries, me):
    lines = []
    for m in entries:
        owner = m.get("from", "?")
        mark = "  <- yours" if owner == me else ""
        lines.append(f"  {owner}  {m.get('signature', '')}{mark}")
        if m.get("text"):
            lines.append(f"      {m['text']}")
    return "\n".join(lines)


def render_beliefs(beliefs):
    return "\n".join(f"  {peer}: {(beliefs.get(peer) or {}).get('note', '')}"
                     for peer in sorted(beliefs))


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
def dump_context(path, sc, r, step_in_round):
    """Append the EXACT prompt the model is about to receive, before this step runs.

    `agent.messages` is the post-history-processor view (agents.py:534) -- the same list
    handed to the API -- so an elided observation is recorded as its "Old environment output"
    placeholder, not its original text. That is the point: this file answers "what did the
    agent actually see before it decided", which is not recoverable from the trajectory
    (which stores what the tools returned) nor from the board (which stores what was sent).

    One JSON object per line: round, step, sizes, then the full message list. Best-effort --
    a dump failure must never take down a paid run.
    """
    try:
        msgs = sc.messages
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "round": r + 1,
            "step_in_round": step_in_round,
            "global_step": sc.n_steps + 1,
            "n_messages": len(msgs),
            "chars": sum(len(str(m.get("content", ""))) for m in msgs),
            "messages": msgs,
        }
        with path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except Exception as e:
        print(f"    (context dump skipped: {type(e).__name__}: {e})")


def _comm_stats_row(r, aid, delivered, posted, round_steps, *, passed, submitted):
    """One row of comm_stats.json: what this agent received and said this round.

    These counts are the dependent variable of the harness study, so they are recorded even
    though most are recoverable from the board and trajectories -- re-deriving "was this
    directed or broadcast" from a JSON dump for every analysis is how numbers stop matching.
    `refused_interfaces` is only observable HERE: a refused publish never reaches the board
    at all, so it has to be counted from the tool observation.
    """
    names = [c.get("name", "") for st in round_steps for c in st.get("tool_calls", [])]
    return {
        "round": r + 1,
        "agent": aid,
        "steps": len(round_steps),
        "received": len(delivered),
        "sent_directed": sum(1 for m in posted
                             if m.get("type") == "message" and m.get("to") != "all"),
        "sent_broadcast": sum(1 for m in posted
                              if m.get("type") == "message" and m.get("to") == "all"),
        "interfaces_published": sum(1 for m in posted if m.get("type") == "interface"),
        "refused_interfaces": sum(1 for st in round_steps
                                  if "NOT PUBLISHED:" in (st.get("observation") or "")),
        "belief_updates": names.count("update_belief"),
        "no_op": bool(passed),
        "submitted": bool(submitted),
    }


def _format_tool_calls(calls):
    if not calls:
        return "(no tool call)"
    return ", ".join(f"{c['name']}({c['args']})" for c in calls)


NOTICE_HEAD = """\
--- Round {n} begins ---
"""

NOTICE_NOTHING = """
No peer sent you anything in round {prev}.
"""

NOTICE_DELIVERED = """
Messages your peers sent you in round {prev} (you receive these automatically -- there is no
tool to fetch them, and nothing here will be shown to you twice):
{delivered}
"""

NOTICE_REGISTRY = """
Interface contracts currently published — these are the EXACT names to code against, and the
exact names you are on the hook for. They stay listed here every round:
{registry}
"""

NOTICE_BELIEFS = """
Your private notes on your peers (nobody else can see these):
{beliefs}
"""

NOTICE_WORKING = """
Anything you post from now on reaches your peers in round {next}, not this one. So:
  * a peer gave you what you were waiting for -> apply it and run `scoped_submit`;
  * your file is already complete and nothing above changes that -> run `scoped_submit` again
    to confirm you are finished (the run continues to the final round regardless, and your
    patch as it stands then is what gets graded);
  * you are still missing something only a peer can give you -> `send_message` to ask, then
    `no_op` to end your turn and wait for the reply next round.
"""

NOTICE_SUBMITTED = """
You already submitted your patch in round {submitted_in}. You are being given another turn
because your peers may need something from you -- they can only reach you while you keep
taking turns. Decide from what is above:
  * a peer asked you for something (a name, a signature, where something lives) -> answer with
    `send_message`, or `publish_interface` the EXACT names you wrote in your file;
  * a peer told you something that changes your file -> edit it, then `scoped_submit` again;
  * nothing above concerns you -> run `scoped_submit` again to confirm you are still finished.
"""


# Substrings that identify a host-injected round notice (incoming peer mail) and an agent's
# own outgoing message. Both are EPHEMERAL: visible for the round they belong to, gone
# afterwards. Published interfaces are exempt -- the registry reprints them every round, so
# a contract survives while the chatter that carried it does not.
def build_notice(r, aid, delivered, beliefs, submitted_in, registry=()):
    """The whole of what an agent is told at the start of a round: the standing interface
    contracts, its new mail, its private notes, and what to do next. This IS the delivery
    mechanism -- under push there is no tool an agent could call to see any of it.

    The registry comes FIRST and repeats every round; messages are new-only. That split is
    deliberate: a contract is state, a message is an event. An interface still arrives as a
    normal message the round it is published, so the transcript keeps showing WHEN each
    contract appeared -- the registry is what keeps it in view afterwards.
    """
    parts = [NOTICE_HEAD.format(n=r + 1)]
    if registry:
        parts.append(NOTICE_REGISTRY.format(registry=render_registry(registry, aid)))
    if delivered:
        parts.append(NOTICE_DELIVERED.format(prev=r,
                                             delivered=render_messages(delivered, aid)))
    else:
        parts.append(NOTICE_NOTHING.format(prev=r))
    if beliefs:
        parts.append(NOTICE_BELIEFS.format(beliefs=render_beliefs(beliefs)))
    if submitted_in:
        parts.append(NOTICE_SUBMITTED.format(submitted_in=submitted_in))
    else:
        parts.append(NOTICE_WORKING.format(next=r + 2))
    return "".join(parts)


def _notify_round(sc, r, aid, delivered, beliefs, submitted_in=None, registry=()):
    """Push the round notice into the agent's model context, via whichever scaffold is in use.

    This IS the delivery mechanism -- under push there is no tool an agent could call to see
    any of it -- so both backends must receive byte-identical text; only the injection
    mechanics differ (see each scaffold's `inject`).

    Expiry runs FIRST: last round's mail goes before this round's is injected. Best-effort --
    the round loop must never die over a prompt nicety.
    """
    dropped = sc.prune_expired()
    if dropped:
        print(f"    [{aid}] pruned {dropped} expired message entry(ies) from context")
    if r == 0:
        return                    # round 1: empty board, nothing to deliver
    try:
        sc.inject(build_notice(r, aid, delivered, beliefs, submitted_in, registry))
    except Exception as e:
        print(f"    (round notice skipped: {type(e).__name__}: {e})")


def read_beliefs(sc, aid):
    """This agent's private belief store, or {} if it has written none yet (the file simply
    does not exist until the first update_belief). Takes a scaffold, not an env: both
    backends expose read_file, so this works unchanged for either."""
    try:
        data = json.loads(sc.read_file(BELIEFS_FILE_IN_IMAGE.format(aid=aid)))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
def run_agents(inst_dir, spec, rounds, steps_per_round, dump_context_enabled=False,
               stop_when_all_submitted=False):
    import yaml
    sys.path.insert(0, str(Path(__file__).resolve().parent))     # for build_runtime_image
    sys.path.insert(0, str(REPO_DIR / "SWE-agent"))
    from build_runtime_image import ensure_runtime_image
    from scaffolds import SweAgentScaffold

    # The harness is fixed at gen_solver_config time (it decided which comm bins exist in
    # <id>/_comm_bundle), so it is read back rather than re-specified with a flag that could
    # disagree with the bundle the agents are actually running.
    try:
        cell = json.loads((inst_dir / "comm_mode.json").read_text())
    except Exception:
        cell = {"mode": "p2p", "beliefs": False}
    beliefs_on = bool(cell.get("beliefs"))
    # Which agent framework the configs were generated for. Recorded in comm_mode.json at
    # generate time for the same reason the harness is: the artifacts on disk (solver.yaml vs
    # mini.yaml) already committed to it, so re-specifying it here could only disagree.
    scaffold_name = cell.get("scaffold", "swe-agent")
    print(f"  harness: {cell.get('mode', 'p2p')}"
          f"{' + beliefs' if beliefs_on else ''}  |  scaffold: {scaffold_name}")

    if scaffold_name == "mini":
        from mini_scaffold import MiniScaffold as _Scaffold
    else:
        _Scaffold = SweAgentScaffold
        # Bake swe-rex into a derived image once (all agents share the same Pro base). The
        # solver.yaml files already point at this deterministic tag with pull=never. mini
        # talks to the Pro image directly and needs no derived runtime.
        ensure_runtime_image(spec["image"])

    scaffolds, retired = {}, {}
    for a in spec["agents"]:
        aid = a["id"]
        sc = _Scaffold(inst_dir, aid, spec["image"])
        sc.start()
        scaffolds[aid], retired[aid] = sc, False
        print(f"  started {aid}")

    board = []
    # What was published at the END of the previous round -- i.e. exactly what gets pushed
    # into contexts now. The barrier already partitions messages by round, so every message
    # is delivered exactly once to every eligible recipient and no read cursor is needed.
    deliveries = []
    submitted_round = {}              # aid -> round it FIRST submitted in (for the notice)
    stats = []                        # per agent per round -> comm_stats.json
    for r in range(rounds):
        print(f"  -- round {r + 1}/{rounds} --")
        frozen = list(board)          # every agent this round sees the SAME board state
        frozen_keys = {_msg_key(m) for m in frozen}
        registry = interface_registry(frozen)   # standing contracts, identical for everyone
        submitted, pending = {}, []
        for a in spec["agents"]:
            aid = a["id"]
            if retired[aid]:          # terminal failure only -- NOT "already submitted"
                continue
            sc = scaffolds[aid]
            if hasattr(sc, "set_round"):      # mini stamps its scope-violation log
                sc.set_round(r + 1)
            # The board still goes in even though nothing reads it there: the bins append to
            # it, and --submit-gate's publish check needs the agent's own past announcements.
            sc.write_file(COMM_BOARD_IN_IMAGE, json.dumps(frozen))    # identical for everyone
            sc.write_file(ROUND_FILE_IN_IMAGE, str(r + 1))
            mine = [m for m in deliveries if visible_to(m, aid)]
            beliefs = read_beliefs(sc, aid) if beliefs_on else {}
            _notify_round(sc, r, aid, mine, beliefs, submitted_round.get(aid), registry)
            if mine:
                print(f"    [{aid}] delivered {len(mine)} message(s) from round {r}")
            round_steps = []
            passed = False
            ctx_path = inst_dir / aid / "context" / "messages.jsonl"
            for k in range(steps_per_round):
                if dump_context_enabled:      # BEFORE the step: what it sees when deciding
                    dump_context(ctx_path, sc, r, k + 1)
                try:
                    res = sc.step()
                except Exception as e:
                    # SWE-agent turns most failures into done-steps, but re-raises
                    # TotalCostLimitExceededError -- unguarded that would abort run_agents
                    # entirely and skip the diff collection below, losing EVERY agent's work.
                    print(f"    [{aid}] step raised {type(e).__name__}: {e} -- retiring agent")
                    retired[aid] = True
                    break
                record = res.as_record()
                round_steps.append(record)
                print(f"    [{aid}] step {record['step']}: {_format_tool_calls(record['tool_calls'])}")
                if NOOP_MARKER in (res.observation or ""):
                    print(f"    [{aid}] passed this round (no_op)")
                    passed = True
                    break             # turn over for this round; agent is NOT done
                if res.done:
                    # `done` covers ~10 outcomes, only one of which is a real submission
                    # (agents.py sets exit_status "submitted"/"submitted (...)"). The rest --
                    # exit_cost, exit_context, exit_format, exit_command_timeout, exit_forfeit,
                    # exit_error, ... -- mean the agent cannot usefully continue, so retire it
                    # instead of burning a wasted step on it every remaining round.
                    if res.submitted:
                        submitted[aid] = True
                        submitted_round.setdefault(aid, r + 1)
                    else:
                        print(f"    [{aid}] ended: {res.exit_status} -- retiring agent")
                        retired[aid] = True
                    break
            traj_dir = inst_dir / aid / "traj"
            traj_dir.mkdir(parents=True, exist_ok=True)
            (traj_dir / f"round_{r + 1}.json").write_text(json.dumps(round_steps, indent=2))
            try:            # stage this agent's new messages; do NOT publish them yet
                posted = json.loads(sc.read_file(COMM_BOARD_IN_IMAGE))
                if not isinstance(posted, list):
                    posted = []
            except Exception:
                posted = []
            posted_now = [m for m in posted
                          if isinstance(m, dict) and _msg_key(m) not in frozen_keys]
            pending.extend(posted_now)
            if beliefs_on:
                # Post-turn state, so the archive shows what the agent believed going INTO
                # the next round -- which is what the next round's notice will replay.
                after = read_beliefs(sc, aid)
                (inst_dir / aid / f"beliefs_round_{r + 1}.json").write_text(
                    json.dumps(after, indent=2))
            stats.append(_comm_stats_row(r, aid, mine, posted_now, round_steps,
                                         passed=passed, submitted=bool(submitted.get(aid))))
        board = merge_board(board, pending)          # publish once, at the round barrier
        deliveries = board[len(frozen):]             # pushed into contexts next round
        for m in deliveries:
            print(f"    [board] {m.get('from')} -> {m.get('to', 'all')}: "
                  f"{m.get('signature') or m.get('text')}")
        (inst_dir / f"board_after_round_{r + 1}.json").write_text(json.dumps(board, indent=2))
        # Rewritten every round, not just at the end, so a run killed mid-flight still leaves
        # usable communication counts behind.
        (inst_dir / "comm_stats.json").write_text(json.dumps(stats, indent=2))
        active = [a["id"] for a in spec["agents"] if not retired[a["id"]]]
        # Submitting no longer ends the run. An agent that finishes in round 2 keeps taking
        # turns, because it is the ONLY way a peer can still reach it -- and its patch stays
        # editable, so a late answer can still change what its file does. The whole round
        # budget is spent unless --stop-when-all-submitted restores the old behaviour.
        if stop_when_all_submitted and active and all(submitted.get(aid) for aid in active):
            print("  all agents submitted in the same round -- stopping early")
            break
        if not active:
            print("  no agents left to run")
            break

    for a in spec["agents"]:
        aid = a["id"]
        sc = scaffolds[aid]
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
            diff = sc.collect_diff(pathspec)
            (inst_dir / f"{aid}.patch").write_text(diff)
            print(f"  {aid}: scoped diff -> {aid}.patch ({len(diff.splitlines())} lines)")
        except Exception as e:
            # Never let one agent's collection failure strand the other agents' containers --
            # that leaks disk until the next manual cleanup.
            print(f"  {aid}: diff collection FAILED: {e}")
        finally:
            sc.close()
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
    ap.add_argument("--rounds", type=int, default=10, help="(agents mode) coordination rounds")
    ap.add_argument("--stop-when-all-submitted", action="store_true",
                    help="End the run early once every active agent submits in the same "
                         "round (the old default). Off by default: all --rounds rounds now "
                         "run, so a peer can still reach an agent that finished early.")
    ap.add_argument("--steps-per-round", type=int, default=6,
                    help="(agents mode) agent.step() calls per agent per round")
    ap.add_argument("--prefix", default="multiagent")
    ap.add_argument("--grade", action="store_true", help="Run the Pro evaluator after merge")
    ap.add_argument("--dockerhub_username", default="jefzda")
    ap.add_argument("--dump-context", action="store_true",
                    help="(agents mode) Before EVERY step, append the exact prompt that step "
                         "will send -- agent.messages, i.e. post-history-processor, what the "
                         "model actually sees -- to <id>/<agent>/context/messages.jsonl (one "
                         "JSON object per line: round, step_in_round, global_step, n_messages, "
                         "chars, messages). Off by default: it writes the whole conversation "
                         "once per step, so the file grows quadratically over a run.")
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
        try:
            cell = json.loads((inst_dir / "comm_mode.json").read_text())
            harness = cell.get("mode", "p2p") + (" + beliefs" if cell.get("beliefs") else "")
        except Exception:
            harness = "unknown -- regenerate with gen_solver_config.py"
        print(f"\n=== {inst_dir.name} ({spec['num_agents']} agents, mode={args.mode}, "
              f"harness={harness}) ===")

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
            run_agents(inst_dir, spec, args.rounds, args.steps_per_round,
                       dump_context_enabled=args.dump_context)
        merge_and_grade(inst_dir, root, args.prefix, args.grade, args.dockerhub_username)


if __name__ == "__main__":
    main()
