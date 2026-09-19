# <Title — what will be true when this ships>

Size: M | L · Started: <yyyy-mm-dd> · Owner: <session or person> · Status: planning | building | in review | blocked on <what>

## Goal

Two or three sentences: the behaviour that changes and who notices. Non-goals in one line.
Which `ROADMAP.md` item or exit criterion this serves, if any.

## Open questions (the user's to answer)

- [ ] … — default if unanswered: …

## Context

What exists today, with `path:line` anchors. Only what the design turns on.

## Decisions

- <decision> — because <reason>. Alternatives considered: <one line each>.
- decided alone: <decision> — reverse by <how>.        ← `/auto` runs mark theirs like this

## Blast radius

Tick what the change touches; each ticked line is a done-criterion.

- [ ] a persisted document (run manifest, envelope, baseline, lock, profile, pack manifest, `schemas/`) → `schema_version` moved, migration, round-trip test
- [ ] an exit code → `docs/exit-codes.md` and the design table agree
- [ ] a CLI command or flag → `docs/usage-*.md`, `docs/index.md`, `FEATURES.md`
- [ ] the extension contract (`Rule` / `Evaluator` / `Target`, entry-point groups, pack manifest, trace format) → the three isolated example suites green
- [ ] the collector → tenancy and authorization stated per route; PostgreSQL tests present
- [ ] a rule, evaluator or target → `add-a-rule` checklist; `docs/generated/` regenerated
- [ ] a count or capability claim in prose → generated or cited
- [ ] a script → `docs/maintainers/ops-catalogue.md`
- [ ] reader-facing wording → `text-broker`, never written here
- [ ] a protected contract (`CLAUDE.md` lists them) → both sides changed together, on purpose

## Lanes

| # | lane | files | owner / tier | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1 | <behaviour> | `path`, `path` | coder (Opus high) | — | `uv run pytest … -q` | [ ] |
| 2 | … | … | main | 1 | … | [ ] |

Per lane, below the table when needed: the change in behaviour, the tests that prove it
(the negative case included), traps.

## Done-criteria

- [ ] full gate green, verdict lines read (`scripts/ci_local.sh --quiet`)
- [ ] the documented command run against a real or faked target, its artifact read
- [ ] reviewed; findings fixed or answered
- [ ] the five documentation places answered in the same change
- [ ] this file deleted in the shipping commit; leftovers in `BACKLOG.md`

## Handoff

Keep current after every lane, so a fresh session can continue from this section alone.

- Done: …
- Next: …
- How to verify where we are: …
- Surprises: …
