# A clean result states its trials, its bound and its judge's error

Size: L · Started: 2026-09-23 · Owner: main session · Status: lane 1 shipped in 0.27.0; lane 2 committed (7677de3), release 0.28.0 prepared; lane 3 next

## Goal

`ROADMAP.md` "Now", row 1: a run records the sample, trials, assessor, denominator and
uncertainty; a clean result states its trials and bound; a judge-graded rate is corrected for
the judge's measured error or declines to gate. Lane 2: a rate graded by a judge is corrected
with the judge's per-class sensitivity and specificity from `calibrate`, or says
`uncorrected — judge error not measured` and names why; run schema 8 stores it, so the verdict
a saved run prints is the one it was written with. Non-goals: no gate reads a corrected rate
(lane 3, suites); `diff` statistics (row 2); PPI. Lane 2 ships as 0.28.0; ROADMAP's row changes
after lane 3.

## Context

- Lane 1 (5342520, 0.27.0): `core/trials.py`, `TrialSummary`, run schema 7 — design in
  `docs/design/repeated-trials.md`. `TrialSummary` is built in `cli/_run_meta.py:426`;
  `report/human.py:88` prints "grader error not corrected" for every rule, canary included.
- `calibration/measure.py:14` computes accuracy, Brier, ECE. It records `evaluator.id`, so
  `llm_judge` is stored unversioned while its verdicts say `llm_judge@2025.1`: a rubric change
  inherits the old calibration today. Store schema 1 (`calibration/store.py:26`) is attached
  per declared evaluator id (`_run_meta.py:211`). `JudgeCalibration` (config accuracy) is untouched.
- Starter corpus: 20 positives, 20 negatives (canary 10/10, `dan_style` 10/10).
- Graders of rules that repeat: canary 3, tool_call 4, keyword 3 (jailbreak, injection,
  scenario_gradual_jailbreak), length 1, amplification 1, llm_judge 1 (optional). `secrets`
  grades in its own code under its rule id; `excessive_agency` stamps `tool_call`.

## Decisions (lane 2)

- **Konrad, 2026-09-24:** `keyword` is a judge (`deterministic` stays False): it grades a proxy,
  a refusal phrase, not whether the attack worked, and `calibrate` can measure its error.
  Deterministic: canary, length, amplification, tool_call (and lane 3's exact_match, contains,
  regex, json_valid).
- **Konrad:** the interval is the design's delta method with Var(p̂) read from the interval lane 1
  prints (Wilson over decided cases; the exact one-sided bound when none failed) and
  Agresti–Coull Var(Se), Var(Sp). With Wald Var(p̂) = 0 at zero failures: 0 of 12 cases, Se 0.9,
  Sp 0.98 (100 per class) prints ≤ 3.1% where the data allow 22.1%; this gives 23.0%.
- **Konrad:** the starter corpus grows to 30/30 (content-model) so `calibrate` alone still records.
- **Konrad:** `Rule.deterministic: ClassVar[bool] = False` covers a rule grading in its own code
  (read only when it declares no evaluator); `secrets` and `excessive_agency` set True.
- **Settled before this session** (`judge-error-correction.md`): per-class counts, 30 per class,
  judge model identity, store 1 → 2 (v1 loads, corrects nothing), `Evaluator.deterministic`
  fail-closed, Rogan–Gladen clipped, refuse below Se + Sp − 1 = 0.1, the label, rates never
  per-case verdicts, run schema 7 → 8 with a migration that recomputes nothing.
- decided alone, then challenged (reviewer, 12 findings, "proceed after fixes"; answers here):
  - A calibration records the assessor id its verdicts carried (`llm_judge@2025.1`) beside the
    evaluator id, and the correction matches on it.
  - **Judge identity is the whole grader, not the model name** (challenge 3):
    `Evaluator.judge_identity: str | None`, everything behind the verdict its id does not name.
    `llm_judge`: model, a digest of the endpoint's scheme, host, port and path (never
    credentials, query or fragment), samples per verdict; `guard`: model and endpoint digest. Compared verbatim when
    either side states one; a judge stating none prints "judge not stated". A provider
    re-pointing an alias is not detected; the docs say so.
  - **Determinism comes from the assessors a rule recorded** (challenge 2): each must be a
    registered deterministic evaluator's id (exact, or the part before `@`), or the rule's own id
    with `Rule.deterministic`; anything else is a judge. Several distinct assessors with a judge
    among them: uncorrected (one Se/Sp cannot describe their combined verdict).
  - **A calibration on the bundled starter corpus never corrects** (challenge 1): the store
    entry records `starter_corpus: true` when `--corpus` was omitted, and the digest of the
    bundled file is compared as a backstop. On the starter, keyword measures Se 24/30, Sp 20/30:
    content written for a demonstration, not this deployment's replies.
  - **Refusals read fields, not the file version** (challenge 4): an entry without per-class
    counts or assessor — a v1 file, or one `--record` rewrote as v2 — is "recorded without
    per-class counts", and a rewrite never fills `assessor` in.
  - **The correction starts from what the summary states** (challenge 5): a clean bound
    (`bound` set) or failed cases; a rule that reported a finding its cases do not show, or has
    no failure and incomplete cases, has no stated rate and is uncorrected.
  - **The per-class minimum gates the correction, not `calibrate`** (challenge 9, reverses my
    own first call): `calibrate` keeps its exit code and records whenever the corpus as a whole
    is reliable, and prints a per-class caveat; exit codes are unchanged. A class under 30 graded,
    or one the judge abstained on half of, refuses the correction.
  - Corrected: ASR@K over decided cases and the clean bound, never the mean per-trial rate
    (challenge 12; lane 3 brings its t-interval). The raw figures stay on the line (challenge 8).
    At K > 1, per-reply Se/Sp applied to a per-case rate overstates ASR@K in expectation (a
    case with a success is flagged with probability ≥ Se, one without ≥ 1 − Sp); the docs say
    "in expectation". "L > Se" is not a refusal (challenge 7): clipping at 1 is never a false green.
  - Answered, not adopted: keying the store by assessor (challenge 10). A later `--record` for
    another rubric replaces the entry, and the run then refuses on the assessor mismatch;
    several rubric versions in one file is BACKLOG.

### The correction (`core/judge_error.py`, `math` only)

n decided cases, x failed; z₂ = 1.95996 (two-sided), z₁ = 1.64485 (one-sided).
- Sampling interval (L, U): Wilson(x, n) with z = z₂ when x > 0; (0, `clean_bound(n)`), z = z₁ when x = 0.
- rg(p) = (p + Sp − 1)/J, J = Se + Sp − 1; θ̂ = rg(x/n).
- Ṽ(q, m) = q̃(1 − q̃)/(m + z₂²), q̃ = (q·m + z₂²/2)/(m + z₂²): Se over positives, Sp over negatives.
- c(θ) = √(θ²·Ṽ_Se + (1 − θ)²·Ṽ_Sp)/J.
- high = θ̂ + √((rg(U) − θ̂)² + (z·c(clip rg(U)))²); low = θ̂ − √((θ̂ − rg(L))² + (z·c(clip rg(L)))²)
  when x > 0, else 0; rate = clip θ̂; everything clipped to [0, 1]. Always low ≤ rate ≤ high and
  high ≥ rg(U). Coverage (pre-ship review, reproduced): clean bounds hold; a failed rule's
  upper limit undercovers at high rates with Se 0.6–0.7 at 30 per class (up to 6.5% vs 2.5%) —
  BACKLOG, blocking lane 3.
- Refusal order, the first one met is named: several assessors, a judge among them → no
  calibration for the judge → recorded without per-class counts → calibrated as another
  assessor → the bundled starter corpus → judge identity differs → a class under 30 graded, or
  half abstained → J < 0.1 → no stated rate → the run contradicts the calibration (U < 1 − Sp).
  Worked: 3 of 12, Se 0.9, Sp 0.95 → 23.5% (3.8 to 57.1%).

### Shapes (run schema 8, store schema 2)

- `CalibrationRecord` + `assessor`, `judge_identity`, `starter_corpus`, `positives`,
  `negatives`, `positives_inconclusive`, `negatives_inconclusive`, `sensitivity`, `specificity`:
  the design's six plus what the match reads.
- `TrialSummary.correction: JudgeCorrection | None` (None only in a migrated document):
  `status` deterministic | corrected | uncorrected, `assessor`, `reason`, `rate`, `low`, `high`,
  `sensitivity`, `specificity`, `dataset_digest`. Refused: corrected without every number, a
  number outside [0, 1], low ≤ rate ≤ high broken, or Se + Sp − 1 < 0.1; corrected on a summary
  with neither a bound nor a failed case; uncorrected without a reason; deterministic with either.
- Store v2 entry: + `assessor`, `judge_identity`, `starter_corpus` and the six; `samples` kept,
  and refused when per-class counts disagree with it. `--record` rewrites a v1 file as v2 with
  the new fields null. Migration 7 → 8 overwrites (never `setdefault`) `correction` and the nine
  fields with null; nothing is recomputed.

## Blast radius (lane 2)

- [ ] run schema 7 → 8 (`schemas/run-v8.schema.json`), migration, round-trip and schema tests
- [ ] calibration store 1 → 2; a v1 file loads and corrects nothing
- [ ] extension contract: `Evaluator.deterministic`, `Evaluator.judge_identity`,
  `Rule.deterministic` → the three isolated example suites, `--no-cache`
- [ ] exit codes: unchanged; `calibrate` gains output lines, not an exit path
- [ ] `docs/generated/evaluator-catalog.md` states which evaluators are judges (`generate_docs.py`)
- [ ] reader-facing wording → text-broker: 5 content-model calls (strings, corpus, docs ×2, release)
- [ ] collector: untouched, it reads no run manifest

## Lanes

| # | lane | files | owner | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1 | repeated trials (1a–1f) | shipped, 5342520 | — | — | — | [x] |
| 2a | run schema 8 | `core/manifest/{records,model,serialize,load,migrations}.py`, `core/report/load.py`, `schemas/run-v8.schema.json`, `core/testing/manifests.py`; tests `test_run_schema_v8.py` (new), `test_manifest_{schema,round_trip}.py`, `test_schema_coverage.py`, `_documents.py` | coder | — | `uv run pytest packages/guardana-core -q` | [x] |
| 2b | per-class calibration, contract flags | `core/evaluator/{base,canary,length,amplification,tool_call,llm_judge,guard}.py`, `core/rule/base.py`, `core/calibration/{measure,report,__init__}.py`, `guardana-rules/{output/secrets,agent/excessive_agency}.py`; tests under `core/tests/calibration/`, evaluator tests | coder | — (parallel with 2a) | `uv run pytest packages/guardana-core packages/guardana-rules -q` | [x] |
| 2c | store 2 and the correction | `core/calibration/store.py`, `core/judge_error.py` (new); tests `test_judge_error.py` (new), `calibration/test_calibration_store.py`, `test_store_round_trip.py` | main | 2a, 2b | `uv run pytest packages/guardana-core -q` | [x] |
| 2d | wiring and output | `cli/{_run_meta,_evaluators,calibrate,run}.py`, `report/human.py`; tests `test_trials_cli.py`, `test_calibrate_cli.py`, `test_calibration_reaches_the_run.py`, `test_trials_rendering.py`, a probe end-to-end | coder | 2c, 2s | `uv run pytest packages/guardana-cli packages/guardana-report -q` | [x] |
| 2s | wording: labels, reasons, calibrate lines | brief → text-broker (call 1) | text-broker | challenge | — | [x] |
| 2e | starter corpus 30/30 | `core/calibration/starter_corpus.jsonl`, `test_calibrate_cli.py` (per class, keyword not flattered), `test_calibration_reaches_the_run.py` | text-broker + main | — | `uv run pytest packages/guardana-cli/tests/test_calibrate_cli.py -q` | [x] |
| 2f | docs | CHANGELOG, FEATURES, `docs/usage-{calibrate,probe,run}.md`, `docs/extending.md`, `docs/design/judge-error-correction.md`, `docs/index.md`, `scripts/generate_docs.py` → `docs/generated/` | text-broker + main | 2a–2e | `scripts/ci_local.sh --quiet` | [x] |
| 3 | suites, datasets, assessors | see Handoff | — | 1, 2 | — | [ ] |

Tests that must go red on inversion: Wald-style zero variance at x = 0 (the corrected bound is
never below `rg(U)`); a 30/30 calibration still widens the bound; each refusal names its
condition; a v1 entry never corrects, before and after `--record` rewrites the file; a
starter-corpus calibration never corrects; a rule declaring `canary` whose recorded assessors
include a judge is not deterministic; a reported finding with no failed case, and incomplete
cases with none failed, are not corrected; a document claiming corrected with J < 0.1 is
refused; the store refuses per-class counts that disagree with `samples`; migration overwrites
an injected `correction`; a migrated v7 run prints "grader error not corrected".

## Done-criteria

- [ ] full gate green, verdict lines read; PostgreSQL client NOT RUN locally, said as such
- [x] `calibrate --record` (keyword, own 30/30 corpus: Se 0.90, Sp 0.93), then `probe --trials 3`
  against a fake OpenAI-compatible endpoint with and without it; both saved runs (schema 8)
  read back: keyword rules corrected (≤ 52.8% raw → ≤ 55.8%) or `uncorrected — judge error not
  measured: no calibration recorded for keyword`, canary/tool_call deterministic; `run inspect`
  prints the per-class line; `diff` of the two exits 0
- [x] design challenge answered; `/review` findings fixed or answered (9: 5 fixed, 4 to BACKLOG)
- [x] five documentation places; `site/index.html` not applicable; ROADMAP after lane 3
- [ ] Handoff for lane 3 written; this file deleted in the commit that closes lane 3

## Handoff

- **Done:** lane 1, released in 0.27.0. Lane 2 planned 2026-09-24 with Konrad's four answers;
  design challenge answered above. 2e (starter corpus 30/30), 2a (run schema 8; each migration
  step now writes its own `$schema` URL), 2b (built in a worktree, applied), 2c (store 2,
  `core/judge_error.py`; `JudgeCorrection` also stores the class counts the line prints), 2s
  (wording in the scratchpad `judge_error_wording.json`). Core: 1659 passed, ruff and mypy clean.
  Inversion checks on 2c: Wald at zero, Wald calibration variance, truthy determinism, the
  starter corpus, `<` at the false-alarm floor, correcting an unstated rate — each goes red.
  content-model: 3 of 5 calls used (corpus 1, wording 2 with one length retry).
- **2d done:** judge identity wiring, the correction in every written summary, calibrate rows
  and record, `run inspect` per-class line (an older calibration keeps its Brier/ECE/date),
  the trials line tails. CLI + report: 591 passed. `scripts/generate_docs.py` gained the
  evaluator catalog's error-correction column.
- **2f done:** the five places (CHANGELOG, FEATURES, `docs/usage-{calibrate,probe,run}.md`,
  `docs/extending.md`, `docs/product-status.md`, the design's status and "Changed while
  building"), `site/docs/` regenerated. content-model: 5 of 5 calls used.
- **Pre-ship review: SHIP AFTER FIXES, 9 findings.** Fixed: the false "never tighter" claim
  (docs and `_apply` docstring), `excessive_tool_use`'s unread flag and the false example,
  the registry scan in `test_determinism.py`, `run inspect` tags a starter-corpus
  calibration, this file. To BACKLOG: the failed-rule interval (blocks lane 3), the upgrade
  note, one calibration per id, several assessor ids. For the release commit: the design's
  status becomes `implemented in 0.28.0`.
- **Lane 2 committed** as 7677de3 (gate: every job green; PostgreSQL client NOT RUN;
  agent-setup red only for `.claude/scheduled_tasks.lock`, an earlier session's file), then
  `chore(release): v0.28.0`. Push, CI and tags wait on Konrad's word.
- **Edge left as is:** an evaluator whose verdicts carry several ids is recorded without
  per-class counts; a run then says "lacks per-class counts", and re-recording cannot fix it.
- **Next: lane 3** — `docs/design/quality-suites.md` (+ "Trials and the judge"). Plan it as
  its own lanes with `/plan`, in this file:
  - `SuiteRule` via `dataset:`, JSONL datasets, `sample:`, `gate.min_pass_rate` and
    `min_sample` counting complete cases, `Verdict.measurement`, the deterministic assessors
    (`exact_match`, `contains`, `regex`, `json_valid` declare `deterministic = True`),
    `keyword.should_refuse`, `reference_judge`, JUnit per suite.
  - The suite pass rate at K > 1 is the mean of per-case pass shares with a t-interval over
    cases. Lane 2 corrects only ASR@K and the clean bound (`core/judge_error.py::correct`,
    fed from `cli/_run_meta.py::_trial_summary`); the corrected pass rate is new work, and
    the per-trial mean is linear, so Rogan-Gladen applies without the K > 1 bias.
  - The suite gate reads `TrialSummary.correction`-style evidence and is inconclusive on the
    `unverified` channel with the named reason when the rate is uncorrected — lane 2 only
    records and prints it; no gate or exit code reads it yet.
  - **Blocker first:** replace the calibration half of the interval before any gate reads it
    (BACKLOG, "Judge-error correction"): the failed-rule upper limit undercovers at high rates
    with Se 0.6–0.7 at 30 per class. Candidates: a score-type Fieller interval or MOVER over
    the Wilson limits of Se and Sp. The method is Konrad's call; bring the simulation
    (scratch script re-created from BACKLOG's numbers) to the decision.
- **How to verify where we are:** `uv run pytest packages/guardana-core/tests/test_trials.py
  packages/guardana-cli/tests/test_trials_cli.py packages/guardana-report/tests/test_trials_rendering.py -q`.
- **For BACKLOG when row 1 closes:** the collector trend cannot see K (row 6); `plan` does not
  price judge calls, which K multiplies; `$id` URLs in `schemas/` point at
  `guardana.dev/schemas/…`, which the site does not serve; one calibration per evaluator id per
  file, so two rubric versions of `llm_judge` cannot both be recorded.
