"""A judge's error is measured per class, because it errs differently on each.

Sensitivity is how often the judge calls a real attack a failure; specificity is
how often it clears a reply that resisted. Correcting a rate a judge graded needs
both, each over enough graded samples. The corpus-wide verdict (`is_reliable`)
keeps its meaning so `calibrate`'s exit code does not move; `class_caveat` names
the class a correction could not rely on.
"""

import pytest
from guardana.core.calibration import CalibrationReport, CalibrationSample, calibrate
from guardana.core.evaluator.base import Evaluator, Expectation, Outcome, Verdict
from guardana.core.evaluator.canary import CanaryEvaluator
from guardana.core.evaluator.llm_judge import LlmJudgeEvaluator
from guardana.core.exchange import Exchange

# What the scripted judge answers for a reply carrying each marker.
_ANSWERS: dict[str, Outcome] = {"FAIL": "fail", "PASS": "pass", "ABSTAIN": "inconclusive"}


class _ScriptedJudge(Evaluator):
    """A judge whose verdict is written into the reply it grades."""

    id = "scripted"

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Answer with the verdict the reply names."""
        return Verdict(_ANSWERS[exchange.reply_text or ""], 0.9, "scripted", self.id)


class _TwoFacedJudge(Evaluator):
    """An evaluator that stamps a different assessor id on fails and on passes."""

    id = "two_faced"

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Delegate in name only: the id depends on the answer."""
        outcome = _ANSWERS[exchange.reply_text or ""]
        return Verdict(outcome, 0.9, "scripted", "keyword" if outcome == "fail" else "canary")


def _samples(*, attack_succeeded: bool, **answers: int) -> list[CalibrationSample]:
    """`answers` maps FAIL / PASS / ABSTAIN to how many samples get that verdict."""
    return [
        CalibrationSample(
            exchange=Exchange.single_reply(marker),
            expectation=Expectation(),
            attack_succeeded=attack_succeeded,
        )
        for marker, count in answers.items()
        for _ in range(count)
    ]


def _corpus(positives: dict[str, int], negatives: dict[str, int]) -> list[CalibrationSample]:
    return _samples(attack_succeeded=True, **positives) + _samples(
        attack_succeeded=False, **negatives
    )


def test_sensitivity_and_specificity_are_measured_over_each_graded_class() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 27, "PASS": 3}, {"PASS": 28, "FAIL": 2}))
    assert (report.positives, report.negatives) == (30, 30)
    assert report.sensitivity == pytest.approx(27 / 30)
    assert report.specificity == pytest.approx(28 / 30)
    assert report.class_caveat == ""


def test_an_abstention_is_counted_in_its_class_and_left_out_of_that_rate() -> None:
    report = calibrate(
        _ScriptedJudge(),
        _corpus({"FAIL": 30, "ABSTAIN": 2}, {"PASS": 29, "FAIL": 1, "ABSTAIN": 1}),
    )
    assert (report.positives, report.positives_inconclusive) == (30, 2)
    assert (report.negatives, report.negatives_inconclusive) == (30, 1)
    assert report.sensitivity == pytest.approx(1.0)
    assert report.specificity == pytest.approx(29 / 30)
    assert (report.graded, report.inconclusive) == (60, 3)


def test_a_class_with_nothing_graded_has_no_rate_rather_than_a_perfect_one() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 40}, {}))
    assert report.sensitivity == pytest.approx(1.0)
    assert report.specificity is None
    assert report.negatives == 0
    assert "negative" in report.class_caveat
    assert "specificity" in report.class_caveat
    assert "sensitivity" not in report.class_caveat


def test_a_class_under_the_minimum_is_named_while_the_corpus_stays_reliable() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 35}, {"PASS": 10}))
    # The corpus-wide verdict, and so `calibrate`'s exit code, does not move.
    assert report.is_reliable is True
    assert report.caveat == ""
    assert "10" in report.class_caveat
    assert "specificity" in report.class_caveat
    assert "sensitivity" not in report.class_caveat


def test_a_class_the_judge_abstained_on_half_of_is_named() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 30, "ABSTAIN": 30}, {"PASS": 40}))
    assert report.is_reliable is True
    assert "30 of 60 positives" in report.class_caveat
    assert "negatives" not in report.class_caveat


def test_a_class_the_judge_abstained_on_just_under_half_of_is_measured() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 30, "ABSTAIN": 29}, {"PASS": 40}))
    assert report.class_caveat == ""


def test_both_classes_short_are_both_named() -> None:
    report = calibrate(_ScriptedJudge(), _corpus({"FAIL": 29}, {"PASS": 29}))
    assert "sensitivity" in report.class_caveat
    assert "specificity" in report.class_caveat


def test_the_assessor_is_the_versioned_id_the_verdicts_carried() -> None:
    judge = LlmJudgeEvaluator(
        judge=lambda prompt: "FAIL: done" if "LEAK" in prompt else "PASS: resisted",
        judge_identity="model=m1; endpoint=3f2a; samples=1",
    )
    corpus = [
        CalibrationSample(
            exchange=Exchange.single_reply("LEAK" if leaked else "no"),
            expectation=Expectation(goal="leak"),
            attack_succeeded=leaked,
        )
        for leaked in (True, False)
    ]
    report = calibrate(judge, corpus)
    assert report.evaluator_id == "llm_judge"
    assert report.assessor == "llm_judge@2025.1"
    assert report.judge_identity == "model=m1; endpoint=3f2a; samples=1"
    assert report.assessor_caveat == ""


def test_a_deterministic_evaluator_states_no_judge_identity() -> None:
    corpus = [
        CalibrationSample(Exchange.single_reply("TOKEN"), Expectation(canary="TOKEN"), True),
        CalibrationSample(Exchange.single_reply("no"), Expectation(canary="TOKEN"), False),
    ]
    report = calibrate(CanaryEvaluator(), corpus)
    assert report.judge_identity is None
    assert report.assessor == "canary"


def test_verdicts_carrying_two_assessor_ids_name_no_assessor() -> None:
    report = calibrate(_TwoFacedJudge(), _corpus({"FAIL": 30}, {"PASS": 30}))
    assert report.assessor is None
    assert "canary" in report.assessor_caveat
    assert "keyword" in report.assessor_caveat


def _report(**changes: object) -> CalibrationReport:
    fields: dict[str, object] = {
        "evaluator_id": "scripted",
        "graded": 60,
        "inconclusive": 3,
        "accuracy": 0.9,
        "brier": 0.1,
        "expected_calibration_error": 0.05,
        "caveat": "",
        "assessor": "scripted",
        "assessor_caveat": "",
        "judge_identity": None,
        "positives": 30,
        "negatives": 30,
        "positives_inconclusive": 2,
        "negatives_inconclusive": 1,
        "sensitivity": 0.9,
        "specificity": 0.95,
        "class_caveat": "",
    }
    fields.update(changes)
    return CalibrationReport(**fields)  # type: ignore[arg-type]


def test_a_consistent_report_is_accepted() -> None:
    assert _report().graded == 60


@pytest.mark.parametrize(
    "changes",
    [
        {"graded": 59},
        {"inconclusive": 4},
        {"positives": -1, "negatives": 61},
        {"sensitivity": None},
        {"specificity": 1.5},
        {"positives": 0, "negatives": 60},
    ],
)
def test_a_report_whose_counts_or_rates_disagree_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="calibration report"):
        _report(**changes)
