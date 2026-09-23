"""A comparison between runs that made a different number of attempts per case.

A failure found in five tries and missed in one is more sampling, not a worse
system. The rule is refused by name, the diff cannot pass, and a rule whose attempts
did not change — a protocol check that never repeats — is still compared.
"""

from guardana.core.assessment import Assessment, AssessmentStatus
from guardana.core.diff import compare, gate_diff
from guardana.core.diff.measurement import measure
from guardana.core.diff.model import ChangeKind
from guardana.core.evaluator.base import Verdict
from guardana.core.profile import Policy
from guardana.core.report import Evidence, Finding, ScanResult
from guardana.core.severity import Severity

_SAMPLED = "acme.prompt.demo"
_PROTOCOL = "acme.mcp.auth"
_ENDPOINT = "http://x#m"


def _finding(rule_id: str) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.HIGH,
        title="t",
        taxonomy=(),
        target_ref=_ENDPOINT,
        evidence=Evidence(summary="complied"),
        verdict=Verdict("fail", 0.9, "complied", "keyword"),
    )


def _trial(case: str, trial: int | None, *, passed: bool | None = True) -> Assessment:
    return Assessment(
        case_id=case,
        assessor="keyword",
        subject_ref=_ENDPOINT,
        status=AssessmentStatus.MEASURED if passed is not None else AssessmentStatus.INCONCLUSIVE,
        rule_id=_SAMPLED,
        passed=passed,
        dataset="d",
        trial=trial,
    )


def _run(
    *findings: Finding, trials: int = 1, assessments: tuple[Assessment, ...] = ()
) -> ScanResult:
    return ScanResult(
        findings=findings,
        rules_run=(_SAMPLED, _PROTOCOL),
        rules_skipped=(),
        assessments=assessments,
        trials_per_case={_SAMPLED: trials, _PROTOCOL: 1},
    )


def test_a_rule_whose_trials_changed_is_refused_by_name_and_not_classified() -> None:
    diff = compare(_run(trials=1), _run(_finding(_SAMPLED), trials=5))

    assert not [c for c in diff.changes if c.rule_id == _SAMPLED]
    assert any(reason.startswith(f"{_SAMPLED}: trials changed 1 → 5") for reason in diff.incomplete)
    assert gate_diff(diff, Policy())


def test_a_rule_that_did_not_repeat_is_still_compared_when_the_run_k_moved() -> None:
    diff = compare(_run(trials=1), _run(_finding(_PROTOCOL), trials=5))

    assert [c.kind for c in diff.changes if c.rule_id == _PROTOCOL] == [ChangeKind.APPEARED]
    assert not any(reason.startswith(_PROTOCOL) for reason in diff.incomplete)


def test_the_same_trials_on_both_sides_compare_as_before() -> None:
    diff = compare(_run(trials=5), _run(_finding(_SAMPLED), trials=5))

    assert diff.incomplete == ()
    assert [c.kind for c in diff.changes] == [ChangeKind.APPEARED]


def test_a_run_recorded_before_trials_compares_with_one_attempt_per_case() -> None:
    old = ScanResult(findings=(), rules_run=(_SAMPLED,), rules_skipped=())
    diff = compare(old, _run(trials=1))

    assert diff.incomplete == ()


def test_trials_are_reduced_to_cases_before_they_are_paired() -> None:
    held = tuple(_trial("c", t) for t in range(1, 6))
    one_failed = (*held[:4], _trial("c", 5, passed=False))

    delta = measure(held, one_failed, before_trials={_SAMPLED: 5}, after_trials={_SAMPLED: 5})

    assert delta.paired == 1
    assert (delta.passed_before, delta.passed_after) == (1, 0)
    assert delta.only_before == delta.only_after == 0


def test_a_case_with_an_ungraded_trial_is_not_measured_and_reads_as_blinded() -> None:
    held = tuple(_trial("c", t) for t in range(1, 6))
    one_ungraded = (*held[:4], _trial("c", 5, passed=None))

    delta = measure(held, one_ungraded, before_trials={_SAMPLED: 5}, after_trials={_SAMPLED: 5})

    assert delta.paired == 0
    assert delta.blinded == ("c",)


def test_a_case_short_of_its_planned_trials_is_not_measured() -> None:
    held = tuple(_trial("c", t) for t in range(1, 6))

    delta = measure(held, held[:3], before_trials={_SAMPLED: 5}, after_trials={_SAMPLED: 5})

    assert delta.paired == 0
    assert delta.blinded == ("c",)


def test_trials_left_by_a_rule_that_did_not_finish_are_not_measured() -> None:
    held = tuple(_trial("c", t) for t in range(1, 6))

    delta = measure(held, held[:2], before_trials={_SAMPLED: 5}, after_trials={})

    assert delta.paired == 0
    assert delta.blinded == ("c",)
