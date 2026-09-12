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
# ONE system prompt, not a set of fragments. The harness cells (broadcast/p2p, scoped/full,
# beliefs) used to each swap a paragraph in; that made the prompt hard to read and easy to
# drift. The tool list below is rendered by SWE-agent from the bundle actually installed, so
# a cell that has `update_belief` documents it there without a paragraph here. NOTE: the text
# describes BROADCAST delivery and repo-wide access minus peer files -- i.e.
# `--comm-mode broadcast` with `--distractors -1`. Other cells need it adjusted.
SYSTEM_PROMPT = """\
You are one of several software-engineering agents fixing the same GitHub issue in a shared
repository. You own one file in the repository and you may read and edit anything in this file.

Each agent owns one file. You may read and edit anything in the repository except the files
your peers own; those are invisible to you, and your own file is invisible to them. Run
`scoped_list` to see both lists.

Because your peers cannot read your code, they will not discover the names you choose — you
have to tell them, and they have to tell you. Ask for whatever you need.

The problem statement and requirements below are complete and unedited. What you are not
given is the new interfaces your peers introduce: the interface section lists only the entries
for your own file, plus any that name no file. The names a peer invents are not there.

The run lasts 10 rounds. Each round you get up to 6 steps (tool calls). Messages you send
during a round arrive at your peers at the start of the next one, and theirs arrive the same
way. A message goes to every peer at once; you cannot address only one agent.

When you write a name a peer must call — a function, class, or signature — announce it with
`publish_interface`, using the exact name you actually wrote. Publishing a name you have not
written is refused by the tool. Published interfaces persist and are reprinted to everyone at
the start of every round. Messages are not — they arrive once at the beginning of the round
and then they are gone.

Your team has 10 rounds to fix the issue. You can submit your patch multiple times. Your patch
as it stands at the end of the final round is what gets graded to resolve the issue.

Available tools:
{{command_docs}}
"""

INSTANCE_PROMPT = """\
You are working in the repository checked out at {{working_dir}}.

{{problem_statement}}
"""

def system_template(scope_mode: str, comm_mode: str, beliefs: bool) -> str:
    """The single system prompt. Arguments are kept so callers need no change, and so a cell
    that needs different wording has one obvious place to branch."""
    return SYSTEM_PROMPT


def instance_template(beliefs: bool) -> str:
    """The task hand-off: where the repo is, and this agent's (redacted) issue text."""
    return INSTANCE_PROMPT


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
                       api_base=None, call_limit=0, submit_gate=False, last_n_observations=6,
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
             call_limit=0, submit_gate=False, last_n_observations=6, comm_mode="p2p",
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
    ap.add_argument("--last-n-observations", type=int, default=6, metavar="N",
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
