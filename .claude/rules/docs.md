---
paths:
  - "docs/**"
  - "*.md"
  - "site/**"
---
# Documentation and the site

Procedure: the `docs` skill. Why: `docs/maintainers/lessons.md` § Documentation.

- **Five places for every user-visible change, in the same commit**: `CHANGELOG.md` under
  `[Unreleased]` (why, not only what) · `FEATURES.md` · the `docs/` page plus `docs/index.md` ·
  `site/index.html` for a headline claim · `ROADMAP.md` when the direction moved (delete what
  shipped, add what was deferred with the reason). Each is an edit or an explicit "not
  applicable".
- **No public claim without generated or cited evidence.** Counts come from the registry
  (`scripts/generate_docs.py`, `scripts/sync_site.py`); a statistic names its source and what
  it measured; a capability claim is testable. The landing page once said "25 rules" for three
  releases.
- **No promise about the future.** `**vX.Y` and "coming in vX.Y" are refused by
  `test_docs_consistency.py` once that version has shipped; `CLAUDE.md` is not exempt.
  `CHANGELOG.md` and `docs/design/` are records and may say what was true when written.
- **Every `docs/**/*.md` carries front matter** (`title`, unique `nav_order`, `summary`,
  `status`) and an entry in `docs/index.md`; the build refuses otherwise. `docs/work/` is work
  in flight and is not built.
- **Design documents** are named for their topic, never a date, open with a `**Status:**` line,
  and are superseded rather than rewritten (`docs/design/README.md`).
- **Generated trees are never edited by hand**: `docs/generated/`, `site/docs/`,
  `site/llms.txt`. Regenerate; `--check` is the gate.
- **A push to `main` deploys `site/`** through Cloudflare before CI runs; the pre-push hook
  refuses when the four `--check` scripts report drift.
- Every local link points at a file that exists; renaming a page is not done until the test
  says so. English everywhere; a user page holds no history, no incident, no measurement —
  those go to `CHANGELOG.md` or lessons.
