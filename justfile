# this is the default so that when you run `just` you get a nice interface
# for selecting a command
chose-a-command:
	just --choose

# run before opening a PR: everything that must be green, offline and free
pre-pr: check test

# --- test: is the code correct? offline, free, run constantly ---

# unit + integration
test: test-unit test-integration

test-unit:
    uv run pytest tests/unit

# our modules composed together - still offline, still free
test-integration:
    uv run pytest tests/integration

# hits a real external service (LLM API, live site) - costs money/time
test-live:
    uv run pytest -m live -v

# just test-one tests/unit/test_smoke.py::test_main_runs
test-one TEST:
    uv run pytest "{{TEST}}" -v

# re-run only what failed last time
test-failed:
    uv run pytest --last-failed

# which lines are untested?
test-cov:
    uv run pytest --cov=newshound --cov-report=term-missing

# --- check: is the code clean? ---

check: check-lint check-todos

check-lint:
    ruff check src tests
    ruff format --check src tests

# every TODO must reference a Linear card: TODO(DAV-N)
# newshound is a project under the DAV team, same as coach-loop - no separate prefix
check-todos:
    #!/usr/bin/env bash
    set -euo pipefail
    if bare=$(grep -rn --include='*.py' \
        -E '(TODO|FIXME|XXX|HACK)' src tests 2>/dev/null \
        | grep -vE '(TODO|FIXME|XXX|HACK)\(DAV-[0-9]+\)' || true); [ -n "$bare" ]; then
        echo "TODOs must reference a Linear card, e.g. TODO(DAV-8):"
        echo "$bare"
        exit 1
    fi
    echo "all TODOs reference a card"

# --- fix: make it clean ---

fix:
    ruff format src tests
    ruff check --fix src tests

# --- run: drive the thing ---
# (recipes land here once there's a server/pipeline module to run)

# --- dev: environment ---

dev-setup: dev-hooks
    uv sync

# point git at .githooks/ - pre-push verifies main before it leaves your machine
dev-hooks:
    git config core.hooksPath .githooks
    @echo "hooks installed (pre-push guards main; --no-verify bypasses)"
