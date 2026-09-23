"""What the renderers say about a repeating rule: its trials, its bound, and what it is not.

Read from the summary the engine stored in the manifest, so a saved run prints the
verdict it was written with, and a rule that ran once is never labelled with the K
somebody asked for.
"""

import json
from dataclasses import replace

from guardana.core.assessment import Assessment
from guardana.core.manifest.records import RuleRecord, TrialSummary
from guardana.core.manifest.settings import ExecutionSettings
from guardana.core.report import Evidence, Finding, ScanResult
from guardana.core.severity import Severity
from guardana.core.target import TargetKind
from guardana.core.testing import manifest_for
from guardana.report import get_renderer

_SAMPLED = "acme.prompt.demo"
_PROTOCOL = "acme.mcp.auth"


def _assessments(cases: int, trials: int) -> tuple[Assessment, ...]:
    return tuple(
        Assessment(
            case_id=f"{_SAMPLED}#{c}",
            assessor="keyword",
            subject_ref="http://x#m",
            rule_id=_SAMPLED,
            passed=True,
            trial=t,
        )
        for c in range(cases)
        for t in range(1, trials + 1)
    )


def _render(
    name: str, summary: TrialSummary, *, asked: int, findings: tuple[Finding, ...] = ()
) -> str:
    result = ScanResult(
        findings,
        (_SAMPLED, _PROTOCOL),
        (),
        assessments=_assessments(summary.cases, summary.trials_per_case),
    )
    manifest = manifest_for(result, target_kind=TargetKind.ENDPOINT)
    manifest = replace(
        manifest,
        execution=replace(manifest.execution, trials=asked),
        rules=(
            RuleRecord(id=_SAMPLED, digest="d", trial_summary=summary),
            RuleRecord(id=_PROTOCOL, digest="p"),
        ),
    )
    return get_renderer(name, run=manifest).render(result)


def _clean(cases: int = 12, trials: int = 5) -> TrialSummary:
    return TrialSummary(
        trials_per_case=trials,
        cases=cases,
        cases_failed=0,
        cases_incomplete=0,
        bound=1 - 0.05 ** (1 / cases),
        mean_success_rate=0.0,
    )


def test_a_clean_rule_states_its_cases_trials_bound_and_grader() -> None:
    text = _render("human", _clean(), asked=5)

    assert (
        f"{_SAMPLED}  clean · 0 of 12 cases in 5 trials each · ASR@5 ≤ 22.1% (95%) · "
        "graded by keyword, grader error not corrected"
    ) in text
    assert "static prompt set · no adaptive attacker ran" in text


def test_a_bound_is_rounded_up_never_down() -> None:
    # Twenty clean cases bound attack success at 13.911...%; rounding to the nearest
    # tenth would print 13.9 and claim a little more than the cases showed.
    text = _render("human", _clean(cases=20, trials=1), asked=1)

    assert "ASR@1 ≤ 14%" in text


def test_a_rule_that_ran_once_is_named_when_more_trials_were_asked_for() -> None:
    text = _render("human", _clean(), asked=5)

    assert f"one attempt per case, whatever was asked: {_PROTOCOL}" in text


def test_a_failed_rule_reports_attack_success_over_cases_with_its_interval() -> None:
    failed = TrialSummary(
        trials_per_case=5,
        cases=12,
        cases_failed=3,
        cases_incomplete=0,
        bound=None,
        mean_success_rate=0.12,
    )

    text = _render("human", failed, asked=5)

    assert "3 of 12 cases failed in 5 trials each · ASR@5 25% (95% CI 8.8 to 53.3%)" in text
    assert "mean failure rate per trial 12%" in text
    assert "clean" not in text.split(_SAMPLED, 2)[-1].split("\n", 1)[0]


def test_an_incomplete_rule_says_so_and_states_no_bound() -> None:
    incomplete = TrialSummary(
        trials_per_case=5,
        cases=12,
        cases_failed=0,
        cases_incomplete=2,
        bound=None,
        mean_success_rate=0.0,
    )

    text = _render("human", incomplete, asked=5)

    assert "not clean: 2 of 12 cases incomplete, a trial could not be graded" in text
    assert "≤" not in text


def test_the_summary_counts_cases_not_trials() -> None:
    text = _render("human", _clean(), asked=5)

    assert "12/12 case(s) measured" in text


def test_nothing_about_trials_is_printed_without_a_manifest_to_read_it_from() -> None:
    result = ScanResult((), (_SAMPLED,), (), assessments=_assessments(2, 3))

    text = get_renderer("human").render(result)

    assert "Trials" not in text
    assert "2/2 case(s) measured" in text


def test_sarif_carries_trials_per_rule_and_not_per_run() -> None:
    def finding(rule_id: str) -> Finding:
        return Finding(rule_id, Severity.HIGH, "t", (), "http://x#m", Evidence(summary="s"))

    sarif = json.loads(
        _render("sarif", _clean(), asked=5, findings=(finding(_SAMPLED), finding(_PROTOCOL)))
    )

    rules = {r["id"]: r for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
    assert rules[_SAMPLED]["properties"] == {"trialsPerCase": 5}
    assert "properties" not in rules[_PROTOCOL]


def test_execution_settings_default_to_one_trial() -> None:
    assert ExecutionSettings(concurrency=1, timeout_seconds=1).trials == 1


def test_a_summary_with_no_bound_and_nothing_failed_says_why() -> None:
    contradicted = TrialSummary(
        trials_per_case=1,
        cases=3,
        cases_failed=0,
        cases_incomplete=0,
        bound=None,
        mean_success_rate=0.0,
    )

    text = _render("human", contradicted, asked=1)

    assert "no bound: the rule reported a finding its 3 recorded case(s) do not show" in text
    assert "clean" not in text.split(_SAMPLED, 2)[-1].split("\n", 1)[0]
