"""A suite's gate concludes only what its measured cases support.

Each refusal is pinned by the scenario it exists for: cases a model left unanswered, a
sample too small, a judge nobody calibrated, a correction that would lift a failing rate
over the bar on its point estimate alone.
"""

from collections.abc import Sequence

import pytest
from guardana.core.assessment import Assessment, AssessmentStatus
from guardana.core.evaluator.canary import CanaryEvaluator
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.judge_error import correct_pass_rate, grading_of
from guardana.core.manifest.records import (
    CalibrationRecord,
    CorrectionStatus,
    SuiteOutcome,
    SuiteSummary,
)
from guardana.core.suite import SuiteGate, measure_suite
from guardana.core.trials import wilson_at

_RULE = "acme.quality.support"
_DIGEST = "sha256:" + "cd" * 32
_EVALUATORS = {"canary": CanaryEvaluator(), "keyword": KeywordEvaluator()}


def _trial(case: str, trial: int, passed: bool | None, assessor: str = "canary") -> Assessment:
    return Assessment(
        case_id=case,
        assessor=assessor,
        subject_ref="https://model.test",
        status=AssessmentStatus.MEASURED if passed is not None else AssessmentStatus.INCONCLUSIVE,
        rule_id=_RULE,
        passed=passed,
        dataset="support@2026.09",
        trial=trial,
    )


def _suite(  # noqa: PLR0913 — one keyword per knob a test turns
    outcomes: Sequence[Sequence[bool | None]],
    *,
    min_pass_rate: float = 0.9,
    min_sample: int = 30,
    assessor: str = "canary",
    calibrations: dict[str, CalibrationRecord] | None = None,
    sample: tuple[int, int] | None = None,
) -> SuiteSummary:
    """Build a suite result from per-case trial outcomes (None is an ungraded trial)."""
    trials = len(outcomes[0]) if outcomes else 1
    assessments = [
        _trial(f"c{n}", t, passed, assessor)
        for n, case in enumerate(outcomes)
        for t, passed in enumerate(case, start=1)
    ]
    return measure_suite(
        assessments,
        rule_id=_RULE,
        case_ids=[f"c{n}" for n in range(len(outcomes))],
        trials_per_case=trials,
        gate=SuiteGate(min_pass_rate=min_pass_rate, min_sample=min_sample),
        dataset="support@2026.09",
        dataset_digest=_DIGEST,
        evaluators=_EVALUATORS,
        calibrations=calibrations or {},
        sample=sample,
    )


def _calibration(sensitivity: int, specificity: int, per_class: int = 30) -> CalibrationRecord:
    return CalibrationRecord(
        dataset_digest=_DIGEST,
        assessor="keyword",
        starter_corpus=False,
        positives=per_class,
        negatives=per_class,
        positives_inconclusive=0,
        negatives_inconclusive=0,
        sensitivity=sensitivity / per_class,
        specificity=specificity / per_class,
    )


def test_a_suite_whose_every_case_passed_passes_with_a_wilson_bound() -> None:
    summary = _suite([[True]] * 30)
    assert summary.outcome is SuiteOutcome.PASS
    assert summary.worst == summary.best == 1.0
    assert summary.low == pytest.approx(wilson_at(1.0, 30)[0])
    assert summary.correction.status is CorrectionStatus.DETERMINISTIC
    assert summary.measured == 30
    assert summary.reason is None


def test_a_suite_below_its_bar_fails() -> None:
    summary = _suite([[True]] * 25 + [[False]] * 5)
    assert summary.outcome is SuiteOutcome.FAIL
    assert summary.best == pytest.approx(25 / 30)


def test_unanswered_cases_bound_the_rate_instead_of_leaving_it() -> None:
    """150 of 400 replies blank: measured alone would read 100% and pass."""
    summary = _suite([[True]] * 250 + [[None]] * 150)
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE
    assert summary.measured == 250
    assert summary.ungraded == 150
    assert summary.worst == pytest.approx(250 / 400)
    assert summary.best == 1.0
    assert summary.reason is not None
    assert "150 ungraded trial(s)" in summary.reason


def test_a_few_ungraded_cases_do_not_block_a_clear_result() -> None:
    summary = _suite([[True]] * 98 + [[None]] * 2)
    assert summary.outcome is SuiteOutcome.PASS
    assert summary.worst == pytest.approx(0.98)
    failing = _suite([[False]] * 50 + [[True]] * 48 + [[None]] * 2)
    assert failing.outcome is SuiteOutcome.FAIL


def test_a_failed_trial_counts_even_when_its_case_is_incomplete() -> None:
    summary = _suite([[True, True, True]] * 29 + [[True, False, None]], min_pass_rate=0.5)
    assert summary.measured == 29
    assert summary.ungraded == 1
    assert summary.worst == pytest.approx((29 + 1 / 3) / 30)
    assert summary.best == pytest.approx((29 + 2 / 3) / 30)


def test_too_few_measured_cases_decline_whatever_the_rate() -> None:
    summary = _suite([[True]] * 29)
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE
    assert summary.reason == "29 of 29 cases measured; at least 30 needed to conclude"
    nothing = _suite([[None]] * 40)
    assert nothing.outcome is SuiteOutcome.INCONCLUSIVE
    assert nothing.measured == 0


def test_a_repeating_suite_rates_each_case_by_its_share_of_passed_trials() -> None:
    summary = _suite([[True, True, False]] * 30, min_pass_rate=0.6)
    assert summary.trials_per_case == 3
    assert summary.worst == pytest.approx(2 / 3)
    assert summary.outcome is SuiteOutcome.PASS
    # The interval is over cases, never over pooled trials: 90 trials would be narrower.
    assert summary.low == pytest.approx(wilson_at(2 / 3, 30)[0])


def test_a_planned_trial_with_no_record_is_ungraded() -> None:
    assessments = [_trial(f"c{n}", 1, True) for n in range(30)]
    summary = measure_suite(
        assessments,
        rule_id=_RULE,
        case_ids=[f"c{n}" for n in range(30)],
        trials_per_case=2,
        gate=SuiteGate(min_pass_rate=0.4),
        dataset="support@2026.09",
        dataset_digest=_DIGEST,
        evaluators=_EVALUATORS,
        calibrations={},
    )
    assert summary.measured == 0
    assert summary.worst == pytest.approx(0.5)
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE


def test_a_sampled_suite_states_its_sample() -> None:
    summary = _suite([[True]] * 30, sample=(30, 7))
    assert (summary.sample_size, summary.sample_seed) == (30, 7)


def test_a_judge_nobody_calibrated_declines_by_name() -> None:
    summary = _suite([[True]] * 30, assessor="keyword")
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE
    assert summary.correction.status is CorrectionStatus.UNCORRECTED
    assert summary.reason == (
        "uncorrected — judge error not measured: no calibration recorded for keyword"
    )


def test_a_correction_never_lifts_a_raw_fail_over_the_bar_on_its_point_alone() -> None:
    """Raw 85% under a 90% bar; corrected 93.75% over it, but not at its lower limit."""
    summary = _suite(
        [[True]] * 85 + [[False]] * 15,
        assessor="keyword",
        calibrations={"keyword": _calibration(27, 27)},
    )
    assert summary.correction.status is CorrectionStatus.CORRECTED
    assert summary.correction.worst == pytest.approx(0.9375)
    assert summary.correction.low is not None
    assert summary.correction.low < 0.9
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE
    assert summary.reason is not None
    assert "95% lower limit" in summary.reason


def test_a_corrected_rate_decides_when_raw_and_corrected_agree() -> None:
    passing = _suite(
        [[True]] * 95 + [[False]] * 5,
        min_pass_rate=0.8,
        assessor="keyword",
        calibrations={"keyword": _calibration(27, 28)},
    )
    assert passing.outcome is SuiteOutcome.PASS
    failing = _suite(
        [[True]] * 60 + [[False]] * 40,
        assessor="keyword",
        calibrations={"keyword": _calibration(27, 28)},
    )
    assert failing.outcome is SuiteOutcome.FAIL
    assert failing.correction.best is not None
    assert failing.correction.best < 0.9


def test_a_calibration_that_reaches_a_blind_judge_at_its_edge_is_refused_by_name() -> None:
    """J = 0.14 clears the 0.1 floor, but the 95% box reaches Se + Sp - 1 <= 0."""
    summary = _suite(
        [[True]] * 50 + [[False]] * 50,
        min_pass_rate=0.4,
        assessor="keyword",
        calibrations={"keyword": _calibration(17, 17)},
    )
    assert summary.outcome is SuiteOutcome.INCONCLUSIVE
    assert summary.correction.status is CorrectionStatus.UNCORRECTED
    assert summary.reason is not None
    assert "the judge cannot distinguish pass from fail" in summary.reason


def test_the_corrected_pass_rates_stay_ordered_and_in_pass_space() -> None:
    grading = grading_of(_RULE, False, ("keyword",), _EVALUATORS)
    corrected = correct_pass_rate(
        grading,
        _EVALUATORS,
        {"keyword": _calibration(27, 27)},
        worst=0.8,
        best=0.85,
        low=0.72,
        high=0.9,
    )
    assert corrected.status is CorrectionStatus.CORRECTED
    assert corrected.worst is not None
    assert corrected.best is not None
    assert corrected.low is not None
    assert corrected.high is not None
    assert corrected.low <= corrected.worst <= corrected.best <= corrected.high
    # Rogan-Gladen on the failure share: (0.2 + 0.9 - 1) / 0.8 = 0.125 failed.
    assert corrected.worst == pytest.approx(0.875)


def test_a_deterministic_assessor_is_never_corrected() -> None:
    grading = grading_of(_RULE, False, ("canary",), _EVALUATORS)
    corrected = correct_pass_rate(grading, _EVALUATORS, {}, worst=0.5, best=0.5, low=0.3, high=0.7)
    assert corrected.status is CorrectionStatus.DETERMINISTIC


@pytest.mark.parametrize(
    ("rate", "sample"),
    [(0.0, 30), (1.5, 30), (True, 30), (0.9, 0), (0.9, True)],
)
def test_a_gate_that_could_never_mean_anything_is_refused(rate: float, sample: int) -> None:
    with pytest.raises(ValueError, match="min_"):
        SuiteGate(min_pass_rate=rate, min_sample=sample)
