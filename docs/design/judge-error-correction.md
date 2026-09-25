---
title: "Judge error in a measured rate"
nav_order: 81
summary: "sensitivity and specificity from the calibration corpus, a rate corrected for the judge's measured error with both uncertainties in its interval, and an explicit outcome when that error was never measured"
status: accepted
---

# Judge error: a rate is only as honest as the thing that graded it

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-09-23 · **`ROADMAP.md` "Now", row 1**

## The question

A rate graded by a model inherits the model's mistakes. `llm_judge`, `guard`
and the planned `reference_judge` are models. When a judge misses attacks, the
measured rate falls and the system looks safer than it is. A false green from
that source is invisible, because every number in the report is computed
correctly from verdicts that are wrong.

The size of the error is not hypothetical. On 596 human-labelled red-team
completions, LLM judges "show erratic recall (0.06 to 0.65)", and benign
wrappers flip every judge "between 57% and 100% of the time"
([arXiv 2606.25487](https://arxiv.org/abs/2606.25487)).

Today `guardana calibrate` measures accuracy, Brier score and expected
calibration error (`calibration/measure.py`). Nothing uses those numbers except
display and a confidence cap in `llm_judge`. Accuracy cannot correct a rate: it
does not say which way the judge errs, and a judge that misses attacks and a
judge that invents them can share one accuracy.

## Decisions

### 1. Calibration records the error in each direction

The corpus already labels every sample (`CalibrationSample.attack_succeeded`).
`calibrate` adds four counts and two rates:

- `positives` and `negatives`: graded samples labelled attack-succeeded and not;
- `sensitivity`: of the positives, the share the evaluator graded `fail`;
- `specificity`: of the negatives, the share it graded `pass`.

Inconclusive answers are counted per class and excluded from both rates, as they
are from accuracy today. `MIN_RELIABLE_SAMPLES` (30) applies **per class**. A
corpus with 200 negatives and 8 positives has not measured sensitivity, and the
caveat says so by name.

The calibration also records the judge's model identity where the evaluator can
state it. `llm_judge@v2` names a rubric, not a model. Swapping the model behind
an unchanged rubric is exactly the change a stored calibration must not survive.

Storage: calibration store schema `1 → 2`, and `CalibrationRecord` in the run
manifest gains nine fields (manifest schema `8`). A version-1 store entry still loads.
Its per-class error is unknown, so it cannot correct anything (see 4).

### 2. Which evaluators need it

`Evaluator` gains a class attribute, `deterministic: ClassVar[bool] = False`.
Built-ins whose verdict is a computation set it to `True`: `canary`,
`length`, `amplification`, `tool_call`, and the planned `exact_match`, `contains`,
`regex` and `json_valid`. Equality is not an opinion. A third-party evaluator that does not
declare the attribute is treated as a judge. This is fail-closed, and it affects
only rate gates, never a per-case finding.

A per-case verdict keeps what it has today: an outcome, a confidence and a
rationale. The correction applies to **rates**: a suite's pass rate, `any_success`
over cases, and the effect in a comparison.

### 3. The corrected rate

For an observed rate p̂ of judge-said-fail, with sensitivity Se and specificity
Sp, the Rogan–Gladen estimate of the true rate is

```text
θ̂ = (p̂ + Sp − 1) / (Se + Sp − 1)          clipped to [0, 1]
```

Its interval comes from the delta method and counts both samples. The run's
cases enter through Var(p̂), which is clustered on the case as in
[`repeated-trials.md`](repeated-trials.md). The calibration's labels enter
through Var(Se) = Se(1−Se)/positives and Var(Sp) = Sp(1−Sp)/negatives:

```text
Var(θ̂) ≈ [ Var(p̂) + θ̂²·Var(Se) + (1−θ̂)²·Var(Sp) ] / (Se + Sp − 1)²
```

The estimator is the one in [arXiv 2511.21140](https://arxiv.org/abs/2511.21140),
which also propagates calibration uncertainty. The whole computation is
`math.sqrt` and arithmetic, with no new dependency.

The limits the source states for itself are recorded here, not rounded away. The
correction assumes the judge errs the same way, **given the true label**, on the
calibration corpus and on this run's replies. A corpus of one model's refusals
does not calibrate a judge reading another model's jailbreaks. The report prints
the corpus digest beside every corrected rate, so a reader can ask the question.

### 4. When the error was never measured, the gate declines

A gate over a judge-graded rate needs a calibration that matches the evaluator id
and, where it is recorded, the judge model. Its calibration must also clear the
per-class minimum and have `Se + Sp − 1 ≥ 0.1`. Below that the denominator is
noise, and the correction would amplify it. When any condition fails:

- the gate is **inconclusive**, routed to the `unverified` channel with the
  missing condition named;
- the uncorrected rate is still printed, labelled
  `uncorrected — judge error not measured`, and is never gated.

garak shows what the alternative looks like: its correction silently uses
`(1.0, 1.0)` when detector metrics are missing, and falls back to an uncorrected
interval when Se + Sp − 1 is near zero. Both are the defect this project exists
to prevent.

### 5. A comparison tests the raw outcomes and reports the corrected effect

When two runs share one judge and one calibration, the paired test in
[`paired-regression-statistics.md`](paired-regression-statistics.md) runs on the
judge's raw outcomes. If the judge errs the same way on both runs' replies, the
raw difference is the true difference scaled by (Se + Sp − 1). The sign and the
p-value remain valid. Only the size shrinks.

The corrected effect is printed beside it, with the assumption stated in the
note. That assumption is where shared calibration goes wrong. Reusing one
calibration across compared models "can introduce severe bias, including … the
wrong direction with high apparent confidence"
([arXiv 2605.06939](https://arxiv.org/abs/2605.06939)). A test on raw outcomes
cannot be flipped that way, and a corrected size can.

## Rejected

**Correcting with accuracy.** One number cannot say which way the judge errs.

**Falling back to the raw rate when calibration is missing.** It is the silent
`(1.0, 1.0)`, and the reason point 4 exists.

**Prediction-powered inference now.** PPI and PPI++ give tighter valid intervals
from a small human-labelled slice ([arXiv 2301.09633](https://arxiv.org/abs/2301.09633),
[2311.01453](https://arxiv.org/abs/2311.01453)). That slice has to come from
*this* run's replies, which means keeping them and labelling some.
[`regrading-stored-exchanges.md`](regrading-stored-exchanges.md) keeps them. A
labelling workflow is later work, and PPI belongs with it.

**A bootstrap interval.** Defensible, heavier, and not more honest at the
per-class minimum this design already demands.

**Correcting per-case verdicts.** A case is one reply and one verdict. Error
rates describe populations, not a single reply.

## Changed while building

- `keyword` is a judge because refusal-phrase matching is an error-prone proxy for
  attack success.
- The interval uses Wilson or exact sampling bounds instead of a Wald variance because
  that variance vanishes at zero failures and understates uncertainty.
- The calibration part corrects each sampling bound at the least favourable corner of
  the sensitivity and specificity 95% Wilson intervals instead of using the delta
  method. In simulations of 1,500–3,000 runs per setting with 30 calibration samples per
  class, the delta method missed the upper-side target in up to 6.5% of runs and the
  lower-side target in up to 4.5%, against 2.5% per side. The corner method stayed below 1%
  (`packages/guardana-core/tests/test_judge_error_coverage.py`), with intervals typically
  20–60% wider.
- The manifest uses schema 8 because schema 7 already shipped with repeated trials.
- Judge identity covers the grader configuration because a model name alone does not
  identify everything behind a verdict.
- Determinism follows the recorded assessors because they identify what actually graded
  the rule.
- `Rule.deterministic` covers rules that grade in their own code and stamp verdicts with
  their own id.
- Starter-corpus calibration never corrects a rate because the corpus is a
  demonstration, not deployment traffic.
- The per-class minimum is enforced where correction is made, so it is not enforced
  twice; `calibrate` keeps its exit codes and Brier and ECE recording.
- The mean per-trial rate stays uncorrected because a later suite design computes its
  own interval.
- Correction requires one judge per rate so the calibration matches one recorded
  assessor.
- A run refuses correction when its observed upper bound contradicts the calibrated
  false-alarm rate.
- No rate gate consumes the corrected rate yet; gates continue to use the recorded run
  verdict.

## See also

- [`repeated-trials.md`](repeated-trials.md): the clustered Var(p̂) this correction consumes
- [`quality-suites.md`](quality-suites.md): the suite gate that declines without a calibration
- [`paired-regression-statistics.md`](paired-regression-statistics.md): raw test, corrected effect
- [`extension-author-tooling.md`](extension-author-tooling.md): where calibration records came from
