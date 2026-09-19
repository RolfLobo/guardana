---
name: docs
description: Documentation work in this repo — the five places a user-visible change must answer, the page conventions the site build enforces, the tests that pin prose to the registry, and a simplification pass that makes a page shorter and truer without inventing a claim. Use for "update the docs", "the README is stale", "simplify this page", "add a usage page", or when /ship needs the five places answered.
argument-hint: "[page or change to document | audit | simplify <page>]"
---
# Documentation — shorter, truer, generated where it can be

Target: $ARGUMENTS

## The five places, every user-visible change

| where | when it needs an edit |
|---|---|
| `CHANGELOG.md` under `[Unreleased]` | any user-visible change — say *why*, not only what |
| `FEATURES.md` | a new capability, or one whose shape changed (a registry test refuses a built-in rule or evaluator missing from it) |
| `docs/` | a new command gets `usage-<command>.md`; a changed one gets its page reconciled; `docs/index.md` lists it under the right heading |
| `site/index.html` | a headline claim moved: a count, a run mode, what the terminal demo prints |
| `ROADMAP.md` | the direction moved — delete what shipped, add what was deferred with the reason |

Then `uv run python scripts/generate_docs.py` for a rule, evaluator or taxonomy change — never
edit `docs/generated/` by hand — and the four `--check` scripts prove the site agrees.

## What the build enforces

- Every `docs/**/*.md` starts with front matter: `title`, `nav_order` (unique), `summary`,
  `status` (`stable` / `beta` / `draft`; design documents take the first word of their
  `**Status:**` line). A page missing any of them fails `build_site.py`.
- Every page is listed in `docs/index.md`; the nav is built from that map and refuses a page it
  cannot reach. Only `docs/work/` is left out — it is work in flight, not documentation.
- Every local link points at a file that exists (`test_docs_consistency.py`); no page promises
  a version that already shipped (`**v0.x`, "coming in 0.x"); every count in prose equals the
  registry (`test_docs_pages_state_the_real_counts.py`, `test_landing_page.py`,
  `test_readme_rule_table.py`); the built site equals its sources (`test_documentation_site.py`).
- A design document is named for its topic, never a date, carries a status line and is
  superseded rather than rewritten (`docs/design/README.md`).

## A page that is easy to read

One page, one job, the answer first. A `usage-*.md` page says what the command does, the
command to type, what it writes, its exit codes, then the options — in fenced blocks, never in
prose. History, incidents and measurements belong in `CHANGELOG.md` or
`docs/maintainers/lessons.md`, not on a user page: a user page that explains why a rule exists
three times is a page nobody finishes. A sentence that a test could pin (a count, a flag, a
path) is written so the test can find it; a sentence nothing can check is a claim to cut.

## A simplification pass

1. Inventory with `scout`: size, last commit, which tests pin the page, which pages link to it.
2. Mark, sentence by sentence: **true and needed** · **true, belongs elsewhere** (move it) ·
   **untrue or unverifiable** (fix or cut, with the evidence) · **repeated** (keep one copy).
3. Readability and wording are `text-broker` work (`content-model`): a rewrite comes back with
   every path, flag, count, rule id and link byte-identical, and a verdict that CUTS a sentence
   needs both engines to agree. The facts stay yours: a model never changes a number.
4. Run the gates that will notice: `uv run pytest packages/guardana-core/tests/test_docs_consistency.py packages/guardana-core/tests/test_documentation_site.py -q`
   and `scripts/ci_local.sh --quiet` before the commit.
5. Report what got shorter (lines before / after), what was cut and why, what moved where.

The maintainer-facing pages (`docs/maintainers/`), `CONTRIBUTING.md` and `CLAUDE.md` follow the
same rules; `CLAUDE.md` additionally has a line budget the setup gate enforces, and the story
behind a rule goes to `docs/maintainers/lessons.md`.
