---
name: refactor
description: Behaviour-preserving restructuring and cleanup — splitting an oversized module, removing dead code, finished scripts, flags or documents, consolidating duplicates, tightening comments. Use for any task whose promise is "nothing changes for users", in any of the five packages, in scripts/ or in docs/.
argument-hint: "[target: file, module, directory or theme]"
---
# Refactor and cleanup

Target: $ARGUMENTS

The promise is "same behaviour". Every step below exists to make that promise checkable.

## 1. Inventory before touching (delegate the sweep)

Send `scout` for callers and references; do not read the tree yourself. For each candidate
record the evidence, because "looks unused" has been wrong here before:

| claim | evidence that settles it |
|---|---|
| code is dead | no import or call (`git grep`), not reached through an entry-point group, the registry, a YAML `evaluator:` / `requires:` string, a CLI command table, a schema `$ref` or a fixture; a test alone does not make it live |
| a script is finished | one-off by its own docstring AND not named in CI, `.pre-commit-config.yaml`, `RELEASING.md`, a skill, or `docs/maintainers/ops-catalogue.md` |
| a flag or option is dead | no producer anywhere (CLI, profile schema, `guardana.yaml` examples, Action inputs, CI templates) |
| a document is consumed | its findings are closed or live elsewhere; no LIVE file cites its path; it is not a design record (`docs/design/` keeps accepted and superseded decisions on purpose) |

Low reference count on a recent file means "new", not "dead" — check `git log -1` first.

## 2. Pin behaviour

- Green full gate on the untouched tree (`/gate`), so later red is yours.
- Where tests do not cover the target, write characterisation tests FIRST from real inputs: the
  fixtures in `guardana.core.testing`, a saved run under `examples/`, a scripted transport.
- For anything that writes a document: run the documented command on a fixture before and after,
  and diff the JSON. Expected result: no difference.

## 3. Change in small, reversible commits

- Move/rename in one commit, change in the next: a reviewer can only trust a move that is pure.
- One theme per commit: "split `x.py` by concept" and "delete finished scripts" are two.
- Deleting is cheap because git keeps it — but fix every inbound reference in the SAME commit:
  `docs/index.md` (the nav refuses a missing page), `docs/` links (a test refuses a dead one),
  `site/llms.txt` and `site/docs/` (regenerate), `docs/maintainers/ops-catalogue.md`,
  `CLAUDE.md`, `.claude/rules/`, the skills.
- Leave alone: `docs/generated/` (regenerate it), `schemas/` (versioned contracts — a change is a
  migration, not a cleanup), `examples/vulnerable-model/` (deliberately malicious fixture),
  anything a user's persisted document depends on.
- Comment cleanup follows the hard rule: keep the WHY, drop dates, names, incident stories and
  references to decisions; history goes to the commit message.

## 4. Prove nothing moved

Full gate green; the before/after artifact diff empty; `guardana scan packages` still at zero
findings. Then `/review`.

## 5. Report

What was removed or moved and the evidence for each, what was kept and why, what is left for
`docs/work/BACKLOG.md`.
