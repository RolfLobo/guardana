---
paths:
  - "packages/*/tests/**"
  - "scripts/tests/**"
  - "examples/*/tests/**"
---
# Tests

Why: `docs/maintainers/lessons.md` § False green, § Gates.

- **Tests are never a leak.** No fixture carries real customer data, a real secret or a real
  production prompt; evidence stays redacted. Crafted fixtures are built in code
  (`guardana.core.testing`) so they are readable in review.
- **A test that cannot fail is not a test.** Invert the behaviour, not the branch, and watch it
  go red; delete `__pycache__` after a same-size edit. `getattr(x, "thing", ())` where nothing
  has `thing` is vacuous and looks thorough. A replay test needs input a replay would answer
  differently: a scripted double repeats its last reply, so grading the last turn agrees by luck.
- **Assert at the seam where the value has to arrive**, not on a log line, a document or a
  mock's call count — those measure what the code said, not what it did.
- **Cost gates count operations** (`test_scan_cost.py` tree walks and parses,
  `test_probe_cost.py` transport calls), never wall-clock; a count means the same thing on a
  laptop and a loaded runner.
- **A skip is not a pass.** Report skip counts. The collector's tests need PostgreSQL
  (`GUARDANA_TEST_DATABASE_URL`); CI sets `GUARDANA_REQUIRE_POSTGRES=1` so the skip fails there.
- **Documentation is pinned by tests**: `test_docs_consistency.py` (links, version markers,
  future promises — `CLAUDE.md` included), `test_features_doc.py`, `test_landing_page.py`,
  `test_docs_pages_state_the_real_counts.py`, `test_documentation_site.py`,
  `test_design_documents_say_where_they_stand.py`. When one goes red, the prose is what is wrong.
- `--cov` is not in `addopts` on purpose; run `uv run pytest <path> -q` while iterating and
  `scripts/ci_local.sh --quiet` for the gate. Shared round-trip helpers sit beside the core tests
  and are on `pythonpath`; never add a second `conftest.py` with the same name.
- `mypy --strict` covers tests; `S101`, `D`, `PLR2004`, `SLF001` are the only ruff families
  relaxed here. Test names are the documentation, so a name says the behaviour, not the method.
