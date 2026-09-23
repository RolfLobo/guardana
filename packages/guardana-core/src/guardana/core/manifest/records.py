"""What did the checking, with what calibration, and what came of it."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from guardana.core.gate import GateOutcome
from guardana.core.report.skipped import SkippedRule
from guardana.core.report.stop import StopReason

if TYPE_CHECKING:
    from guardana.core.trials import RuleTrials


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
