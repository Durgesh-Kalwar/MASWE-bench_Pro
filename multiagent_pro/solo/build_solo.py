#!/usr/bin/env python
"""Build single-agent (solo) instances for the requirements ablation.

WHY THIS EXISTS. The multi-agent benchmark (multiagent_pro_bench50) is built WITH the dataset's
`requirements` field in every agent's issue text. That field is a prose implementation spec --
"Replace all remaining direct uses of UnsafeProxy with wrap_var(...)", "wrap_var(v) must behave
as follows: ..." -- i.e. close to a description of the gold patch. An instance can therefore
look solvable because the spec was handed over, not because the task is well posed. This builds
the control: ONE agent, the whole repo, issue text WITHOUT requirements, to find which instances
are solvable at all once the spec is withheld. Only those go on to the multi-agent grid.

WHAT THE PAPER ACTUALLY FED THE MODEL, and why it matters here. SWE-bench Pro's own
mini-swe-agent runs read a single field, `instance["problem_statement"]`
(mini-swe-agent/src/minisweagent/run/extra/swebench.py:148), and this repo composes that field
from three dataset fields in helper_code/create_problem_statement.py:

    {problem_statement}\\n\\nRequirements:\\n{requirements}\\n\\nNew interfaces introduced:\\n{interface}

So the paper's baseline includes requirements AND interface, and this ablation is one term
removed from it. `--arm noreq` drops the Requirements block; `--arm withreq` reproduces the
paper's composition as a control. Both arms come from the same code path, so the only difference
between them is that block.

ONE DELIBERATE DEVIATION FROM THE PAPER. Those three fields are JSON-encoded strings, and
create_problem_statement.py never decodes them -- the paper's prompt therefore contains literal
backslash-n and wrapping quotes (`"**Title: ...\\n\\n**Description:**\\n\\n`). multiagent_pro
decodes them (build_multiagent_pro.decode_text). We decode in BOTH arms: the comparison that
matters is solo vs multi-agent inside this study, and reproducing the escaping would leave the
solo arm reading mangled text while the multi-agent arm reads clean text -- any gap between them
would then partly measure prompt formatting. `--raw-json-text` restores paper-faithful escaping
if an absolute comparison against published numbers is ever needed.

OUTPUT LAYOUT. Written straight into the harness50 grid, so the existing dashboard picks it up
with no configuration (dashboard/build_dashboard.py discovers cells from the directory layout):

    <root>/<harness>/mini_swe_agent/<model>/<instance_id>/
        spec.json roster.json comm_mode.json
        agent_1/{local_issue.md, mini.yaml}

`harness` is the ablation arm (`solo_noreq` / `solo_withreq`), because the grid's path components
are the study's dimensions and "requirements on/off" is one the layout does not otherwise encode
-- the same reasoning harness50/README.md gives for `_superseded/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
MINI_SRC = REPO_DIR / "mini-swe-agent" / "src"

# The Pro images check the repo out at /app (WORKDIR), not /testbed.
REPO_ROOT_IN_IMAGE = "/app"

NO_INTERFACE_SENTINEL = "No new interfaces are introduced."


def decode_text(v) -> str:
    """Pro's text fields are JSON-encoded strings: one json.loads turns `"a\\nb"` into real text
    with a real newline. Non-strings and already-decoded strings pass through unchanged."""
    if v is None:
        return ""
    if not isinstance(v, str):
        return str(v)
    try:
        d = json.loads(v)
        return d if isinstance(d, str) else v
    except (json.JSONDecodeError, ValueError):
        return v


def compose_problem(meta: dict, *, with_requirements: bool, raw: bool) -> str:
    """The single string that becomes `problem_statement` for mini.

    Section order and headings follow create_problem_statement.py, so the withreq arm is
    comparable with the paper's composition (modulo decoding -- see module docstring).
    """
    pick = (lambda k: meta.get(k) or "") if raw else (lambda k: decode_text(meta.get(k)).strip())
    out = [pick("problem_statement")]
    if with_requirements:
        out += ["", "Requirements:", pick("requirements")]
    itf = pick("interface")
    # An instance whose interface field is the "none" sentinel gets no interface section at all:
    # printing "New interfaces introduced: No new interfaces are introduced." is pure noise, and
    # the multi-agent build omits the section in the same situation (build_local_info).
    if itf and itf != NO_INTERFACE_SENTINEL:
        out += ["", "New interfaces introduced:", itf]
    return "\n".join(out).strip() + "\n"


# --------------------------------------------------------------------------- #
# Opus 5.5 prompt compatibility
# --------------------------------------------------------------------------- #
# MEASURED, not guessed. The paper's swebp.yaml system prompt contains:
#
#     "Include a THOUGHT section before your command where you explain your reasoning process."
#
# On claude5_5_opus that sentence makes the gateway return an EMPTY completion -- 1-8 output
# tokens, content "", finish_reason "stop", no error -- so mini's parse_action finds 0 bash
# blocks and every single step becomes a format_error. A 250-step run would burn the full budget
# and produce a 0-line patch, and the aggregate score would look like an ordinary bad run.
#
# Opus 5.5 added a `reasoning_extraction` safety classifier (alongside bio and cyber), and asking
# the model to emit a labelled section of its reasoning trips it. Through an OpenAI-compatible
# shim there is no stop_details field, so the refusal arrives as empty content instead of
# stop_reason "refusal" -- which is why it presents as a format error rather than a refusal.
#
# Scope of the problem, measured on this gateway with the paper's prompt verbatim:
#
#     claude5_5_opus  -> DEAD (0 chars)      claude5_opus   -> ok
#     claude5_sonnet  -> ok                  claude4_8_opus -> ok      gpt4o_mini -> ok
#
# So it is specific to Opus 5.5, and the fix is deliberately the SMALLEST one that clears the
# classifier: replace that one sentence. Everything else in swebp.yaml -- including the
# instance_template's own "THOUGHT:" example, which does NOT trip it -- stays byte-identical, and
# mini's parse_action never required a THOUGHT section in the first place (it matches only the
# ```bash fence). The agent still explains itself before acting, so the dashboard's `thought`
# field is still populated.
THOUGHT_OLD = ("Include a THOUGHT section before your command where you explain your "
               "reasoning process.")
THOUGHT_NEW = ("Before the command, write a short explanation of what you are about to do "
               "and why.")

# Models measured to need the substitution. Anything else keeps the paper's prompt verbatim.
PROMPT_COMPAT_MODELS = ("claude5_5_opus",)


def apply_prompt_compat(templates: dict, model: str, mode: str) -> bool:
    """Rewrite the reasoning-extraction sentence when the target model needs it.

    Returns whether the substitution was applied. `auto` applies it only for the models above,
    so a run on Opus 5 or Sonnet 5 is still the paper's prompt byte-for-byte.

    A requested substitution that finds nothing is a hard error, not a no-op: it means the
    submodule's swebp.yaml changed and the run would otherwise silently produce 250 empty steps.
    """
    if mode == "off" or (mode == "auto" and not any(m in model for m in PROMPT_COMPAT_MODELS)):
        return False
    agent = templates.get("agent") or {}
    sys_t = agent.get("system_template") or ""
    if THOUGHT_OLD not in sys_t:
        raise SystemExit(
            "prompt-compat requested but the expected sentence is not in swebp.yaml's "
            "system_template:\n  " + THOUGHT_OLD + "\nThe submodule's prompt has changed. "
            "Re-measure against the model before running -- on Opus 5.5 an unpatched prompt "
            "yields empty completions and every step becomes a format_error.")
    agent["system_template"] = sys_t.replace(THOUGHT_OLD, THOUGHT_NEW)
    templates["agent"] = agent
    return True


def load_swebp_templates() -> dict:
    """The paper's prompt config, read from the submodule rather than copied.

    Read from disk so that if the submodule's swebp.yaml ever changes, the solo arm follows it
    instead of silently diverging from the baseline it is meant to reproduce.
    """
    import yaml
    p = MINI_SRC / "minisweagent" / "config" / "swebp.yaml"
    if not p.is_file():
        raise SystemExit(f"missing {p} -- run `git submodule update --init --recursive`")
    return yaml.safe_load(p.read_text())


def mini_config(image: str, model: str, api_base: str, *, step_limit: int, cost_limit: float,
                registry_path: Path, templates: dict, command_timeout: int,
                container_timeout: str) -> dict:
    """mini.yaml for one solo agent.

    Prompt templates come from the submodule's config/swebp.yaml verbatim (`templates`), so the
    prompt is the paper's, not ours. Everything set here is either a fact about these images or a
    budget, and each one is a silent failure if omitted:

      * cwd /app            -- mini defaults to "/", which on these images is an empty directory,
                               so the agent is told the repo lives somewhere it is not;
      * --entrypoint ""     -- the images set ENTRYPOINT ["/bin/bash"], so mini's
                               `docker run -d <image> sleep N` becomes `/bin/bash sleep N`, exits
                               126, and EVERY later command returns "No such container";
      * --rm                -- mini's run_args DEFAULT is ["--rm"], and setting run_args replaces
                               it rather than appending, so --rm must be repeated or every run
                               leaks a container;
      * container_timeout   -- default "2h". A 250-step Opus 5.5 run can exceed that, and when
                               the container's `sleep` ends mid-run the failure looks exactly
                               like the ENTRYPOINT bug above;
      * litellm_model_registry -- the gateway's model ids are unknown to litellm, so
                               completion_cost raises, which mini turns into a hard failure at
                               zero API calls (or, with MSWEA_COST_TRACKING=ignore_errors as the
                               multi-agent runs use, into a silent $0.00 and an INERT
                               cost_limit). Registering real per-token prices instead is what
                               gives `cost_limit` teeth -- the only dollar brake in the run.

    Caching is deliberately NOT enabled (`set_cache_control` left unset). The gateway was
    measured ignoring it: an identical 28,930-token prefix sent three times reported
    cached_tokens=0 every time, with and without cache_control blocks. Turning it on would buy
    nothing and add a non-paper-faithful transform of the message list.
    """
    return {
        "environment": {
            "image": image,
            "cwd": REPO_ROOT_IN_IMAGE,
            "run_args": ["--rm", "--entrypoint", ""],
            "container_timeout": container_timeout,
            "timeout": command_timeout,
            "env": dict((templates.get("environment") or {}).get("env") or {}),
        },
        "agent": {
            **(templates.get("agent") or {}),
            # swebp.yaml ships step_limit 0 / cost_limit 0 (both unlimited) because the paper
            # passes --per-instance-call-limit on the CLI. Unlimited here would be a runaway.
            "step_limit": step_limit,
            "cost_limit": cost_limit,
        },
        "model": {
            "model_name": model,
            "litellm_model_registry": str(registry_path),
            "model_kwargs": {
                **((templates.get("model") or {}).get("model_kwargs") or {}),
                "api_base": api_base,
            },
        },
    }


def write_price_registry() -> Path:
    """Per-token prices for the gateway model ids, in litellm's registry format.

    litellm prices only what its bundled table knows, and these gateway ids are not in it.
    Both spellings are written because litellm strips the leading `openai/` as a provider prefix
    and which form reaches the cost calculator has been version-dependent.

    Rates are Anthropic list prices and were CONFIRMED against this gateway: a 28,930-token
    input billed $0.11582, i.e. exactly $4.00/M.
    """
    prices = {                                  # (input $/tok, output $/tok, context)
        "aws/claude5_5_opus":        (4e-06, 20e-06, 1_000_000),
        "aws/claude5_opus":          (5e-06, 25e-06, 1_000_000),
        "aws/claude5_sonnet":        (2e-06, 10e-06, 1_000_000),
    }
    reg = {}
    for name, (i, o, ctx) in prices.items():
        entry = {"input_cost_per_token": i, "output_cost_per_token": o,
                 "litellm_provider": "openai", "mode": "chat",
                 "max_input_tokens": ctx, "max_output_tokens": 128_000,
                 "max_tokens": 128_000}
        reg[name] = entry
        reg[f"openai/{name}"] = dict(entry)
    out = Path(__file__).resolve().parent / "gateway_model_prices.json"
    out.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", nargs="+", required=True, help="instance_ids to build")
    ap.add_argument("--arm", choices=("noreq", "withreq"), default="noreq",
                    help="noreq (default): problem statement + interface, NO requirements -- the "
                         "ablation. withreq: the paper's composition, as a control.")
    ap.add_argument("--root", default="/media/data/dkalwar/harness50",
                    help="harness50 grid root")
    ap.add_argument("--model-label", default="claude_opus_5_5",
                    help="model directory name in the grid")
    ap.add_argument("--model", default="openai/aws/claude5_5_opus",
                    help="litellm model string. The gateway's own ids are prefixed "
                         "(aws/claude5_5_opus) and litellm strips the first segment as the "
                         "provider, so the EXTRA leading openai/ is what routes to the "
                         "OpenAI-compatible endpoint while putting the full gateway id on the "
                         "wire. Verified: this serves inference_model=claude5_5_opus.")
    ap.add_argument("--api-base", default=None, help="defaults to $CREATAI_BASE_URL")
    ap.add_argument("--src", default=str(REPO_DIR / "sampled_pro"),
                    help="dir of <instance_id>/metadata.json holding the dataset text fields")
    ap.add_argument("--bench50", default=str(REPO_DIR / "multiagent_pro_bench50"),
                    help="built multi-agent set, read only for repo / coupling / base_commit")
    ap.add_argument("--step-limit", type=int, default=250,
                    help="model calls per instance. 250 is the SWE-bench Pro paper's "
                         "--per-instance-call-limit. Cost grows ~QUADRATICALLY in this number "
                         "(full history, no elision, and no caching on this gateway), so halving "
                         "it quarters the bill.")
    ap.add_argument("--cost-limit", type=float, default=5.0,
                    help="hard $ ceiling per instance; mini raises LimitsExceeded when hit. The "
                         "paper runs 0 (unlimited) -- do NOT copy that here: Opus 5.5 is ~40x "
                         "the per-token price of the gpt-4o-mini runs this harness was built on.")
    ap.add_argument("--command-timeout", type=int, default=60,
                    help="seconds per bash command. mini's default is 30, which can kill a "
                         "legitimate test run; 60 is a deviation from stock, recorded in "
                         "spec.json.")
    ap.add_argument("--container-timeout", default="8h",
                    help="how long the container is kept alive. mini's default 2h is shorter "
                         "than a 250-step Opus run can take.")
    ap.add_argument("--prompt-compat", choices=("auto", "on", "off"), default="auto",
                    help="Rewrite the paper prompt's THOUGHT/reasoning sentence, which makes "
                         "Opus 5.5 return EMPTY completions (every step a format_error). auto "
                         "(default): only for models measured to need it. off: keep the paper's "
                         "prompt verbatim -- correct for Opus 5 / Sonnet 5, fatal for Opus 5.5.")
    ap.add_argument("--raw-json-text", action="store_true",
                    help="Do NOT decode the JSON-encoded text fields, reproducing the paper's "
                         "literal backslash-n escaping. Off by default -- see module docstring.")
    ap.add_argument("--dockerhub_username", default="jefzda")
    args = ap.parse_args()

    api_base = args.api_base or os.environ.get("CREATAI_BASE_URL")
    if not api_base:
        raise SystemExit(
            "--api-base not given and $CREATAI_BASE_URL is unset. Source it first:\n"
            "  eval \"$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)\"")

    sys.path.insert(0, str(REPO_DIR / "helper_code"))
    from image_uri import get_dockerhub_image_uri

    import yaml
    templates = load_swebp_templates()
    compat = apply_prompt_compat(templates, args.model, args.prompt_compat)
    registry_path = write_price_registry()
    print(f"prompt-compat({args.prompt_compat}): "
          f"{'APPLIED -- THOUGHT sentence rewritten' if compat else 'not applied'}")

    harness = f"solo_{args.arm}"
    cell = Path(args.root) / harness / "mini_swe_agent" / args.model_label
    src, bench = Path(args.src), Path(args.bench50)
    built = []

    for iid in args.instances:
        meta_p = src / iid / "metadata.json"
        if not meta_p.is_file():
            print(f"SKIP {iid}: no {meta_p}")
            continue
        meta = json.loads(meta_p.read_text())

        # repo / coupling / base_commit come from the built multi-agent spec when it exists, so a
        # solo row and its multi-agent counterpart carry identical metadata in the dashboard.
        ms = bench / iid / "spec.json"
        mspec = json.loads(ms.read_text()) if ms.is_file() else {}
        repo = mspec.get("repo") or meta.get("repo") or ""
        image = get_dockerhub_image_uri(iid, args.dockerhub_username, repo)

        idir = cell / iid
        adir = idir / "agent_1"
        adir.mkdir(parents=True, exist_ok=True)

        problem = compose_problem(meta, with_requirements=(args.arm == "withreq"),
                                  raw=args.raw_json_text)
        (adir / "local_issue.md").write_text(problem)
        (adir / "mini.yaml").write_text(yaml.safe_dump(
            mini_config(image, args.model, api_base,
                        step_limit=args.step_limit, cost_limit=args.cost_limit,
                        registry_path=registry_path, templates=templates,
                        command_timeout=args.command_timeout,
                        container_timeout=args.container_timeout),
            sort_keys=False, width=100))

        # num_agents 1 with an empty scope/deny is what makes this the solo control: no denylist,
        # so no scope guard is installed and the agent sees the whole repository.
        (idir / "spec.json").write_text(json.dumps({
            "instance_id": iid,
            "repo": repo,
            "base_commit": mspec.get("base_commit") or meta.get("base_commit"),
            "num_agents": 1,
            "solo": True,
            "arm": args.arm,
            "requirements_included": args.arm == "withreq",
            "interface_included": True,
            "json_text_decoded": not args.raw_json_text,
            "prompt_compat": args.prompt_compat,
            "prompt_compat_applied": compat,
            "step_limit": args.step_limit,
            "cost_limit": args.cost_limit,
            "command_timeout": args.command_timeout,
            "model": args.model,
            "image": image,
            # Carried through so solo rows stratify by coupling exactly like multi-agent rows.
            "coupling": mspec.get("coupling"),
            "multiagent_num_agents": mspec.get("num_agents"),
            "agents": [{"id": "agent_1", "scope": [], "deny": [], "scope_mode": "full"}],
        }, indent=2) + "\n")
        (idir / "roster.json").write_text(json.dumps(
            [{"id": "agent_1", "gold_file": None}], indent=2) + "\n")
        # No communication exists in a solo run. Recorded explicitly rather than omitted, so the
        # dashboard shows "solo" instead of a blank harness field.
        (idir / "comm_mode.json").write_text(json.dumps(
            {"mode": "solo", "beliefs": False, "scaffold": "mini"}, indent=2) + "\n")

        built.append(iid)
        n_req = len(decode_text(meta.get("requirements")).strip())
        print(f"{iid[:58]}  arm={args.arm}  issue={len(problem):>6}c  "
              f"requirements({n_req}c)="
              f"{'INCLUDED' if args.arm == 'withreq' else 'WITHHELD'}")

    print(f"\n{len(built)}/{len(args.instances)} built -> {cell}")


if __name__ == "__main__":
    main()
