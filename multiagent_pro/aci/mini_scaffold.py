"""mini-swe-agent backend for the multi-agent harness, plus the scope guard it needs.

mini-swe-agent gives the model RAW BASH and a ~190-line agent loop. That is the reason to use
it -- SWE-agent's fixed tool surface is what makes an agent retry one rejected `scoped_insert`
twenty times -- but it removes the mechanism the study depends on.

SWE-agent enforces file scope by WITHHOLDING TOOLS: an agent has `scoped_view`/`scoped_insert`
and no `bash`, so a peer's file is simply unreachable. With raw bash that is gone, and READS
matter more than writes: an agent that can `cat` a peer's file never needs to ask, so every
communication harness would look identical and the comparison would measure nothing.

`ScopedDockerEnvironment` restores the asymmetry by refusing commands that name a peer-owned
path. See its docstring for exactly how far that goes -- it is a guard, not a sandbox, and the
leak rate is measured rather than assumed.

Nothing here modifies the mini-swe-agent submodule. The environment is registered by dotted
path (`get_environment_class` falls back to importlib), and the agent is driven directly
rather than through `mini-extra run-batch`, which parallelises INSTANCES, not agents on one
instance.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scaffolds import NOTICE_MARK, SENT_MARKS, StepResult, prune_history, sum_usage

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_DIR / "mini-swe-agent" / "src"))

from minisweagent.environments.docker import (  # noqa: E402
    DockerEnvironment,
    DockerEnvironmentConfig,
)

# The sentinel mini's DefaultAgent.has_finished() matches on a command's FIRST output line.
SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"

# Shell segment separators, for checking scope per command rather than per whole line. Not a
# shell parser: it does not know about quotes or subshells, so a separator inside a string
# splits too. That errs toward MORE segments and hence more checking, which is the safe
# direction -- a segment is only ever exempted when its own first word is a comm bin.
COMMAND_SEP = re.compile(r"&&|\|\||;|\n")

# mini's own action regex, duplicated here so the override below counts blocks exactly as
# DefaultAgent.parse_action does. Keep in step with default.py if the submodule pin moves.
BASH_BLOCK = re.compile(r"```bash\s*\n(.*?)\n```", re.DOTALL)

MULTI_BLOCK_NOTE = (
    "\n\nNote: your reply contained {n} ```bash blocks. Only ONE command runs per step, so the "
    "FIRST block was executed and the other {extra} were ignored. Send one block per reply; you "
    "will get this observation back and can send the next command then."
)


def _first_action_agent_class():
    """DefaultAgent, but a reply with SEVERAL bash blocks executes the FIRST instead of failing.

    Multi-agent ONLY -- the paper's solo arm keeps upstream's exactly-one contract, so this is an
    override here rather than a submodule edit (`docs/submodules.md`: a scaffold fix would have to
    be pushed to the fork before the pin could move, and solo would inherit it).

    Measured on the two gpt6_sol cells: 1,750/1,928 broadcast and 1,407/1,642 p2p format_error
    steps were multi-block replies carrying a perfectly valid first command, so upstream's rule
    threw away ~91% of them. Taking the FIRST block and not the last is the whole point: in 76% of
    those replies the LAST block is `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`, which
    has_finished() turns into Submitted -- a TerminatingException that would end the agent's round
    on the spot and discard the real work queued in block 1. Later blocks are also written blind,
    before the model has seen the first block's output, so they are speculative by construction.

    ZERO blocks remains a FormatError: there is no action to run. That was 3 steps per cell.

    NOT a no-op for Opus 5.5, though nearly so: replaying the recorded cells, exactly ONE step
    per cell changes (broadcast a 2-block reply, p2p a 4-block one whose last block was the submit
    echo). Its other recorded format_errors are 2 and 6 ExecutionTimeoutErrors -- which share this
    exit_status label, parse fine and are untouched -- plus 1 and 5 genuine zero-block replies that
    still fail. So re-running Opus under this override will NOT reproduce the recorded cells
    byte-identically; 28/34 and 29/34 belong to the old parsing rule.
    """
    from minisweagent.agents.default import DefaultAgent, FormatError

    class FirstActionAgent(DefaultAgent):
        def parse_action(self, response: dict) -> dict:
            actions = BASH_BLOCK.findall(response["content"])
            if not actions:
                raise FormatError(
                    self.render_template(self.config.format_error_template, actions=actions))
            self.n_blocks_last_parse = len(actions)
            return {"action": actions[0].strip(), **response}

        def get_observation(self, response: dict) -> dict:
            """Append the ignored-block note to the observation the model sees.

            Done here rather than in the template so `action_observation_template` stays byte-wise
            swebp's (gen_solver_config.swebp_templates), and so a single-block reply -- every Opus
            reply -- gets no extra text at all.
            """
            self.n_blocks_last_parse = 1
            out = super().get_observation(response)
            n = getattr(self, "n_blocks_last_parse", 1)
            if n > 1 and self.messages and self.messages[-1].get("role") == "user":
                self.messages[-1]["content"] += MULTI_BLOCK_NOTE.format(n=n, extra=n - 1)
            return out

    return FirstActionAgent

# The comm bundle's bins (tools/comm/bin). Naming a peer's file in one of these is the intended
# way to ask its owner about it, so these segments are exempt from the scope check.
COMM_BINS = frozenset({"list_agents", "publish_interface", "send_message", "update_belief"})


def _splittable(seg: str) -> bool:
    """Whether shlex can tokenize this segment -- unbalanced quotes raise ValueError, and a
    heredoc body routinely contains them."""
    try:
        shlex.split(seg)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Scope guard
# --------------------------------------------------------------------------- #
def deny_needles(deny_paths: list[str], repo_root: str = "/app") -> list[tuple[str, str]]:
    """(needle, owning_path) pairs to search a command string for.

    Three spellings per denied file, because an agent reaches a path in more than one way:
      * the repo-relative path            lib/ansible/config/manager.py
      * the absolute path                 /app/lib/ansible/config/manager.py
      * the last TWO components           config/manager.py

    Two components, never one: basenames like `__init__.py` or `utils.py` recur all over a
    repo, so matching on them alone would refuse an agent access to its OWN files. Two is
    specific enough in practice.

    Split directory/basename matching is handled separately by `deny_pairs`, because the
    components need not be adjacent in the command string.
    """
    out = []
    for p in deny_paths:
        p = p.strip().lstrip("./")
        if not p:
            continue
        out.append((p, p))
        out.append((f"{repo_root.rstrip('/')}/{p}", p))
        parts = p.split("/")
        if len(parts) >= 2:
            out.append(("/".join(parts[-2:]), p))
    return out


def deny_pairs(deny_paths: list[str]) -> list[tuple[str, str, str]]:
    """(parent_dir, basename, owning_path) triples for the split-reference case.

    `cd lib/ansible/config && cat manager.py` never contains the substring
    `config/manager.py`, so needle matching alone misses it. Requiring BOTH the specific
    parent directory and the basename to appear somewhere in the same command catches it
    while keeping false positives low -- an agent working on its own `lib/ansible/cli/
    config.py` names neither `lib/ansible/config` nor `manager.py`.
    """
    out = []
    for p in deny_paths:
        p = p.strip().lstrip("./")
        parts = p.split("/")
        if len(parts) >= 2:
            out.append(("/".join(parts[:-1]), parts[-1], p))
    return out


@dataclass
class ScopedDockerEnvironmentConfig(DockerEnvironmentConfig):
    scope_deny: list[str] = field(default_factory=list)
    """Repo-relative paths owned by PEERS. Commands naming one of these are refused."""
    repo_root: str = "/app"
    violation_log: str = ""
    """Host path for the scope_violations.jsonl audit trail (empty disables logging)."""


class ScopedDockerEnvironment(DockerEnvironment):
    """DockerEnvironment that refuses commands touching peer-owned files.

    A refusal is returned in the SAME shape as a normal result (`{"output", "returncode": 1}`)
    and the command is never run, so the model sees it exactly as it would see a failing
    command and can recover -- the message names the file and points at `send_message`, the
    way scoped_fs does.

    LIMITATION, stated plainly: this is substring matching over the command string. It stops
    an agent doing the obvious thing (`cat`, `sed`, `grep`, `python peer_file.py`). It does
    NOT stop a determined one -- `find /app -name 'mana*' -exec cat {} \\;`, a `cd` in an
    earlier command followed by a bare basename, reading via a variable, or base64 round-trips
    all get through. Agents here are not adversarial, they are trying to do a task; this keeps
    them honest without pretending to be a sandbox. Every refusal is logged, and the
    verification suite deliberately measures how many obfuscated reads leak so the number is
    reported rather than assumed.

    Harness-issued commands (board writes, belief reads, diff collection) bypass the check via
    `execute(..., internal=True)` -- the orchestrator is not an agent and legitimately touches
    the whole worktree.
    """

    # Class-level defaults, not just instance ones: DockerEnvironment.__init__ calls
    # self.execute("pwd") (via _get_working_dir) BEFORE our __init__ body runs, so `execute`
    # -- and therefore `_denied` -- must be safe on a half-built object. Empty guards deny
    # nothing, which is correct: that startup probe is the harness's, not an agent's.
    _needles: list = []
    _pairs: list = []

    def __init__(self, *, config_class: type = ScopedDockerEnvironmentConfig, **kwargs):
        self.violations: list[dict] = []
        self.round = 0
        super().__init__(config_class=config_class, **kwargs)
        deny = list(self.config.scope_deny or [])
        self._needles = deny_needles(deny, self.config.repo_root)
        self._pairs = deny_pairs(deny)

    def _denied(self, command: str) -> str | None:
        """The peer path this command names, or None. Longest needle first so the reported
        path is the most specific match rather than a two-component suffix.

        Checked per shell segment, not over the whole string. A peer path is legitimate INSIDE
        a comm command -- naming a peer's file is how you ask its owner about it -- so a
        segment that only invokes a comm bin is exempt, the same exemption `internal=True`
        gives the harness. Measured on the 2026-10-15 smoke run: whole-command matching refused
        a correct `send_message` announcement because `cd /app/<dir>` supplied the parent and
        the peer's basename appeared in the prose.

        Deliberate limitation: only comm bins and `cd` are exempt, so a peer path inside an
        ordinary command is still refused even when the command EXCLUDES that file
        (`grep -v peer.py`, `--exclude=peer.py`). Telling those apart needs per-flag argument
        analysis, which would be easy to get wrong in the permissive direction.
        """
        for seg in COMMAND_SEP.split(command):
            seg = seg.strip()
            if not seg:
                continue
            head = shlex.split(seg)[0] if _splittable(seg) else seg.split()[0]
            if head in COMM_BINS or head == "cd":
                continue                       # asking about a peer's file is allowed
            for needle, owner in sorted(self._needles, key=lambda t: -len(t[0])):
                if needle in seg:
                    return owner
            # Split reference: `cd <peer dir> && cat <basename>` -- both parts present, but not
            # adjacent, so no single needle matches. Pairs are checked against the WHOLE command
            # because that is precisely a cross-segment construction.
            for parent, base, owner in self._pairs:
                if parent in command and base in seg:
                    return owner
        return None

    def _record(self, command: str, owner: str) -> None:
        entry = {"round": self.round, "command": command[:500], "denied_path": owner}
        self.violations.append(entry)
        if getattr(self, "config", None) and self.config.violation_log:
            try:
                p = Path(self.config.violation_log)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except Exception:
                pass                        # auditing must never break a paid run

    def execute(self, command: str, cwd: str = "", *, timeout: int | None = None,
                internal: bool = False) -> dict:
        if not internal and (owner := self._denied(command)):
            self._record(command, owner)
            return {
                "output": (
                    f"REFUSED: `{owner}` is owned by another agent and is invisible to you "
                    f"(as your files are to them). Nothing was executed.\n"
                    f"If you need something from that file -- a name, a signature, where "
                    f"something lives -- ask for it with `send_message`; only its owner can "
                    f"tell you."
                ),
                "returncode": 1,
            }
        return super().execute(command, cwd, timeout=timeout)


def _usage_of(out: dict) -> dict:
    """The token receipt for one model call, from what LitellmModel.query already returns.

    `query()` hands back {"content": ..., "extra": {"response": response.model_dump()}}, so
    `usage` is right there, and on the CreateAI gateway so is its own billed cost under
    `metadata.usage_metric.total_token_cost` -- the figure the monthly budget is actually
    debited by (`solo/run_solo.py::_gateway_cost` uses the same path). mini's DefaultAgent
    keeps only `content`, which is why this has to be read at the call site.

    `cost_gateway` is best-effort: litellm's ModelResponse may or may not carry that
    non-standard top-level key through `model_dump()`. `tokens_out` already INCLUDES
    reasoning tokens where a provider bills them as output; `reasoning_tokens` is recorded
    separately when reported so the two can be told apart rather than assumed equal.
    """
    resp = ((out or {}).get("extra") or {}).get("response") or {}
    u = resp.get("usage") or {}
    rec = {"calls": 1,
           "tokens_in": int(u.get("prompt_tokens") or 0),
           "tokens_out": int(u.get("completion_tokens") or 0)}
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if reasoning:
        rec["reasoning_tokens"] = int(reasoning)
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached:
        rec["cached_tokens"] = int(cached)
    try:
        rec["cost_gateway"] = float(resp["metadata"]["usage_metric"]["total_token_cost"])
    except (KeyError, TypeError, ValueError):
        pass
    return rec


# --------------------------------------------------------------------------- #
# The scaffold
# --------------------------------------------------------------------------- #
class MiniScaffold:
    """Drives mini's DefaultAgent one step at a time under the shared round loop.

    `DefaultAgent.run()` owns its own while-loop and its own exception protocol; we need
    per-step control, so `start()` reproduces run()'s message seeding and `step()` reproduces
    its exception handling:

        NonTerminatingException (FormatError, ExecutionTimeoutError) -> add as a user message
                                                                        and keep going
        TerminatingException    (Submitted, LimitsExceeded)          -> the turn is over

    Only `Submitted` counts as a real submission; `LimitsExceeded` is an agent that ran out of
    budget, which the caller retires rather than treating as finished.
    """

    name = "mini"

    def __init__(self, inst_dir, aid: str, image: str):
        self.inst_dir, self.aid, self.image = inst_dir, aid, image
        self.agent = None
        self.env = None
        self._steps = 0
        self._cfg = {}
        self._prev_round_start = 0     # index where the PREVIOUS round's messages begin
        self._usage = []               # one receipt per model call, in call order

    # -- lifecycle ---------------------------------------------------------- #
    def start(self) -> None:
        import yaml
        from minisweagent.models import get_model

        self._cfg = yaml.safe_load((self.inst_dir / self.aid / "mini.yaml").read_text())
        env_cfg = dict(self._cfg.get("environment") or {})
        env_cfg.pop("environment_class", None)          # we instantiate the class directly
        env_cfg.setdefault("image", self.image)
        env_cfg["violation_log"] = str(self.inst_dir / self.aid / "scope_violations.jsonl")
        self.env = ScopedDockerEnvironment(**env_cfg)

        model_cfg = dict(self._cfg.get("model") or {})
        model = get_model(config=model_cfg)
        self._wrap_model(model)
        self.agent = _first_action_agent_class()(
            model, self.env, **(self._cfg.get("agent") or {}))
        self._install_tools()

        # run() seeds these before its loop; we drive step() directly, so do it here.
        # `problem_statement` is this agent's OWN local_issue.md -- under --route-interface
        # every agent gets the complete issue text but only the interface entries for its own
        # file, so the asymmetry lives in this file, not in the template. StrictUndefined
        # means a missing var is a hard jinja error, not a silently blank prompt.
        issue = self.inst_dir / self.aid / "local_issue.md"
        self.agent.extra_template_vars |= {
            "task": "",
            "problem_statement": issue.read_text() if issue.exists() else "",
        }
        self.agent.add_message(
            "system", self.agent.render_template(self.agent.config.system_template))
        self.agent.add_message(
            "user", self.agent.render_template(self.agent.config.instance_template))

    def _wrap_model(self, model) -> None:
        """Record every call's token receipt on the way past.

        A wrapper rather than a subclass because `get_model` picks the class from the config
        (litellm here, but not necessarily), and rather than a patch to the submodule because
        this is our bookkeeping, not a scaffold defect. Auditing must never break a paid run,
        so a malformed response costs the receipt, not the step.
        """
        inner = model.query

        def query(messages, **kwargs):
            before = getattr(model, "cost", 0.0) or 0.0
            out = inner(messages, **kwargs)
            try:
                rec = _usage_of(out)
                # litellm's own figure, which is 0.0 until the price registry is wired
                # (things_to_fix E4) -- kept so this starts reporting the moment it is.
                spent = (getattr(model, "cost", 0.0) or 0.0) - before
                if spent:
                    rec["cost_litellm"] = spent
                self._usage.append(rec)
            except Exception:
                pass
            return out

        model.query = query

    def _usage_since(self, mark: int) -> dict:
        """Receipts for the model calls made since `mark`, summed.

        Normally exactly one call per step; a retry inside litellm never returns, so it adds
        no receipt. Summing rather than taking the last one keeps a step honest if a backend
        ever queries twice.
        """
        return sum_usage(self._usage[mark:])

    def _install_tools(self) -> None:
        """Copy the materialized comm bundle into the container and put it on PATH.

        The comm bins are already framework-agnostic -- standalone Python reading AGENT_ID /
        COMM_MODE / COMM_BOARD / AGENTS_ROSTER and writing JSON -- so they are used verbatim
        here. Only the delivery mechanism differs: SWE-agent declares them as tools, mini just
        needs them executable on PATH.
        """
        bundle = self.inst_dir / "_comm_bundle"
        if not bundle.exists():
            return
        payload = {}
        for sub in ("bin", "lib"):
            d = bundle / sub
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.is_file():
                    payload[f"{sub}/{f.name}"] = base64.b64encode(
                        f.read_bytes()).decode()
        # Only the comm bins. `scoped_submit` and `submit_gate.py` are deliberately NOT installed
        # any more: mini now records a round by echoing the sentinel itself
        # (`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git --no-pager diff --stat HEAD`, as the
        # system prompt instructs), which is what `DefaultAgent.has_finished()` matches on the
        # first output line of any command, so the wrapper had nothing left to do. The graded
        # patch never came from it either -- `orchestrate.py` recomputes the diff from the
        # worktree at run end.
        #
        # CONSEQUENCE, recorded rather than hidden: `--submit-gate`'s delete-announcement check
        # (a public def/class you removed must have been announced) ran inside that wrapper, so it
        # is now SWE-agent-only. The independent false-attestation guard is unaffected -- the
        # `publish_interface` existence check lives in comm/lib/verify.py and runs inside the tool.
        # Either run a sweep with the gate off for both arms, or note the asymmetry when reporting.
        #
        # `no_op` was never installed here at all (it lives in tools/scoped_fs/bin and was only
        # ever copied for SWE-agent), which is why mini recorded 0 no_ops across every round of
        # every run while the SWE-agent cells used it. The prompt no longer advertises it.
        blob = base64.b64encode(json.dumps(payload).encode()).decode()
        script = (
            "mkdir -p /root/tools/bin /root/tools/lib /root/comm && "
            f"echo {blob} | base64 -d > /tmp/_bundle.json && "
            "python3 -c \"import base64,json,os;"
            "d=json.load(open('/tmp/_bundle.json'));"
            "[open('/root/tools/'+k,'wb').write(base64.b64decode(v)) for k,v in d.items()]\" && "
            "chmod +x /root/tools/bin/* 2>/dev/null; "
            # `docker exec ... bash -lc` starts a LOGIN shell, which re-sources /etc/profile
            # and overwrites the PATH we passed with -e. So the tools have to be announced
            # somewhere the login shell actually reads. profile.d covers PYTHONPATH too;
            # the symlinks are belt-and-braces for any shell that skips profile.d.
            "printf '%s\\n' "
            "'export PATH=/root/tools/bin:$PATH' "
            "'export PYTHONPATH=/root/tools/lib:$PYTHONPATH' "
            "> /etc/profile.d/maswe_tools.sh 2>/dev/null; "
            "for f in /root/tools/bin/*; do ln -sf \"$f\" /usr/local/bin/ 2>/dev/null; done; "
            "true"
        )
        self.env.execute(script, internal=True)

    def close(self) -> None:
        if self.env is not None:
            try:
                self.env.cleanup()
            except Exception:
                pass

    # -- harness surface ---------------------------------------------------- #
    def inject(self, text: str) -> None:
        # Public API, unlike SWE-agent's _append_history. mini has NO history processor, so
        # there is no elision hazard to dodge here -- the notice simply stays in context.
        self.agent.add_message("user", text)

    def set_round(self, r: int) -> None:
        self.env.round = r

    def prune_expired(self) -> int:
        """Expire last round's mail, with the SAME rule SWE-agent uses.

        mini has no message_type: observations are appended with role "user" exactly like an
        injected notice, so both predicates key on CONTENT instead. That is sufficient because
        a notice always begins with the round banner and a successful send always prints both
        sentinel fragments -- neither of which an ordinary bash observation contains.
        """
        def is_notice(e):
            return (e.get("role") == "user"
                    and NOTICE_MARK in str(e.get("content") or "")[:40])

        def is_own_send(e):
            if e.get("role") != "user":
                return False
            c = str(e.get("content") or "")
            return all(mark in c for mark in SENT_MARKS)

        try:
            msgs = self.agent.messages
            dropped = prune_history(msgs, is_notice, is_own_send, self._prev_round_start)
            self._prev_round_start = len(msgs)
            return dropped
        except Exception as e:
            print(f"    (message pruning skipped: {type(e).__name__}: {e})")
            return 0

    def step(self) -> StepResult:
        from minisweagent.agents.default import (
            NonTerminatingException,
            Submitted,
            TerminatingException,
        )
        self._steps += 1
        mark = len(self._usage)        # receipts this step is responsible for
        try:
            out = self.agent.step()
        # Both handlers record the thought and action that CAUSED the exception. Leaving them
        # empty made every terminating step a blank row in the trajectory: a fired submission
        # looked indistinguishable from one that never happened, which is exactly how the
        # submission-loss measurement first came out wrong. Mirrors solo/run_solo.py.
        except NonTerminatingException as e:
            # run() feeds the error back to the model as a user turn and continues.
            thought, action = self._last_thought(), self._last_action()
            self.agent.add_message("user", str(e))
            return StepResult(step=self._steps, thought=thought, action=action,
                              observation=str(e), exit_status="format_error",
                              usage=self._usage_since(mark))
        except TerminatingException as e:
            submitted = isinstance(e, Submitted)
            thought, action = self._last_thought(), self._last_action()
            self.agent.add_message("user", str(e))
            return StepResult(step=self._steps, thought=thought, action=action,
                              observation=str(e),
                              tool_calls=[{"name": _command_name(action),
                                           "args": {"command": action}}] if action else [],
                              exit_status=type(e).__name__, done=True,
                              submitted=submitted, usage=self._usage_since(mark))
        except Exception as e:                       # never let one step kill the run
            return StepResult(step=self._steps, observation=f"{type(e).__name__}: {e}",
                              exit_status=type(e).__name__, done=True,
                              usage=self._usage_since(mark))

        action = self._last_action()
        return StepResult(
            step=self._steps,
            thought=self._last_thought(),
            action=action,
            observation=str(out.get("output", "")),
            # No tool schema exists in mini; the bash command IS the action. Recorded under
            # the same key so comm_stats' name-counting works identically for both scaffolds.
            tool_calls=[{"name": _command_name(action), "args": {"command": action}}],
            exit_status="",
            usage=self._usage_since(mark),
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

    # -- file / diff helpers ------------------------------------------------ #
    def read_file(self, path: str) -> str:
        r = self.env.execute(f"cat {shlex.quote(path)} 2>/dev/null | base64 -w0",
                             internal=True)
        if r.get("returncode", 1) != 0:
            raise FileNotFoundError(path)
        return base64.b64decode("".join(r.get("output", "").split())).decode(
            "utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        blob = base64.b64encode(content.encode()).decode()
        self.env.execute(
            f"mkdir -p {shlex.quote(str(Path(path).parent))} && "
            f"echo {blob} | base64 -d > {shlex.quote(path)}", internal=True)

    def collect_diff(self, pathspec: str) -> str:
        r = self.env.execute(
            f'cd "${{ROOT:-/app}}" && git add -A{pathspec} && '
            f'git --no-pager diff --cached{pathspec} | base64 -w0',
            internal=True, timeout=120)
        return base64.b64decode("".join(r.get("output", "").split())).decode(
            "utf-8", errors="replace")

    @property
    def messages(self) -> list:
        return self.agent.messages

    @property
    def n_steps(self) -> int:
        return self._steps


def _command_name(action: str) -> str:
    """First word of a bash command, so comm_stats can count `send_message` etc. the same way
    it counts SWE-agent tool names."""
    action = (action or "").strip()
    if not action:
        return ""
    try:
        parts = shlex.split(action)
    except ValueError:
        parts = action.split()
    return os.path.basename(parts[0]) if parts else ""
