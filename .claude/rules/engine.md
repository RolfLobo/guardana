---
paths:
  - "packages/guardana-core/**"
---
# The engine (`guardana-core`)

Why and the incidents: `docs/maintainers/lessons.md` § Engine, § False green.

- **The engine knows no regulation and no vendor.** A law, a model vendor or a file format is
  data in a rule, a taxonomy entry or an extension package — never a branch in core.
- **Never import `guardana.server`**, directly or transitively; `uv run lint-imports` fails the
  build on it, and `test_reporter.py` walks core to prove no server module loads.
- **Silence is never spelled `pass`.** A check that cannot run — no canary planted, a judge's
  reply unparseable, no text returned, a budget exhausted — yields `inconclusive` or a finding.
  No linter sees this; only a reader looking for it does.
- **Fail loudly on bad input, degrade safely on a bad rule.** A typo in a YAML rule or a profile
  raises at load time; a rule that throws at run time is recorded as skipped, never allowed to
  take down the scan, never allowed to read as a pass.
- **Never narrow a type with `assert`** — it vanishes under `python -O`. A rule handed a target
  it cannot handle returns nothing.
- **Cost grows with the target, not with the rule count.** No new tree walk, re-read or re-parse:
  ask through `target.python_source(path)` and `target.iter_files(suffixes)`, which cache.
  `test_scan_cost.py` and `test_probe_cost.py` count operations, and a count is the gate.
- **A channel rebuilt field by field drops the next field.** Where the input is already the
  dataclass, use `replace(...)`, never `X(a=…, b=…)`.
- **Every persisted document is versioned and migratable**: a `schema_version`, a migration, a
  round-trip test that covers the new field, `schemas/` updated in the same change.
- **PEP 420**: never add `packages/*/src/guardana/__init__.py`; each package owns its own
  subpackage only. `INP` and `ARG` stay off in ruff for this reason.
- **No new dependency without a justification in the PR**; core depends on `pyyaml` only.
- Every public `Rule`, `Evaluator` and `Target` has a docstring and tests; they are the
  extension points third parties implement.
