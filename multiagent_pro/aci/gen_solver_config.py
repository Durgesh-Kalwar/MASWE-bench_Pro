#!/usr/bin/env python
"""Stage W3c — generate one SWE-agent solver config per agent from a built multi-agent spec.

Reads `multiagent_pro_out/<id>/spec.json` (produced by build_multiagent_pro.py) and emits,
for each agent, a self-contained `agent_<k>/solver.yaml` that wires the scoped multi-agent
ACI:

  * env.deployment   -> the instance's Pro Docker image (repo baked in at /app)
  * env.repo         -> preexisting repo, repo_name=app, reset to base_commit
  * agent.tools      -> bash DISABLED + function_calling; only our scoped_fs + comm bundles
                        (absolute paths). Scope/identity/board are injected as env_variables
                        the bins read (SCOPE_FILES, REPO_ROOT, AGENT_ID, COMM_BOARD,
                        AGENTS_ROSTER, COMM_MODE) — no dependency on SWE-agent's own
                        (missing) tool libs.
  * problem_statement-> the agent's local_issue.md (full issue + its focus highlight)

The COMMUNICATION HARNESS is a study variable here (`--comm-mode`, `--beliefs`), so the comm
bundle is not used in place: it is MATERIALIZED per instance into `<id>/_comm_bundle/` with
only the bins and tool declarations that harness has. The declaration is the only thing the
model sees, so a cell that lacks addressed messaging must not merely refuse a recipient
argument -- it must not have one. Materializing also archives the exact harness beside the
run, which is what makes a harness comparison reproducible.

Also writes `<id>/roster.json` (the agent->gold_file roster list_agents surfaces) and
`<id>/comm_mode.json` (the harness, so orchestrate.py reads the cell from one source of truth
instead of duplicating flags that could disagree with the generated bundle). The round-based
orchestrator (orchestrate.py) consumes all of these.
"""
import argparse
import json
import shutil
from pathlib import Path

import yaml

from build_runtime_image import derived_runtime_tag

REPO_DIR = Path(__file__).resolve().parent.parent.parent          # MASWE-bench_Pro/
ACI_TOOLS = Path(__file__).resolve().parent / "tools"             # .../multiagent_pro/aci/tools
SCOPED_FS_BUNDLE = str(ACI_TOOLS / "scoped_fs")
COMM_BUNDLE_SRC = ACI_TOOLS / "comm"          # template; materialized per instance, see below

REPO_ROOT_IN_IMAGE = "/app"     # Pro images check the repo out at /app (not /testbed)
COMM_BOARD_IN_IMAGE = "/root/comm/board.json"

COMM_MODES = ("broadcast", "p2p")


# --------------------------------------------------------------------------- #
# System / instance templates
#
# Assembled from fragments rather than written out per cell: the only thing that varies
# between communication harnesses is the delivery paragraph, and duplicating the other 20
# lines three times is how they drift apart. Note these strings reach SWE-agent as Jinja
# templates ({{command_docs}} is rendered there), so they are concatenated, never .format()ed.
# --------------------------------------------------------------------------- #
SYSTEM_HEAD_SCOPED = """\
You are ONE of several software-engineering agents collaborating to resolve a GitHub issue
in a shared repository. The work has been split by file: you OWN exactly one file and may
read and edit ONLY the files in your scope (run `scoped_list` to see them). Every other
file in the repo is invisible to you — there is no `bash` tool and no general file access.

Because each agent sees only its own files, you must COORDINATE. If you define or change
something a peer depends on (a function, class, or signature they must call), announce it
with `publish_interface` — publish the EXACT names you actually wrote, and only for files
you own; publishing a name you have not actually written is REFUSED, because your peers
will code against whatever you announce. If you need something owned by another file, ask
for it with `send_message`.

Coordination runs BOTH ways. Your peers cannot see inside the files you own any more than you
can see inside theirs, so a question about your files is one only YOU can settle -- answer it.
"""

SYSTEM_HEAD_FULL = """\
You are ONE of several software-engineering agents collaborating to resolve a GitHub issue
in a shared repository. Each agent is primarily responsible for one file, but in THIS setting
you have FULL read/write access to the entire repository — you may read and edit ANY file —
EXCEPT the files owned by your peers (run `scoped_list` to see your primary file and the
peer-owned files you may not touch). Those peer files are the only ones off-limits.

Focus on your assigned file, but edit any other file you need to make the fix complete and
consistent. Because peers can also edit shared (non-owned) files, COORDINATE: if you change
something a peer depends on, announce it with `publish_interface` — publish the EXACT names
you actually wrote, and only for files you own; publishing a name you have not actually
written is REFUSED, because your peers will code against whatever you announce. If a peer
owns a file you need changed, ask with `send_message`. Avoid clobbering a shared file
another agent is actively editing.

Coordination runs BOTH ways. Peer-owned files are invisible to you and yours are invisible to
them, so a question about the files you own is one only YOU can settle -- answer it.
"""

# Common to every harness: rounds, and the fact that receiving costs no action.
DELIVERY_COMMON = """
WORK PROCEEDS IN ROUNDS, and messages travel one round at a time. You never have to fetch
them: everything your peers post during a round is DELIVERED to you automatically at the
start of the next one, and appears in front of you before your turn begins. Likewise,
anything you post now reaches them next round, not this one — so ask early.

Interface contracts are different from messages: a message is an event, a contract is
standing state. Every contract anyone has published — including your own — is listed again
at the start of EVERY round, so you never have to remember or re-derive a signature. Code
against the names in that list exactly as written; do not invent your own name for something
already published there, and do not silently change a signature you published (republish it
if it must change).
"""

COORD_BROADCAST = """
Every message you send goes to ALL of your peers. There is no way to write to just one of
them, and no way to overhear less than everything: whatever anyone says, everyone gets.
"""

COORD_P2P = """
`send_message` may be addressed to ONE peer by id, or to 'all'. A message addressed to a
single agent is delivered to that agent alone — no one else sees it, so choose the recipient
who can actually act on it. `publish_interface` always reaches everyone.
"""

COORD_BELIEFS = """
You also keep PRIVATE notes on your peers with `update_belief`: what each one owns, what they
have promised you, what they still owe you, and whether a claim of theirs has actually shown
up in the code. No peer ever sees your notes, and they are shown back to you at the start of
every round. Keep them current and use them to decide whom to ask for what.
"""

SYSTEM_BULLETS = """
  * Do not guess a name a peer is supposed to define — a wrong guess silently breaks the
    build. Ask with `send_message`, then run `no_op` to end your turn and wait; you get
    another turn next round, with their reply already in front of you.
  * Answer what your peers ask you. Nobody else can see inside the files you own, so an
    unanswered question stays unanswered and blocks that peer for a whole round. Answer from
    what you have ALREADY written -- being unfinished is no reason to withhold a name or
    signature that exists now; just say so if it may still change.
  * Run `scoped_submit` when your changes are complete. You will still get a turn in later
    rounds so peers can reach you; if nothing has changed for you, simply `scoped_submit`
    again to confirm you are finished. Submitting is NOT final: if you later edit your file
    and run `scoped_submit` again, the new version REPLACES the old one.

Available tools:
{{command_docs}}
"""

INSTANCE_HEAD = """\
You are working in the repository checked out at {{working_dir}}.

{{problem_statement}}

Reminders:
- Run `scoped_list` first to see the file(s) you may edit, and `list_agents` to see peers.
- You never fetch messages: whatever your peers post reaches you automatically at the start
  of the next round.
- `publish_interface` anything peers must code against — the exact name you actually wrote.
"""

INSTANCE_BELIEFS = """\
- `update_belief` to keep private notes on what each peer owns, owes you, and has claimed.
"""

INSTANCE_TAIL = """\
- Make the minimal change needed in YOUR file(s); do not try to fix peers' files.
- Missing something only a peer can tell you? `send_message` to ask, then `no_op` to wait for
  their reply next round — do not guess.
- A peer asked you something? Answer it from what you have written so far — you do not need to
  be finished to be useful.
- Run `scoped_submit` when done.
"""


def system_template(scope_mode: str, comm_mode: str, beliefs: bool) -> str:
    head = SYSTEM_HEAD_FULL if scope_mode == "full" else SYSTEM_HEAD_SCOPED
    coord = COORD_BROADCAST if comm_mode == "broadcast" else COORD_P2P
    return head + DELIVERY_COMMON + coord + (COORD_BELIEFS if beliefs else "") + SYSTEM_BULLETS


def instance_template(beliefs: bool) -> str:
    return INSTANCE_HEAD + (INSTANCE_BELIEFS if beliefs else "") + INSTANCE_TAIL


# --------------------------------------------------------------------------- #
# Comm bundle materialization
# --------------------------------------------------------------------------- #
def materialize_comm_bundle(inst_dir: Path, *, comm_mode: str, beliefs: bool) -> str:
    """Write `<inst_dir>/_comm_bundle/` holding exactly the tools this harness has.

    SWE-agent reads a bundle's declarations from `<bundle>/config.yaml` at a fixed path and
    hard-fails at agent.setup() if a declared tool has no matching bin (tools.py
    _check_available_commands), so declarations and bins must be selected together -- which is
    the whole reason this is generated rather than switched at runtime.
    """
    defs = yaml.safe_load((COMM_BUNDLE_SRC / "tool_defs.yaml").read_text())
    selected = {
        "list_agents": defs["list_agents"],
        "send_message": defs[f"send_message_{comm_mode}"],
        "publish_interface": defs["publish_interface"],
    }
    if beliefs:
        selected["update_belief"] = defs["update_belief"]

    out = inst_dir / "_comm_bundle"
    shutil.rmtree(out, ignore_errors=True)            # never leave a previous cell's tools behind
    (out / "bin").mkdir(parents=True, exist_ok=True)
    (out / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMM_BUNDLE_SRC / "install.sh", out / "install.sh")
    for f in sorted((COMM_BUNDLE_SRC / "lib").glob("*.py")):
        shutil.copy2(f, out / "lib" / f.name)
    for name in selected:                             # bin name == tool name, by construction
        dst = out / "bin" / name
        shutil.copy2(COMM_BUNDLE_SRC / "bin" / name, dst)
        dst.chmod(0o755)
    (out / "config.yaml").write_text(
        yaml.safe_dump({"tools": selected}, sort_keys=False, width=100)
    )
    return str(out.resolve())


def build_agent_config(spec, agent, inst_dir, *, model, cost_limit, roster, comm_bundle,
                       api_base=None, call_limit=0, submit_gate=False, last_n_observations=5,
                       comm_mode="p2p", beliefs=False):
    inst_id = spec["instance_id"]
    aid = agent["id"]
    scope_mode = agent.get("scope_mode", "allow")
    model_cfg = {"name": model, "per_instance_cost_limit": cost_limit, "top_p": None}
    if call_limit:
        model_cfg["per_instance_call_limit"] = call_limit
    if api_base:
        # Self-hosted / institute-proxied OpenAI-compatible endpoint (e.g. ASU RC). litellm has
        # no built-in pricing for these model names -- generate() already made sure (via
        # model_pricing.ensure_registered) that pricing is either already known to litellm or
        # saved in custom_model_pricing.json, so completion_cost() at run time succeeds and
        # per_instance_cost_limit works normally instead of needing to be forced to 0.
        # api_key uses "$ENV_VAR" indirection (GenericAPIModelConfig resolves it from os.environ
        # at call time) so the real secret never lands in the generated solver.yaml.
        model_cfg["api_base"] = api_base
        model_cfg["api_key"] = "$OPENAI_API_KEY"
    return {
        "env": {
            "deployment": {
                "type": "docker",
                # A swe-rex *runtime* image derived from the Pro base (see
                # build_runtime_image.py): it bakes in a glibc-2.31-compatible portable
                # Python + swerex-remote on PATH. python_standalone_dir=None + pull=never
                # means swe-rex just execs the pre-installed server — no per-run compile,
                # no in-container network. orchestrate.py builds this tag before start.
                "image": derived_runtime_tag(spec["image"]),
                "python_standalone_dir": None,
                "pull": "never",
            },
            "repo": {
                "type": "preexisting",
                "repo_name": "app",            # -> SWE-agent cd's /app and resets there
                "base_commit": spec["base_commit"],
            },
        },
        "agent": {
            # top_p=null: SWE-agent defaults top_p=1.0 and sends it whenever temperature
            # isn't set (the default path), but Sonnet 5 rejects top_p ("deprecated for this
            # model") with a BadRequestError that retry-loops forever. 1.0 is the identity
            # value, so dropping it is behavior-neutral for models that still accept it.
            "model": model_cfg,
            "templates": {
                "system_template": system_template(scope_mode, comm_mode, beliefs),
                "instance_template": instance_template(beliefs),
                "next_step_template": "OBSERVATION:\n{{observation}}",
                "next_step_no_output_template":
                    "Your command ran successfully and did not produce any output.",
            },
            "tools": {
                "enable_bash_tool": False,
                "parse_function": {"type": "function_calling"},
                "submit_command": "scoped_submit",
                "env_variables": {
                    "REPO_ROOT": REPO_ROOT_IN_IMAGE,
                    "SCOPE_FILES": json.dumps(agent["scope"]),
                    # scope_mode="allow": SCOPE_FILES is a strict allowlist (gold + distractors).
                    # scope_mode="full": denylist -- any in-repo path is editable EXCEPT SCOPE_DENY
                    # (the other agents' gold files); SCOPE_FILES then names only the primary file.
                    "SCOPE_MODE": scope_mode,
                    "SCOPE_DENY": json.dumps(agent.get("deny", [])),
                    "AGENT_ID": aid,
                    "COMM_BOARD": COMM_BOARD_IN_IMAGE,
                    "AGENTS_ROSTER": json.dumps(roster),
                    # Communication harness. The generated bundle already withholds the
                    # recipient argument in broadcast mode; send_message re-forces to="all"
                    # from this var so the topology cannot be circumvented either way.
                    "COMM_MODE": comm_mode,
                    # --submit-gate only: scoped_submit refuses until the agent has announced
                    # any public def/class its edits delete. Empty string = gate off
                    # (scoped_submit tests [ -n "$SUBMIT_GATE" ]).
                    "SUBMIT_GATE": "1" if submit_gate else "",
                },
                "bundles": [
                    {"path": SCOPED_FS_BUNDLE},
                    {"path": comm_bundle},
                ],
            },
            # Sliding window over ALL observations ever, not per round -- SWE-agent has no
            # notion of rounds. n=5 (the SWE-agent 0.7 default) is tuned for a single-agent
            # loop where stale file dumps are noise. Peer messages are NOT at risk from it any
            # more: they are pushed into history as message_type "user", and
            # last_n_observations only ever elides message_type "observation". Still worth
            # raising past --steps-per-round so an agent keeps a full round of its own file
            # views in view.
            "history_processors": [
                {"type": "last_n_observations", "n": last_n_observations}
            ],
        },
        "problem_statement": {
            "type": "text_file",
            "path": str((inst_dir / aid / "local_issue.md").resolve()),
            "id": f"{inst_id}__{aid}",
        },
        "output_dir": str((inst_dir / aid / "traj").resolve()),
    }


def generate(inst_dir: Path, *, model, cost_limit, dockerhub_username, api_base=None,
             call_limit=0, submit_gate=False, last_n_observations=5, comm_mode="p2p",
             beliefs=False):
    spec = json.loads((inst_dir / "spec.json").read_text())
    inst_id = spec["instance_id"]

    # Resolve the Pro image (same derivation the evaluator uses).
    import sys
    sys.path.insert(0, str(REPO_DIR / "helper_code"))
    from image_uri import get_dockerhub_image_uri
    spec["image"] = get_dockerhub_image_uri(inst_id, dockerhub_username, spec["repo"])

    roster = [{"id": a["id"], "gold_file": a["gold_file"]} for a in spec["agents"]]
    (inst_dir / "roster.json").write_text(json.dumps(roster, indent=2))
    (inst_dir / "comm_mode.json").write_text(
        json.dumps({"mode": comm_mode, "beliefs": bool(beliefs)}, indent=2)
    )
    comm_bundle = materialize_comm_bundle(inst_dir, comm_mode=comm_mode, beliefs=beliefs)

    written = []
    for agent in spec["agents"]:
        cfg = build_agent_config(spec, agent, inst_dir, model=model,
                                 cost_limit=cost_limit, roster=roster,
                                 comm_bundle=comm_bundle,
                                 api_base=api_base, call_limit=call_limit,
                                 submit_gate=submit_gate,
                                 last_n_observations=last_n_observations,
                                 comm_mode=comm_mode, beliefs=beliefs)
        out = inst_dir / agent["id"] / "solver.yaml"
        out.write_text(yaml.safe_dump(cfg, sort_keys=False, width=100))
        written.append(out)
    return spec["image"], written


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="multiagent_pro_out",
                    help="Build-output root containing <id>/spec.json")
    ap.add_argument("--instances", nargs="*", help="Restrict to these instance ids")
    ap.add_argument("--model", default="claude-sonnet-4-6", help="LM name for solver agents")
    ap.add_argument("--per-instance-cost-limit", type=float, default=1.0)
    ap.add_argument("--dockerhub_username", default="jefzda")
    ap.add_argument("--api-base", default=None,
                    help="Custom OpenAI-compatible endpoint (e.g. an institute-hosted proxy). "
                         "api_key is read from $OPENAI_API_KEY at run time. If --model isn't "
                         "already priced by litellm, pass --price-per-million-tokens and "
                         "--context-window (from your institute's model page) the first time; "
                         "the pricing is saved to custom_model_pricing.json and reused after.")
    ap.add_argument("--price-per-million-tokens", type=float, default=None,
                    help="Blended $ price per 1M tokens for an unregistered --model (from your "
                         "institute/provider's model page). Only needed once per model name.")
    ap.add_argument("--context-window", type=int, default=None,
                    help="Context window (tokens) for an unregistered --model. Only needed once "
                         "per model name; paired with --price-per-million-tokens.")
    ap.add_argument("--per-instance-call-limit", type=int, default=0,
                    help="Hard cap on API calls per agent, independent of $ cost. Extra safety "
                         "net alongside per-instance-cost-limit.")
    ap.add_argument("--comm-mode", choices=COMM_MODES, default="p2p",
                    help="Communication harness (default: p2p). 'p2p': send_message may be "
                         "addressed to one "
                         "peer by id (delivered to that agent alone) or to 'all'. 'broadcast': "
                         "send_message has NO recipient argument at all and always reaches "
                         "every peer. publish_interface broadcasts in both. Delivery is push "
                         "in both -- there is no read tool; the host injects each agent's "
                         "messages into its context at the start of the next round.")
    ap.add_argument("--beliefs", action="store_true",
                    help="Give agents `update_belief <peer> --note ...`: a PRIVATE per-peer "
                         "note store no other agent ever sees, shown back to the agent at the "
                         "start of every round and archived per round for analysis. Without "
                         "it, agents must infer whom to address from the messages themselves.")
    ap.add_argument("--last-n-observations", type=int, default=5, metavar="N",
                    help="Keep the full text of only the last N tool observations per agent; "
                         "older ones are replaced by 'Old environment output: (K lines "
                         "omitted)'. The window spans ALL rounds (SWE-agent has no round "
                         "concept), and actions/thoughts are never elided -- only tool output. "
                         "Peer messages are exempt (they are pushed as message_type 'user', "
                         "which this processor never elides), so N now only affects the "
                         "agent's own file views. Use N >= --steps-per-round to keep a full "
                         "round of them.")
    ap.add_argument("--submit-gate", action="store_true",
                    help="Coordination gate (OFF by default): scoped_submit refuses until the "
                         "agent has announced (publish_interface / send_message) any public "
                         "def/class its edits delete. A pure refusal check -- the harness "
                         "never calls comm tools for the agent.")
    args = ap.parse_args()

    # No-ops immediately for models litellm already prices (claude-*, gpt-*, ...); only prompts
    # via UnregisteredModelError for genuinely unknown models (self-hosted / institute-proxied).
    from model_pricing import ensure_registered
    ensure_registered(args.model, price_per_million=args.price_per_million_tokens,
                      context_window=args.context_window)

    root = Path(args.output)
    inst_dirs = ([root / i for i in args.instances] if args.instances
                 else [p for p in root.iterdir() if (p / "spec.json").exists()])
    if not inst_dirs:
        raise SystemExit(f"No <id>/spec.json under {root}/")
    for d in inst_dirs:
        image, written = generate(d, model=args.model,
                                  cost_limit=args.per_instance_cost_limit,
                                  dockerhub_username=args.dockerhub_username,
                                  api_base=args.api_base,
                                  call_limit=args.per_instance_call_limit,
                                  submit_gate=args.submit_gate,
                                  last_n_observations=args.last_n_observations,
                                  comm_mode=args.comm_mode, beliefs=args.beliefs)
        cell = args.comm_mode + (" + beliefs" if args.beliefs else "")
        print(f"{d.name}: image={image}  harness={cell}  ->  {len(written)} solver config(s)")


if __name__ == "__main__":
    main()
