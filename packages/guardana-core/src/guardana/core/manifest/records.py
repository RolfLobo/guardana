"""What did the checking, with what calibration, and what came of it."""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from guardana.core.calibration.report import MIN_RELIABLE_SAMPLES
from guardana.core.gate import GateOutcome
from guardana.core.report.skipped import SkippedRule
from guardana.core.report.stop import StopReason

if TYPE_CHECKING:
    from guardana.core.trials import RuleTrials


MIN_YOUDEN = 0.1
"""The least sensitivity + specificity - 1 a judge may have for its error to be corrected.

Below it the correction divides by a number close to zero and amplifies noise into a rate.
"""


class CorrectionStatus(StrEnum):
    """Whether a rule's rate was corrected for its grader's error."""

    DETERMINISTIC = "deterministic"
    """Graded by computation alone; there is no judge error to correct."""

    CORRECTED = "corrected"
    """Graded by a judge whose per-class error was measured and applied."""

    UNCORRECTED = "uncorrected"
    """Graded by a judge whose error could not be applied; `reason` says why."""


def _is_share(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0.0 <= value <= 1.0
    )


_CORRECTION_NUMBERS = ("rate", "low", "high", "sensitivity", "specificity")
_CALIBRATION_COUNTS = (
    "positives",
    "negatives",
    "positives_inconclusive",
    "negatives_inconclusive",
)


@dataclass(frozen=True, slots=True)
class JudgeCorrection:
    """A rule's attack-success rate corrected for its judge's error, or why it was not.

    Stored rather than recomputed by a reader for the reason `TrialSummary` is: a later
    build correcting with other constants must not print a different verdict for the
    same run.
    """

    status: CorrectionStatus
    assessor: str | None = None
    """The assessor id the rule's verdicts carried, which the calibration was matched on."""

    reason: str | None = None
    """Why the rate stays uncorrected; set only when it does."""

    rate: float | None = None
    low: float | None = None
    high: float | None = None
    sensitivity: float | None = None
    specificity: float | None = None
    dataset_digest: str | None = None
    """The digest of the corpus the applied calibration was measured on."""

    positives: int | None = None
    """The graded positives the applied sensitivity was measured over."""

    negatives: int | None = None
    """The graded negatives the applied specificity was measured over."""

    def __post_init__(self) -> None:
        """Refuse a correction whose numbers contradict its status or each other.

        A corrected rate missing a number, or one computed from a judge too weak to
        correct, would print as a measured result the calibration never supported.
        """
        if not isinstance(self.status, CorrectionStatus):
            raise TypeError(f"status must be a CorrectionStatus, got {self.status!r}")
        self._check_ranges()
        if self.status is CorrectionStatus.CORRECTED:
            self._check_corrected()
            return
        stated = [name for name in ("rate", "low", "high") if getattr(self, name) is not None]
        if self.status is CorrectionStatus.UNCORRECTED:
            if not self.reason:
                raise ValueError("an uncorrected rate must name why it was not corrected")
            if stated:
                raise ValueError(f"an uncorrected rate states no corrected {', '.join(stated)}")
            return
        stated += [
            name
            for name in (
                "sensitivity",
                "specificity",
                "reason",
                "dataset_digest",
                "positives",
                "negatives",
            )
            if getattr(self, name) is not None
        ]
        if stated:
            raise ValueError(f"a deterministic grader has no {', '.join(stated)} to state")

    def _check_ranges(self) -> None:
        for name in _CORRECTION_NUMBERS:
            value = getattr(self, name)
            if value is not None and not _is_share(value):
                raise ValueError(f"{name} must lie in [0, 1], got {value!r}")
        for name in ("positives", "negatives"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a whole number of at least 0, got {value!r}")

    def _check_corrected(self) -> None:
        rate, low, high = self.rate, self.low, self.high
        sensitivity, specificity = self.sensitivity, self.specificity
        if (
            rate is None
            or low is None
            or high is None
            or sensitivity is None
            or specificity is None
            or not self.assessor
            or not self.dataset_digest
        ):
            raise ValueError(
                "a corrected rate needs its rate, low, high, sensitivity, specificity, "
                "assessor and dataset_digest"
            )
        if not low <= rate <= high:
            raise ValueError(
                f"a corrected rate needs low <= rate <= high, got {low}, {rate}, {high}"
            )
        for name, graded in (("positives", self.positives), ("negatives", self.negatives)):
            if graded is None or graded < MIN_RELIABLE_SAMPLES:
                raise ValueError(
                    f"a corrected rate needs at least {MIN_RELIABLE_SAMPLES} graded {name} "
                    f"behind it, got {graded!r}"
                )
        youden = sensitivity + specificity - 1.0
        if youden < MIN_YOUDEN:
            raise ValueError(
                f"sensitivity + specificity - 1 is {youden:.3f}; a judge below {MIN_YOUDEN} "
                f"is not corrected"
            )


@dataclass(frozen=True, slots=True)
class TrialSummary:
    """What one repeating rule's trials added up to, over cases, as the engine reduced them.

    Stored rather than re-derived by each reader, as `ResultSummary.gate` is: a later
    build reducing the same assessments differently must not print a different
    verdict for the same run.
    """

    trials_per_case: int
    cases: int
    cases_failed: int
    """Cases where at least one trial failed."""

    cases_incomplete: int
    """Cases with no failure and at least one trial that never resolved."""

    bound: float | None
    """Upper bound on attack success over cases when every case held, else None."""

    mean_success_rate: float | None
    """The mean over cases of each case's share of failed trials; None when none graded."""

    correction: JudgeCorrection | None = None
    """The rate corrected for the grader's error, or why not; None in a migrated document."""

    def __post_init__(self) -> None:
        """Refuse counts that contradict each other, and a bound over a rule that was not clean.

        A bound stated beside a failed or incomplete case would read as a clean result
        the trials never showed.
        """
        if isinstance(self.trials_per_case, bool) or self.trials_per_case < 1:
            raise ValueError(f"trials_per_case must be at least 1, got {self.trials_per_case!r}")
        counts = (self.cases, self.cases_failed, self.cases_incomplete)
        if any(isinstance(n, bool) or n < 0 for n in counts):
            raise ValueError(f"case counts must be whole numbers of at least 0, got {counts}")
        if self.cases_failed + self.cases_incomplete > self.cases:
            raise ValueError(
                f"{self.cases_failed} failed and {self.cases_incomplete} incomplete cases "
                f"cannot come from {self.cases}"
            )
        for name in ("bound", "mean_success_rate"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1], got {value!r}")
        if self.bound is not None and (
            self.cases == 0 or self.cases_failed or self.cases_incomplete
        ):
            raise ValueError("a bound is stated only over a rule whose every case held")
        if (
            self.correction is not None
            and self.correction.status is CorrectionStatus.CORRECTED
            and self.bound is None
            and not self.cases_failed
        ):
            raise ValueError(
                "a corrected rate needs a stated bound or a failed case to correct; "
                "this summary states neither"
            )

    @classmethod
    def from_trials(cls, trials: "RuleTrials") -> "TrialSummary":
        """Summarise one rule's reduced trials."""
        return cls(
            trials_per_case=trials.trials,
            cases=len(trials.cases),
            cases_failed=len(trials.failed),
            cases_incomplete=len(trials.incomplete),
            bound=trials.bound,
            mean_success_rate=trials.mean_success_rate,
        )


class SuiteOutcome(StrEnum):
    """What a suite's gate concluded about its pass rate."""

    PASS = "pass"  # noqa: S105 — an outcome name, not a credential
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    """The suite declined: too few cases measured, a judge it could not correct, or ungraded
    trials that could carry the rate to either side of the threshold."""


_SUITE_SHARES = ("worst", "best", "low", "high")


@dataclass(frozen=True, slots=True)
class SuiteCorrection:
    """A suite's pass rate corrected for its judge's error, or why it was not.

    In pass space throughout, unlike `JudgeCorrection`, whose rate is a corrected failure
    rate: the two are separate types so no reader can take one for the other.
    """

    status: CorrectionStatus
    assessor: str | None = None
    reason: str | None = None
    worst: float | None = None
    """The corrected pass rate with every ungraded trial counted failed."""

    best: float | None = None
    """The corrected pass rate with every ungraded trial counted passed."""

    low: float | None = None
    high: float | None = None
    sensitivity: float | None = None
    specificity: float | None = None
    dataset_digest: str | None = None
    positives: int | None = None
    negatives: int | None = None

    def __post_init__(self) -> None:
        """Refuse a correction whose numbers contradict its status or each other."""
        if not isinstance(self.status, CorrectionStatus):
            raise TypeError(f"status must be a CorrectionStatus, got {self.status!r}")
        for name in (*_SUITE_SHARES, "sensitivity", "specificity"):
            value = getattr(self, name)
            if value is not None and not _is_share(value):
                raise ValueError(f"{name} must lie in [0, 1], got {value!r}")
        stated = [name for name in _SUITE_SHARES if getattr(self, name) is not None]
        if self.status is CorrectionStatus.CORRECTED:
            self._check_corrected()
        elif self.status is CorrectionStatus.UNCORRECTED:
            if not self.reason:
                raise ValueError("an uncorrected rate must name why it was not corrected")
            if stated:
                raise ValueError(f"an uncorrected rate states no corrected {', '.join(stated)}")
        else:
            stated += [
                name
                for name in (
                    "assessor",
                    "reason",
                    "sensitivity",
                    "specificity",
                    "dataset_digest",
                    "positives",
                    "negatives",
                )
                if getattr(self, name) is not None
            ]
            if stated:
                raise ValueError(f"a deterministic grader has no {', '.join(stated)} to state")

    def _check_corrected(self) -> None:
        worst, best, low, high = self.worst, self.best, self.low, self.high
        sensitivity, specificity = self.sensitivity, self.specificity
        if (
            worst is None
            or best is None
            or low is None
            or high is None
            or sensitivity is None
            or specificity is None
            or not self.assessor
            or not self.dataset_digest
        ):
            raise ValueError(
                "a corrected pass rate needs its worst, best, low, high, sensitivity, "
                "specificity, assessor and dataset_digest"
            )
        if not low <= worst <= best <= high:
            raise ValueError(
                f"a corrected pass rate needs low <= worst <= best <= high, "
                f"got {low}, {worst}, {best}, {high}"
            )
        for name, graded in (("positives", self.positives), ("negatives", self.negatives)):
            if (
                isinstance(graded, bool)
                or not isinstance(graded, int)
                or graded < MIN_RELIABLE_SAMPLES
            ):
                raise ValueError(
                    f"a corrected rate needs at least {MIN_RELIABLE_SAMPLES} graded {name} "
                    f"behind it, got {graded!r}"
                )
        youden = sensitivity + specificity - 1.0
        if youden < MIN_YOUDEN:
            raise ValueError(
                f"sensitivity + specificity - 1 is {youden:.3f}; a judge below {MIN_YOUDEN} "
                f"is not corrected"
            )


@dataclass(frozen=True, slots=True)
class SuiteSummary:
    """What a suite measured over its dataset and what its gate concluded.

    Built once, by the suite while it runs, and stored as it was built: a reader that
    recomputed it could hold other calibrations or another K and print another verdict.
    Every rate is a pass share over cases, each case weighted by its share of passed trials.
    """

    dataset: str
    """The dataset's declared identity, `name@version`."""

    dataset_digest: str
    trials_per_case: int
    cases: int
    """Cases after sampling: the ones the suite set out to measure."""

    measured: int
    """Cases whose every planned trial was graded: what `min_sample` counts."""

    ungraded: int
    """Cases with at least one trial that could not be graded."""

    min_pass_rate: float
    min_sample: int
    outcome: SuiteOutcome
    correction: SuiteCorrection
    worst: float | None = None
    """The raw pass rate with every ungraded trial counted failed; None with no case."""

    best: float | None = None
    """The raw pass rate with every ungraded trial counted passed; None with no case."""

    low: float | None = None
    """The 95% lower limit at `worst`."""

    high: float | None = None
    """The 95% upper limit at `best`."""

    sample_size: int | None = None
    sample_seed: int | None = None
    reason: str | None = None
    """Why the suite declined; set exactly when it did."""

    def __post_init__(self) -> None:
        """Refuse a summary whose outcome its own numbers do not support.

        A stored pass is what a pipeline reads; one the counts or the rates contradict would
        be a green build nobody measured.
        """
        self._check_counts()
        shares = [getattr(self, name) for name in _SUITE_SHARES]
        if any(value is not None and not _is_share(value) for value in shares):
            raise ValueError(f"worst, best, low and high must lie in [0, 1], got {shares}")
        if self.cases and any(value is None for value in shares):
            raise ValueError("a suite with cases states worst, best, low and high")
        worst, best, low, high = shares
        if (
            worst is not None
            and best is not None
            and low is not None
            and high is not None
            and not low <= worst <= best <= high
        ):
            raise ValueError(f"a suite needs low <= worst <= best <= high, got {shares}")
        if not _is_share(self.min_pass_rate) or self.min_pass_rate == 0.0:
            raise ValueError(f"min_pass_rate must lie in (0, 1], got {self.min_pass_rate!r}")
        self._check_outcome()

    def _check_counts(self) -> None:
        for name in ("trials_per_case", "min_sample"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a whole number of at least 1, got {value!r}")
        counts = (self.cases, self.measured, self.ungraded)
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in counts):
            raise ValueError(f"case counts must be whole numbers of at least 0, got {counts}")
        if self.measured + self.ungraded != self.cases:
            raise ValueError(
                f"{self.measured} measured and {self.ungraded} ungraded cases do not make "
                f"{self.cases}"
            )
        if (self.sample_size is None) != (self.sample_seed is None):
            raise ValueError("a sample states both its size and its seed, or neither")

    def _check_outcome(self) -> None:
        if not isinstance(self.outcome, SuiteOutcome):
            raise TypeError(f"outcome must be a SuiteOutcome, got {self.outcome!r}")
        if self.outcome is SuiteOutcome.INCONCLUSIVE:
            if not self.reason:
                raise ValueError("a suite that declined must say why")
            return
        if self.reason is not None:
            raise ValueError(f"a suite that concluded {self.outcome} states no reason")
        if self.measured < self.min_sample:
            raise ValueError(
                f"{self.measured} measured cases are below min_sample {self.min_sample}; "
                f"the suite cannot conclude {self.outcome}"
            )
        worst, best, low = self._gated()
        threshold = self.min_pass_rate
        if self.outcome is SuiteOutcome.PASS and not (
            worst >= threshold and (low is None or low >= threshold)
        ):
            raise ValueError(f"a suite passes only with its worst rate at {threshold} or above")
        if self.outcome is SuiteOutcome.FAIL and not best < threshold:
            raise ValueError(f"a suite fails only with its best rate below {threshold}")

    def _gated(self) -> tuple[float, float, float | None]:
        """Return the worst and best rates the gate reads, and the low end a pass must clear.

        Raw for a deterministic assessor, corrected for a judge. A corrected pass over a raw
        worst below the threshold must also clear it at the corrected lower limit; the low
        end is None when no lower limit is required.
        """
        status = self.correction.status
        if status is CorrectionStatus.UNCORRECTED:
            raise ValueError("a suite graded by an uncorrected judge cannot conclude")
        if self.worst is None or self.best is None:
            raise ValueError("a suite with no case cannot conclude")
        if status is CorrectionStatus.DETERMINISTIC:
            return self.worst, self.best, None
        corrected = self.correction
        if corrected.worst is None or corrected.best is None or corrected.low is None:
            raise ValueError("a corrected suite states its corrected rates")
        low = corrected.low if self.worst < self.min_pass_rate else None
        return corrected.worst, corrected.best, low


@dataclass(frozen=True, slots=True)
class RuleRecord:
    """One rule that ran, with the digest of what it was when it ran.

    The digest is what stops a sharpened rule from being read as a worse model:
    more findings from a rule whose corpus grew is the test talking, not the
    target.
    """

    id: str
    digest: str
    version: str | None = None
    """The version of the distribution that supplied this rule, when it named one.

    With `origin`, the only thing in a saved run that separates two rules sharing
    an id: `digest` hashes the declaration, which a replacement copies exactly.
    """

    origin: str | None = None
    """Which installed distribution supplied it, or the file a YAML rule came from.

    `None` means unattributed — built in code by an embedding caller — and stays
    distinguishable from "nothing installed", which is why it is not `""`.
    """

    maturity: str | None = None
    declared_requests: int | None = None
    """How many model calls this rule declared it would make, or None if it could not say.

    Part of the coverage fingerprint rather than decoration: a rule trimmed from
    four prompts to one checks less, and a run that recorded only the rule's name
    would read as unchanged. `None` is the honest answer for a rule whose cost is
    unknown up front, and it stays distinguishable from zero. For a rule that
    repeats, the count includes every trial.
    """

    trial_summary: TrialSummary | None = None
    """What the rule's repeated trials added up to; None for a rule that made one attempt."""

    suite: SuiteSummary | None = None
    """What a suite measured and concluded; None for every rule that is not a suite."""


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    """How well an evaluator's confidence was measured, and when.

    `measured_at` matters as much as the scores: a calibration from six months
    ago describes a judge model that has since been replaced under the same name.
    """

    dataset_digest: str | None = None
    measured_at: datetime | None = None
    brier: float | None = None
    ece: float | None = None
    assessor: str | None = None
    """The assessor id the calibrated verdicts carried, versioned as the verdicts were."""

    judge_identity: str | None = None
    """Everything behind the judge's verdict that its id does not name."""

    starter_corpus: bool | None = None
    """Whether the calibration ran on the bundled starter corpus rather than the operator's."""

    positives: int | None = None
    """Graded positive examples; this and the three below are None when never recorded."""

    negatives: int | None = None
    positives_inconclusive: int | None = None
    negatives_inconclusive: int | None = None
    sensitivity: float | None = None
    specificity: float | None = None

    def __post_init__(self) -> None:
        """Refuse a negative count and a rate outside [0, 1]."""
        for name in _CALIBRATION_COUNTS:
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a whole number of at least 0, got {value!r}")
        for name in ("sensitivity", "specificity"):
            value = getattr(self, name)
            if value is not None and not _is_share(value):
                raise ValueError(f"{name} must lie in [0, 1], got {value!r}")


@dataclass(frozen=True, slots=True)
class EvaluatorRecord:
    """One evaluator that graded, with its calibration when it has one."""

    id: str
    version: str | None = None
    digest: str | None = None
    calibration: CalibrationRecord | None = None


@dataclass(frozen=True, slots=True)
class ResultSummary:
    """The counts and the verdict, written by the engine rather than inferred.

    `gate` is a stored field on purpose. A consumer that re-derives the verdict
    from the counts will eventually derive it differently from the engine — a
    threshold read from the wrong place, an `unverified` channel nobody knew
    about — and the divergence shows up as a green build.

    It is nullable for exactly one case: a document migrated from schema version
    1, which never recorded a verdict. Computing one during migration would be
    that same re-derivation, done with this build's thresholds against another
    build's run — so the honest answer is that the old document does not say.
    """

    findings: int
    unverified: int
    waived: int
    errors: int
    observations: int
    rules_run: tuple[str, ...]
    rules_skipped: tuple[SkippedRule, ...]
    max_severity: str | None
    gate: GateOutcome | None
    stopped_by: StopReason | None = None
    assessments: int = 0
    """How many cases this run recorded a measurement for, of any status."""

    measured: int = 0
    """How many of them produced a value — the denominator, kept beside the total.

    Two numbers because their difference is the fact that matters: 40 assessments
    and 3 measured is a rate over three cases.
    """
