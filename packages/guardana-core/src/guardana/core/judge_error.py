"""Correct a judge-graded rate for the judge's measured error, or say why it cannot be.

A rate graded by a model inherits the model's mistakes: a judge that misses attacks makes
the system look safer than it is, and every number computed from its verdicts is still
arithmetically right. The correction uses the judge's sensitivity and specificity from
`guardana calibrate`, applies to rates and never to one case's verdict, and refuses — naming
the missing condition — whenever the calibration cannot be trusted to describe this run.
Why, and what was rejected:
[`docs/design/judge-error-correction.md`](../../../../../docs/design/judge-error-correction.md).
"""

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from guardana.core.calibration.report import class_caveat
from guardana.core.evaluator.base import Evaluator
from guardana.core.manifest.records import (
    MIN_YOUDEN,
    CalibrationRecord,
    CorrectionStatus,
    JudgeCorrection,
    TrialSummary,
)
from guardana.core.trials import wilson_interval

_Z_TWO_SIDED = 1.959963984540054
"""The two-sided normal quantile at 95%, as the Wilson interval of a failed rule uses."""

_Z_ONE_SIDED = 1.6448536269514722
"""The one-sided normal quantile at 95%, as the bound of a clean rule is stated."""

_NOT_MEASURED = "judge error not measured: "
"""Opens every reason about the calibration, so the line reads as the label it prints under."""


@dataclass(frozen=True, slots=True)
class Grading:
    """Who graded one rule's recorded trials, and which of them are judges."""

    assessors: tuple[str, ...]
    judges: tuple[str, ...]
    """The assessors whose verdict is an opinion rather than a computation."""


@dataclass(frozen=True, slots=True)
class _Measured:
    """The part of a usable calibration the correction computes with."""

    dataset_digest: str
    positives: int
    negatives: int
    sensitivity: float
    specificity: float


def grading_of(
    rule_id: str,
    rule_deterministic: bool,
    assessors: Collection[str],
    evaluators: Mapping[str, Evaluator],
) -> Grading:
    """Classify the assessors a rule actually recorded, failing closed.

    Read from the recorded assessments rather than the evaluators a rule declares: a rule
    can declare `canary` and still grade some cases with a judge. An assessor is
    deterministic only when it is a registered evaluator declaring `deterministic = True`,
    or the rule's own id on a rule declaring the same; anything else is a judge.
    """
    ordered = tuple(sorted(set(assessors)))
    judges = tuple(
        assessor
        for assessor in ordered
        if not _is_deterministic(assessor, rule_id, rule_deterministic, evaluators)
    )
    return Grading(assessors=ordered, judges=judges)


def correct(
    summary: TrialSummary,
    grading: Grading,
    evaluators: Mapping[str, Evaluator],
    calibrations: Mapping[str, CalibrationRecord],
    starter_digest: str | None = None,
) -> JudgeCorrection:
    """Correct what `summary` states for the judge's measured error, or record why not.

    `calibrations` is keyed by the id an evaluator is registered under, as the calibration
    store is. `starter_digest` is the digest of the bundled starter corpus, compared as a
    backstop to the flag a calibration carries.
    """
    if not grading.judges:
        return JudgeCorrection(status=CorrectionStatus.DETERMINISTIC)
    if len(grading.assessors) > 1:
        return _uncorrected(
            None, f"multiple assessors graded this rule: {', '.join(grading.assessors)}"
        )
    assessor = grading.judges[0]
    usable = _usable(assessor, evaluators, calibrations, starter_digest)
    if isinstance(usable, str):
        return _uncorrected(assessor, _NOT_MEASURED + usable)
    observed = _observed(summary)
    if observed is None:
        return _uncorrected(assessor, _no_rate(summary))
    return _apply(observed, assessor, usable)


def rogan_gladen(rate: float, sensitivity: float, specificity: float) -> float:
    """Return the Rogan-Gladen estimate of the true rate behind an observed one, unclipped."""
    return (rate + specificity - 1.0) / (sensitivity + specificity - 1.0)


def agresti_coull_variance(rate: float, count: int) -> float:
    """Return the variance of a proportion measured over `count`, never zero.

    The Wald variance is zero at 30 of 30, which would let a calibration's own sampling
    error vanish from the interval exactly when its sample is smallest.
    """
    adjusted = (rate * count + _Z_TWO_SIDED**2 / 2.0) / (count + _Z_TWO_SIDED**2)
    return adjusted * (1.0 - adjusted) / (count + _Z_TWO_SIDED**2)


def _is_deterministic(
    assessor: str, rule_id: str, rule_deterministic: bool, evaluators: Mapping[str, Evaluator]
) -> bool:
    _key, evaluator = _resolve(assessor, evaluators)
    if evaluator is not None:
        return getattr(evaluator, "deterministic", False) is True
    return assessor == rule_id and rule_deterministic is True


def _resolve(
    assessor: str, evaluators: Mapping[str, Evaluator]
) -> tuple[str | None, Evaluator | None]:
    """Find the registered evaluator an assessor id names: exactly, or before its `@version`."""
    if assessor in evaluators:
        return assessor, evaluators[assessor]
    base, versioned, _version = assessor.partition("@")
    if versioned and base in evaluators:
        return base, evaluators[base]
    return None, None


def _usable(
    assessor: str,
    evaluators: Mapping[str, Evaluator],
    calibrations: Mapping[str, CalibrationRecord],
    starter_digest: str | None,
) -> "_Measured | str":
    """Return the calibration's per-class error for `assessor`, or why none can be used."""
    key, evaluator = _resolve(assessor, evaluators)
    calibration = calibrations.get(key) if key is not None else None
    if calibration is None:
        return f"no calibration recorded for {assessor}"
    lacking = f"{key} calibration lacks per-class counts; rerun guardana calibrate --record"
    if (
        calibration.assessor is None
        or calibration.dataset_digest is None
        or calibration.positives is None
        or calibration.negatives is None
        or calibration.positives_inconclusive is None
        or calibration.negatives_inconclusive is None
    ):
        return lacking
    refusal = (
        _refusal(assessor, evaluator, calibration, starter_digest)
        or class_caveat(
            "positives", "sensitivity", calibration.positives, calibration.positives_inconclusive
        )
        or class_caveat(
            "negatives", "specificity", calibration.negatives, calibration.negatives_inconclusive
        )
    )
    if refusal:
        return refusal
    sensitivity, specificity = calibration.sensitivity, calibration.specificity
    if sensitivity is None or specificity is None:
        return lacking
    return _youden_refusal(sensitivity + specificity - 1.0) or _Measured(
        dataset_digest=calibration.dataset_digest,
        positives=calibration.positives,
        negatives=calibration.negatives,
        sensitivity=sensitivity,
        specificity=specificity,
    )


def _refusal(
    assessor: str,
    evaluator: Evaluator | None,
    calibration: CalibrationRecord,
    starter_digest: str | None,
) -> str | None:
    """Name the first condition that keeps `calibration` from describing this run, or None."""
    if calibration.assessor != assessor:
        return f"calibration is for {calibration.assessor}; run was graded by {assessor}"
    if calibration.starter_corpus is True or (
        starter_digest is not None and calibration.dataset_digest == starter_digest
    ):
        return (
            "bundled starter corpus is a demonstration corpus with no real deployment; "
            "it cannot correct this run"
        )
    judge = getattr(evaluator, "judge_identity", None) if evaluator is not None else None
    if (calibration.judge_identity is not None or judge is not None) and (
        calibration.judge_identity != judge
    ):
        return (
            f"judge identity changed: calibrated as {calibration.judge_identity or 'not stated'}"
            f", run as {judge or 'not stated'}"
        )
    return None


def _youden_refusal(youden: float) -> str | None:
    if youden < MIN_YOUDEN:
        return f"Youden's J is {youden:.2f}, below the {MIN_YOUDEN} correction threshold"
    return None


def _observed(summary: TrialSummary) -> tuple[float, float, float, float] | None:
    """Return (rate, low, high, z) of the rate `summary` states, or None when it states none.

    Only a failed case or a stated bound is a rate here. Correcting the raw counts of any
    other summary would state a bound the summary deliberately withheld.
    """
    decided = summary.cases - summary.cases_incomplete
    if summary.cases_failed:
        low, high = wilson_interval(summary.cases_failed, decided)
        return summary.cases_failed / decided, low, high, _Z_TWO_SIDED
    if summary.bound is not None:
        return 0.0, 0.0, summary.bound, _Z_ONE_SIDED
    return None


def _no_rate(summary: TrialSummary) -> str:
    if summary.cases_incomplete:
        return (
            f"not clean: {summary.cases_incomplete} of {summary.cases} cases incomplete, "
            f"a trial could not be graded"
        )
    return "reported finding is not shown by the recorded cases"


def _apply(
    observed: tuple[float, float, float, float], assessor: str, measured: _Measured
) -> JudgeCorrection:
    """Correct the observed interval, or refuse when the run contradicts the calibration.

    The sampling half of the interval is the one the uncorrected line prints and the
    calibration half is the delta method's, with variances that stay positive at a perfect
    score, so the upper limit is never below the Rogan-Gladen image of the raw one. Near a
    judge's false-alarm floor that image can still sit far below the raw bound.
    """
    rate, low_seen, high_seen, z = observed
    sensitivity, specificity = measured.sensitivity, measured.specificity
    # At or below the false-alarm floor the corrected bound would rest on the calibration's
    # spread alone, which says nothing about this run's cases.
    if high_seen <= 1.0 - specificity:
        return _uncorrected(
            assessor,
            _NOT_MEASURED + f"observed fail share ≤ {_percent_up(high_seen)}% is at or below "
            f"calibrated false-alarm rate {_percent_up(1.0 - specificity)}%",
        )
    var_se = agresti_coull_variance(sensitivity, measured.positives)
    var_sp = agresti_coull_variance(specificity, measured.negatives)
    youden = sensitivity + specificity - 1.0

    def spread(theta: float) -> float:
        t = _clip(theta)
        return z * math.sqrt(t * t * var_se + (1.0 - t) ** 2 * var_sp) / youden

    centre = rogan_gladen(rate, sensitivity, specificity)
    upper = rogan_gladen(high_seen, sensitivity, specificity)
    high = centre + math.hypot(upper - centre, spread(upper))
    if rate > 0.0:
        lower = rogan_gladen(low_seen, sensitivity, specificity)
        low = centre - math.hypot(centre - lower, spread(lower))
    else:
        low = 0.0
    return JudgeCorrection(
        status=CorrectionStatus.CORRECTED,
        assessor=assessor,
        rate=_clip(centre),
        low=_clip(low),
        high=_clip(high),
        sensitivity=sensitivity,
        specificity=specificity,
        dataset_digest=measured.dataset_digest,
        positives=measured.positives,
        negatives=measured.negatives,
    )


def _uncorrected(assessor: str | None, reason: str) -> JudgeCorrection:
    return JudgeCorrection(status=CorrectionStatus.UNCORRECTED, assessor=assessor, reason=reason)


def _clip(value: float) -> float:
    return min(1.0, max(0.0, value))


def _percent_up(value: float) -> str:
    """Render a share as a percentage rounded up at one decimal."""
    return f"{math.ceil(value * 1000 - 1e-9) / 10:.1f}".removesuffix(".0")
