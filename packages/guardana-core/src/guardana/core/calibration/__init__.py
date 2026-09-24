"""Measuring how honest an evaluator's confidence is.

Guardana exists because dynamic AI scanners misjudge whether an attack actually
succeeded, and its answer is an Evaluator that reports a confidence. Until that
confidence is checked against known-correct labels it is the same unbacked claim
everyone else makes — so this module checks it.

The cheap way to build a labelled corpus is the deterministic graders. A planted
canary appearing verbatim in a reply is ground truth, not an opinion, and so is
the list of tools a model actually called. Label a corpus with those, ask a judge
the same questions, and you get a measured error rate without anyone hand-labelling
a row:

    report = calibrate(judge, samples)
    if not report.is_reliable:
        ...                                  # `report.caveat` says why
    print(report.brier, report.expected_calibration_error)
    print(report.sensitivity, report.specificity)   # `report.class_caveat` if unmeasured

A report names the evaluator it measured by its registered id (`llm_judge`) and,
as `assessor`, the id its verdicts carried (`llm_judge@2025.1`), which includes
the rubric version. `judge_identity` states the rest: the model, where it is
served, and how many samples make one verdict.
"""

from guardana.core.calibration.measure import calibrate
from guardana.core.calibration.report import MIN_RELIABLE_SAMPLES, CalibrationReport
from guardana.core.calibration.sample import CalibrationSample

__all__ = [
    "MIN_RELIABLE_SAMPLES",
    "CalibrationReport",
    "CalibrationSample",
    "calibrate",
]
