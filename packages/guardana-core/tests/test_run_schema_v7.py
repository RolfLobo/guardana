"""Run schema 7 records repeated trials, and carries a schema-6 run forward inventing nothing.

Three new facts: the trials per case the operator asked for (`execution.trials`), what
each repeating rule's trials added up to (`rules[].trial_summary`), and which attempt an
assessment was (`assessments[].trial`). `rules[].trials` is renamed `declared_requests`,
and the coverage fingerprint hashes the same string it always did.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _documents import run_manifest, scan_result
from guardana.core.assessment import Assessment, AssessmentStatus
from guardana.core.fingerprint import digest_of
from guardana.core.manifest.coverage import coverage_digest
from guardana.core.manifest.load import ManifestLoadError, manifest_from_dict
from guardana.core.manifest.migrations import migrate_v6
from guardana.core.manifest.records import RuleRecord, TrialSummary
from guardana.core.manifest.serialize import manifest_to_dict
from guardana.core.report.load import ReportLoadError, load_report, migrate_forward
from guardana.core.report.result import ScanResult
from guardana.core.report.serialize import run_to_dict
from guardana.core.trials import clean_bound, reduce_rule
from jsonschema import Draft202012Validator

_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
_RULE = "guardana.prompt.jailbreak"
_CASE = f"{_RULE}#b94d27b9934d"


def _validator(version: int) -> Draft202012Validator:
    schema = json.loads((_SCHEMAS / f"run-v{version}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _errors(document: dict[str, Any], version: int) -> list[str]:
    return [error.message for error in _validator(version).iter_errors(document)]


def _write(document: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _as_v6(document: dict[str, Any]) -> dict[str, Any]:
    """Rewrite a version-7 document into the shape a version-6 build wrote."""
    run = document["run"]
    return {
        **document,
        "schema_version": 6,
        "$schema": "https://guardana.dev/schemas/run/v6.schema.json",
        "assessments": [
            {k: v for k, v in entry.items() if k != "trial"} for entry in document["assessments"]
        ],
        "run": {
            **run,
            "execution": {k: v for k, v in run["execution"].items() if k != "trials"},
            "rules": [
                {
                    **{
                        k: v
                        for k, v in rule.items()
                        if k not in {"declared_requests", "trial_summary"}
                    },
                    "trials": rule["declared_requests"],
                }
                for rule in run["rules"]
            ],
        },
    }


def _trials(*outcomes: bool | None) -> tuple[Assessment, ...]:
    """One case's trials, in order; None is a trial that could not be graded."""
    return tuple(
        Assessment(
            case_id=_CASE,
            assessor="llm_judge",
            subject_ref="http://model.invalid/v1",
            status=AssessmentStatus.INCONCLUSIVE if passed is None else AssessmentStatus.MEASURED,
            rule_id=_RULE,
            passed=passed,
            trial=n,
        )
        for n, passed in enumerate(outcomes, start=1)
    )


def test_the_written_document_satisfies_the_v7_schema() -> None:
    document = run_to_dict(scan_result(), run_manifest())

    assert not _errors(document, 7)


def test_every_new_field_is_written_and_read_back() -> None:
    manifest = run_manifest()
    block = manifest_to_dict(manifest)

    assert block["execution"]["trials"] == 3  # type: ignore[index]
    rules = {rule["id"]: rule for rule in block["rules"]}  # type: ignore[attr-defined]
    assert rules[_RULE]["declared_requests"] == 3
    assert rules[_RULE]["trial_summary"] == {
        "trials_per_case": 3,
        "cases": 1,
        "cases_failed": 0,
        "cases_incomplete": 0,
        "bound": 0.95,
        "mean_success_rate": 0.0,
    }
    assert "trials" not in rules[_RULE]
    assert manifest_from_dict(block) == manifest


def test_the_coverage_fingerprint_hashes_the_same_string_after_the_rename() -> None:
    # Every coverage digest already on disk was computed over this string; a new
    # spelling would report a coverage change between two identical runs.
    rules = (
        RuleRecord(id="a", digest="d1", declared_requests=4),
        RuleRecord(id="b", digest="d2"),
    )

    assert coverage_digest(rules, (), (), (), {}) == digest_of("rule:a:d1:4", "rule:b:d2:?")


def test_the_trials_of_one_case_survive_being_saved_and_read(tmp_path: Path) -> None:
    trials = _trials(True, False, None)
    summary = TrialSummary.from_trials(reduce_rule(_RULE, trials, 3))
    written = ScanResult(
        findings=(),
        rules_run=(_RULE,),
        rules_skipped=(),
        assessments=trials,
        trials_per_case={_RULE: 3},
    )
    rules = (RuleRecord(id=_RULE, digest="sha256:1", declared_requests=3, trial_summary=summary),)

    report = load_report(
        _write(run_to_dict(written, replace(run_manifest(), rules=rules)), tmp_path)
    )

    assert report.result.assessments == trials
    assert [a.trial for a in report.result.assessments] == [1, 2, 3]
    assert report.result.trials_per_case == {_RULE: 3}
    assert report.manifest.rules[0].trial_summary == summary
    assert TrialSummary.from_trials(reduce_rule(_RULE, report.result.assessments, 3)) == summary


def test_a_summary_is_what_the_engine_reduced() -> None:
    clean = TrialSummary.from_trials(reduce_rule(_RULE, _trials(True, True), 2))
    failed = TrialSummary.from_trials(reduce_rule(_RULE, _trials(True, False), 2))
    incomplete = TrialSummary.from_trials(reduce_rule(_RULE, _trials(True, None), 2))

    assert clean == TrialSummary(2, 1, 0, 0, clean_bound(1), 0.0)
    assert failed == TrialSummary(2, 1, 1, 0, None, 0.5)
    assert incomplete == TrialSummary(2, 1, 0, 1, None, 0.0)


@pytest.mark.parametrize(
    "fields",
    [
        {"cases_failed": 1, "bound": 0.5},
        {"cases_incomplete": 1, "bound": 0.5},
        {"cases": 0, "bound": 0.5},
        {"trials_per_case": 0},
        {"cases_failed": 3},
        {"mean_success_rate": 1.5},
    ],
)
def test_a_summary_that_contradicts_itself_is_refused(fields: dict[str, Any]) -> None:
    # A bound beside a failed case would state a clean result the trials never showed.
    base: dict[str, Any] = {
        "trials_per_case": 3,
        "cases": 2,
        "cases_failed": 0,
        "cases_incomplete": 0,
        "bound": None,
        "mean_success_rate": None,
    }
    with pytest.raises(ValueError):  # noqa: PT011 — each case names its own contradiction
        TrialSummary(**{**base, **fields})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("trials_per_case", True),
        ("cases", "4"),
        ("bound", "0.2"),
        ("cases_failed", 9),
    ],
)
def test_the_loader_refuses_a_malformed_trial_summary(key: str, value: object) -> None:
    block = manifest_to_dict(run_manifest())
    block["rules"][1]["trial_summary"][key] = value  # type: ignore[index]

    with pytest.raises(ManifestLoadError, match="trial_summary"):
        manifest_from_dict(block)


def test_the_loader_refuses_a_summary_missing_its_bound() -> None:
    # A missing bound and a null one differ: null says there is none to state.
    block = manifest_to_dict(run_manifest())
    del block["rules"][1]["trial_summary"]["bound"]  # type: ignore[index]

    with pytest.raises(ManifestLoadError, match="bound"):
        manifest_from_dict(block)


@pytest.mark.parametrize("value", [0, True, "3"])
def test_the_loader_refuses_execution_trials_that_are_not_a_count(value: object) -> None:
    block = manifest_to_dict(run_manifest())
    block["execution"]["trials"] = value  # type: ignore[index]

    with pytest.raises(ManifestLoadError, match=r"execution\.trials"):
        manifest_from_dict(block)


@pytest.mark.parametrize("value", [0, True, "2"])
def test_the_loader_refuses_an_assessment_trial_that_is_not_one(
    value: object, tmp_path: Path
) -> None:
    document = run_to_dict(scan_result(), run_manifest())
    document["assessments"][0]["trial"] = value  # type: ignore[index]

    with pytest.raises(ReportLoadError, match="trial"):
        load_report(_write(document, tmp_path))


@pytest.mark.parametrize(
    ("where", "value"),
    [("execution", 0), ("assessment", 0), ("summary", 1.2)],
)
def test_the_v7_schema_refuses_what_the_loader_refuses(where: str, value: object) -> None:
    document = run_to_dict(scan_result(), run_manifest())
    if where == "execution":
        document["run"]["execution"]["trials"] = value  # type: ignore[index]
    elif where == "assessment":
        document["assessments"][0]["trial"] = value  # type: ignore[index]
    else:
        document["run"]["rules"][1]["trial_summary"]["bound"] = value  # type: ignore[index]

    assert _errors(document, 7)


def test_the_v7_schema_refuses_the_old_field_name() -> None:
    document = run_to_dict(scan_result(), run_manifest())
    document["run"]["rules"][0]["trials"] = 4  # type: ignore[index]

    assert _errors(document, 7)


def test_a_v6_run_migrates_to_7_keeping_the_count_and_inventing_nothing(tmp_path: Path) -> None:
    v6 = _as_v6(run_to_dict(scan_result(), run_manifest()))
    assert not _errors(v6, 6), "the fixture must be a real version-6 document"

    migrated = migrate_forward(v6, 6)

    assert migrated["schema_version"] == 7
    assert migrated["$schema"].endswith("/v7.schema.json")
    assert not _errors(migrated, 7)
    rules = migrated["run"]["rules"]
    assert [rule["declared_requests"] for rule in rules] == [4, 3]
    assert all("trials" not in rule for rule in rules)
    assert all(rule["trial_summary"] is None for rule in rules)
    assert migrated["run"]["execution"]["trials"] == 1
    assert all(entry["trial"] is None for entry in migrated["assessments"])

    report = load_report(_write(v6, tmp_path))

    assert report.result.trials_per_case == {}
    assert all(a.trial is None for a in report.result.assessments)
    assert report.manifest.execution.trials == 1


def test_a_v6_run_that_recorded_no_declared_count_keeps_it_unknown() -> None:
    v6 = _as_v6(run_to_dict(scan_result(), run_manifest()))
    del v6["run"]["rules"][0]["trials"]

    migrated = migrate_v6(v6)

    assert migrated["run"]["rules"][0]["declared_requests"] is None


def test_the_migration_refuses_an_assessment_channel_that_is_not_a_list() -> None:
    v6 = _as_v6(run_to_dict(scan_result(), run_manifest()))
    v6["assessments"] = {"case": "one"}

    with pytest.raises(ManifestLoadError, match="assessments"):
        migrate_v6(v6)
