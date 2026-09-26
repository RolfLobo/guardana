"""A suite's interval keeps its confidence when cases differ and trials repeat.

Each case below fixes a population of cases whose pass rates differ, draws a suite from
it, and counts how often each end of the stated interval lands on the wrong side of the
population's mean pass rate. Trials of one case are correlated, so an interval over
pooled trials, or one that collapses when every case agrees, misses far more often.
"""

import random

import pytest
from guardana.core.assessment import Assessment, AssessmentStatus
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.manifest.records import CalibrationRecord, CorrectionStatus, SuiteSummary
from guardana.core.suite import SuiteGate, measure_suite

_RUNS = 1000
_PER_SIDE = 0.025
"""The share of runs one end may miss by: what a two-sided 95% interval allows."""

_EVALUATORS = {"keyword": KeywordEvaluator()}
_RULE = "acme.quality"


def _draw(mean: float, concentration: float | None, rng: random.Random) -> float:
    if concentration is None:
        return mean
    return rng.betavariate(mean * concentration, (1.0 - mean) * concentration)


def _suite(passes: list[list[bool]], calibrations: dict[str, CalibrationRecord]) -> SuiteSummary:
    assessments = [
        Assessment(
            case_id=f"c{n}",
            assessor="keyword",
            subject_ref="https://model.test",
            status=AssessmentStatus.MEASURED,
            rule_id=_RULE,
            passed=passed,
            trial=t,
        )
        for n, case in enumerate(passes)
        for t, passed in enumerate(case, start=1)
    ]
    return measure_suite(
        assessments,
        rule_id=_RULE,
        case_ids=[f"c{n}" for n in range(len(passes))],
        trials_per_case=len(passes[0]),
        gate=SuiteGate(min_pass_rate=0.5, min_sample=1),
        dataset="d@1",
        dataset_digest="sha256:" + "ef" * 32,
        evaluators=_EVALUATORS if calibrations else {},
        calibrations=calibrations,
    )


@pytest.mark.parametrize(
    ("cases", "trials", "mean", "concentration"),
    [
        (30, 3, 0.98, None),
        (30, 3, 0.95, 5.0),
        (30, 5, 0.9, 2.0),
        (100, 5, 0.99, 50.0),
        (50, 3, 0.5, 1.0),
    ],
)
def test_each_end_of_the_pass_rate_interval_rarely_misses(
    cases: int, trials: int, mean: float, concentration: float | None
) -> None:
    rng = random.Random(7)  # noqa: S311 — a seeded simulation, not a secret
    lower = upper = 0
    for _ in range(_RUNS):
        passes = [
            [rng.random() < p for _ in range(trials)]
            for p in (_draw(mean, concentration, rng) for _ in range(cases))
        ]
        summary = _suite(passes, {})
        assert summary.low is not None
        assert summary.high is not None
        lower += summary.low > mean
        upper += summary.high < mean
    assert lower / _RUNS <= _PER_SIDE
    assert upper / _RUNS <= _PER_SIDE


@pytest.mark.parametrize(
    ("population", "judge"),
    [
        ((30, 3, 0.9, 5.0), (0.9, 0.9)),
        ((100, 3, 0.9, 10.0), (0.8, 0.9)),
        ((30, 5, 0.8, 2.0), (0.7, 0.9)),
        ((100, 1, 0.9, None), (0.9, 0.9)),
    ],
)
def test_each_end_of_the_corrected_pass_rate_rarely_misses(
    population: tuple[int, int, float, float | None], judge: tuple[float, float]
) -> None:
    """The judge flips each trial's grade with its true error; the calibration is a sample."""
    cases, trials, mean, concentration = population
    sensitivity, specificity = judge
    rng = random.Random(11)  # noqa: S311 — a seeded simulation, not a secret
    lower = upper = 0
    for _ in range(_RUNS):
        calibration = CalibrationRecord(
            dataset_digest="sha256:" + "ab" * 32,
            assessor="keyword",
            starter_corpus=False,
            positives=30,
            negatives=30,
            positives_inconclusive=0,
            negatives_inconclusive=0,
            sensitivity=sum(rng.random() < sensitivity for _ in range(30)) / 30,
            specificity=sum(rng.random() < specificity for _ in range(30)) / 30,
        )
        passes = []
        for _case in range(cases):
            p = _draw(mean, concentration, rng)
            graded = []
            for _trial in range(trials):
                truly_passed = rng.random() < p
                flagged = rng.random() < ((1.0 - specificity) if truly_passed else sensitivity)
                graded.append(not flagged)
            passes.append(graded)
        summary = _suite(passes, {"keyword": calibration})
        correction = summary.correction
        if correction.status is not CorrectionStatus.CORRECTED:
            continue
        assert correction.low is not None
        assert correction.high is not None
        lower += correction.low > mean
        upper += correction.high < mean
    assert lower / _RUNS <= 0.01
    assert upper / _RUNS <= 0.01
