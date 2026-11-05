"""mini-swe-agent backend for the multi-agent harness, plus the scope guard it needs.

mini-swe-agent gives the model RAW BASH and a ~190-line agent loop. That is the reason to use
it -- SWE-agent's fixed tool surface is what makes an agent retry one rejected `scoped_insert`
twenty times -- but it removes the mechanism the study depends on.

SWE-agent enforces file scope by WITHHOLDING TOOLS: an agent has `scoped_view`/`scoped_insert`
and no `bash`, so a peer's file is simply unreachable. With raw bash that is gone, and READS
matter more than writes: an agent that can `cat` a peer's file never needs to ask, so every
communication harness would look identical and the comparison would measure nothing.

`ScopedDockerEnvironment` restores the asymmetry in two layers. The SEAL removes every
peer-owned file's source from the agent's worktree at container start (Python files are
swapped for their bytecode so the repo still imports and tests still run; see `seal_script`),
and the GUARD refuses commands that name a peer-owned path or reach into git history, where
the removed sources still live. The guard alone was measured on the 34-instance P2P sweep:
198 of its allowed commands printed peer source, 173 of them plain `grep -r` over a directory,
because matching the command text cannot know which files a recursive search will open. The
seal closes that by leaving nothing to print; the guard remains for the routes the seal cannot
cover (`git show`, `git clone`, a direct path).

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

# Gateway keys that answered "exhausted its monthly budget", shared by every agent in this
# process so a dead key is skipped by all of them (see MiniScaffold._install_key_rotation).
_EXHAUSTED_KEYS: set = set()

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


# --------------------------------------------------------------------------- #
# Filesystem seal
# --------------------------------------------------------------------------- #
def seal_script(deny_paths: list[str], repo_root: str = "/app") -> str:
    """Bash that removes the SOURCE of every denied file from the worktree, idempotently.

    The guard below inspects command text, so it cannot stop `grep -rn X lib/`, a glob, or a
    Python traceback from printing a peer's file: those never spell the path out, and the file
    is sitting on disk. The seal makes the file not be there.

      * `.py`   -> compiled to a sourceless `<name>.pyc` NEXT TO where the source was (the
                   legacy layout; Python ignores `__pycache__` when the source is missing),
                   then the `.py` is deleted. Imports resolve, tests run, `inspect.getsource`
                   raises OSError, and a traceback shows the frame but no source line.
      * other  -> deleted. Templates and YAML cannot be stubbed; a local test that renders a
                   peer's template fails, as it would anyway once the peer edits it.

    Every sealed path then gets git's `skip-worktree` bit, so the deletion is invisible to
    `git status`/`git diff`/`git add -A` (otherwise `git diff` would print the whole file as
    removed lines, a worse leak than the one being fixed) and `git checkout .`, `git stash`
    and `git reset --hard` leave the file absent (verified in the ansible image). The bit can
    be undone (`sparse-checkout disable`, `--no-skip-worktree`) and history is still in `.git`
    (`git show HEAD:path`, `git cat-file`, `git clone`): `_denied_git` refuses those routes,
    and the environment reseals after every agent command that mentions git.

    Compiled with `python3` from PATH, i.e. the interpreter the image's tests use. A file
    python3 cannot compile is deleted anyway -- it was not importable by that interpreter.

    The `.pyc` is also copied to `/root/.scope_seal/<path>c`, and a reseal restores it from
    there if it has gone: agents seeing an ImportError against a peer's frozen module have
    read it as a "stray .pyc" and gone looking for it, and a routine
    `find . -name '*.pyc' -delete` would otherwise turn the peer's module into
    ModuleNotFoundError for the rest of the run. Prints one line per path: `sealed`,
    `compile_failed`, `restored`, `absent`, so the caller can report.
    """
    lines = [
        f"cd {shlex.quote(repo_root)} 2>/dev/null || exit 0",
        "seal_one() {",
        "  p=\"$1\"; b=\"/root/.scope_seal/$p\"",
        "  if [ -f \"$p\" ]; then",
        "    case \"$p\" in",
        "      *.py) [ -f \"${p}c\" ] || python3 - \"$p\" <<'PYEOF' || echo \"compile_failed $p\"",
        "import py_compile, sys",
        "py_compile.compile(sys.argv[1], cfile=sys.argv[1] + 'c', doraise=True)",
        "PYEOF",
        "      ;;",
        "    esac",
        "    rm -f -- \"$p\" && echo \"sealed $p\"",
        "  else",
        "    echo \"absent $p\"",
        "  fi",
        "  case \"$p\" in",
        "    *.py)",
        "      if [ -f \"${p}c\" ]; then",
        "        [ -f \"${b}c\" ] || { mkdir -p \"$(dirname \"$b\")\" && cp -p \"${p}c\" \"${b}c\"; }",
        "      elif [ -f \"${b}c\" ]; then",
        "        cp -p \"${b}c\" \"${p}c\" && echo \"restored ${p}c\"",
        "      fi",
        "      ;;",
        "  esac",
        "  git update-index --skip-worktree -- \"$p\" >/dev/null 2>&1 || true",
        "}",
    ]
    for p in deny_paths:
        p = p.strip().lstrip("./")
        if p:
            lines.append(f"seal_one {shlex.quote(p)}")
    return "\n".join(lines)


# git subcommands that read blobs out of history or make a second checkout; none is needed to
# work on the agent's own file in the working tree.
GIT_HISTORY_SUBCMDS = frozenset({
    "clone", "worktree", "archive", "bundle", "cat-file", "sparse-checkout", "read-tree",
    "checkout-index", "format-patch", "fast-export", "filter-branch", "replay",
})
GIT_PATCH_FLAGS = frozenset({"-p", "-u", "--patch", "--full-diff", "--cc"})
GIT_SHOW_SAFE = frozenset({"--stat", "--name-only", "--name-status", "-s", "--no-patch",
                           "--shortstat", "--summary", "--oneline"})
_REV_RE = re.compile(r"^(HEAD|@|[0-9a-f]{7,40})([~^]|@\{|$)")


@dataclass
class ScopedDockerEnvironmentConfig(DockerEnvironmentConfig):
    scope_deny: list[str] = field(default_factory=list)
    """Repo-relative paths owned by PEERS. Commands naming one of these are refused."""
    repo_root: str = "/app"
    violation_log: str = ""
    """Host path for the scope_violations.jsonl audit trail (empty disables logging)."""
    scope_seal: bool = True
    """Remove peer-owned sources from the worktree at start (`seal_script`). Off reproduces the
    guard-only behaviour of the sweep34 runs."""
    scope_base_commit: str = ""
    """The instance's base commit. `git diff <base>` is the working-tree diff and is allowed;
    any other revision in `git diff`/`git grep` reaches history and is refused."""


class ScopedDockerEnvironment(DockerEnvironment):
    """DockerEnvironment in which peer-owned files are absent from the worktree and commands
    that could reach them anyway are refused.

    Two layers. `seal()` (run once by the scaffold after the container is up, and again after
    any agent command that mentions git) applies `seal_script`: peer sources are gone from
    disk, so `grep -r`, globs, `find`, tracebacks and `cat` have nothing of theirs to print.
    The guard, `_denied` + `_denied_git`, refuses the routes that survive the seal: a command
    that names a peer path (the file's bytecode is still there, and `git show HEAD:path` would
    print the source), and git subcommands that read history or make a second checkout.

    A refusal is returned in the SAME shape as a normal result (`{"output", "returncode": 1}`)
    and the command is never run, so the model sees it exactly as it would see a failing
    command and can recover -- the message names the file and points at `send_message`, the
    way scoped_fs does.

    What still gets through, stated plainly: the `.pyc` is readable (`strings` on it yields
    names, docstrings and string constants, not source), the file's NAME is visible in
    listings and in `grep: ... binary file matches`, and `git diff <branch>` against a branch
    the guard does not recognise as a revision would print historical hunks. With the seal off
    (`scope_seal: false`) only the text guard remains, which the sweep34 analysis measured at
    198 peer-source exposures over 34 runs.

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
    _deny: list = []

    def __init__(self, *, config_class: type = ScopedDockerEnvironmentConfig, **kwargs):
        self.violations: list[dict] = []
        self.round = 0
        self.seal_report: dict = {}
        super().__init__(config_class=config_class, **kwargs)
        deny = list(self.config.scope_deny or [])
        self._deny = deny
        self._needles = deny_needles(deny, self.config.repo_root)
        self._pairs = deny_pairs(deny)

    def seal(self) -> dict:
        """Apply `seal_script` (idempotent) and return {sealed, compile_failed, absent, raw}.

        Called by the scaffold once at start and by `execute` after any agent command that
        mentions git, as the backstop for routes that restore a sealed file. A reseal finds
        the `.pyc` already present and only re-deletes the source / re-sets the bit."""
        if not self._deny or not getattr(self, "config", None) or not self.config.scope_seal:
            return {}
        r = super().execute(seal_script(self._deny, self.config.repo_root), timeout=300)
        rep: dict = {"sealed": [], "compile_failed": [], "restored": [], "absent": [], "raw": r.get("output", "")}
        for line in r.get("output", "").splitlines():
            kind, _, p = line.partition(" ")
            if kind in rep and p:
                rep[kind].append(p)
        if not self.seal_report:                   # keep the first (start-up) report
            self.seal_report = rep
        return rep

    def _denied_git(self, command: str) -> str | None:
        """The git route this command would take into history, or None.

        The seal leaves `.git` intact, so a peer's source is one `git show HEAD:path` away.
        Direct path forms are caught by `_denied`; this covers the forms that name no path:
        blob reads (`cat-file`, `show <sha>`), history diffs (`log -p`, `diff HEAD~1`,
        `grep <pat> HEAD`), second checkouts (`clone`, `worktree`, `archive`) and undoing the
        skip-worktree bit. `git status`, `git diff`, `git diff HEAD`, `git diff <base>`,
        `git show --stat`, `git log` (no patch), `git blame <own file>` all pass."""
        base = (self.config.scope_base_commit or "") if getattr(self, "config", None) else ""
        for seg in COMMAND_SEP.split(command):
            seg = seg.strip()
            if not seg:
                continue
            toks = shlex.split(seg) if _splittable(seg) else seg.split()
            if not toks or toks[0] != "git":
                continue
            i = 1
            while i < len(toks) and toks[i].startswith("-"):     # global opts: -C <dir>, --no-pager
                i += 2 if toks[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
            if i >= len(toks):
                continue
            sub, args = toks[i], toks[i + 1:]
            args_before_dd = args[:args.index("--")] if "--" in args else args

            def is_rev(a: str) -> bool:
                return bool(_REV_RE.match(a))

            def is_historic(a: str) -> bool:
                # HEAD and the base commit (any prefix of it) are the working-tree baseline.
                return is_rev(a) and a != "HEAD" and not (base and len(a) >= 7 and base.startswith(a))

            if sub in GIT_HISTORY_SUBCMDS:
                return f"git {sub}"
            if sub == "update-index" and "--no-skip-worktree" in args:
                return "git update-index --no-skip-worktree"
            if sub in ("log", "stash", "whatchanged") and any(
                    a in GIT_PATCH_FLAGS or a.startswith("-L") for a in args):
                return f"git {sub} -p"
            if sub == "show":
                # `git show HEAD:own/file.py` is a legitimate look at one's own file (the path
                # part is checked by `_denied`), and `--stat`-style forms print no content.
                # Anything else -- bare `git show`, a commit, a blob sha -- prints source.
                if not any(a in GIT_SHOW_SAFE for a in args) and not any(":" in a for a in args_before_dd):
                    return "git show <revision>"
            if sub == "grep" and any(is_rev(a) for a in args_before_dd):
                # `git grep <pat> HEAD` searches the committed tree, where the sealed sources
                # still are; without a revision it searches the worktree, which is fine.
                return "git grep <revision>"
            if sub in ("diff", "difftool", "blame", "annotate", "restore", "checkout", "switch"):
                if any(is_historic(a) or (a.startswith("--source=") and is_historic(a[9:]))
                       for a in args_before_dd):
                    return f"git {sub} <historic revision>"
        return None

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
        if not internal and self._deny and (route := self._denied_git(command)):
            self._record(command, f"git-history:{route}")
            return {
                "output": (
                    f"REFUSED: `{route}` reads the repository history or makes a second "
                    f"checkout, where files owned by other agents are visible. Nothing was "
                    f"executed.\n"
                    f"Work from the working tree instead: `git status`, `git diff`, "
                    f"`git diff HEAD`, `git show --stat`, `git log` (without -p) are all "
                    f"allowed, as is anything on your own file."
                ),
                "returncode": 1,
            }
        out = super().execute(command, cwd, timeout=timeout)
        # Backstop for the seal after EVERY agent command: a git command may have restored a
        # sealed source (checkout of another ref, sparse-checkout, an un-set bit) and a cleanup
        # (`find . -name '*.pyc' -delete`, `git clean -xdf`) may have removed the bytecode the
        # peer's module now lives in. One extra exec per step that normally finds nothing to do;
        # a few tens of milliseconds against a model call.
        if not internal and self._deny:
            try:
                self.seal()
            except Exception:
                pass                        # the seal must never break a paid run
        return out


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
        self._seal_peers()

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
        self._install_key_rotation(model)
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

    def _install_key_rotation(self, model) -> None:
        """Swap to the next gateway key when the current one's MONTHLY budget is exhausted.

        The CreateAI gateway answers a spent project with a 429 whose text says "exhausted its
        monthly budget"; litellm maps it to RateLimitError and mini's tenacity policy retries
        it ten times with backoff -- against a key that will not recover until next month, so
        the agent burns its round and the instance dies. Measured 2026-11-04: key #1 ran dry
        mid-instance after ~12 instances across two arms.

        If CREATEAI_KEYS (space-separated) is in the environment, `_query` is re-wrapped with
        the SAME tenacity policy (`Retrying.wraps`), and a budget 429 rotates
        `model_kwargs["api_key"]` to the next key not yet seen exhausted before re-raising, so
        the retry that follows goes out on a key with budget. Exhausted keys are remembered
        process-wide (one orchestrate = one shard = many agents), so every agent in the shard
        skips them. Other 429s (true rate limits) are left to the normal backoff. Without
        CREATEAI_KEYS this is a no-op and the model behaves exactly as upstream.
        """
        pool = [k for k in os.environ.get("CREATEAI_KEYS", "").split() if k]
        kw = getattr(getattr(model, "config", None), "model_kwargs", None)
        retrying = getattr(type(model)._query, "retry", None) if hasattr(type(model), "_query") else None
        raw = getattr(type(model)._query, "__wrapped__", None) if retrying else None
        if len(pool) < 2 or not isinstance(kw, dict) or raw is None:
            return
        import litellm  # noqa: WPS433  (already imported by the model)

        aid = self.aid

        def rotating(messages, **kwargs):
            try:
                return raw(model, messages, **kwargs)
            except litellm.exceptions.RateLimitError as e:
                if "monthly budget" in str(e):
                    cur = kw.get("api_key")
                    _EXHAUSTED_KEYS.add(cur)
                    start = pool.index(cur) + 1 if cur in pool else 0
                    nxt = next((pool[(start + i) % len(pool)] for i in range(len(pool))
                                if pool[(start + i) % len(pool)] not in _EXHAUSTED_KEYS), None)
                    if nxt is None:
                        print(f"    [{aid}] every gateway key in CREATEAI_KEYS is exhausted")
                    else:
                        kw["api_key"] = nxt
                        print(f"    [{aid}] gateway key #{pool.index(cur) + 1 if cur in pool else '?'} "
                              f"exhausted its monthly budget -> switching to key #{pool.index(nxt) + 1}")
                raise

        model._query = retrying.wraps(rotating)

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

    def _seal_peers(self) -> None:
        """Remove peer-owned sources from this agent's worktree (see `seal_script`) and record
        what happened in agent_<k>/scope_seal.json, next to scope_violations.jsonl. A path the
        seal could not compile is reported, not hidden: it means that peer's module was not
        importable by the image's python3 to begin with."""
        try:
            rep = self.env.seal()
        except Exception as e:
            rep = {"error": f"{type(e).__name__}: {e}"}
        if rep:
            (self.inst_dir / self.aid / "scope_seal.json").write_text(
                json.dumps({k: v for k, v in rep.items() if k != "raw"}, indent=1))
            n, bad = len(rep.get("sealed", [])), rep.get("compile_failed", [])
            print(f"    {self.aid}: sealed {n} peer/fixed file(s)"
                  + (f", {len(bad)} not compilable: {bad}" if bad else "")
                  + (f" ({rep['error']})" if "error" in rep else ""))

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
                              submitted=submitted,
                              # A submission can arrive in a multi-block reply too -- first block
                              # submits, later ones never run.
                              n_blocks=getattr(self.agent, "n_blocks_last_parse", 1),
                              usage=self._usage_since(mark))
        except Exception as e:                       # never let one step kill the run
            return StepResult(step=self._steps, observation=f"{type(e).__name__}: {e}",
                              exit_status=type(e).__name__, done=True,
                              usage=self._usage_since(mark))

        action = self._last_action()
        return StepResult(
            step=self._steps,
            thought=self._last_thought(),
            action=action,
            # Only the FIRST block ran, so record how many arrived -- otherwise the trajectory
            # shows a lone valid command and the multi-block reply is invisible. The note the
            # model got lives in its context, not in `observation` (raw command output).
            n_blocks=getattr(self.agent, "n_blocks_last_parse", 1),
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
