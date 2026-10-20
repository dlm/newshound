# newshound

Autonomous agent that scrapes 10 personal news sites, extracts articles with
an LLM, scores them against a personal interest profile with a second LLM,
deduplicates, and serves the result as an RSS feed from a homelab k3s
cluster.

This file is the living record of what's decided and why. It replaced an
initial all-in-one spec prompt that asked for everything (code, Dockerfile,
k8s manifests) in one shot - we deliberately slowed down and are building
this step by step instead. Update this file as decisions change; don't let
it drift from reality.

## Status

Scaffolding only. No pipeline/server code written yet. Next step after this
scaffold is agreed: start on the data models (`Article` / `ArticleList`) and
the storage layer.

## Architecture decisions

### Two separate LLM calls (not one combined extract+score call)

- **Extraction LLM**: page markdown -> strict Pydantic schema
  (`Article(title, url, summary, date)`, `ArticleList(articles: list[Article])`)
  via tool-calling. Needs a model that's reliably good at structured output.
- **Scoring LLM**: `(summary, interest_profile.txt)` -> integer 1-10. A much
  simpler task - this is where a small/cheap/local model belongs.
- Both go through **LiteLLM** so the provider is swappable via env var, not
  code. `EXTRACTION_LLM_MODEL` / `SCORING_LLM_MODEL`.
- Scoring will eventually point at **Jev** (a model from TypesafeAI) served
  via Ollama on a Mac on the home network - but that Mac isn't always on.
  Design for this now, don't implement it yet: `SCORING_LLM_MODEL` (primary)
  +`SCORING_LLM_FALLBACK_MODEL` (a reachable cloud model). On a connection
  error to the primary, log a warning and fall back rather than failing the
  run. Today, both extraction and scoring point at ordinary cloud models.

### Single Deployment, not a CronJob (for now)

Considered: CronJob (scrape pipeline) + separate always-on Deployment
(serving `feed.xml`), sharing one PVC. Rejected for now because k3s'
`local-path` StorageClass binds a PVC to whichever node first claims it -
fine for one pod type, but with two workload types (CronJob pods +
Deployment pod) sharing a PVC, both get pinned to that node, and the user is
adding 1-2 more nodes to the cluster within about a month. Didn't want to
build in a single-node assumption right before that changes.

Chosen instead: **one long-running Deployment** that both serves `feed.xml`
and runs the pipeline - an internal scheduler thread on a ~24h cadence, plus
a `POST /trigger` endpoint for on-demand runs (covers the "I want to rerun
this now" need without a CronJob).

Migration path, kept open on purpose: the pipeline logic is written as a
**standalone callable, agnostic to how it's invoked**. Moving to a CronJob
later (if/when RWX storage like Longhorn is in place post-multi-node) is a
wrapper change - split `server.py` into serve-only + a CronJob entrypoint
that calls the same pipeline function - not a rewrite. DB schema and PVC
contents don't change either way.

### Auth: manual login once, fail loudly and visibly (not silently)

- One-time setup: `setup_auth.py`, a standalone script (not run by the main
  app) that opens a real Playwright browser so the user can log into
  password-walled sites once. Saves cookies/tokens to
  `/app/data/session_state.json`.
- Automated runs load that session file. Before spending LLM calls on a
  site, do a cheap check for a login-wall signal; on failure, **skip that
  site and keep going** - one dead session shouldn't take down the whole
  feed.
- Decided explicitly **against** silent failure or log-only failure. On an
  auth failure, synthesize a high-priority `Article` and insert it into the
  feed itself: score 10, title like `"⚠️ Auth expired: <site>"`,
  synthetic URL `internal://auth-failure/<site>/<YYYY-MM-DD>` (dedupes to
  one nag per site per day; stops once the site is reauthenticated). This is
  the user's actual "I will see it" channel - not a push notification (that
  can be layered on later if this isn't enough).
- Reauth is manual: rerun `setup_auth.py` for the affected site. No
  automated re-login with stored credentials (user explicitly didn't want
  credentials that could lock them out living in the automated path).

### Storage / feed generation

- SQLite at `/app/data/feed.db`, unique constraint on URL, for dedup.
- RSS output via the `feedgen` library (not hand-rolled XML).
- `/app/data` is the PVC mount point in the cluster; `data/` locally in dev
  (gitignored) mirrors it.

### k8s / deployment target

- Homelab k3s cluster, currently single-node, expanding to 2-3 nodes within
  about a month of 2026-10-20 (i.e. roughly mid-to-late November 2026).
- PVC uses k3s' default `local-path` StorageClass for now. Revisit once
  multi-node - RWX storage (e.g. Longhorn) would remove the node-pinning
  concern, and since the user will be touching cluster topology anyway, that
  might be the natural moment to add it. Not a blocker for v1.
- `Secret` holds LLM API key(s) (via whatever env vars LiteLLM / the chosen
  providers need). Site login credentials are used only by the
  interactively-run `setup_auth.py`, not by the running pod - so they likely
  don't need to live in the cluster `Secret` at all. Revisit if automated
  re-login is ever added.
- Memory limit ~1.5Gi on the pod (buffer for headless Chromium via
  Crawl4AI/Playwright).
- `Service` + Traefik-compatible `Ingress` routing some `*.local` hostname to
  the service (exact hostname not yet chosen).
- Base image: `mcr.microsoft.com/playwright/python` (the original spec said
  `://microsoft.com`, which isn't a real image reference - this is the real
  Playwright-maintained Python image).
- DockerHub username / final image tag: not yet decided.

### Tooling / project hygiene

- **Language/deps**: Python 3.13, managed with `uv` (`pyproject.toml` +
  `uv.lock`, `hatchling` build backend).
  - **Gotcha hit during setup**: `uv init`'s default `uv_build` backend ships
    a prebuilt, dynamically-linked `uv-build` binary that NixOS can't run
    without FHS/`nix-ld` shims ("NixOS cannot run dynamically linked
    executables..."). Switched to `hatchling` (pure Python backend, matches
    coach-loop) to sidestep it entirely rather than patch the environment.
- **Lint/format**: `ruff`.
- **Task runner**: `just` (see `justfile`). Modeled closely on a sibling
  project, `~/repos/dlm/coach-loop`, which has the same shape of problem
  (Python engine + LLM calls) and already encodes the test-tiering and
  pre-push patterns below.
- **Tests, tiered on purpose** (the user was explicit: no "nothing but
  slow end-to-end tests"):
  - `tests/unit/` - fast, offline, no network, mocked dependencies.
  - `tests/integration/` - modules composed together, still offline/free.
  - a `live` pytest marker (`@pytest.mark.live`) for anything that hits a
    real external service (real LLM API calls, real site scraping) - costs
    money/time, excluded from the default test run via
    `addopts = "-m 'not live'"`, run deliberately via `just test-live`.
- **Dev shell**: `flake.nix` (flake-utils, `eachDefaultSystem`), provides
  `git`, `jujutsu`, `just`, `python313`, `uv`, `ruff`.
  - **Gotcha hit during setup**: `nixpkgs#jj` is a *different* package (a
    JSON stream editor also named `jj`) - the Jujutsu VCS package is
    `nixpkgs#jujutsu`. Don't repeat that mistake when touching the flake.
- **VCS**: [Jujutsu (`jj`)](https://github.com/jj-vcs/jj), colocated with git
  (`jj git init --colocate`) so GitHub interop still works via
  `jj git push`. GitHub remote **not created yet** - local-only until
  there's something worth pushing (deliberate choice, not an oversight).
  - **Unverified**: whether `jj git push` triggers `.githooks/pre-push` the
    way a plain `git push` does. The hook (copied from coach-loop, see
    `.githooks/pre-push`) guards pushes to `main` behind `just pre-pr`.
    Confirm this actually fires before relying on it.
  - **Gotcha hit during setup**: `jj` doesn't automatically maintain a git
    branch - after committing, `git branch` showed `(no branch)` until a
    `main` bookmark was created (`jj bookmark create main -r <rev>`). Keep
    the `main` bookmark pointed at the right commit as work lands (`jj
    bookmark set main -r <rev>`, or `jj bookmark move main --to <rev>`
    depending on jj version) - it won't move on its own the way a git branch
    does on commit.
- **Issue tracking**: Linear, matching the user's existing workflow on
  coach-loop (`TODO(DAV-N)` there). This project's prefix is **`NH`**,
  provisionally - the actual Linear project/team for newshound has not been
  created yet. `just check-todos` already enforces `TODO(NH-N)` /
  `FIXME(NH-N)` / etc. in `src` and `tests`; update the prefix here and in
  the justfile if it ends up different once the Linear project exists.
- **License**: MIT, copyright holder `dlm` (matches the convention used in
  other repos under `~/repos/dlm`).

## Repo layout

Flat layout (no `engine/` nesting like coach-loop - that project also has a
separate JS frontend sitting next to its Python engine; newshound has no
frontend, so there's no reason to nest).

```
newshound/
  src/newshound/       # package code
  tests/unit/
  tests/integration/
  data/                # gitignored; local mirror of /app/data in the cluster
  flake.nix
  justfile
  .githooks/pre-push
  pyproject.toml
  README.md
  LICENSE
  CLAUDE.md
```

Not yet created (future steps): `Dockerfile`, `k8s/` manifests,
`interest_profile.txt`, a site-list config file.

## Open / not yet decided

- The actual 10 target site URLs - placeholders for now, added as they're
  confirmed.
- `interest_profile.txt` format - starting as free-form prose; the user
  expects to refine this over time rather than get it right up front.
- Which sites (if any) need the auth flow, beyond the generic mechanism
  existing for any that do.
- Final LLM provider/model choices for extraction and scoring (LiteLLM makes
  this a config change, not an architecture one).
- Linear project creation + confirming the `NH` prefix.
- When to create the GitHub remote and push.
- DockerHub username / image naming for the k8s manifests.
- RWX storage migration, if/when the cluster goes multi-node.
