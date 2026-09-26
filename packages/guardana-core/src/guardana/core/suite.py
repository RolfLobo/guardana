"""A suite's pass rate over its dataset, and what its gate may conclude from it.

A suite sends every case K times and asks one question of the result: is the pass rate
at or above the bar its author set, over enough cases to say so? Three answers, because
a rate that could not be established is neither. Every rate is over cases, each case
weighted by its share of passed trials, since the K trials of one case are correlated.

Trials nobody could grade never leave the denominator: they bound the rate from both
sides, and the gate concludes only when both bounds agree. Why, and what was rejected:
[`docs/design/quality-suites.md`](../../../../../docs/design/quality-suites.md).
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from guardana.core.assessment import Assessment, AssessmentStatus
from guardana.core.evaluator.base import Evaluator
from guardana.core.judge_error import correct_pass_rate, grading_of
from guardana.core.manifest.records import (
    CalibrationRecord,
    CorrectionStatus,
    SuiteCorrection,
    SuiteOutcome,
    SuiteSummary,
)
from guardana.core.trials import check_trials, wilson_at

DEFAULT_MIN_SAMPLE = 30
"""Cases a suite must measure before its gate may conclude, unless the suite says otherwise."""


@dataclass(frozen=True, slots=True)
class SuiteGate:
    """The pass rate a suite must reach, and how many measured cases it takes to say so."""

    min_pass_rate: float
    min_sample: int = DEFAULT_MIN_SAMPLE

    def __post_init__(self) -> None:
        """Refuse a bar outside (0, 1] and a sample of fewer than one case.

        A bar of zero passes a suite that measured nothing wrong and nothing right.
        """
        rate = self.min_pass_rate
        if (
            isinstance(rate, bool)
            or not isinstance(rate, int | float)
            or not math.isfinite(rate)
            or not 0.0 < rate <= 1.0
        ):
            raise ValueError(f"min_pass_rate must lie in (0, 1], got {rate!r}")
        sample = self.min_sample
        if isinstance(sample, bool) or not isinstance(sample, int) or sample < 1:
            raise ValueError(f"min_sample must be a whole number of at least 1, got {sample!r}")


@dataclass(frozen=True, slots=True)
class _Case:
    trials: int
    passed: int
    ungraded: int


def measure_suite(  # noqa: PLR0913 — one keyword per fact the assessments cannot supply
    assessments: Iterable[Assessment],
    *,
    rule_id: str,
    case_ids: Sequence[str],
    trials_per_case: int,
    gate: SuiteGate,
    dataset: str,
    dataset_digest: str,
    evaluators: Mapping[str, Evaluator],
    calibrations: Mapping[str, CalibrationRecord],
    sample: tuple[int, int] | None = None,
    starter_digest: str | None = None,
) -> SuiteSummary:
    """Reduce a suite's recorded trials to its rates and the conclusion its gate reaches.

    `case_ids` are the cases the suite set out to measure, after sampling; a planned trial
    with no record counts as ungraded, never as absent. `sample` is (size, seed) when a
    subset ran.
    """
    check_trials(trials_per_case)
    recorded = [a for a in assessments if a.rule_id == rule_id]
    by_case: dict[str, list[Assessment]] = {}
    for assessment in recorded:
        by_case.setdefault(assessment.case_id, []).append(assessment)
    cases = [_reduce(by_case.get(case_id, []), trials_per_case) for case_id in case_ids]
    measured = sum(1 for case in cases if case.ungraded == 0)
    worst = best = low = high = None
    if cases:
        worst = math.fsum(c.passed / c.trials for c in cases) / len(cases)
        best = math.fsum((c.passed + c.ungraded) / c.trials for c in cases) / len(cases)
        # Wilson's interval contains its share; min and max keep rounding at 0 and 1 from
        # putting a limit on the wrong side of it.
        low = min(wilson_at(worst, len(cases))[0], worst)
        high = max(wilson_at(best, len(cases))[1], best)
    correction = _correction(
        rule_id,
        recorded,
        evaluators=evaluators,
        calibrations=calibrations,
        rates=(worst, best, low, high),
        starter_digest=starter_digest,
    )
    outcome, reason = _conclude(
        gate,
        measured=measured,
        cases=len(cases),
        ungraded_trials=sum(c.ungraded for c in cases),
        raw=(worst, best),
        correction=correction,
    )
    return SuiteSummary(
        dataset=dataset,
        dataset_digest=dataset_digest,
        trials_per_case=trials_per_case,
        cases=len(cases),
        measured=measured,
        ungraded=len(cases) - measured,
        min_pass_rate=gate.min_pass_rate,
        min_sample=gate.min_sample,
        outcome=outcome,
        correction=correction,
        worst=worst,
        best=best,
        low=low,
        high=high,
        sample_size=None if sample is None else sample[0],
        sample_seed=None if sample is None else sample[1],
        reason=reason,
    )


def _reduce(trials: Sequence[Assessment], planned: int) -> _Case:
    """Count one case's passed and ungraded trials; more records than planned count too."""
    graded = [a for a in trials if a.status is AssessmentStatus.MEASURED and a.passed is not None]
    total = max(planned, len(trials))
    return _Case(
        trials=total,
        passed=sum(1 for a in graded if a.passed is True),
        ungraded=total - len(graded),
    )


def _correction(  # noqa: PLR0913 — the grading inputs and the four observed rates
    rule_id: str,
    recorded: Sequence[Assessment],
    *,
    evaluators: Mapping[str, Evaluator],
    calibrations: Mapping[str, CalibrationRecord],
    rates: tuple[float | None, float | None, float | None, float | None],
    starter_digest: str | None,
) -> SuiteCorrection:
    grading = grading_of(rule_id, False, {a.assessor for a in recorded}, evaluators)
    worst, best, low, high = rates
    if not grading.judges or worst is None or best is None or low is None or high is None:
        return SuiteCorrection(status=CorrectionStatus.DETERMINISTIC)
    return correct_pass_rate(
        grading,
        evaluators,
        calibrations,
        worst=worst,
        best=best,
        low=low,
        high=high,
        starter_digest=starter_digest,
    )


def _conclude(  # noqa: PLR0913 — every count the conclusion is allowed to read
    gate: SuiteGate,
    *,
    measured: int,
    cases: int,
    ungraded_trials: int,
    raw: tuple[float | None, float | None],
    correction: SuiteCorrection,
) -> tuple[SuiteOutcome, str | None]:
    """Decide pass, fail or declined, and say why when declined.

    Fail is read off the most favourable rate and pass off the least favourable one, so
    ungraded trials can only ever keep the gate from concluding.
    """
    threshold = gate.min_pass_rate
    if measured < gate.min_sample:
        return SuiteOutcome.INCONCLUSIVE, (
            f"{measured} of {cases} cases measured; at least {gate.min_sample} needed to conclude"
        )
    if correction.status is CorrectionStatus.UNCORRECTED:
        return SuiteOutcome.INCONCLUSIVE, f"uncorrected — {correction.reason}"
    raw_worst, worst, best, low = _gated(raw, correction, threshold)
    if best < threshold:
        return SuiteOutcome.FAIL, None
    if worst >= threshold and (low is None or low >= threshold):
        return SuiteOutcome.PASS, None
    if worst >= threshold:
        return SuiteOutcome.INCONCLUSIVE, (
            f"raw pass rate {_percent(raw_worst)}% is below {_percent(threshold)}%; corrected "
            f"{_percent(worst)}% reaches it, but its 95% lower limit {_percent(low or 0.0)}% "
            f"does not"
        )
    return SuiteOutcome.INCONCLUSIVE, (
        f"{ungraded_trials} ungraded trial(s) put the pass rate between {_percent(worst)}% "
        f"and {_percent(best)}%, across {_percent(threshold)}%"
    )


def _gated(
    raw: tuple[float | None, float | None], correction: SuiteCorrection, threshold: float
) -> tuple[float, float, float, float | None]:
    """Return the raw worst rate, the worst and best rates the gate reads, and a pass's floor.

    Raw for a deterministic assessor, corrected for a judge; a corrected pass over a raw
    worst below the threshold must also clear it at the corrected lower limit.
    """
    raw_worst, raw_best = raw
    if raw_worst is None or raw_best is None:
        raise ValueError("a suite with measured cases states its rates")
    if correction.status is not CorrectionStatus.CORRECTED:
        return raw_worst, raw_worst, raw_best, None
    if correction.worst is None or correction.best is None or correction.low is None:
        raise ValueError("a corrected suite states its corrected rates")
    low = correction.low if raw_worst < threshold else None
    return raw_worst, correction.worst, correction.best, low


def describe(summary: SuiteSummary) -> str:
    """State what a suite measured and concluded in one line, from its stored summary.

    Shared by the finding, the terminal report and JUnit, so no two outputs can word the
    same conclusion differently. Rates are printed with bounds rounded outward.
    """
    k = summary.trials_per_case
    parts = [
        f"{summary.dataset}: {summary.measured} of {summary.cases} cases measured, "
        f"{k} trial{'s' if k != 1 else ''} each"
    ]
    if summary.worst is not None and summary.best is not None:
        parts.append(
            f"pass rate {_span(summary.worst, summary.best)} "
            f"(95% CI {_down(summary.low)} to {_up(summary.high)}%)"
        )
    correction = summary.correction
    if correction.status is CorrectionStatus.CORRECTED and correction.worst is not None:
        parts.append(
            f"corrected {_span(correction.worst, correction.best or correction.worst)} "
            f"(95% CI {_down(correction.low)} to {_up(correction.high)}%) via "
            f"{correction.assessor}'s sensitivity {correction.sensitivity:.2f}/"
            f"{correction.positives} and specificity {correction.specificity:.2f}/"
            f"{correction.negatives}"
        )
    parts.append(f"bar {_percent(summary.min_pass_rate)}%")
    if summary.outcome is SuiteOutcome.INCONCLUSIVE:
        parts.append(f"declined: {summary.reason}")
    elif summary.outcome is SuiteOutcome.FAIL:
        parts.append("below the bar")
    else:
        parts.append("at or above the bar")
    return " · ".join(parts)


def _span(worst: float, best: float) -> str:
    if _percent(worst) == _percent(best):
        return f"{_percent(worst)}%"
    return (
        f"{_percent(worst)}% to {_percent(best)}% (ungraded trials counted as failed, then passed)"
    )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}".removesuffix(".0")


def _up(value: float | None) -> str:
    """Round an upper limit up at one decimal, so a printed bound never claims more."""
    return "?" if value is None else _percent(math.ceil(value * 1000 - 1e-9) / 1000)


def _down(value: float | None) -> str:
    return "?" if value is None else _percent(math.floor(value * 1000 + 1e-9) / 1000)
