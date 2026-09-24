"""A judge-graded rate is corrected for the judge's measured error, or says why it is not.

The numbers are pinned against worked examples, and every refusal is pinned by name: a
refusal that quietly fell through to a correction would print a measured-looking rate over
a judge nobody measured for this run, which is the defect this module exists to prevent.
"""

from collections.abc import Mapping
from dataclasses import replace
from typing import ClassVar

import pytest
from guardana.core.evaluator.base import Evaluator, Expectation, Verdict
from guardana.core.evaluator.canary import CanaryEvaluator
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.exchange import Exchange
from guardana.core.judge_error import (
    Grading,
    agresti_coull_variance,
    correct,
    grading_of,
    rogan_gladen,
)
from guardana.core.manifest.records import (
    CalibrationRecord,
    CorrectionStatus,
    JudgeCorrection,
    TrialSummary,
)
from guardana.core.trials import clean_bound

_RULE = "acme.jailbreak"
_DIGEST = "sha256:" + "ab" * 32


class _Judge(Evaluator):
    """A judge that states who it is, as a config-wired one does."""

    id = "acme.judge"

    def __init__(self, judge_identity: str | None = "model=m1; endpoint=e1; samples=1") -> None:
        self.judge_identity = judge_identity

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        return Verdict("pass", 0.5, "scripted", self.id)


class _Undeclared(Evaluator):
    """A third-party evaluator that never heard of `deterministic`."""

    id = "acme.undeclared"

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        return Verdict("pass", 1.0, "scripted", self.id)


class _Truthy(Evaluator):
    """Declares determinism with a value that is truthy and not True."""

    id = "acme.truthy"
    deterministic: ClassVar[bool] = "yes"  # type: ignore[assignment]

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        return Verdict("pass", 1.0, "scripted", self.id)


def _evaluators() -> Mapping[str, Evaluator]:
    return {
        "canary": CanaryEvaluator(),
        "keyword": KeywordEvaluator(),
        "acme.judge": _Judge(),
        "acme.undeclared": _Undeclared(),
        "acme.truthy": _Truthy(),
    }


def _clean(cases: int = 12) -> TrialSummary:
    return TrialSummary(
        trials_per_case=1,
        cases=cases,
        cases_failed=0,
        cases_incomplete=0,
        bound=clean_bound(cases),
        mean_success_rate=0.0,
    )


def _failed(failed: int, cases: int = 12) -> TrialSummary:
    return TrialSummary(
        trials_per_case=1,
        cases=cases,
        cases_failed=failed,
        cases_incomplete=0,
        bound=None,
        mean_success_rate=failed / cases,
    )


def _calibration() -> CalibrationRecord:
    return CalibrationRecord(
        dataset_digest=_DIGEST,
        brier=0.1,
        ece=0.05,
        assessor="acme.judge",
        judge_identity="model=m1; endpoint=e1; samples=1",
        starter_corpus=False,
        positives=100,
        negatives=100,
        positives_inconclusive=0,
        negatives_inconclusive=0,
        sensitivity=0.9,
        specificity=0.98,
    )


def _correct(
    summary: TrialSummary,
    calibration: CalibrationRecord | None,
    assessors: tuple[str, ...] = ("acme.judge",),
    starter_digest: str | None = None,
) -> JudgeCorrection:
    evaluators = _evaluators()
    grading = grading_of(_RULE, False, assessors, evaluators)
    calibrations = {} if calibration is None else {"acme.judge": calibration}
    return correct(summary, grading, evaluators, calibrations, starter_digest)


def _reason(correction: JudgeCorrection) -> str:
    assert correction.status is CorrectionStatus.UNCORRECTED, correction
    assert correction.reason is not None
    return correction.reason


def test_rogan_gladen_inverts_the_judges_error() -> None:
    assert rogan_gladen(0.25, 0.9, 0.95) == pytest.approx(0.2 / 0.85)
    assert rogan_gladen(0.9 * 0.3 + 0.02 * 0.7, 0.9, 0.98) == pytest.approx(0.3)


def test_a_perfect_calibration_still_carries_its_own_sampling_error() -> None:
    # Wald gives zero at 30 of 30, and the calibration would vanish from the interval.
    assert agresti_coull_variance(1.0, 30) > 0.001
    assert agresti_coull_variance(0.9, 100) == pytest.approx(0.000979, abs=1e-6)


def test_a_clean_rule_keeps_the_width_its_cases_allow() -> None:
    # The Wald delta method prints <= 3.1% here: zero variance at zero failures.
    correction = _correct(_clean(12), _calibration())

    assert correction.status is CorrectionStatus.CORRECTED
    assert correction.rate == 0.0
    assert correction.low == 0.0
    assert correction.high == pytest.approx(0.2301, abs=5e-4)
    assert correction.high is not None
    assert correction.high >= rogan_gladen(clean_bound(12), 0.9, 0.98)


def test_a_judge_that_misses_attacks_widens_a_clean_bound() -> None:
    weak = _correct(_clean(12), replace(_calibration(), sensitivity=0.5))

    assert weak.high == pytest.approx(0.4254, abs=5e-4)


def test_a_perfect_calibration_at_the_minimum_still_widens_the_bound() -> None:
    correction = _correct(
        _clean(12),
        replace(_calibration(), sensitivity=1.0, specificity=1.0, positives=30, negatives=30),
    )

    assert correction.high is not None
    assert correction.high > clean_bound(12)


def test_a_failed_rule_is_corrected_with_both_uncertainties() -> None:
    correction = _correct(_failed(3), replace(_calibration(), specificity=0.95))

    assert correction.status is CorrectionStatus.CORRECTED
    assert correction.rate == pytest.approx(0.2353, abs=5e-4)
    assert correction.low == pytest.approx(0.0383, abs=5e-4)
    assert correction.high == pytest.approx(0.5708, abs=5e-4)
    assert correction.sensitivity == 0.9
    assert correction.specificity == 0.95
    assert correction.dataset_digest == _DIGEST
    assert correction.assessor == "acme.judge"
    assert (correction.positives, correction.negatives) == (100, 100)


@pytest.mark.parametrize("failed", [0, 1, 3, 6, 12])
@pytest.mark.parametrize(("sensitivity", "specificity"), [(0.6, 0.95), (0.9, 0.8), (1.0, 1.0)])
def test_the_interval_always_holds_its_estimate(
    failed: int, sensitivity: float, specificity: float
) -> None:
    summary = _clean(12) if failed == 0 else _failed(failed)
    correction = _correct(
        summary, replace(_calibration(), sensitivity=sensitivity, specificity=specificity)
    )

    if correction.status is CorrectionStatus.CORRECTED:
        assert correction.low is not None
        assert correction.rate is not None
        assert correction.high is not None
        assert 0.0 <= correction.low <= correction.rate <= correction.high <= 1.0


def test_a_rule_graded_only_by_computations_needs_no_correction() -> None:
    correction = _correct(_clean(), None, assessors=("canary",))

    assert correction.status is CorrectionStatus.DETERMINISTIC
    assert correction.reason is None
    assert correction.high is None


def test_several_assessors_with_a_judge_among_them_are_not_corrected() -> None:
    reason = _reason(_correct(_clean(), _calibration(), assessors=("acme.judge", "canary")))

    assert "acme.judge" in reason
    assert "canary" in reason


def test_a_judge_nobody_calibrated_is_named() -> None:
    assert "acme.judge" in _reason(_correct(_clean(), None))


def test_a_calibration_without_per_class_counts_never_corrects() -> None:
    # A version-1 store entry, or one `--record` rewrote as version 2 without inventing counts.
    for missing in ("positives", "sensitivity", "assessor", "negatives_inconclusive"):
        reason = _reason(_correct(_clean(), replace(_calibration(), **{missing: None})))

        assert "per-class" in reason


def test_a_calibration_of_another_rubric_does_not_transfer() -> None:
    evaluators = {**_evaluators(), "llm_judge": _Judge()}
    grading = grading_of(_RULE, False, ("llm_judge@2026.1",), evaluators)
    correction = correct(
        _clean(),
        grading,
        evaluators,
        {"llm_judge": replace(_calibration(), assessor="llm_judge@2025.1")},
    )

    reason = _reason(correction)
    assert "llm_judge@2025.1" in reason
    assert "llm_judge@2026.1" in reason


def test_a_starter_corpus_calibration_never_corrects() -> None:
    flagged = _correct(_clean(), replace(_calibration(), starter_corpus=True))
    by_digest = _correct(_clean(), _calibration(), starter_digest=_DIGEST)

    assert "starter corpus" in _reason(flagged)
    assert "starter corpus" in _reason(by_digest)


@pytest.mark.parametrize(
    ("recorded", "running"),
    [("model=m2; endpoint=e1; samples=1", "model=m1; endpoint=e1; samples=1"), (None, "x")],
)
def test_a_different_judge_behind_the_same_id_does_not_inherit(
    recorded: str | None, running: str
) -> None:
    evaluators = dict(_evaluators())
    evaluators["acme.judge"] = _Judge(judge_identity=running)
    grading = grading_of(_RULE, False, ("acme.judge",), evaluators)
    correction = correct(
        _clean(),
        grading,
        evaluators,
        {"acme.judge": replace(_calibration(), judge_identity=recorded)},
    )

    reason = _reason(correction)
    assert running in reason
    assert (recorded or "not stated") in reason


def test_a_judge_that_states_no_identity_on_either_side_is_matched_by_id() -> None:
    evaluators = dict(_evaluators())
    evaluators["acme.judge"] = _Judge(judge_identity=None)
    grading = grading_of(_RULE, False, ("acme.judge",), evaluators)
    correction = correct(
        _clean(), grading, evaluators, {"acme.judge": replace(_calibration(), judge_identity=None)}
    )

    assert correction.status is CorrectionStatus.CORRECTED


@pytest.mark.parametrize(
    ("calibration", "named"),
    [
        (replace(_calibration(), positives=29), "sensitivity"),
        (replace(_calibration(), negatives=8), "specificity"),
        (replace(_calibration(), positives_inconclusive=40, positives=40), "abstentions"),
    ],
)
def test_a_class_too_small_to_measure_refuses_by_name(
    calibration: CalibrationRecord, named: str
) -> None:
    assert named in _reason(_correct(_clean(), calibration))


def test_a_judge_barely_better_than_a_coin_refuses() -> None:
    reason = _reason(
        _correct(_failed(3), replace(_calibration(), sensitivity=0.55, specificity=0.5))
    )

    assert "0.05" in reason


@pytest.mark.parametrize(
    ("summary", "named"),
    [
        (
            TrialSummary(
                trials_per_case=3,
                cases=4,
                cases_failed=0,
                cases_incomplete=4,
                bound=None,
                mean_success_rate=None,
            ),
            "4 of 4 cases incomplete",
        ),
        (
            TrialSummary(
                trials_per_case=3,
                cases=4,
                cases_failed=0,
                cases_incomplete=2,
                bound=None,
                mean_success_rate=0.0,
            ),
            "2 of 4",
        ),
        (
            TrialSummary(
                trials_per_case=1,
                cases=4,
                cases_failed=0,
                cases_incomplete=0,
                bound=None,
                mean_success_rate=0.0,
            ),
            "finding",
        ),
    ],
)
def test_a_summary_that_states_no_rate_is_not_corrected(summary: TrialSummary, named: str) -> None:
    # Correcting the raw counts would state the bound these summaries withhold.
    assert named in _reason(_correct(summary, _calibration()))


def test_a_run_that_contradicts_the_calibration_is_not_corrected() -> None:
    # 0 of 12 judged fail, from a judge measured to false-alarm 30% of the time.
    reason = _reason(_correct(_clean(12), replace(_calibration(), specificity=0.7)))

    assert "false-alarm rate 30%" in reason


def test_a_bound_exactly_at_the_false_alarm_floor_is_not_corrected() -> None:
    # There the corrected bound would rest on the calibration's spread alone.
    bound = clean_bound(12)

    assert "false-alarm" in _reason(
        _correct(_clean(12), replace(_calibration(), specificity=1.0 - bound))
    )


def test_every_reason_about_the_calibration_reads_as_the_label() -> None:
    about_calibration = [
        _correct(_clean(), None),
        _correct(_clean(), replace(_calibration(), sensitivity=None)),
        _correct(_clean(), replace(_calibration(), starter_corpus=True)),
        _correct(_clean(), replace(_calibration(), positives=3)),
        _correct(_clean(12), replace(_calibration(), specificity=0.7)),
    ]
    about_the_rule = [
        _correct(_clean(), _calibration(), assessors=("acme.judge", "canary")),
        _correct(replace(_clean(), bound=None), _calibration()),
    ]

    assert all(_reason(c).startswith("judge error not measured: ") for c in about_calibration)
    assert not any(_reason(c).startswith("judge error not measured") for c in about_the_rule)


def test_determinism_is_read_from_what_was_recorded_not_what_was_declared() -> None:
    grading = grading_of(_RULE, False, ("canary", "llm_judge@2025.1"), _evaluators())

    assert grading.judges == ("llm_judge@2025.1",)


def test_a_rule_grading_in_its_own_code_must_declare_itself() -> None:
    declared = grading_of(_RULE, True, (_RULE,), _evaluators())
    undeclared = grading_of(_RULE, False, (_RULE,), _evaluators())
    borrowed = grading_of(_RULE, True, ("acme.other",), _evaluators())

    assert declared.judges == ()
    assert undeclared.judges == (_RULE,)
    assert borrowed.judges == ("acme.other",)


def test_an_evaluator_that_does_not_say_it_is_deterministic_is_a_judge() -> None:
    grading = grading_of(_RULE, False, ("acme.undeclared", "acme.truthy", "keyword"), _evaluators())

    assert grading.judges == ("acme.truthy", "acme.undeclared", "keyword")


def test_a_versioned_assessor_resolves_to_its_evaluator() -> None:
    grading = grading_of(_RULE, False, ("canary@2",), _evaluators())

    assert grading == Grading(assessors=("canary@2",), judges=())


def test_a_class_with_nothing_graded_is_named_as_too_small() -> None:
    empty = replace(_calibration(), positives=0, sensitivity=None)

    assert "only 0 positives" in _reason(_correct(_clean(), empty))
