# Checkpoint — multi-agent full-access mode + coordination findings

**Date:** 2026-08-07 (updated 2026-08-08) · **Branch:** `main` (base `da9a301`) · **State:** all changes UNCOMMITTED in the working tree.

> **2026-08-08 UPDATE — decision (b) TAKEN and IMPLEMENTED.** The genuine-coordination
> mode now exists and is verified offline: `--partition-issue` (build) + optional
> `--submit-gate` (config-gen, OFF by default). See §6 below; §3's fork is resolved.

This file is a resume anchor: where the work stands, what was learned, and the one open
decision to pick up next. Feature docs live in `README.md` (§scope) and `multiagent_aci.md`
(§2.5); this file is the experiment log + next-step plan.

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

## 3. The open decision (RESUME HERE)

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
  revival introduces.

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
