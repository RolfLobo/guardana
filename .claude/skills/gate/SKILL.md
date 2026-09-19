---
name: gate
description: Run this project's verification — the full local CI mirror (ruff, mypy, import contract, pytest with PostgreSQL, coverage floors, dogfood, generated docs and site, the three isolated example suites, the setup checks), a scoped subset, or a fast run that marks the slow jobs NOT RUN — and read the verdict lines. Use while iterating (scoped) and always before a commit (full).
argument-hint: "[full | release | one <path::test> | <paths>]"
---
# Gate — prove it is green

Requested: $ARGUMENTS (nothing = `full`).

## While iterating — scoped, seconds

```bash
uv run pytest <path>[::test] -q                  # one file or one test; --cov stays off on purpose
uv run ruff check <paths> && uv run ruff format <paths>
uv run mypy --strict <paths>
uv run guardana rule test <rule-id>              # a rule's positive, negative and inconclusive fixtures
```

A scoped run is what green looks like right up until CI disagrees: failures live in packages
nobody touched, and a rule change moves `docs/generated/` (regenerate, do not edit).

## Before every commit — the whole thing

```bash
scripts/ci_local.sh --quiet          # --fast skips the slow jobs (reported NOT RUN); --skip-audit when offline
```

One line per gate; a red gate prints its last 40 lines and the full log sits in `cache/ci/`.
It runs every job of `.github/workflows/ci.yml` — the locked sync, lint, types, the import
contract, pytest with PostgreSQL, the coverage floors, `uv audit`, the dogfood scan, the four
generated-truth checks, the three isolated example suites, the clean-install check, the SBOM
check and the image smoke — plus two local-only gates CI has no job for: the ops catalogue
(`scripts/check_ops_catalogue.py`) and the agent setup (`scripts/check_claude_setup.py`).
`--fast` leaves out the three slow jobs and reports them as NOT RUN, so a fast run is never
called green. For a long run hand the command to `runner` and keep working.

What the script does so you do not have to remember it: deletes `.ruff_cache` and `__pycache__`
(both have answered for changed files before), starts the PostgreSQL from
`deploy/docker-compose.dev.yml` and sets `GUARDANA_REQUIRE_POSTGRES=1` so the collector's tests
cannot skip, runs the three example suites with `--no-cache` (a cached wheel hides exactly the
data files an extension change touches), and reports any gate it could not run as **NOT RUN**
with exit 1. A skipped gate is not a passing gate; say which ones did not run and why.

Read the verdict lines themselves — pytest's `N passed, M skipped`, mypy's `Success: no issues`
/ `Found N errors`, `Contracts: N kept`, `in sync`, `is current`. Red for a reason that is not
yours → say so in the commit message. Never push past it silently.

## Before a tag

The same command, without `--fast`: the clean-install check (five distributions in an empty
venv, the documented commands), the SBOM check and the image smoke are part of every run.
`release.py` runs its own gate again before it bumps anything.

## Report

Per gate: ✓/✗/– and the verdict line verbatim. Anything you did not run, name it as NOT RUN.
