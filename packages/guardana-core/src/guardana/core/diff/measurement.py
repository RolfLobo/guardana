"""How the measurement channel moved between two runs, paired case by case.

What the change list cannot show: *over how many cases*. A suite that graded forty
yesterday and twelve today reports fewer findings, which every change kind reads
as an improvement.

Deliberately not a second report of per-case pass→fail — that already reaches the
comparison as a `Finding`, and counting it twice would double the one thing the
diff is most careful about. What is new is the denominator, the pairing, and the
refusal to compare cases whose definition moved.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from guardana.core.assessment import Assessment, AssessmentStatus, ComparableKey

_NAMED_IN_A_NOTE = 3
"""How many case ids a note quotes before it stops. A note nobody finishes is a
note nobody reads, and the count above it is the part that matters."""


@dataclass(frozen=True, slots=True)
class MeasurementDelta:
    """The measured sample of two runs, paired on `case_id`.

    Every field is a count of cases, never of runs. `paired` is the only population
    any rate may be computed over: the others are the reasons a case is outside it,
    kept apart so none of them can be quietly read as a zero.
    """

    paired: int = 0
    """Cases both runs measured, with the same assessor, dataset and measurement bound."""

    incomparable: int = 0
    """Cases both runs have, graded by a different assessor, over a different dataset,
    or measured in a different unit, direction or threshold.

    Excluded from every rate rather than counted as changed. A rule whose
    expectation was edited produces the same `case_id` and a different definition
    of passing it, and pairing those two would attribute an authoring decision to
    the system under test.
    """

    only_before: int = 0
    only_after: int = 0
    passed_before: int = 0
    passed_after: int = 0
    blinded: tuple[str, ...] = ()
    """Cases that produced a value before and could not be graded this time.

    Named individually because this is the shape of going blind: the finding count
    falls, every gate stays green, and the reason is that the grader stopped
    working rather than that the model started behaving.
    """

    @property
    def sample_shrank(self) -> bool:
        """Whether the second run measured fewer of the paired cases than the first."""
        return bool(self.blinded) or self.only_before > self.only_after

    def notes(self) -> tuple[str, ...]:
        """Sentences a reader needs before believing any rate computed from this."""
        lines: list[str] = []
        if self.incomparable:
            lines.append(
                f"{self.incomparable} measured case(s) were not compared: the assessor, "
                f"dataset, or measurement unit, direction, or threshold changed, so the "
                f"results answer different questions"
            )
        if self.blinded:
            shown = self.blinded[:_NAMED_IN_A_NOTE]
            more = ", …" if len(self.blinded) > _NAMED_IN_A_NOTE else ""
            lines.append(
                f"{len(self.blinded)} case(s) produced a value before and could not be "
                f"graded this time ({', '.join(shown)}{more}) — a smaller sample, not a "
                f"better result"
            )
        if self.only_before:
            lines.append(f"{self.only_before} case(s) measured before are absent from this run")
        return tuple(lines)


def measure(
    before: Sequence[Assessment],
    after: Sequence[Assessment],
    *,
    before_trials: Mapping[str, int] | None = None,
    after_trials: Mapping[str, int] | None = None,
) -> MeasurementDelta:
    """Pair two runs' assessments on `case_id` and count what each population is.

    Paired on the case alone, then checked for comparability — not paired on the
    full comparability key. Keying on all three would make an edited expectation
    look like one case disappearing and another arriving, which reads as lost
    coverage plus new coverage: two changes, both wrong, for one edit.

    A rule that repeats records one assessment per trial, so each side is first
    reduced to cases: a case is measured only when every trial its rule planned was
    measured, and it passed only when every one of them passed. `*_trials` map a rule
    to its attempts per case; a rule absent from them made one.
    """
    lhs = _cases(before, before_trials or {})
    rhs = _cases(after, after_trials or {})
    paired = incomparable = passed_before = passed_after = 0
    blinded: list[str] = []
    for case_id in sorted(lhs.keys() & rhs.keys()):
        was, now = lhs[case_id], rhs[case_id]
        if not _comparable(was.comparable_key, now.comparable_key):
            incomparable += 1
            continue
        if was.measured and not now.measured:
            blinded.append(case_id)
        if not was.measured or not now.measured:
            continue
        paired += 1
        passed_before += 1 if was.passed else 0
        passed_after += 1 if now.passed else 0
    return MeasurementDelta(
        paired=paired,
        incomparable=incomparable,
        only_before=len(lhs.keys() - rhs.keys()),
        only_after=len(rhs.keys() - lhs.keys()),
        passed_before=passed_before,
        passed_after=passed_after,
        blinded=tuple(blinded),
    )


@dataclass(frozen=True, slots=True)
class _Case:
    """One case of one run, its trials reduced to what a pairing needs."""

    comparable_key: ComparableKey
    measured: bool
    passed: bool


def _comparable(was: ComparableKey, now: ComparableKey) -> bool:
    """Whether two cases answer one question.

    An ungraded trial records no unit, direction or threshold: its bound is unknown
    rather than different, so the measurement half is compared only when both sides
    carry one. Otherwise a grader that went blind would read as an edited case.
    """
    if was[:3] != now[:3]:
        return False
    if was[3] is None or now[3] is None:
        return True
    return was[3:] == now[3:]


def _cases(assessments: Sequence[Assessment], trials: Mapping[str, int]) -> dict[str, _Case]:
    grouped: dict[str, list[Assessment]] = {}
    for assessment in assessments:
        grouped.setdefault(assessment.case_id, []).append(assessment)
    cases = {}
    for case_id, recorded in grouped.items():
        planned = trials.get(recorded[0].rule_id)
        # A rule that recorded trials and has no K on record stopped part-way or never
        # finished: how many attempts it planned is unknown, so none of its cases counts.
        if planned is None and any(a.trial is not None for a in recorded):
            known = False
        else:
            known = len(recorded) >= (planned or 1)
        measured = known and all(a.status is AssessmentStatus.MEASURED for a in recorded)
        keyed = next((a for a in recorded if a.unit is not None), recorded[0])
        cases[case_id] = _Case(
            comparable_key=keyed.comparable_key,
            measured=measured,
            passed=measured and all(a.passed for a in recorded),
        )
    return cases
