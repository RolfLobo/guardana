from dataclasses import dataclass

# Below this many graded samples the metrics are noise: a handful of lucky
# answers produce a perfect score. Reporting that as a calibration would be the
# false confidence this whole measurement exists to expose.
MIN_RELIABLE_SAMPLES = 30


def class_caveat(name: str, rate: str, graded: int, inconclusive: int) -> str:
    """Say why one class of a calibration cannot supply `rate`, or return an empty string.

    Per class, because a corpus of 200 negatives and 8 positives has measured
    specificity and not sensitivity, and a correction reads both.
    """
    if graded < MIN_RELIABLE_SAMPLES:
        return (
            f"only {graded} {name} graded in calibration; {MIN_RELIABLE_SAMPLES} needed "
            f"to measure {rate}"
        )
    if inconclusive * 2 >= graded + inconclusive:
        return (
            f"too many abstentions in calibration: {inconclusive} of {graded + inconclusive} {name}"
        )
    return ""


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """How wrong an evaluator's confidence actually is, measured against known labels.

    Two metrics, because they answer different questions. **Brier** is the mean
    squared error of the predicted probability — one number for "how good are
    these predictions overall". **Expected calibration error** asks the narrower
    and, here, more damning question: when this judge says it is 90% sure, is it
    right 90% of the time? A judge can be no better than a coin flip and still
    claim certainty every time; accuracy hides that, ECE names it.

    `inconclusive` is counted and excluded from both. A judge that abstained has
    not made a prediction, and scoring an abstention as one would invent data —
    but a judge that abstains on half the corpus is not calibrated, it is absent,
    so the count is reported and `is_reliable` refuses. All three numbers are
    `None` when nothing was graded, so a measurement that never happened cannot
    read as a flawless one.

    The per-class figures are what a correction of a judged rate needs.
    `positives` / `negatives` count the graded samples where the attack did / did
    not succeed, and the `_inconclusive` pair counts each class's abstentions;
    `graded` and `inconclusive` are their sums, which construction enforces.
    `sensitivity` is the share of graded positives the evaluator failed,
    `specificity` the share of graded negatives it passed; each is `None` when its
    class had nothing graded. `class_caveat` names the class whose rate is not
    measured well enough to correct with, and is empty when both are.

    `evaluator_id` is the id the evaluator is registered under; `assessor` is the
    id its verdicts carried (`llm_judge@2025.1` for `llm_judge`), or `None` when
    they carried more than one, which `assessor_caveat` then names.
    `judge_identity` is copied from the evaluator.
    """

    evaluator_id: str
    graded: int
    inconclusive: int
    accuracy: float | None
    brier: float | None
    expected_calibration_error: float | None
    caveat: str
    assessor: str | None
    assessor_caveat: str
    judge_identity: str | None
    positives: int
    negatives: int
    positives_inconclusive: int
    negatives_inconclusive: int
    sensitivity: float | None
    specificity: float | None
    class_caveat: str

    def __post_init__(self) -> None:
        problem = self._inconsistency()
        if problem:
            raise ValueError(f"calibration report of {self.evaluator_id!r}: {problem}")

    def _inconsistency(self) -> str:
        counts = (
            self.positives,
            self.negatives,
            self.positives_inconclusive,
            self.negatives_inconclusive,
        )
        if min(counts) < 0:
            return "a per-class count is negative"
        if self.graded != self.positives + self.negatives:
            return f"graded {self.graded} is not positives + negatives"
        if self.inconclusive != self.positives_inconclusive + self.negatives_inconclusive:
            return f"inconclusive {self.inconclusive} is not the sum of the per-class counts"
        for name, rate, graded in (
            ("sensitivity", self.sensitivity, self.positives),
            ("specificity", self.specificity, self.negatives),
        ):
            if (rate is None) != (graded == 0):
                return f"{name} must be stated exactly when its class had graded samples"
            if rate is not None and not 0.0 <= rate <= 1.0:
                return f"{name} {rate} is outside [0, 1]"
        return ""

    @property
    def is_reliable(self) -> bool:
        """Whether these numbers are worth quoting; `caveat` says why not."""
        return not self.caveat
