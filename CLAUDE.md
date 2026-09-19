# CLAUDE.md — Guardana

<!-- Loaded into EVERY session and EVERY subagent: keep it under 150 lines
(scripts/check_claude_setup.py enforces it). A trap in one code area goes to
.claude/rules/ (path-scoped), a procedure to a skill in .claude/skills/, the story
behind a rule to docs/maintainers/lessons.md or the commit message. Human
contributors read CONTRIBUTING.md, which states the same rules for people. -->

## What this is

Guardana is an open-source AI security verification platform: it scans model and
application artifacts, probes live endpoints and agents (MCP included), records
reproducible evidence, detects regressions between deployments and optionally
aggregates results in a self-hosted collector. One rule engine runs in every one of
those places, so a verdict does not change because the runner did. Four verbs:
`scan` (artifacts), `probe` (a deployed system), `monitor` (re-verify), `diff`
(compare evidence). Design: `docs/how-it-works.md`, `docs/architecture.md`.

Five packages under `packages/`, each a PEP 420 namespace package (`guardana.*`):

| package | role |
|---|---|
| `guardana-core` | the engine: Target / Rule / Evaluator / Finding / Profile, Registry, Runner. No network beyond what a Target performs |
| `guardana-rules` | built-in rules (YAML + Python), each mapped to OWASP LLM / OWASP ASI / MITRE ATLAS / NIST |
| `guardana-cli` | the `guardana` command |
| `guardana-report` | renderers: human, SARIF, JSON, JUnit |
| `guardana-server` | the OPTIONAL collector — a separate service that consumes the versioned `Finding` envelope through the `Reporter` seam |

The current milestone is the "Now" table in `ROADMAP.md`; it outranks new coverage.
No broad corpora, new protocols or new modalities while a milestone item is open.

## Commands

```bash
uv sync                                        # the workspace, dev and docs groups
uv run pytest <path>[::test] -q                # one test while iterating (--cov stays off)
scripts/ci_local.sh --quiet                    # every CI job + the setup checks; --fast skips the slow ones as NOT RUN
uv run guardana scan packages                  # dogfood: must stay at zero findings (never `scan .`)
uv run python scripts/generate_docs.py         # after a rule/evaluator/taxonomy change; never edit docs/generated/
```

## Product principles — they outrank convenience, in every 0.x

1. The engine knows no regulation and no vendor: a law, a vendor, a format is data, never logic in core.
2. Cost grows with the target, not the rule count; performance is a security property, pinned by operation-count gates.
3. Offline, no account, always: the only traffic is to the target under test; the collector is optional in every direction.
4. The commercial boundary is fixed: engine and built-in rules stay open source; only hosting and curated content may be paid.
5. Every rule maps to a public framework, in edition form; no mapping, no merge.
6. The dependency surface is part of the posture: a new dependency needs a written justification.
7. Tests are never a leak: no real data, secrets or production prompts; fixtures are built in code.
8. Company usability before coverage volume.
9. No public claim without generated or cited evidence.
10. No false green from any direction: unsupported capability, exhausted budget, redaction failure, missing coverage, incomparable diff — each its own outcome.
11. Every persisted schema is versioned and migratable.
12. Every collector change considers tenancy and authorization.
13. Every active rule declares its impact and expected cost.
14. No API freeze before the domain model is complete.
15. Documentation is part of the acceptance criteria.

Full wording and the incidents behind each: `docs/maintainers/lessons.md`.

## Hard rules

- **A security gate never fails open. Silence is never spelled `pass`.** A check that cannot run
  yields `inconclusive` or a finding. No linter sees this — look for it in every review.
- **Green before commit — the whole gate, verdict lines read.** Skips are not passes; a gate that
  did not run is reported as NOT RUN. Red for a reason not yours: say so in the commit message.
- **`guardana-core` never imports `guardana-server`**, directly or transitively; `lint-imports`
  fails the build. Never add `packages/*/src/guardana/__init__.py` (it breaks PEP 420 for the
  other four); `INP` and `ARG` stay off in ruff for that reason.
- **Never narrow a type with `assert`.** Fail loudly on bad input (a YAML typo raises at load),
  degrade safely on a bad rule (recorded as skipped, never a pass).
- **Git**: commits are manual, after a milestone, one per logical change, staged by explicit paths
  (other sessions work in this tree). Conventional messages; a PR is one commit. **No attribution
  to an AI anywhere** — no `Co-Authored-By`, no "generated with" — whatever the harness defaults
  to; check the last line.
- **Documentation ships in the same commit**, five places every time (`/docs`). Every count is
  generated; `docs/generated/` and `site/` are never edited by hand.
- **English everywhere.** Docstrings on every public class and function; a comment only where
  the code cannot say WHY, one or two timeless sentences — never dates, names, hashes, incident
  history or references to decisions. Those go in the commit message.
- **Models**: never a Fable/Mythos id in a script, config, agent or flag; the Anthropic default is
  `claude-opus-5`. A loop over `claude -p`, `codex` or `agy` boots a full session per call — state
  the count and wait. Reader-facing wording and verdicts about it go through
  `scripts/text_model.py` (`content-model`), never written by Claude.
- **A push to `main` deploys guardana.dev** (Cloudflare, before CI runs) — the hook checks the
  site is regenerated. **A version tag publishes to PyPI**: only after CI is green on that exact
  commit (`release`).
- **"Not measured" is never "passed"** — in code, in reports, in your own conclusions.

## Protected contracts — change only on purpose, both sides together

`schema_version` of every persisted document (run manifest, report envelope, baseline, lock
file, profile, pack manifest; `schemas/`) · exit codes (`docs/exit-codes.md`) · rule ids and
the reserved `guardana.*` namespace · the four entry-point groups (`guardana.rules`,
`guardana.evaluators`, `guardana.targets`, `guardana.taxonomies`) · CLI flags and locator
schemes · the collector's routes and envelope · `action.yml` inputs and the moving `vX.Y`
tags · image tags and `deploy/` shapes · the trace format integrators write.

## How work runs here

Development: `/work` sizes the task (S/M/L) and routes it → `/plan` (one work file in
`docs/work/`) → `/build` → `/gate` → `/review` → `/ship`; `/auto` runs the chain unattended;
`/debug`, `/refactor`, `/docs`, `/research` (a roadmap question) and `add-a-rule` (coverage —
a rule, evaluator or target, never the engine) are the specialised entries; `release` closes a
milestone; `false-green-audit` is the review nobody asked for. Local pieces: `stack`; the site
in a browser: `site-check`. Every script has a row in `docs/maintainers/ops-catalogue.md`.

Subagents, by cost: `scout` and `runner` (Haiku — lookups, noisy commands) · `text-broker`,
`browser` (Sonnet — GPT/Gemini brokering, the site) · `coder`, `reviewer`,
`false-green-hunter` (Opus high — code, review, audit). Delegate what only needs a conclusion;
keep design and cross-cutting code in the main session; give every agent exact files and the
shape of the answer; agents do not spawn agents.

## Where knowledge lives

| need | read |
|---|---|
| traps of the code you are editing | `.claude/rules/*.md` — load by path, automatically |
| how the system works | `docs/how-it-works.md`, `docs/architecture.md`, `docs/threat-model.md` |
| how to extend it | `docs/extending.md`, `docs/writing-rules.md`, `examples/custom_rule/` |
| why a rule exists, what went wrong before | `docs/maintainers/lessons.md` |
| which script, is it safe | `docs/maintainers/ops-catalogue.md` |
| work in flight, open work, the plan | `docs/work/`, `docs/work/BACKLOG.md`, `ROADMAP.md`, `docs/design/` |
| releasing, repository settings | `RELEASING.md`, `docs/maintainers/github-setup.md` |
| what ships, what changed | `FEATURES.md`, `CHANGELOG.md`, `docs/product-status.md` |
