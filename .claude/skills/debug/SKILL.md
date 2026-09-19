---
name: debug
description: Systematic diagnosis of a red test, a rule that fires or stays silent wrongly, a scan or probe whose artifact looks wrong, a collector error, a red CI run or a gate that is green for the wrong reason. Use before proposing any fix — it names where this project's evidence lives and the failure shapes that mislead here.
argument-hint: "[symptom, test id, rule id or run file]"
---
# Debug — evidence before theory

Symptom: $ARGUMENTS

## Method

1. **Reproduce or locate the evidence first.** No fix is proposed until the failing command, the
   exact error text and the input (fixture, run file, target) are known.
2. **One hypothesis at a time**, each with the observation that would refute it. Check it with
   the cheapest read (one test with `-x -vv`, one JSON field, one log line) before reading code
   broadly.
3. **Fix the cause where every path passes**, then add the test that would have caught it —
   including the negative case. A symptom patched in one command comes back through the others
   that share the code.
4. Hand log reading and bulk lookups to `scout` / `runner`; keep the reasoning here.

## Where the evidence lives

| question | look here |
|---|---|
| why is this test red | `uv run pytest <path>::<test> -x -vv`; delete `__pycache__` first after a same-size edit |
| does the rule fire / stay quiet / say inconclusive | `uv run guardana rule test <rule-id>`; the fixtures beside the rule; `guardana.core.testing` doubles |
| what did the command really write | run the documented command against a fixture or a fake endpoint (three lines of `http.server`) and open the JSON it wrote — the method that found the worst defect in three releases |
| what does a saved run contain | `uv run guardana run inspect <file>`; `schemas/` for the contract |
| why did CI go red | `gh run view <id> --log-failed`; read the failing **step**, not the job's conclusion |
| the collector | `docker compose -f deploy/docker-compose.dev.yml up -d`, then `uv run guardana-collector migrate` / `serve`; the PostgreSQL tests need `GUARDANA_TEST_DATABASE_URL` |
| an image | `uv run --no-project python scripts/image_smoke.py` (builds and runs both; needs docker) |
| the site | `uv run python scripts/build_site.py --check`; `python3 -m http.server -d site 8099` |

## Shapes that mislead here

- **Green with skips.** Without PostgreSQL ~245 tests skip and pytest exits 0; CI refuses the
  skip. Read the `M skipped` count, not the exit code.
- **A stale cache.** `.ruff_cache` has answered for a changed file; `__pycache__` reuses old
  bytecode after a same-size edit in the same second; a cached wheel in the isolated example
  runs hides the data files an extension change touches. `scripts/ci_local.sh` clears all three.
- **`--help` is not safe on four scripts.** `release.py`, `clean_install_check.py`,
  `generate_sbom.py` and `image_smoke.py` have no argument parser and run for real. Read the
  docstring instead.
- **A green suite is not a working command.** Every unit test can pass while the command drops a
  field, sends twice the budget or reports "no regression" over an indeterminate run — each of
  these has happened. Run the command; read the artifact.
- **Silence spelled `pass`.** A check that could not run and returned clean looks like a passing
  check in every gate. The verdict must be `inconclusive` or a finding.
- **A test measuring an echo.** An assertion on a log line, a document or a mock's call count
  measures what the code *said*. Move it to the seam where the value has to arrive.
- **A count in prose.** A number that disagrees with the registry is the prose being stale, not
  the registry; `generate_docs.py --check` and `sync_site.py --check` say which.

Write down: symptom → evidence → cause → fix → the test that now guards it. If the lesson is
general, add one line to the matching `.claude/rules/` file; the story goes in the commit message.
