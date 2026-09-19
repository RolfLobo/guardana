---
paths:
  - "scripts/**"
---
# Scripts

Catalogue: `docs/maintainers/ops-catalogue.md`. Why: `docs/maintainers/lessons.md` § Gates.

- **Every script has a row in the catalogue** (what it writes, its safe mode, what it needs);
  `scripts/check_ops_catalogue.py` fails the gate otherwise. Add, rename or delete the row in the
  same change as the script.
- **A script that writes has `--check` or `--dry-run`.** Four do not have an argument parser and
  run for real when handed `--help`: `release.py` (fetches from origin, runs the gate),
  `clean_install_check.py`, `generate_sbom.py`, `image_smoke.py`. Read their docstring; give
  them `argparse` when you next touch them.
- **Generated files are never edited by hand**: `docs/generated/`, the built-in pack manifest,
  `site/docs/`, `site/llms.txt`, the counts in `site/index.html`. Every generator has `--check`
  and each is a CI gate.
- **`release.py` pushes `main` first, waits for green CI, then pushes the tag** — and refuses
  when it cannot check. A tag that moved after a publish no longer names the bytes people
  installed.
- **Hooks live here, not under `.claude/`**, because `mypy --strict` skips dot-directories and a
  checked-in script the gate cannot see is an unverified corner. `guard_hook.py` is tested by a
  case table in `scripts/tests/test_guard_hook.py`; `ruff_on_edit.py` never blocks.
- **`scripts/sitegen` refuses rather than skips**: a page without front matter or without a
  `docs/index.md` entry fails the build, because the page a nav silently drops is the page
  nobody can find.
- Fixed literal subprocess commands carry `# noqa: S603` with the reason; `T201` is allowed
  here. `scripts/` is on `pythonpath`, so tests import a script by module name.
- Never a Fable/Mythos model id in a script, config or flag; the Anthropic default is
  `claude-opus-5`. A loop over `claude -p`, `codex exec` or `agy --print` boots a full agent
  session per call — batch, announce the count, and go through `scripts/text_model.py`.
