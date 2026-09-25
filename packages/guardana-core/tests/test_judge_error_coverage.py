"""The corrected interval keeps its confidence when the calibration is itself a sample.

A corrected rate divides by the judge's measured sensitivity and specificity, and at 30
samples per class those move enough to move the result. Each case below fixes a true rate
and a true judge, draws the calibration and the run's cases from them, and counts how
often each end of the printed interval lands on the wrong side of the true rate.
"""

import random

import pytest
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.judge_error import correct, grading_of
from guardana.core.manifest.records import CalibrationRecord, CorrectionStatus, TrialSummary
from guardana.core.trials import clean_bound

_RUNS = 2000
_PER_SIDE = 0.01
"""The share of runs one end may miss by: below the 2.5% a two-sided 95% interval allows."""


def _binomial(trials: int, chance: float, rng: random.Random) -> int:
    return sum(1 for _ in range(trials) if rng.random() < chance)


@pytest.mark.parametrize(
    ("rate", "cases", "sensitivity", "specificity", "per_class"),
    [
        (0.9, 300, 0.6, 0.95, 30),
        (0.8, 300, 0.7, 0.9, 30),
        (0.5, 100, 0.7, 0.9, 30),
        (0.05, 30, 0.9, 0.8, 30),
        (0.0, 13, 0.9, 0.8, 30),
        (0.02, 12, 0.9, 0.98, 100),
    ],
)
def test_each_end_of_the_corrected_interval_rarely_misses_the_true_rate(
    rate: float, cases: int, sensitivity: float, specificity: float, per_class: int
) -> None:
    rng = random.Random(7)  # noqa: S311 — a seeded simulation, not a secret
    evaluators = {"keyword": KeywordEvaluator()}
    grading = grading_of("acme.rule", False, ("keyword",), evaluators)
    upper_misses = lower_misses = 0
    for _ in range(_RUNS):
        calibration = CalibrationRecord(
            dataset_digest="sha256:" + "ab" * 32,
            assessor="keyword",
            starter_corpus=False,
            positives=per_class,
            negatives=per_class,
            positives_inconclusive=0,
            negatives_inconclusive=0,
            sensitivity=_binomial(per_class, sensitivity, rng) / per_class,
            specificity=_binomial(per_class, specificity, rng) / per_class,
        )
        judged = sensitivity * rate + (1.0 - specificity) * (1.0 - rate)
        failed = _binomial(cases, judged, rng)
        summary = TrialSummary(
            trials_per_case=1,
            cases=cases,
            cases_failed=failed,
            cases_incomplete=0,
            bound=clean_bound(cases) if failed == 0 else None,
            mean_success_rate=failed / cases,
        )
        correction = correct(summary, grading, evaluators, {"keyword": calibration})
        if correction.status is not CorrectionStatus.CORRECTED:
            continue
        assert correction.low is not None
        assert correction.high is not None
        upper_misses += correction.high < rate
        lower_misses += correction.low > rate

    assert upper_misses / _RUNS <= _PER_SIDE
    assert lower_misses / _RUNS <= _PER_SIDE
