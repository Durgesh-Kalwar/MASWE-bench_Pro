# Checkpoint — multi-agent full-access mode + coordination findings

**Started:** 2026-08-07 · **Last updated:** 2026-08-16 · **Branch:** `main`

> ## ▶ START HERE (2026-08-16): read **§9** (newest), then **§8** for the mechanism it tests.
> §§1-7 are historical: §§1-5 = full-access mode (committed as `4ad402b`), §6 = the
> coordination mode (`--partition-issue`/`--submit-gate`), §7 = a design study whose open
> questions §8 **supersedes**. Everything from §8 onward is the current state.
>
> **One-line status:** lockstep rounds + `no_op` + per-round read gate are implemented and
> verified. On a second instance (§9) coordination **provably changed real code** — a published
> `prepare_multipart` contract crossed the board and two consumers coded against it (35/46
> tests pass across two runs, best results yet). Remaining blockers are NOT the coordination
> channel: `no_op` livelock (an agent talked for 3 rounds and shipped 0 lines), agents that
> invent a competing API instead of adopting the published one (reproducible in BOTH runs), and
> a structural edit bug (§8). **Ranked next steps: §9.3.**

This file is the resume anchor: where the work stands, what was learned, and what to pick up
next. Feature docs live in `README.md` (§scope) and `multiagent_aci.md` (§2.5); this file is
the experiment log + next-step plan.

---

## 1. What was implemented this session (done + verified)

### A. `--distractors -1` full-access mode (the feature)
Selects a per-agent **denylist** instead of the default allowlist: each agent may read/write
the **entire repo EXCEPT the gold files owned by other agents** (its own gold file stays
editable). Contrasts the scoped "localization-under-decoys" setting with an unrestricted
baseline. Touch points:
- `build_multiagent_pro.py` — `-1` ⇒ per-agent `scope_mode="full"`, `deny = other agents' gold
  files`, written into `spec.json`.
- `aci/gen_solver_config.py` — injects env `SCOPE_MODE` + `SCOPE_DENY`; swaps to
  `FULL_SYSTEM_TEMPLATE` (tells the agent it may edit anything except peers' files).
- `aci/tools/scoped_fs/lib/scoped.py` — denylist branch in `in_scope`/`require_scope`
  (`_within_repo(p) and str(p) not in _denied()`); all edit tools inherit it via `require_scope`.
- `bin/scoped_list` / `bin/scoped_search` — full-mode UX (list shows primary+deny; search walks
  the whole repo skipping `.git`+denied). `bin/scoped_submit` — unscoped whole-repo diff in full mode.
- `aci/orchestrate.py` — **critical**: full mode collects an UNSCOPED whole-repo `git diff`
  (the agent's `scope` is no longer the edit boundary), else non-gold edits would be dropped.
- Overlap policy (user-chosen): agents may edit the same non-gold file; `merge_instance` warns
  on duplicate `diff --git` paths and the patch may fail `git apply` — surfaced, not reconciled.
- Default `--distractors 3` path is unchanged (`scope_mode="allow"`).

### B. Runtime-image ENTRYPOINT fix (`aci/build_runtime_image.py`)
Some Pro bases set `ENTRYPOINT ["/bin/bash"]` (e.g. `395e5e20`), which broke swe-rex's
`docker run <img> /bin/sh -c '...'` launch → `/bin/sh: cannot execute binary file`. Fix: derived
Dockerfile appends `ENTRYPOINT []` + `CMD ["bash"]`. Also folded `_DOCKERFILE` into
`derived_runtime_tag`'s hash so recipe changes force a rebuild (else the broken cached image is
reused). **Consequence:** all derived tags changed → `gen_solver_config.py` must be RE-RUN before
relaunching any instance (it bakes the tag into `solver.yaml`).

### C. CreateAI / GPT-4o-mini access (a 2nd OpenAI-compatible endpoint)
Registered `openai/gpt4o_mini` pricing; verified end-to-end. Details in memory
`anthropic-key-noninteractive-bashrc` (env-var names, model id, key wiring).

---

## 2. Run results (all real local-docker grades)

| Instance | Agents | Model | Mode | Grade | Note |
|---|---|---|---|---|---|
| `f327e65d` | 2 | qwen3-coder-30b | `-1` full | **PASS 100%** | first-ever pass; whole-repo diff captured a non-gold file agent_1 created at repo root |
| `395e5e20` | 4 | qwen3-coder-30b | `-1` full | **FAIL 0%** | agent_2 deleted public `class HostState` → ImportError → 0 tests collected |
| `395e5e20` | 4 | **gpt-4o-mini** (CreateAI) | `-1` full | **PASS 100%** | 8/8 tests; agent_2 preserved `HostState`; all 4 files engaged |

**Coordination finding (both models):** ZERO actual `send_message`/`read_messages`/
`publish_interface`/`list_agents` calls; board empty every round. (Grepping raw logs for these
names counts the tool DOCS in each prompt — false inflation; only `[agent_N] step K: <tool>`
lines are real calls.) So unused comm tools are **model-agnostic**, not a weak-model artifact.

---

## 3. The open decision *(HISTORICAL — resolved on 2026-08-08; see §6. Current state is §8.)*

**Insight (user, confirmed on `395e5e20`):** cooperation is **not required** in the current
setup, because the coordinating information is pre-loaded into every agent:
- "limited info = file scope, not issue text" ⇒ every agent gets the FULL `problem_statement`.
- `--include-interface` emits `shared/coordination.md` with the EXACT cross-file signatures
  (`IteratingStates`/`FailedStates`/`MetaPlayIterator`, names+paths+base classes, "one defines,
  others call"). Verified: agent_4 (a *consumer*, owns `linear.py`) already had
  `IteratingStates`/`FailedStates`/`HostState` named in its own `local_issue.md`.

So each agent implements its slice from a spec everyone already holds → the message board is
redundant → the benchmark currently measures **parallel decomposition + localization under
file-scope**, NOT coordination. A submit-gate forcing function would force tool *usage* but the
agents would have nothing genuinely new to exchange.

**The fork — depends on the research question:**
- **(a) Studying decomposition/localization under scope** → current design is fine. Do NOT add
  the comm forcing-function. Next step: run more instances × models to measure pass rate.
- **(b) Studying genuine coordination/negotiation** → the lever is **information partitioning**,
  not a submit-gate: (i) drop `--include-interface`, and more importantly (ii) route only a
  *slice* of the issue text per agent (revive the superseded symbol-routed partition) so a caller
  genuinely doesn't know the definer's chosen names → must `read_messages`/`publish_interface` or
  fail. THEN a submit-gate (gate `scoped_submit` on having read the board; require
  `publish_interface` on public-symbol delete/rename) becomes meaningful.

**Decision needed before more building:** which of (a) / (b) is the goal.

---

## 4. How to reproduce / continue (commands)

```bash
# key sourcing (bashrc has a non-interactive guard — source explicitly)
eval "$(grep -m1 '^export OPENAI_API_KEY=' ~/.bashrc)"; export OPENAI_API_KEY      # ASU RC / qwen
# for gpt-4o-mini via CreateAI, instead point OPENAI_API_KEY at the CreateAI key:
eval "$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)"; export OPENAI_API_KEY="$CREATEAI_API_KEY"
eval "$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)"

INST=<instance_id>
# 1) build (full mode)
python multiagent_pro/build_multiagent_pro.py --mode build --distractors -1 \
    --instances $INST --output multiagent_pro_out --include-requirements --include-interface
# 2) generate configs  (RE-RUN whenever build_runtime_image.py changed — tag is baked in)
python multiagent_pro/aci/gen_solver_config.py --output multiagent_pro_out --instances $INST \
    --model openai/gpt4o_mini --api-base "$CREATAI_BASE_URL" \
    --price-per-million-tokens 0.375 --context-window 128000 --per-instance-cost-limit 1.5
# 3) clear stale grade for this instance (see gotcha), then run + grade
rm -rf multiagent_pro_out/eval_out/$INST
python multiagent_pro/aci/orchestrate.py --mode agents --instances $INST \
    --output multiagent_pro_out --rounds 2 --steps-per-round 25 --grade
```

**Gotchas:**
- **Stale grade:** `orchestrate --grade` runs the evaluator WITHOUT `--redo`; it SKIPS any
  instance whose `eval_out/<inst>/<prefix>_output.json` exists and re-reports the OLD result.
  Always `rm -rf multiagent_pro_out/eval_out/<inst>` before a re-run, or re-grade with `--redo`.
- **Config regen after runtime-image change:** `solver.yaml` bakes the derived image tag; re-run
  gen_solver_config after any `build_runtime_image.py` edit.
- **CreateAI model id** is `openai/gpt4o_mini` (underscore); env vars are `CREATAI_BASE_URL`
  (no E) and `CREATEAI_API_KEY` (with E).

## 5. Git state
Uncommitted on `main` (base `da9a301`). Changed (feature): `build_multiagent_pro.py`,
`aci/build_runtime_image.py`, `aci/gen_solver_config.py`, `aci/orchestrate.py`,
`aci/tools/scoped_fs/lib/scoped.py`, `bin/{scoped_list,scoped_search,scoped_submit}`,
`aci/tools/scoped_fs/config.yaml`, `aci/custom_model_pricing.json`, `README.md`,
`multiagent_aci.md`. Nothing committed yet — commit is a pending choice for the resume session.

---

## 6. 2026-08-08 — genuine-coordination mode implemented (decision (b))

**User's clarified requirements:** (i) partition the issue text per agent so callers don't
know definers' chosen names; (ii) the submit-gate must be a REFUSAL only (never the harness
calling comm tools for the agent) and must be OFF by default behind its own flag — the
default experiment measures unprompted comm usage under partitioning alone.

**Implemented:**
- **`--partition-issue`** (build_multiagent_pro.py): exclusive unit assignment via
  `partition_units` — symbol-overlap scoring + **definer priority** (+100 per mention of a
  symbol the agent's gold diff *introduces*: added `def`/`class`/UPPERCASE-const lines →
  `defined_symbols()`); symbol-free units shared to all; empty-slice rescue that never moves
  a unit naming another agent's defined symbols (leak-guard). No full issue text, no "Key
  symbols" hint. Incompatible with `--include-interface` (SystemExit). Requirements routed
  through the same partition under `--include-requirements`. `spec.json` gains
  `partition_issue`, per-agent `local_units` + `defined_symbols`.
- **`--submit-gate`** (gen_solver_config.py → env `SUBMIT_GATE`): `scoped_submit` runs
  `scoped_fs/lib/submit_gate.py` first; refuses (exit 0, NO markers, NO /root/model.patch →
  episode continues) until (1) read-gate: `read_messages` wrote a canonical content-hash
  marker (`/root/comm/.read_<AGENT_ID>`) matching the current board (content hash because
  the host truncate-rewrites the board each turn — mtime is meaningless — and host/agent
  JSON formatting differs); (2) publish-check: every public def/class deleted (HEAD vs
  worktree, ast) is named in one of the agent's own board messages. Fails OPEN on internal
  errors. `read_messages` now calls `board.mark_read()` unconditionally (harmless gate-off).

**Verified offline (2026-08-08):**
- Partition on `395e5e20` (4 agents): units 2/16/3/2; ONLY agent_2 (definer) sees
  `IteratingStates`/`FailedStates`/`MetaPlayIterator`/members; consumers see zero defined
  names; no-flag rebuild byte-identical to pre-change output. Found+fixed two leaks along
  the way: consumer-wins-argmax (fixed by definer priority) and rescue-pulls-contract-unit
  (fixed by the leak-guard).
- Gate in the real py3.9 container (swerex-runtime:da5951963937328f): refuse-before-read /
  pass-after-read / stale-after-host-rewrite / re-read-pass; HostState deletion blocked
  naming HostState+copy+get_current_block, passes after one announcing message + fresh
  read; gate-off path byte-identical (markers emitted, patch written).

**EXPERIMENT RUN (2026-08-08, gpt-4o-mini, `395e5e20`, partition, full scope, NO gate):**
- **First-ever real comm usage:** agent_4 (consumer, linear.py) hit the engineered knowledge
  gap and asked over the board — `send_message` to agent_3 requesting "the definition of the
  HostState enum and the deprecated constants mapping", then 3× `read_messages` waiting for a
  reply. Zero comm calls in ALL unpartitioned runs → partitioning demonstrably induces
  coordination attempts.
- **But coordination did not complete:** agent_4 misaddressed the ask (agent_3, not the real
  definer agent_2), and agent_3 NEVER called read_messages (0 reads) so the question was
  never seen or answered. agent_4 then invented wrong names (`HostState.FAILED` mapping —
  HostState isn't even an enum); agent_3 burned 50 steps on scoped_search/view and submitted
  an EMPTY patch; agent_2 (definer) implemented `IteratingStates`/`FailedStates` correctly
  but never published them.
- **True grade: FAIL 0%** (8 tests: 3 PASS, 5 FAIL — deprecation class-attrs + iterator
  behavior; the unfinished consumer/compat work). Unpartitioned baseline was PASS 100% with
  zero comm — so partitioning made the task genuinely coordination-bound, and the model
  failed at coordination. This run is exactly the motivation for the `--submit-gate`
  ablation (its read-gate would have forced agent_3 to see the question).
- **Infra bug found + fixed during grading:** the whole-repo diff collection via
  `env.communicate` (pty) CRLF-mangles and can TRUNCATE trailing blank-context lines —
  agent_4's hunk came back 2 lines short of its @@ header count → `git apply: corrupt patch`
  → the merged patch silently graded as no-op (first grade printed 0% with `tests: []`).
  Fixed in `orchestrate.py`: pipe the diff through `base64 -w0` and decode host-side
  (byte-exact through the pty). This run's agent_4.patch was hand-repaired (recounted @@
  header) to obtain the true grade above.

**`--submit-gate` ABLATION RESULT (2026-08-08, same setup + `--submit-gate`):**
- **Gate worked exactly as designed:** 8 refusals converted into real coordination. Comm
  calls jumped from 1 (agent_4 only, ungated) to **10 across 3 agents**, including the FIRST
  EVER `publish_interface` calls (4 of them: agent_1 x2, agent_2 x2). agent_1 tried its usual
  3-step submit, got refused, immediately `read_messages` -> `publish_interface` -- the
  refusal-to-action pattern the gate is designed to produce.
- **New failure mode surfaced: a naming COLLISION.** agent_1 and agent_2 (the actual definer)
  both published interfaces for the same concept under DIFFERENT names: agent_1 published
  `enum PlayIteratorRunState`/`PlayIteratorFailureState`; agent_2 published
  `class IteratingStates(IntFlag)`/`FailedStates(IntFlag)` (the names it actually wrote in
  code). agent_4 used NEITHER name (0 matches). Nothing in the comm protocol marks which
  agent's publish is authoritative for a file it doesn't own, and no one asked to resolve
  the conflict.
- **Grade: still FAIL 0%, but from an UNRELATED cause** (`tests: []`, real, base64 fix
  confirmed working -- `git apply --check` passes cleanly). agent_2's own edit (in the file
  IT owns) has a genuine structural bug: it dedented `from enum import ...` + two new
  `IntFlag` classes to column 0 mid-`class PlayIterator:`, but the ORIGINAL trailing class
  body (`FAILED_NONE = 0`, `__init__`, all methods) stayed at 4-space indent -- which now
  nests it inside the new `class FailedStates(IntFlag)` instead of back inside
  `PlayIterator`. Verified via `ast.walk`: `PlayIterator` ends up with ZERO methods;
  `FailedStates` inherits `__init__(play, play_context, variable_manager, all_vars)`, so
  Python's Enum metaclass TypeErrors constructing `NONE = 0` at import time. Syntactically
  valid Python (`compile()` succeeds) -- the syntax linter correctly did NOT catch this, as
  documented (it catches SyntaxError, not structural/semantic corruption). This bug is
  ORTHOGONAL to coordination -- it would have happened in the unpartitioned/no-gate runs
  too, on the same file, if agent_2 made the same edit.

**Bottom line across all three runs:** partitioning induces the *need* to coordinate;
the gate reliably converts that need into actual comm-tool usage. The remaining gaps are
(1) no interface-collision resolution when two agents publish conflicting names for the same
concept, and (2) the edit tools' syntax check doesn't catch structurally-corrupting-but-valid
indentation changes. Neither gap is specific to full-access/partition mode -- both are
general robustness issues in the comm protocol and the scoped edit tools respectively.

**NEXT STEP (not started):** candidates, in rough priority: (a) publish-collision handling
(e.g. `publish_interface` on a symbol another agent already published triggers a required
reconciliation message, or the gate could flag divergent signatures for the same concept);
(b) a stronger structural check beyond `compile()` -- e.g. re-parse and diff the AST's
top-level class/def boundaries before/after an edit to catch "content moved into the wrong
enclosing scope" corruption; (c) run more instances to see how often the indentation-bug
class of failure recurs independent of coordination.

---

## 7. 2026-08-08 (cont'd) — round-retirement gap, parallel-feasibility research, resumable-done risk catalog

### 7.1 Two new findings while inspecting agent_1's round-1 trajectory (`agent_1/traj/round_1.json`)

**Finding A — the submit-gate's read-marker self-invalidates on the agent's OWN writes.**
Traced the exact step sequence from the `--submit-gate` ablation run (see §6's ablation
result). `submit_gate.py`'s `check_read_gate()` hashes the ENTIRE current board and compares
to what the agent's marker recorded at its last `read_messages` call. But `publish_interface`/
`send_message` both call `board.append()` (`comm/lib/board.py`), which mutates the same
`board.json` the hash is computed over — so **an agent invalidates its own read-marker every
time it writes to the board**, indistinguishable from a peer posting something new. Real trace
(agent_1, round 1):

| Step | Action | Board after | Marker | Gate |
|---|---|---|---|---|
| 3 | `scoped_submit` | `[]` | none | BLOCKED (never read) |
| 4 | `read_messages` | `[]` | `hash([])` | — |
| 5 | `publish_interface` | `[msg1]` | stale (`hash([])`) | — |
| 6 | `scoped_submit` | `[msg1]` | stale | **BLOCKED** |
| 7 | `scoped_submit` (retried) | `[msg1]` | stale | **BLOCKED** |
| 8 | `read_messages` | `[msg1]` | `hash([msg1])` | — |
| 9 | `publish_interface` | `[msg1,msg2]` | stale | — |
| 11 | `scoped_submit` | `[msg1,msg2]` | stale | **BLOCKED** |
| 12 | `read_messages` | `[msg1,msg2]` | `hash([msg1,msg2])` | — |
| 13 | `scoped_submit` | `[msg1,msg2]` | matches | **PASSES** |

Not a fatal bug (agent_1 completed in 13 steps regardless), but it's an unintended side effect,
not the designed intent ("make sure you've seen the board," not "penalize you for writing to
it"). **Fix identified, not yet applied:** either (a) have `send_message`/`publish_interface`
call `mark_read()` themselves right after appending (their own write already reflects "current
state"), or (b) hash only `messages from other agents` (`m["from"] != me`) in the gate check —
option (b) is closer to the actual intent.

**Finding B — a successful `scoped_submit` PERMANENTLY retires an agent from the whole run.**
Re-read `orchestrate.py`'s round loop (`~168-199`) to confirm precisely:
```python
for r in range(rounds):
    for a in spec["agents"]:
        aid = a["id"]
        if done[aid]:
            continue                    # <-- skipped entirely, agent.step() never called again
        env.write_file(COMM_BOARD_IN_IMAGE, json.dumps(board))   # board sync IN
        for _ in range(steps_per_round):
            out = agent.step()
            if getattr(out, "done", False):
                done[aid] = True        # <-- PERMANENT, never reset
                break
```
Once `done[aid] = True`, every later round's `if done[aid]: continue` skips that agent
forever — `agent.step()` is never invoked again, the board is never synced into its container
again, it can never read a new message, never answer a question, never revise its patch, even
if a peer's question arrives one step later in the SAME round. Agents run in a fixed order
(`agent_1 → agent_2 → agent_3 → agent_4` every round), so an agent that finishes at the START
of round 1 is deaf to everything any peer posts for the rest of the run.

**This directly explains the coordination failures already logged in §6**: even a
perfectly-targeted, perfectly-timed question from agent_4 to agent_2 would go unanswered if
agent_2 had already submitted, independent of the gate or model quality. The submit-gate makes
an agent more likely to check the board *before* submitting; it does nothing for messages that
arrive *after*.

### 7.2 Two candidate fixes discussed: "final catch-up round" vs. "resumable done"

**Final catch-up round** (smaller, additive): after the normal round loop ends, do ONE extra
pass — any `done` agent whose board grew since it went silent (tracked via a new
`done_at_len[aid] = len(board)` snapshot at the moment `done[aid]` becomes `True`) gets a
small fixed budget (e.g. 5 steps) to react. **Limitation: only closes ONE hop.** If the asker
(e.g. agent_4) is *also* already done by the time the definer's late answer lands, it never
sees the answer — a single end-of-run pass can't chain.

**Resumable `done`** (bigger, more complete): the round-loop skip condition becomes
`if done[aid] and not has_new_relevant_messages(aid): continue` — re-evaluated EVERY round, not
just once at the end. A `done` agent with new messages addressed to it gets re-activated with a
fresh turn. Naturally closes multi-hop chains (ask → answer → revise) as long as `--rounds` is
generous enough, though how many rounds a given chain needs depends on agent iteration order
relative to who's asking whom (gist: if the answerer's fixed turn-order slot falls before the
asker's in the same round, the chain can close within that round; if after, it needs one more
round).

**User's stated lean: resumable `done`**, but wanted the full risk surface understood first
(§7.4) and wanted **parallel execution investigated first** as a possible alternative framing
(§7.3) before committing.

### 7.3 Parallel-execution feasibility research (read-only investigation, two Explore agents)

**Question asked:** instead of "rounds" at all, could all N agents run their step loops
truly CONCURRENTLY, using one large step budget instead of round barriers?

**Verdict: technically feasible, evidenced concretely, not speculative.** SWE-agent's own
`sweagent/run/run_batch.py` already does exactly this pattern for batch-solving many
instances: a `concurrent.futures.ThreadPoolExecutor` drives separate `Agent`/`SWEEnv` pairs
concurrently, one thread per agent/instance (`run_batch.py:268-289`, `main_multi_worker()`).
Confirmed safe building blocks:
- Separate `Agent`/`SWEEnv` instances have no hidden shared state — both explicitly
  deep-copy their configs ("Always copy config to avoid shared state between different
  instances" — `SWE-agent/sweagent/agent/models.py:563-564`, `swe_env.py:90-91`).
- The one genuinely shared, mutable, process-global state (`GLOBAL_STATS`, cost-limit
  tracking) is already lock-protected by SWE-agent itself
  (`GLOBAL_STATS_LOCK`, `models.py:265-271,608-610`).
- Container isolation (one Docker container per agent, no shared filesystem/volume) means
  filesystem/git-index races between agents are NOT possible regardless of scheduling model —
  confirmed by reading `scoped_fs/lib/scoped.py`'s full-mode denylist logic and
  `scoped_submit`'s git operations; "the same file" edited by two agents is always two
  physically distinct on-disk copies in two distinct containers.
- **Why asyncio is the WRONG primitive** (would actively break things): `SWEEnv`'s I/O methods
  (`communicate`/`read_file`/`write_file`) each call a **fresh `asyncio.run()`** per operation
  (`swe_env.py:183,220,247,254`), and `swerex`'s "async" deployment/runtime methods are
  actually backed by blocking `requests`/`subprocess` calls under the hood
  (`swerex/runtime/remote.py:157-164`, `swerex/deployment/docker.py:256`) — scheduling
  multiple agents as `asyncio.Task`s on one shared event loop would crash the instant any
  agent's tool call nested another `asyncio.run()` inside the already-running loop
  (`RuntimeError: asyncio.run() cannot be called from a running event loop`), and would gain
  nothing anyway since there's no genuine async I/O underneath to interleave.
- **Why multiprocessing is unnecessary**: no CPU-bound work in the hot path (LLM calls +
  container HTTP calls are both I/O-bound, release the GIL) — multiprocessing would just add
  IPC/pickling overhead and fragment `GLOBAL_STATS` cost-limit tracking across processes.
- **Threading is the right primitive**, matching SWE-agent's own proven pattern.

**But four pieces of NEW synchronization infrastructure would be required — none of which
exist anywhere in this codebase today** (confirmed via exhaustive grep across `multiagent_pro/`
for `threading`/`Lock`/`asyncio`/`Semaphore`/`ThreadPoolExecutor`/`filelock`/`fcntl`/`flock`:
**zero hits**):

1. **A lock around the host-side `board` Python list.** `merge_board(board, ...)` →
   `board = new_board` (`orchestrate.py:189-195`) is a pure function over a snapshot, safe
   only because it's sequential today. Concurrent calls are a **confirmed lost-update race**:
   thread A and B both read `board` at state S0; A computes and assigns S1; B (unaware of A's
   write) computes from its stale S0 snapshot and assigns S2, silently discarding everything A
   appended.
2. **An entirely new board-propagation mechanism.** The design's ONLY sync point today is the
   round barrier (`orchestrate.py:11-12`'s own comment: "messages propagate at the round
   barrier"; IN at line 176, OUT at 189-195). Remove rounds and this vanishes completely — no
   other propagation path exists. Would need a background polling/push loop per agent
   container, built from scratch, with a genuine latency-vs-container-I/O-overhead tradeoff
   (poll interval × N containers).
3. **Atomic writes for `board.json`, both host- and container-side.** `save_board`
   (`comm/lib/board.py`) is a plain non-atomic read-modify-write (no temp-file-plus-rename);
   safe today only because the host's `env.write_file` and the in-container `append()` never
   overlap in time (turn boundaries guarantee this). Without turn boundaries, they could
   interleave.
4. **Atomic + locked writes for `custom_model_pricing.json`.** `model_pricing.py`'s
   `_save_registry()` is a full-file overwrite, not atomic. Two threads registering different
   NEW custom models at the same instant risk either a **lost update** (second writer's save
   clobbers the first's) or genuine **byte-level file corruption** (interleaved writes producing
   invalid JSON that crashes the next read). Only bites when new (not-yet-registered) models
   are registered concurrently at startup — the common re-run case is read-only and safe.

**Pre-existing risk that parallelism does NOT introduce, but does make more consequential:**
full-mode semantic file conflicts (two agents both editing a shared non-gold file, breaking
`merge_instance`'s naive concatenation — already explicitly warned about in
`build_multiagent_pro.py`) already exist in the current sequential design (nothing about
round-based turns prevents two agents editing the same file in different rounds). Parallelism
removes the weak, incidental protection round barriers currently provide (an agent at least has
a *chance* to see a peer's board post from an earlier round before its own turn) — making
silent, simultaneous collisions more likely, not introducing a new failure class.

**The key structural insight for the decision:** **parallel execution and resumable-`done` are
orthogonal — they solve different axes of the problem.** Parallel changes WHEN agents run
relative to each other (concurrent vs. turn-based) and could reduce wall-clock latency /
remove turn-order fairness bias. It does **NOT**, by itself, solve "an agent that already
finished can't hear a later message" — that's independent of scheduling model. Even under full
parallelism, once an agent's `agent.step()` loop naturally ends (it decided it's done), nothing
restarts it unless something explicitly revives it — you'd need a resumable-done-equivalent
mechanism regardless of whether execution is sequential or parallel.

**Decision (user, this session):** defer parallel execution to a **separate branch**, if/when
pursued — it is not a substitute for resumable-`done`, and the new-infrastructure cost above is
substantial. Proceed with evaluating resumable-`done` as the near-term fix on `main`.

### 7.4 Resumable-`done` — full risk catalog (before implementation)

| # | Risk | Mechanism | Severity |
|---|---|---|---|
| 1 | **Cost/step budget blowout via re-trigger cascades** | Each revival costs up to a full step budget; the only backstops are SWE-agent's `per_instance_cost_limit`/`per_instance_call_limit`, both cumulative over the agent's WHOLE life, not per-revival. A chatty exchange could burn real $ / calls on communication instead of code-editing. | High |
| 2 | **Live-lock / oscillation between two agents** | ask → answer → follow-up question → answer → ... Bounded only by `--rounds` and cost limits, nothing detects "going in circles." Could consume the whole run on chat with zero code progress. | High |
| 3 | **False-positive revivals from broadcast noise** | Nearly all observed comm traffic uses `to: "all"` (`publish_interface` hardcodes this). A naive "revive if board grew" check wakes EVERY done agent on EVERY broadcast, even irrelevant ones — compounds risk #1 even without a genuine multi-hop chain. | Medium-High |
| 4 | **Compounds with `--submit-gate`'s self-invalidating marker (§7.1 Finding A)** | A revived agent that posts a reply immediately re-gates itself under the current (unfixed) marker logic, needing yet another `read_messages` inside its already-small revival budget. Should fix together if both features are ever enabled at once. | Medium (only if both features on) |
| 5 | **`done_at_len` snapshot timing must be exact** | Same bug CLASS as Finding A — if "board length I last saw" is snapshotted at the wrong moment, get the same "invalidated by my own action" pattern. Needs care; we now have a concrete precedent bug to test against. | Medium (implementation-correctness) |
| 6 | **Doesn't fully close the loop for silent file edits, only messages** | If a peer revises code in a later round after another agent went `done` and was NOT revived (e.g. filtered out as irrelevant), that agent never learns of the change unless it was ALSO announced via `publish_interface`. Ties into the still-open interface-collision gap from §6. | Medium |
| 7 | **Reduced determinism/reproducibility** | Total run length and exact call sequence become sensitive to precise message timing/content — harder to reason about/reproduce for benchmark write-up than the current fixed `rounds × steps_per_round` structure. | Low-Medium (a cost, not a bug) |
| 8 | **No filtering policy is simultaneously precise and complete** | Directed-only revival (`to == aid`) misses relevant broadcasts (e.g. a corrected interface signature); any-growth revival triggers #1/#3. This is a genuine design tension requiring an explicit choice, not something to solve away. | Design decision |

**Checked and confirmed NOT risks** (so these aren't re-litigated next session):
- **Final diff collection is safe regardless of revival count** — runs strictly after the
  entire round loop, reads whatever's on disk at that moment.
- **Agent conversation continuity across a revival gap already works** — `agent.trajectory` is
  cumulative, step numbering just continues; being paused across several rounds then revived is
  structurally identical to how a normal not-yet-done agent is already paused between its own
  turns today (existing mechanism, no new plumbing needed).
- **`history_processors: last_n_observations n=5`** means a long-dormant revived agent may have
  "forgotten" earlier context — pre-existing behavior for ANY multi-round agent, not something
  revival introduces. (Superseded in part: N is now the `--last-n-observations` flag, and the
  elision is *not* harmless for `read_messages` output — see §9.4.)

### 7.5 Open sub-decisions before implementing (unresolved, pick up next session)

1. **Revival-bound strategy** — max-revivals-per-agent cap, directed-only filtering, or both
   together (tradeoffs: cap is simple but doesn't reduce noise; directed-only avoids noise but
   provably misses relevant broadcasts like a corrected interface signature — see risk #8).
   A middle-ground floated but not evaluated: let broadcasts arrive passively into an agent's
   NEXT natural turn (if it has one) without forcing a revival, reserving forced revival for
   directed messages only.
2. **Whether to fix the self-invalidating read-marker (Finding A) alongside**, since risk #4/#5
   share the same root cause class.
3. **Exact `done_at_len` snapshot semantics** — must snapshot `len(board)` at the moment
   `done[aid]` becomes `True` (i.e., AFTER that agent's own end-of-turn board merge, so its own
   just-posted messages don't count as "missed"), verified conceptually correct in the
   worked examples but not yet implemented/tested.

### 7.6 Session status: STOP HERE

**No implementation started.** User is inclined toward resumable-`done` but wants §7.4/§7.5
weighed carefully before committing. Nothing to run, nothing pending in the background.
**Resume next session from §7.5's three open sub-decisions.**

If parallel execution is later pursued instead of / in addition to resumable-`done`, it will
be built on a **separate branch** (user's explicit choice), not on `main`.

Still-open items carried over from §6 (unchanged, not addressed this session):
- Interface-naming-collision handling (two agents publishing different names for the same
  concept, no reconciliation mechanism).
- Structural edit-check beyond `compile()` (AST scope-boundary diff, to catch
  valid-but-corrupting indentation changes like the `IntFlag`/`PlayIterator` bug in §6).

Git state unchanged from §5 — still all uncommitted on `main` (base `da9a301`).
*(Superseded: §7's work was committed + pushed as `4ad402b`; see §8.)*

---

## 8. 2026-08-15 — lockstep rounds, `no_op`, unread-only reads, read-once gate (IMPLEMENTED)

§7 ended with three open sub-decisions about "resumable done". The user replaced that design
with a cleaner one, implemented and verified this session. **This supersedes §7.5** — the
revival-bound/filtering questions are moot because agents are never retired on submission at
all, and the read-marker bug (§7.1 Finding A) is fixed by construction.

### The new protocol
1. **Lockstep board.** The board is FROZEN at the start of each round; every agent in that
   round is handed byte-identical state, and everything posted during the round is published
   only at the round barrier. An agent therefore reads peers' messages from **previous rounds
   only**. (Before: the board was merged after *each agent's turn*, so agent *k* saw agents
   1…*k*−1's same-round messages — turn order silently decided who knew what.)
2. **Everyone runs every round.** No retirement on submission. A submitted agent still gets a
   turn so it can answer a peer's later question or revise; the run stops when every
   still-active agent submits **in the same round** (or `--rounds` runs out). No early stop on
   an all-`no_op` stalemate (user's explicit choice).
3. **New `no_op` tool** (`scoped_fs/bin/no_op`): "I'm missing information only a peer can give
   me" — ends the agent's step loop for THIS round only, does not mark it done, returns next
   round. Distinct from `exit_forfeit` (permanent).
4. **Peer-only, unread-only reads.** `visible_to` now excludes the agent's own messages, and a
   per-agent cursor (`/root/comm/.read_<AGENT_ID>`, content-digest set) means each peer message
   is shown exactly once, ever.
5. **Read-once submit gate.** `check_read_gate` now only asks whether the cursor file exists.
   Kills §7.1 Finding A by construction: nothing posted later (least of all the agent's own
   `publish_interface`) can re-block a submission.

### Two SWE-agent facts that shaped the implementation
- **`done=True` has ~10 causes**, only one being a real submission. The loop treats
  `exit_status.startswith("submitted")` as submitted (per-round, resettable) and every other
  cause (`exit_cost`, `exit_context`, `exit_format`, `exit_command_timeout`, `exit_forfeit`,
  `exit_error`, …) as **permanent retirement** — otherwise a cost-limited agent would burn a
  wasted step every remaining round.
- **`TotalCostLimitExceededError` is re-raised**, not converted to a done-step
  (`agents.py:1163-1164`). Unguarded it would abort `run_agents` and skip diff collection,
  losing every agent's work. `agent.step()` is now wrapped.
- `no_op`'s marker must be the FIRST output line (observations truncate head-first at 100k),
  matched as a substring (pty adds CRLF), must not collide with `###SWE-AGENT-*` /
  `<<SWE_AGENT_SUBMISSION>>`, and must stay off the submit path (a submitting step overwrites
  its own observation with the patch text).
- A **round notice** is injected as a plain `user` turn via `agent._append_history` from round 2
  on (valid because function-calling observations are appended with role `tool`). Without it a
  re-invoked agent has no idea why it is being stepped again, and "all submit in the same
  round" termination is unreachable. Best-effort: wrapped in try/except.

### Verified (2026-08-15)
- **Host unit tests:** peer-only filter drops self-authored messages; cursor returns each
  message exactly once and survives the host rewriting `board.json` in different formatting.
- **Lockstep simulation:** all agents in a round see identical state; round-1 posts invisible
  in round 1 and delivered in round 2; no duplication through `merge_board`.
- **Real py3.9 container** (`swerex-runtime:da5951963937328f`), 8 checks: `no_op` marker is
  line 1 / exit 0; gate blocks before any read; read of an EMPTY board satisfies it;
  **publishing afterwards does NOT re-block (the §7.1 regression)**; a host-added peer message
  does not re-block; `read_messages` shows a new message once then nothing; own messages never
  echoed back; gate-off `scoped_submit` still emits both markers + writes `/root/model.patch`.
- Configs regenerated (templates changed) + `--mode dry` passes for all 4 agents.

### Files changed
`aci/orchestrate.py` (lockstep loop, `NOOP_MARKER`, `_notify_round`, retire-vs-submitted, step
guard), `aci/tools/scoped_fs/bin/no_op` (NEW), `aci/tools/scoped_fs/config.yaml`,
`aci/tools/scoped_fs/lib/submit_gate.py`, `aci/tools/comm/lib/board.py`,
`aci/tools/comm/bin/read_messages`, `aci/tools/comm/config.yaml`, `aci/gen_solver_config.py`
(templates), `README.md`, `multiagent_aci.md`.

### Per-round read gate (user amendment, same session)
The first lockstep run exposed that a **read-once-ever** gate lets a finished agent submit
straight past a board holding a question for it: agent_2 (the only agent that knew the enum
names) took exactly ONE step in round 3 (`scoped_submit`) while agent_3 and agent_4 sat
blocked asking for exactly those names. Fix (user-specified):
- **Read once per ROUND, not once ever.** The host writes the round number to
  `/root/comm/.round` at the start of every turn; `read_messages` stamps it into
  `.read_round_<AGENT_ID>`; the gate blocks unless they match. Still not a content
  comparison, so the §7.1 self-invalidation stays fixed (publishing after reading never
  re-blocks within a round). Falls back to read-once-ever when no `.round` file exists
  (offline tooling / gold mode).
- **Personalized re-invocation notice.** An agent that already submitted gets a notice naming
  the round it submitted in ("You already submitted your patch in round N …"), telling it to
  read the board FIRST and decide from what it finds (answer a peer / apply their info /
  re-submit to confirm).

### RUN RESULT (2026-08-15, gpt-4o-mini, `395e5e20`, partition + full scope + gate, rounds=3)
**PASS 100% — 8/8 tests, real local-docker eval** (`eval_results.json: true`; eval_out cleared
beforehand). First pass under the partitioned/coordination-required setting.

**First successful definer→consumer answer in the project's history:**
`agent_2 -> agent_3: "the HostState class is defined in lib/ansible/executor/play_iterator.py.
Its __str__ method was just updated to use the new IteratingStates and FailedStates enums..."`
— produced only because the per-round gate forced agent_2 to read in round 3.

Board timeline (lockstep verified): round 1 = **0 messages**; round 2 = agent_3 broadcasts a
question + agent_4 asks agent_1; round 3 = agent_1 replies, **agent_2 answers agent_3**,
agent_4 follows up.

Comm usage: 5 `send_message`, 8 `read_messages`, 3 `no_op`, 1 `list_agents` (vs 4 total
ungated, 10 gated-non-lockstep). Gate refusals: **5** across 4 agents × 3 rounds — one per
agent-round, vs 8 for a single agent under the old hash gate.

**But the answer was delivered one round too late.** agent_2 posted it *during* round 3, so it
was only readable in round 4 — which never ran. Verified: agent_3's round-3 read saw **0
messages**, and both consumers submitted 0-line patches. The PASS came from agent_1 +
agent_2's own work, not from completed coordination.

**Actionable consequence — `--rounds 3` is too few for a full chain.** Under lockstep, an
ask→answer→apply cycle costs three round transitions: ask in round R, readable R+1, answer in
R+1, readable R+2, applied in R+2. With the first ask landing in round 2, the consumer cannot
act before round 4. **Use `--rounds 5+` for coordination experiments.**

Secondary: agent_4 twice asked **agent_1** (the changelog owner) for the enum names instead of
agent_2, despite calling `list_agents`; agent_1 honestly answered that it had not defined
them. Peer-targeting remains a real weakness (same root as the §6 collision finding).

### NEW failure mode observed: a bad patch can HANG the grader
The preceding (read-once) run's eval ran **25+ minutes at 100% CPU while allocating ~10 GiB/min
(reached 132 GiB)** — a non-terminating loop in agent_2's `play_iterator.py` rewrite, driven
forever by `test_play_iterator.py`. Killed manually; freed ~128 GiB. Grading now deserves a
timeout/memory guard, since a runaway patch threatens the whole machine, not just the run.

### RUN RESULT (2026-08-15, same setup, `--rounds 5`) — richer coordination, FAIL 0%
Run with two extra rounds so an ask→answer→apply chain could physically complete.

**Coordination went much further than any previous run:**
- 12 `send_message`, 15 `read_messages`, **2 `publish_interface`**, 6 `no_op`; 10 gate refusals
  (≈1 per agent-round, as designed).
- agent_2 published the **correct** contract, twice: `class IteratingStates(IntEnum)` and
  `class FailedStates(IntFlag)` — and answered agent_3 directly with the enum members. The
  §6 naming-collision reappeared (agent_1 again announced invented
  `PlayIteratorRunState`/`PlayIteratorFailureState`), but agent_2 also *corrected the record*
  on the board, which is new.

**Yet both consumers still shipped 0-line patches.** agent_3 `no_op`'d in rounds 2, 3, 4 AND 5
— it kept re-asking for "the exact enum names and members" even after agent_2 published them,
never once submitting. agent_4 `no_op`'d in 2 and 5 and at one point forwarded agent_3's own
question *back to agent_3*. So more rounds bought more conversation, not more code.

**Grade: FAIL 0%, `tests: []` — but NOT a coordination failure.** Same recurring structural
bug as §6, third occurrence on this file: agent_2 dedented the new enum classes mid-`class
PlayIterator`, orphaning the original class body into the enum. Verified by `ast.walk` on the
applied patch: `PlayIterator` ends with **0 methods** while `FailedStates` swallowed **15**
(`__init__`, `get_host_state`, `get_next_task_for_host`, …), so the Enum metaclass raises
`TypeError: __init__() missing 4 required positional arguments` at import. Syntactically valid,
so `compile()` (the current linter) cannot see it.

**Regression worth noting: agent_2's code output shrank as coordination grew** — 159 patch
lines under `--rounds 3` (PASS) vs **68** under `--rounds 5` (FAIL). Time went into the board
instead of the file. More rounds is not monotonically better.

### 8.8 All runs to date on `395e5e20` (4 agents, gpt-4o-mini via CreateAI)

| # | Setting | Real comm calls | Grade | What decided it |
|---|---|---|---|---|
| 1 | unpartitioned (§6) | **0** | PASS 100% | no coordination needed — every agent held the full issue |
| 2 | partition, no gate (§6) | 4 (1 agent) | FAIL 0% | agent_3 never read the board; question died unseen |
| 3 | partition + hash gate (§6) | 10 (3 agents) | FAIL 0% | **structural edit bug** (`PlayIterator` methods reparented) |
| 4 | + lockstep, read-once gate, rounds=3 | 17 | *(ungraded — grader HUNG, see above)* | agent_2 submitted past the board without reading |
| 5 | + **per-round gate**, rounds=3 | 17 | **PASS 100%** (8/8) | agent_2 answered agent_3 — but 1 round too late to use |
| 6 | + per-round gate, **rounds=5** | **35** | FAIL 0% | **structural edit bug again** (3rd time) |

Read across the rows: the coordination mechanisms are working (0 → 35 real comm calls, and by
run 6 the definer publishes correct contracts and corrects a peer's wrong ones). What now
decides pass/fail is **not** coordination — it is the edit-tool bug in rows 3 and 6, and
round-budget arithmetic in row 5.

### 8.9 Session status — STOP HERE (2026-08-15)

**Nothing is running.** No background processes, no stray containers (verified). Grading of
run 4 was killed deliberately (runaway; see above) and its container removed.

**Working tree: COMMITTED + PUSHED** as `bec29b9` (all of §8's work; supersedes the
"uncommitted" note that stood here mid-session). `origin/main` is level with local.
(`SWE-agent` submodule still carries its own separate uncommitted `models.py` fix —
deliberately excluded, see §5.)

**`.gitignore` bug fixed in that same commit:** a stock Python-packaging `lib/` rule was
silently excluding the ACI tool libraries, so `4ad402b` and earlier had shipped bins that
`import scoped`/`import board` **without the modules themselves** — a fresh clone had broken
bundles. `scoped.py`, `board.py` and `submit_gate.py` are now tracked via a targeted negation
(`!multiagent_pro/aci/tools/*/lib/`); `__pycache__` and real build `lib/` dirs stay ignored.

**Artifacts kept for comparison:** the rounds=3 PASS (boards, patches, `eval_results.json`) is
backed up under the session scratchpad `.../scratchpad/rounds3_pass/`; `multiagent_pro_out/`
currently holds the rounds=5 FAIL run.

**Ranked next steps (start here tomorrow):**
1. **AST structural edit-check** — highest value by a wide margin; this one bug class has now
   decided runs 3 and 6. In `scoped_fs/lib/scoped.py`, extend the existing `check_syntax()`
   (which only runs `compile()`) to also parse before/after and **reject an edit that changes
   the enclosing class/def of any pre-existing member** — i.e. catch "content reparented into
   the wrong scope", which is syntactically valid and therefore invisible today. Verify by
   replaying agent_2's exact bad edit: `PlayIterator` must not end up with 0 methods.
2. **`no_op` livelock guard** — agent_3 passed in rounds 2/3/4/5 and shipped nothing. Options:
   cap consecutive `no_op`s, or force a submit attempt in the final round.
3. **Peer-targeting** — agents broadcast, ask the wrong peer (agent_4 asked the changelog
   owner for enum names, twice), or echo a question back to its own sender. `list_agents`
   exists and is under-used; consider surfacing the owner of a symbol/file in the roster.
4. **Round budget** — `--rounds 5` gave more talk but *less* code (agent_2: 159 → 68 patch
   lines). Not monotonic; worth measuring 4 vs 5 vs 6 once (1) is fixed.
5. Interface-naming-collision reconciliation; grader timeout/memory guard; parallel execution
   (separate branch, §7.3).

**Reproduce the current best configuration** (run 5, the PASS) — note `--rounds 3`:
```bash
eval "$(grep -m1 '^export CREATEAI_API_KEY=' ~/.bashrc)"; export OPENAI_API_KEY="$CREATEAI_API_KEY"
eval "$(grep -m1 '^export CREATAI_BASE_URL=' ~/.bashrc)"
INST=instance_ansible__ansible-395e5e20fab9cad517243372fa3c3c5d9e09ab2a-v7eee2454f617569fd6889f2211f75bc02a35f9f8
python multiagent_pro/build_multiagent_pro.py --mode build --distractors -1 \
    --instances $INST --output multiagent_pro_out --include-requirements --partition-issue
python multiagent_pro/aci/gen_solver_config.py --output multiagent_pro_out --instances $INST \
    --model openai/gpt4o_mini --api-base "$CREATAI_BASE_URL" \
    --per-instance-cost-limit 1.5 --submit-gate
rm -rf multiagent_pro_out/eval_out/$INST                      # else the grade is STALE
rm -f  multiagent_pro_out/$INST/agent_*.patch multiagent_pro_out/$INST/board*.json
rm -rf multiagent_pro_out/$INST/agent_*/traj
python multiagent_pro/aci/orchestrate.py --mode agents --instances $INST \
    --output multiagent_pro_out --rounds 3 --steps-per-round 25 --grade
```
**Watch grading** — a non-terminating patch can hang it at 100% CPU while allocating ~10
GiB/min (it reached 132 GiB before being killed). If `Overall accuracy` has not appeared a few
minutes after `Running local-docker evaluation`, check `docker stats` and kill it.

**Counting comm calls correctly:** only `[agent_N] step K: <tool>` lines are real calls.
Grepping the raw log for tool names also counts the tool DOCS embedded in every prompt, which
inflates the number several-fold.

---

## 9. 2026-08-16 — second instance (`b748edea`, multipart): coordination provably changes code

Switched instances to test coordination independently of the PlayIterator case. Picked
`b748edea` because it is the only remaining sample whose dataset `interface` field declares a
**real cross-file contract**: `prepare_multipart` defined in `lib/ansible/module_utils/urls.py`
and called from three other files. (`a26c325b` says "No new interfaces are introduced" — no
contract, so partitioning would create no coordination need; `e40889e7` is 10 agents, 6 of them
docs.) Topology: **1 definer + 3 consumers + 1 changelog**.

**Partition verified before launch:** `prepare_multipart` appears **6×** in the definer's issue
slice and **0×** in all four consumers'. They are told they need multipart handling with
`filename`/`content`/`mime_type` but never the function name — the name is obtainable *only*
over the board.

Config: partition + full scope + per-round gate, gpt-4o-mini, `--rounds 4` (minimum for a
complete ask→answer→apply chain per §8's arithmetic, avoiding the `--rounds 5` talk-drift).

### Three firsts
1. **Coordination provably changed real code.** `agent_3` published
   `def prepare_multipart(fields)`; `agent_4` (`modules/uri.py`) and `agent_5`
   (`plugins/action/uri.py`) then used that exact name in their patches (2 mentions each).
   Their issue slices contain 0 mentions, so the name can only have come from the board.
   Previous instance never reached this.
2. **The "all agents submitted in the same round" termination fired** — run ended at round 2
   of 4 instead of exhausting the budget.
3. **Every agent produced a non-empty patch** (13/48/88/33/82 lines) — no 0-line consumers.

Best grade shape so far: **35/46 tests PASSED** (previous runs were all-or-nothing 8/8 or 0).
Comm: 2 `publish_interface`, 9 `read_messages`, 1 `send_message`, 9 gate refusals, 0 `no_op`.

### Grade: FAIL 0% — two distinct causes, both instructive
- **8 failures in `test/units/galaxy/test_api.py` = agent_2 non-adoption.** In round 1 (board
  necessarily empty) agent_2 spent all 25 steps implementing its OWN
  `_encode_multipart_formdata(self, fields, files)` as a method on its class. In round 2 it
  DID read the board and see `prepare_multipart` — and instead of adopting it, announced its
  own competing function to agent_3 and submitted. Its patch has **0** mentions of
  `prepare_multipart`.
- **3 failures in `test/units/module_utils/urls/test_prepare_multipart.py` = the definer's own
  edge cases** (`test_bad_mime`, `test_unknown_mime`): agent_3 implemented the contract but got
  MIME fallback handling wrong. Nothing to do with coordination.

### The full conversation was THREE messages (verbatim)
- **round 1** — `agent_3 -> all` *(interface)*: `def prepare_multipart(fields)` + "Prepares a
  multipart/form-data body and Content-Type header from a dictionary of fields. Raises
  TypeError if fields is not a Mapping...; ValueError if a file field mapping does not contain
  'filename' or 'content'." (Nobody else could post anything useful — round 1's board is empty
  by construction.)
- **round 2** — `agent_2 -> agent_3`: "The multipart encoding function I implemented is
  `_encode_multipart_formdata(fields, files)`... **Let me know if you want me to publish this
  interface explicitly or adapt it.**"
- **round 2** — `agent_4 -> all`: re-broadcast of agent_3's interface *verbatim* (a pure echo,
  no new information).

### GAP 1: `publish_interface` transmits the signature but NOT the location
agent_3's broadcast said *what* the function is and never *where* it lives. Both adopting
consumers learned the name and call convention correctly — and then **each invented a
different, wrong import path**:

| agent | import written | reality |
|---|---|---|
| agent_4 | `ansible.module_utils.common._multipart` | invented |
| agent_5 | `ansible.utils.multipart` | invented, and different from agent_4's |
| truth | `ansible.module_utils.urls` | where agent_3 actually defined it |

Both call sites are otherwise correct (`body, content_type = prepare_multipart(body)` — right
name, right 2-tuple return). The board conveyed the contract's *shape* and failed to convey its
*address*. **Cheap fix:** have `publish_interface` attach the publisher's owning file — the
harness already knows it (it is in `AGENTS_ROSTER`), so this needs no extra agent effort.

### GAP 2: termination fired while a negotiation was still in flight
agent_2's message explicitly asked whether to adapt its function. Under lockstep that question
was posted *during* round 2 and would only be readable in round 3 — but all five agents
submitted in round 2, the "all submitted in the same round" condition fired, and the run ended
with an **unanswered question on the board**. agent_2 therefore shipped its competing
implementation, which is exactly what produced the 8 `test_api.py` failures.
**Fix to consider:** do not terminate while the final round posted messages nobody can yet have
read — i.e. require a quiet round (all submitted AND no new messages) before stopping.

### Evidence that "everyone runs every round" (§8) paid off
`agent_5` **had already submitted in round 1**. Because submitted agents still get a turn, it
read the contract in round 2, made 4 more edits, and re-submitted — adopting `prepare_multipart`
in work it had already called finished. Under the pre-§8 design it would have been retired
after round 1 and would never have seen the contract at all.

### The sharpest new finding: round-1 sunk cost defeats coordination
agent_2's failure is not "didn't see the contract" — it is that it **fully implemented a
competing design in round 1, before any contract could exist**, and would not revise in round 2.
By construction round 1 has an empty board, so any agent that front-loads implementation locks
in a design blind. agent_4 by contrast did mostly *searching* in round 1 (9 searches, 14 views,
1 edit) and did its real editing in round 2 **after** reading — and adopted cleanly.

**Implied mitigation (new, untried):** make round 1 discovery/announce-only — no edit tools, or
require definers to `publish_interface` before consumers may edit. This would remove the
blind-implementation window entirely. Worth trying before more prompt tweaking.

### Priority update
This run **demotes** "peer-targeting" and **promotes** adoption + message payload: the contract
was broadcast correctly and read by everyone; one agent chose not to use it, and the two that
did could not tell where to import it from. Revised ranking:
1. **`publish_interface` should carry the owning file** (GAP 1) — smallest change, highest
   certainty of payoff: the harness already knows the publisher's file from `AGENTS_ROSTER`,
   and today two adopting agents each invented a different wrong import path.
2. **AST structural edit-check** (unchanged from §8 — decided 2 runs on `395e5e20`; not
   implicated in this run).
3. **Round-1 blind-implementation window** — discovery-only first round, so no agent commits
   to a design before any contract can exist (this is what sank agent_2).
4. **Don't terminate with unread messages in flight** (GAP 2) — require a quiet round.
5. **Adoption over invention** — an agent that reads a published interface for a symbol it
   needs should use it, not publish a competitor. Consider gating `publish_interface` on
   owning the file, and/or surfacing "an interface already exists for X" on conflict.
6. `no_op` livelock guard; round budget; grader timeout/memory guard.

### 9.2 SECOND run, identical config — large variance, and GAP 1 self-corrects

Re-ran `b748edea` with the *same* settings (partition + full scope + per-round gate,
gpt-4o-mini, `--rounds 4`) purely to measure run-to-run variance. It diverged sharply.

| | run 1 | run 2 |
|---|---|---|
| rounds used | 2 (early termination fired) | 4 (full budget) |
| board messages | **3** | **14** |
| `send_message` / `read_messages` | 1 / 9 | **12 / 18** |
| `no_op` | 0 | 4 |
| agent_4 (consumer) patch | 33 lines, adopted | **0 lines**, livelocked |
| agent_5 (consumer) patch | 82 lines, adopted | 23 lines, adopted |
| tests | 35/46 pass | **36/46 pass** |
| grade | FAIL | FAIL |

**GAP 1 self-corrected through dialogue.** agent_4 asked the exact missing question —
*"Could you please share the exact file path…"* — and agent_3 answered correctly:
*"`prepare_multipart(fields)` is defined in **lib/ansible/module_utils/urls.py**. It accepts a
dictionary where keys are field names and values are either strings, bytes, or dictionaries
containing 'filename', 'content', and optionally 'mimetype'. It returns a tuple of
(body_bytes, content_type_header)…"* — i.e. given enough rounds, agents can recover the
location the `publish_interface` payload omits. That does **not** retire GAP 1: attaching the
owning file makes this free instead of costing a 2-round round-trip that may not happen.

**But more talk produced LESS code.** agent_4 asked its question, *got a complete and correct
answer*, and still shipped **0 lines** — it `no_op`'d in rounds 2, 3 AND 4, spending each turn
on further follow-ups (next wanting "the exact name and location of the standard utility
function used to determine MIME types"). Run 1's agent_4, with far less information, wrote 33
working lines. **`no_op` livelock is therefore promoted to a top-tier problem**: it converts an
agent that would have produced a decent-but-imperfect patch into one that produces nothing.

**The FAIL cause is reproducible, not noise.** Both runs fail in exactly the same two places:
`test/units/galaxy/test_api.py` (8 then 7 failures — agent_2 inventing
`_encode_multipart_formdata` and never adopting the published contract, in BOTH runs) and
`test/units/module_utils/urls/test_prepare_multipart.py` (3 failures both times — agent_3's MIME
fallback edge cases). Coordination varies wildly run-to-run; these two defects do not.

**New minor oddity:** run 2 contains an `agent_1 -> agent_1` message. Since `visible_to`
excludes an agent's own messages, self-addressed sends are guaranteed no-ops and silently waste
a turn. Cheap fix: have `send_message` reject `to == $AGENT_ID` with a hint to use `list_agents`.

### 9.3 Revised priorities after two runs on `b748edea`
1. **`no_op` livelock guard** (promoted from #6) — demonstrably worse than imperfect action:
   agent_4 went 33 lines → 0 lines while asking 3× more questions. Cap consecutive `no_op`s
   and/or force a submit attempt in the final round.
2. **`publish_interface` should carry the owning file** — GAP 1; agents can recover it by
   dialogue (proven in run 2) but it costs a 2-round round-trip and often doesn't happen.
3. **Adoption over invention** — agent_2 shipped its own competing encoder in BOTH runs,
   causing 7-8 failures each time. The single most reproducible defect.
4. **AST structural edit-check** (§8) — still open; not implicated on this instance.
5. Round-1 discovery-only window; quiet-round termination (GAP 2); `send_message` self-send
   rejection; grader timeout/memory guard.

---

## 9.4 `--last-n-observations`: the context window is a coordination variable

**New knob** (`aci/gen_solver_config.py`, threaded main → `generate` → `build_agent_config`):

```
--last-n-observations N     default 5
```

It sets `history_processors: [{type: last_n_observations, n: N}]` in each generated
`solver.yaml`. Mechanism and rationale are documented in `multiagent_aci.md` §2.6; this
section records the evidence that motivated exposing it.

**The bug it was found chasing.** At the SWE-agent default N=5, `read_messages` output is
elided like any other observation — but `read_messages` is unread-only (content-digest cursor),
so an elided message is **unrecoverable**. Traced concretely in run 2 on `b748edea`: `agent_4`
received `agent_3`'s `prepare_multipart` interface, lost the observation at ~step 40, and
re-invented `prepare_multipart_payload`. The window spans the whole run, not a round, so with
`--steps-per-round 25` an agent begins round 2 having lost all of round 1 but the first
observation.

**N=25 works mechanically.** Run 3 (gpt-4o-mini) and run 5 (gpt-4o), both N=25 / 25 steps:
zero `read_messages` observations elided for any agent; `agent_2` elided nothing at all in any
round; `agent_4` elided only 5-7 round-1 searches. `agent_4`'s output went 0 → 61 lines vs run 2.

**But N does not fix adoption.** `agent_4` wrote its own competing multipart encoder in run 3
*and* run 5 with the published interface fully in context. In run 5 the definer even endorsed
the duplication when asked — `agent_3` replied the two were *"intended to complement"* each
other. Elision was a *contributing* cause of §9.3 priority #3, not the cause. Priority #3
stands unchanged.

### Run ledger on `b748edea` (same instance throughout)

| run | model | N | tests | notes |
| --- | --- | --- | --- | --- |
| 2 | gpt-4o-mini | 5 | 36/46 | interface elided → re-invention |
| 3 | gpt-4o-mini | 25 | 2/5 | **collection died** — structural edit bug (reparenting) |
| 4 | claude sonnet | 25 | — | aborted; see repetition loop below |
| 5 | **gpt-4o** | 25 | **42/46** | best yet; all 46 collected; $5.30; 3 of 4 rounds |

**Cost scales with N.** Run 5 spent $5.30 across 5 agents ($1.74/$1.90/$0.70/$0.73/$0.23)
against ~$0.05 for run 2 at N=5 — a large N raises prompt size on every step, so
`--per-instance-cost-limit` must rise with it. Sizing run 4's Sonnet limit off run 3's
gpt-4o-mini token peak was wrong by ~4×.

**Sonnet-only degenerate loop (run 4, aborted).** At N=25 Claude Sonnet issued 26-70 identical
`read_messages` calls per agent with **empty THOUGHT fields**. The initial hypothesis — that 25
verbatim copies of the same observation prime the same action — is **not supported**: gpt-4o at
identical N=25 (run 5) used 2-3 `read_messages` calls per agent and showed no loop. Treat it as
model-specific until a Sonnet-at-N=5 control is run (offered, declined).

**Default deliberately left at 5** so every reproduce command already recorded above still
reproduces what it claims. New runs should pass the flag explicitly.

### Structural edit bug — 5th occurrence, and a variant the proposed check would miss

Run 5, `agent_2` inserted a new method *between* a decorator and the function it decorates:

```python
     @g_connect(['v2', 'v3'])
+    def _encode_multipart(self, fields):            # steals the decorator
+        ...
     def publish_collection(self, collection_path):  # now undecorated
```

`publish_collection` loses its API-version guard, so `test_publish_collection_unsupported_version`
sees `"The collection path specified 'path' does not exist."` instead of the version error.
Syntactically valid — `compile()` passes, so `scoped.check_syntax` cannot catch it.

Critically this is **not** a reparenting: `publish_collection` stays inside `GalaxyAPI`, so the
scope-map/parent-changed AST check sketched in §8 would **not** flag it. The check needs a
second invariant: *which decorators attach to which pre-existing function must not change.*
