# docs/work — work in flight, and nothing else

How development runs in this repo. The executable version lives in the project skills
(`.claude/skills/`): `/work` (entry, sizing, model tiers) → `/plan` → `/build` → `/gate` →
`/review` → `/ship`; `/auto` runs the whole chain unattended; `/debug`, `/refactor`, `/docs`,
`/research` and `add-a-rule` are the specialised entries; `release` closes a milestone.

This directory is not part of the documentation site: `scripts/sitegen` leaves it out, so a file
here needs no front matter and no entry in `docs/index.md`. The link test still reads it.

## The lifecycle

| phase | output | done when |
|---|---|---|
| intake | size S / M / L, "is it still true?" checked | the task is real and nobody else holds it |
| plan (M, L) | ONE file here, from `TEMPLATE.md` | goal, decisions, lanes with files + verification, done-criteria |
| build | code + tests, lanes ticked in the file | each lane's scoped verification is green |
| gate | `scripts/ci_local.sh --quiet` | every verdict line read; nothing NOT RUN |
| review (M, L) | findings from a fresh-context reviewer | fixed or answered, at most three rounds |
| ship | one commit on `main`, explicit paths, no attribution | the five documentation places answered; the site checks green before the push; CI green after it |
| close | this directory is clean again | work file deleted; knowledge moved to its home |

## What lives here

- `<yyyy-mm-dd>-<slug>.md` — one file per task in flight: spec, plan, ledger and handoff in one.
  A file here means someone is working on it; check before starting anything nearby.
- `research-<slug>.md` — a roadmap question being researched (`/research`); it ends as a
  design document, a `ROADMAP.md` edit or a deletion.
- `BACKLOG.md` — open work that has no owner right now, each item with where it stands in code.
- `TEMPLATE.md`.

Designs that are agreed but not scheduled are not parked here: `docs/design/` keeps them with
a `**Status:**` line, and `BACKLOG.md` lists the ones the roadmap does not carry.

## Where knowledge goes when a task closes

| kind | home |
|---|---|
| how the system works now | `docs/how-it-works.md`, `docs/architecture.md`, the `usage-*.md` page |
| why it is shaped this way | a design document under `docs/design/` |
| how to do an operation | a skill, a row in `docs/maintainers/ops-catalogue.md`, `RELEASING.md` |
| a trap in a code area | one or two lines in the matching `.claude/rules/*.md` |
| the story, the measurements, the incident | the commit message; `docs/maintainers/lessons.md` when it explains a rule |
| what is still open | `BACKLOG.md` |

Shipped specs and plans are not archived: git keeps them, and a directory of finished documents
is how stale status lines get mistaken for the state of the code.
