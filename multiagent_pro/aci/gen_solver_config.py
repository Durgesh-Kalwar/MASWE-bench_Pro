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
                        AGENTS_ROSTER) — no dependency on SWE-agent's own (missing) tool libs.
  * problem_statement-> the agent's local_issue.md (full issue + its focus highlight)

Also writes `<id>/roster.json` (the agent->gold_file roster the comm tools surface via
list_agents). The round-based orchestrator (orchestrate.py) consumes these configs.
"""
import argparse
import json
from pathlib import Path

import yaml

from build_runtime_image import derived_runtime_tag

REPO_DIR = Path(__file__).resolve().parent.parent.parent          # MASWE-bench_Pro/
ACI_TOOLS = Path(__file__).resolve().parent / "tools"             # .../multiagent_pro/aci/tools
SCOPED_FS_BUNDLE = str(ACI_TOOLS / "scoped_fs")
COMM_BUNDLE = str(ACI_TOOLS / "comm")

REPO_ROOT_IN_IMAGE = "/app"     # Pro images check the repo out at /app (not /testbed)
COMM_BOARD_IN_IMAGE = "/root/comm/board.json"

SYSTEM_TEMPLATE = """\
You are ONE of several software-engineering agents collaborating to resolve a GitHub issue
in a shared repository. The work has been split by file: you OWN exactly one file and may
read and edit ONLY the files in your scope (run `scoped_list` to see them). Every other
file in the repo is invisible to you — there is no `bash` tool and no general file access.

Because each agent sees only its own files, you must COORDINATE. If you define or change
something a peer depends on (a function, class, or signature they must call), announce it
with `publish_interface` — publish the EXACT names you actually wrote, and only for files
you own. If you need something owned by another file, ask for it with `send_message`.

WORK PROCEEDS IN ROUNDS, and the message board advances one round at a time: messages you
post are delivered to your peers in the NEXT round, and `read_messages` shows you what peers
posted in PREVIOUS rounds (only what is new, never your own messages). So:

  * Run `read_messages` at the start of EVERY round, before editing and before submitting --
    a peer may be blocked waiting on an answer only you can give.
  * Do not guess a name a peer is supposed to define — a wrong guess silently breaks the
    build. Ask with `send_message`, then run `no_op` to end your turn and wait; you get
    another turn next round, with their reply readable.
  * Run `scoped_submit` when your file's changes are complete. You will still get a turn in
    later rounds so peers can reach you; if nothing has changed for you, simply
    `scoped_submit` again to confirm you are finished.

Available tools:
{{command_docs}}
"""

FULL_SYSTEM_TEMPLATE = """\
You are ONE of several software-engineering agents collaborating to resolve a GitHub issue
in a shared repository. Each agent is primarily responsible for one file, but in THIS setting
you have FULL read/write access to the entire repository — you may read and edit ANY file —
EXCEPT the files owned by your peers (run `scoped_list` to see your primary file and the
peer-owned files you may not touch). Those peer files are the only ones off-limits.

Focus on your assigned file, but edit any other file you need to make the fix complete and
consistent. Because peers can also edit shared (non-owned) files, COORDINATE: if you change
something a peer depends on, announce it with `publish_interface` — publish the EXACT names
you actually wrote, and only for files you own; if a peer owns a file you need changed, ask
with `send_message`. Avoid clobbering a shared file another agent is actively editing.

WORK PROCEEDS IN ROUNDS, and the message board advances one round at a time: messages you
post are delivered to your peers in the NEXT round, and `read_messages` shows you what peers
posted in PREVIOUS rounds (only what is new, never your own messages). So:

  * Run `read_messages` at the start of EVERY round, before editing and before submitting --
    a peer may be blocked waiting on an answer only you can give.
  * Do not guess a name a peer is supposed to define — a wrong guess silently breaks the
    build. Ask with `send_message`, then run `no_op` to end your turn and wait; you get
    another turn next round, with their reply readable.
  * Run `scoped_submit` when your changes are complete. You will still get a turn in later
    rounds so peers can reach you; if nothing has changed for you, simply `scoped_submit`
    again to confirm you are finished.

Available tools:
{{command_docs}}
"""

INSTANCE_TEMPLATE = """\
You are working in the repository checked out at {{working_dir}}.

{{problem_statement}}

Reminders:
- Run `scoped_list` first to see the file(s) you may edit, and `list_agents` to see peers.
- Run `read_messages` before each edit; `publish_interface` anything peers must code against.
- Make the minimal change needed in YOUR file(s); do not try to fix peers' files.
- Missing something only a peer can tell you? `send_message` to ask, then `no_op` to wait for
  their reply next round — do not guess.
- Run `scoped_submit` when done.
"""


def build_agent_config(spec, agent, inst_dir, *, model, cost_limit, roster, api_base=None,
                       call_limit=0, submit_gate=False):
    inst_id = spec["instance_id"]
    aid = agent["id"]
    scope_mode = agent.get("scope_mode", "allow")
    system_template = FULL_SYSTEM_TEMPLATE if scope_mode == "full" else SYSTEM_TEMPLATE
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
                "system_template": system_template,
                "instance_template": INSTANCE_TEMPLATE,
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
                    # --submit-gate only: scoped_submit refuses until the agent has ITSELF
                    # read the current board (and announced any public-symbol removal).
                    # Empty string = gate off (scoped_submit tests [ -n "$SUBMIT_GATE" ]).
                    "SUBMIT_GATE": "1" if submit_gate else "",
                },
                "bundles": [
                    {"path": SCOPED_FS_BUNDLE},
                    {"path": COMM_BUNDLE},
                ],
            },
            "history_processors": [{"type": "last_n_observations", "n": 5}],
        },
        "problem_statement": {
            "type": "text_file",
            "path": str((inst_dir / aid / "local_issue.md").resolve()),
            "id": f"{inst_id}__{aid}",
        },
        "output_dir": str((inst_dir / aid / "traj").resolve()),
    }


def generate(inst_dir: Path, *, model, cost_limit, dockerhub_username, api_base=None,
             call_limit=0, submit_gate=False):
    spec = json.loads((inst_dir / "spec.json").read_text())
    inst_id = spec["instance_id"]

    # Resolve the Pro image (same derivation the evaluator uses).
    import sys
    sys.path.insert(0, str(REPO_DIR / "helper_code"))
    from image_uri import get_dockerhub_image_uri
    spec["image"] = get_dockerhub_image_uri(inst_id, dockerhub_username, spec["repo"])

    roster = [{"id": a["id"], "gold_file": a["gold_file"]} for a in spec["agents"]]
    (inst_dir / "roster.json").write_text(json.dumps(roster, indent=2))

    written = []
    for agent in spec["agents"]:
        cfg = build_agent_config(spec, agent, inst_dir, model=model,
                                 cost_limit=cost_limit, roster=roster,
                                 api_base=api_base, call_limit=call_limit,
                                 submit_gate=submit_gate)
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
    ap.add_argument("--submit-gate", action="store_true",
                    help="Coordination gate (OFF by default): scoped_submit refuses until the "
                         "agent has itself run read_messages on the current board state, and "
                         "has announced (publish_interface / send_message) any public "
                         "def/class its edits delete. Pure refusal checks -- the harness "
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
                                  submit_gate=args.submit_gate)
        print(f"{d.name}: image={image}  ->  {len(written)} solver config(s)")


if __name__ == "__main__":
    main()
