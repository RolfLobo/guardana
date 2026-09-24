# A clean result states its trials, its bound and its judge's error

Size: L · Started: 2026-09-23 · Owner: main session · Status: lane 1 committed (5342520, not pushed); lane 2 next

## Goal

`ROADMAP.md` "Now", row 1. Today "clean" means "not observed in one trial by a judge whose
error was never measured" (`docs/design/audit-0.26-measurement.md`). After row 1 a run records
the sample, trials, assessor, denominator and uncertainty; a clean result states its trials and
bound; a judge-graded rate is corrected for the judge's measured error or declines to gate.
Three lanes in dependency order, each its own commit. Row 1 is released as a whole: lane 1
alone is not a release, because its bound over a model-graded rule is not yet corrected.
Non-goals: paired statistical diff (row 2), adaptive attackers, anytime-valid monitoring.
`ROADMAP.md` changes only when all three lanes landed.

## Context

- `rule/yaml_rule.py:71,104` one reply per prompt; `scenario_rule.py`, `trajectory_rule.py`
  build conversation and memory per `run`; two Python built-ins also sample a reply and record
  nothing: `guardana-rules/agent/excessive_agency.py`, `output/secrets.py`.
- `report/result.py` `merged` de-duplicated assessments by `comparable_key`, which would have
  kept one trial per case; `diff/measurement.py:90` keys on `case_id` the same way.
- `manifest/records.py:37` `RuleRecord.trials` = declared model calls, in the coverage
  fingerprint (`manifest/coverage.py:86`). Schema 6. `RuleRecord` exists only for `rules_run`.
- Canary planted per rule per run in the CLI (`cli/_probe_run.py:38`); fixtures run with a
  default `RuleContext()` (`rule/verify.py:90`); every renderer receives the manifest.
- `probe`/`monitor` apply no baseline, so a finding's fingerprint moving with `m of K` waives
  nothing away. The collector's envelope carries no assessments and has its own version.

## Decisions

- **(a) A trial restarts the case from nothing**: fresh history, fresh `AgentMemory`, both
  sessions of a `then` rule inside one trial. A `stateful: true` scenario does not repeat
  (`with_trials` → None): the server holds its conversation and nothing opens a fresh one. A
  third-party `ToolDouble` that keeps state is not rebuilt; `docs/extending.md` says so.
- **(b) One canary per rule per run, shared by its K trials**: a trial is the same input again;
  a token per trial changes the input. `monitor` still plants one per cycle.
- **(c) Fixtures always run at K = 1**: only `probe`, `monitor`, `plan probe` apply trials, and
  a scripted double repeats its last reply. The loop is proven by core tests whose doubles
  answer differently per trial.
- **(d) K in the manifest, three fields.** `run.execution.trials`: what the operator asked for.
  `run.rules[].trial_summary`: null for a rule that does not repeat, else what it did —
  `trials_per_case`, `cases`, `cases_failed`, `cases_incomplete`, `bound`,
  `mean_success_rate`, computed by the engine from the trials it recorded (a stored field, as
  `gate` is, so a later build cannot print a different verdict for the same run). The old
  `run.rules[].trials` is renamed `declared_requests`: same value (now prompts × K), and the
  name no longer collides with K. K is read from the rule object that ran
  (`ScanResult.trials_per_case`), not the registry's copy. Migration 6 → 7: rename,
  `trial_summary: null`, `execution.trials: 1`, `trial: null` — nothing recomputed.
- **(e) Formats.** JSON: every trial is an assessment with a 1-based `trial`, plus (d). Human:
  a trials block from the stored summaries — `clean · 0 of 12 cases in 5 trials each · ASR@5 ≤
  22% (95%) · graded by keyword, grader error not measured`; failed rules add ASR@K with a
  Wilson interval over cases and the mean per-trial rate; incomplete cases are counted; at
  K > 1 the rules that made one attempt are named; the run line `static prompt set · no
  adaptive attacker ran`. Printed at K = 1 too; bounds round up. SARIF: the message carries
  `m of K` from the evidence; `tool.driver.rules[].properties.trialsPerCase` per rule. JUnit:
  the same message, no run-level K (it would misattribute K to rules that ran once).
- **Contract**: `Rule.with_trials(k) -> Rule | None` (default None) and `Rule.trials_per_case`
  (default 1), mirroring `with_canary`. `Registry.apply_trials(k)` in place, before anything
  prices or runs. A third-party rule that ignores it records one attempt.
- **Case → finding** (`trials.case_outcome`): at most one finding per case — the most
  confident failing trial (`min_confidence` reads it), else an inconclusive one when a trial
  did not resolve (`unverified`, never clean), else nothing. K = 1 returns the evaluator's
  verdict untouched. When any exception stops a case, a failure already seen is yielded first.
- **Reduction** (`trials.reduce_case`, `reduce_rule`): tri-state `any_success`/`held_all`,
  bound `1 − 0.05^(1/n)` over cases, Wilson over decided cases; only rules in `rules_run`.
  A scenario (`Rule.grades_one_case`) is one case per walk: its turn and conversation grades
  are correlated checkpoints. A case id is never shared: duplicate `prompts:` and duplicate
  graded `send:` are refused at load. A rule that reported a finding never stores a bound.
  A rule's trials with no K on record (it stopped) are never measured in `diff`.
- **Diff**: a rule whose K differs is not classified and joins `RunDiff.incomplete` ("trials
  changed 1 → 5"), which `diff` gates on (exit 2) — no new field, no diff schema bump.
  `monitor` does not read `incomplete`; every cycle of one process has the same K. `measure()` reduces trials to cases first: measured only when complete,
  `passed` = `held_all`, an incomplete case that was measured before is blinded.
- **Plan**: `plan probe --trials N` prices prompts × K; the human line names K and the rules
  that do not repeat; plan JSON gains `trials`, schema 1 → 2.
- **Summary counts**: `result_summary.assessments`/`measured` stay record counts (one per
  trial), docstrings say so; the human summary counts cases.
- decided alone: K has no ceiling — the plan prices it and a budget bounds it. Reverse by a
  maximum in `check_trials`. Answered, not adopted, from the design challenge: a cache making
  K replies identical (the deployed system is what an attacker faces); `RuleMeta.adaptive` for
  the run line (the line is the user's decision; revisit when an adaptive attacker ships).

## Blast radius

- [x] run schema 6 → 7 (`schemas/run-v7.schema.json`), plan 1 → 2; migration; round-trip tests
- [x] CLI flag `--trials` on `probe`, `monitor`, `plan probe`; `trials:` in `guardana.yaml`
- [x] extension contract (`Rule.with_trials`) → the three isolated example suites green
- [x] built-ins cost prompts × K only when K > 1 → `docs/generated/` regenerated
- [x] reader-facing wording → `text-broker`
- [ ] exit codes: none new; `diff` reuses 2
- [ ] collector: untouched; its trend counts findings and cannot see K (BACKLOG, row 6)

## Lanes

| # | lane | files | owner | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1a | trials core | `core/trials.py` (new), `assessment.py`, `rule/{base,yaml_rule,scenario_rule,trajectory_rule}.py`, `registry.py`, `profile/{model,loader}.py`, `report/result.py`, `runner.py`, `tests/test_trials.py` | main | — | `uv run pytest packages/guardana-core -q` | [x] |
| 1b | run schema 7 | `manifest/{records,settings,model,serialize,load,migrations,coverage}.py`, `report/{serialize,load}.py`, `schemas/run-v7.schema.json` + tests | coder | 1a | `uv run pytest packages/guardana-core -q` | [x] |
| 1c | Python built-ins repeat | `guardana-rules/agent/excessive_agency.py`, `output/secrets.py`, `tests/test_probe_cost.py` + tests | coder | 1a | `uv run pytest packages/guardana-rules -q` | [x] |
| 1d | diff refuses a changed K | `diff/{compare,measurement}.py`, `report/load.py` (K into `ScanResult`) + tests | coder | 1b | `uv run pytest packages/guardana-core packages/guardana-cli -q` | [x] |
| 1e | CLI and renderers | `cli/{probe,monitor,plan,_run_meta}.py`, `core/plan.py`, `schemas/plan-v2.schema.json`, `guardana-report/{human,sarif}.py` + tests | coder | 1b | `uv run pytest packages/guardana-cli packages/guardana-report -q` | [x] |
| 1f | docs | `CHANGELOG.md`, `FEATURES.md`, `docs/usage-{probe,monitor,plan,diff,run}.md`, `docs/extending.md`, `docs/exit-codes.md`, design status lines | text-broker + main | 1a–1e | `scripts/ci_local.sh --quiet` | [x] |
| 2 | calibration per class, judge-error correction | see Handoff | — | 1 | — | [ ] |
| 3 | suites, datasets, assessors | see Handoff | — | 1, 2 | — | [ ] |

1c: `secrets` groups by (prompt, secret label) across trials — one finding per pair with the
trials that matched; blank replies stay one unverified finding per prompt. Both record one
assessment per trial. Cost gate: exact for YAML and scenario rules, `<=` for agent runs
(`stop_after` ends a run early) at K = 3. 1d/1e: tests go through `run_target_probe`, not only
`Runner`, because the merge is where trials were lost.

## Done-criteria

- [ ] full gate green, verdict lines read; PostgreSQL client NOT RUN locally is said as such
- [x] `guardana probe --trials 3` against a scripted target, the saved run read back
- [x] reviewed; findings fixed or answered (design challenge 25, pre-ship review 9)
- [x] the five documentation places answered: CHANGELOG, FEATURES, `docs/` (probe, monitor,
  plan, diff, run, profiles, extending, writing-rules, exit-codes), `site/index.html` not
  applicable (no headline claim moved), ROADMAP after lane 3
- [x] `repeated-trials.md`: status line, §2 migration wording, §7 "same treatment" corrected
- [ ] this file deleted in the commit that closes lane 3; leftovers in `BACKLOG.md`

## Handoff

- **Done (lane 1, commit 5342520, not pushed):** trials core, run schema 7, both Python built-ins, diff
  refusal, `--trials` on probe/monitor/plan probe, plan schema 2, human/SARIF/inspect output,
  docs. Pre-ship review "SHIP AFTER FIXES": all nine findings fixed with tests that go red on
  inversion. Gate: every code gate green; PostgreSQL, PostgreSQL client and Images NOT RUN
  (no Docker, no `pg_dump`), so the collector's coverage floors are red for that reason;
  agent-setup red only for the harness file `.claude/scheduled_tasks.lock`.
- **Lane 1 is committed**, so lane 2 takes run schema **8** — never edit schema 7 in place.
  Row 1 is released as a whole. Before a push: the research design documents, ROADMAP and
  `docs/index.md` from the measurement audit are still uncommitted, and `site/` must be
  regenerated with them.
- **Next: lane 2** — `docs/design/judge-error-correction.md`. Start with `/plan` on this file's
  lane 2 row, then build:
  - `calibration/measure.py`: per-class `positives`, `negatives`, `sensitivity`,
    `specificity`, inconclusive counted per class and excluded; `MIN_RELIABLE_SAMPLES` (30)
    per class; judge model identity where the evaluator can state it.
  - `calibration/store.py` schema 1 → 2 (a v1 entry loads and corrects nothing);
    `manifest/records.py` `CalibrationRecord` + the six fields (run schema 8, migration).
  - `evaluator/base.py` `deterministic: ClassVar[bool] = False`; `True` on `canary`,
    `length`, `amplification`, `tool_call`. **Open for Konrad:** the design lists `keyword`
    as deterministic; both challenges argued it is a refusal-phrase proxy whose error is real.
  - a new `core/judge_error.py` (`math` only): Rogan–Gladen `θ̂ = (p̂ + Sp − 1)/(Se + Sp − 1)`,
    clipped; delta-method variance with Var(p̂) clustered on the case (`RuleTrials` gives the
    per-case outcomes), Var(Se), Var(Sp); refuse when `Se + Sp − 1 < 0.1`, a class is under
    30, or the evaluator id / judge model does not match.
  - where it lands in lane 1's code: `human.py::_trials_line` prints "grader error not
    corrected" today — replace with the corrected ASR@K and interval, or with `uncorrected —
    judge error not measured` when no usable calibration exists; `TrialSummary` gains the
    corrected fields (schema 8) so the stored verdict stays the printed one.
  - no gate consumes a corrected rate until lane 3 (suites); `diff` effects are row 2.
- **Then lane 3** — `docs/design/quality-suites.md` (+ "Trials and the judge"): `SuiteRule`
  via `dataset:`, JSONL datasets, `sample:`, `gate.min_pass_rate`/`min_sample` counting
  complete cases, a t-interval over per-case means at K > 1, `Verdict.measurement`, the
  deterministic assessors, `keyword.should_refuse`, `reference_judge`, JUnit per suite. It is
  large; plan it as its own lanes.
- **How to verify where we are:** `uv run pytest packages/guardana-core/tests/test_trials.py
  packages/guardana-cli/tests/test_trials_cli.py packages/guardana-report/tests/test_trials_rendering.py -q`.
- **Surprises:** `ScanResult.merged` collapsed trials; a failure seen before a later trial
  raised was lost; the first failing trial's confidence could hide a certain failure; a
  scenario's checkpoints counted as independent cases; duplicate prompts shared a case id.
- **For BACKLOG when lane 1 closes:** the collector trend cannot see K (row 6); `plan` does not
  price judge calls, which K multiplies; `$id` URLs in `schemas/` point at
  `guardana.dev/schemas/…`, which the site does not serve.
