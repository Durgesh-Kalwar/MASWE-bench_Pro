# Submodules: why they point at forks

`SWE-agent/` and `mini-swe-agent/` are git submodules that supply the agent scaffolds used to
*generate* patches. As of 2026-09-14 both resolve through personal forks rather than Scale's
repositories. This note records why, and what that means when you clone or pull.

## Current state

| submodule | `.gitmodules` URL | pinned commit | `upstream` remote |
|---|---|---|---|
| `SWE-agent` | `Durgesh-Kalwar/SWE-agent` | `ddff6a5` (branch `scale-customizations`) | `scaleapi/SWE-agent` |
| `mini-swe-agent` | `Durgesh-Kalwar/mini-swe-agent` | `0d6a460` (branch `main`) | `scaleapi/mini-swe-agent` |

Both forks retain Scale's full history, so upstream changes can still be fetched and merged.
All branches of this repo carry the same configuration — `main`, `comm-harness-50`,
`multiagent-50-split`, `comm-harness-study`, `last-n-observations`, and
`reciprocity-and-coupled20`.

## Why

`SWE-agent` needed a local fix. Commit `ddff6a5`, *"Default custom_llm_provider to None in
LiteLLMModel cost calculation"*, is required by the `multiagent_pro` runs: litellm has no price
entry for the gateway models, and without the fix SWE-agent raises during cost accounting.

That commit could not be pushed to `scaleapi/SWE-agent` (no write access), which left it
stranded on one machine. A submodule stores only a URL and a commit SHA, not the code — so
bumping the pin to `ddff6a5` while the URL still named `scaleapi` would have produced a
reference no clone could resolve, and `git submodule update --init` would fail for everyone
else. Forking gives the commit a fetchable home and makes the pin honest.

`mini-swe-agent` had no local commits and its pin was never broken; its fork is preparatory.
`multiagent_pro/aci/mini_scaffold.py` subclasses mini's `DockerEnvironment`, which is the kind
of coupling that eventually needs a local patch, and this way there is somewhere to push one.

The tradeoff, stated plainly: these forks no longer track upstream automatically. Pulling
Scale's changes is now a deliberate step (see below), and `main` depends on a personal account.

## Cloning

Unchanged from before — a fresh clone picks up the fork URLs automatically:

```bash
git clone https://github.com/Durgesh-Kalwar/MASWE-bench_Pro.git
cd MASWE-bench_Pro
git submodule update --init --recursive
```

## Existing checkouts need one extra command

`.gitmodules` is version-controlled; `.git/config` is **not**, and git never updates it on its
own. Any clone that existed before this change keeps resolving submodules through `scaleapi`
until it is told otherwise:

```bash
git pull
git submodule sync --recursive      # copy .gitmodules URLs into .git/config
git submodule update --init --recursive
```

Skipping `sync` on an existing checkout means git looks for `ddff6a5` in Scale's repository,
where it does not exist, and the update fails.

## Pulling upstream changes into a fork

```bash
cd SWE-agent
git fetch upstream
git merge upstream/scale-customizations      # or rebase, if the fork's history allows
git push origin scale-customizations
cd ..
git add SWE-agent && git commit -m "Bump SWE-agent submodule"
```

Same shape for `mini-swe-agent`, against `upstream/main`.

## Making a local fix to a scaffold

The rule that motivated all of this: **never bump a submodule pin to a commit that exists only
on your machine.** Push it to the fork first.

```bash
cd SWE-agent
# ...edit, commit...
git push origin scale-customizations         # origin IS the fork
cd ..
git add SWE-agent
git commit -m "Bump SWE-agent submodule: <what the fix does>"
```

To verify a pin is resolvable before trusting it, fetch the bare SHA into an empty repo:

```bash
git init -q /tmp/pintest && cd /tmp/pintest
git remote add origin https://github.com/Durgesh-Kalwar/SWE-agent.git
git fetch --depth 1 origin <sha>             # success means a fresh clone will work
```

## Switching branches

Because every branch now carries identical submodule URLs, `.git/config` stays correct no
matter which branch is checked out, and `git submodule sync` is not needed again on a machine
that has run it once.

Note that `git checkout` does not move submodule working trees unless asked, so a submodule can
appear modified after a branch switch when it is merely stale. To make checkouts carry
submodules along:

```bash
git config submodule.recurse true
```
