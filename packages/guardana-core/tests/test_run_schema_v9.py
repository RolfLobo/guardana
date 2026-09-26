"""Run schema 9 records what a suite measured and concluded, and carries a v8 run forward.

One new fact: `rules[].suite`, the summary a suite built while it ran — its dataset, the
cases measured and ungraded, the worst and best pass rates with their limits, the
threshold, the outcome, and the pass rate corrected for its judge's error or why not. A
version-8 run arrives with every `suite` null, whatever it held.
"""

import copy
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from _documents import run_manifest, saved_run_at_v8, scan_result
from guardana.core.manifest.load import ManifestLoadError, manifest_from_dict
from guardana.core.manifest.migrations import migrate_v6, migrate_v7, migrate_v8
from guardana.core.manifest.records import (
    CorrectionStatus,
    SuiteCorrection,
    SuiteOutcome,
    SuiteSummary,
)
from guardana.core.manifest.serialize import manifest_to_dict
from guardana.core.report.load import ReportLoadError, load_report, migrate_forward
from guardana.core.report.serialize import run_to_dict
from guardana.core.testing.manifests import suite_rule, suite_summary
from jsonschema import Draft202012Validator

_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
_SUITE = 2
"""Index of the rule in the shared fixture that is a suite."""

_CORRECTED: dict[str, Any] = {
    "status": CorrectionStatus.CORRECTED,
    "assessor": "llm_judge@2025.1",
    "worst": 0.92,
    "best": 0.94,
    "low": 0.9,
    "high": 0.97,
    "sensitivity": 0.9,
    "specificity": 0.95,
    "dataset_digest": "sha256:abab",
    "positives": 120,
    "negatives": 130,
}


def _errors(document: dict[str, Any], version: int = 9) -> list[str]:
    schema = json.loads((_SCHEMAS / f"run-v{version}.schema.json").read_text(encoding="utf-8"))
    return [error.message for error in Draft202012Validator(schema).iter_errors(document)]


def _document() -> dict[str, Any]:
    return run_to_dict(scan_result(), run_manifest())


def _write(document: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _suite(document: dict[str, Any]) -> dict[str, Any]:
    suite: dict[str, Any] = document["run"]["rules"][_SUITE]["suite"]
    return suite


def _corrected(**fields: object) -> SuiteCorrection:
    return SuiteCorrection(**{**_CORRECTED, **fields})


_DETERMINISTIC_PASS = suite_summary()
_CORRECTED_FAIL = suite_summary(
    worst=0.7,
    best=0.75,
    low=0.58,
    high=0.85,
    outcome=SuiteOutcome.FAIL,
    correction=_corrected(worst=0.72, best=0.78, low=0.6, high=0.88),
)
_UNCORRECTED_INCONCLUSIVE = suite_summary(
    outcome=SuiteOutcome.INCONCLUSIVE,
    reason="uncorrected — no calibration recorded for llm_judge@2025.1",
    correction=SuiteCorrection(
        status=CorrectionStatus.UNCORRECTED,
        assessor="llm_judge@2025.1",
        reason="no calibration recorded for llm_judge@2025.1",
    ),
)
_SAMPLED = suite_summary(sample_size=50, sample_seed=7, cases=50, measured=50)


# The document this build writes


def test_the_written_document_satisfies_the_v9_schema() -> None:
    assert not _errors(_document())


@pytest.mark.parametrize(
    "summary",
    [_DETERMINISTIC_PASS, _CORRECTED_FAIL, _UNCORRECTED_INCONCLUSIVE, _SAMPLED],
    ids=["deterministic pass", "corrected fail", "uncorrected inconclusive", "sampled"],
)
def test_a_suite_survives_being_saved_and_read_back(summary: SuiteSummary, tmp_path: Path) -> None:
    manifest = replace(run_manifest(), rules=(suite_rule(summary),))
    document = run_to_dict(scan_result(), manifest)

    assert not _errors(document)
    assert manifest_from_dict(manifest_to_dict(manifest)) == manifest
    assert load_report(_write(document, tmp_path)).manifest.rules[0].suite == summary


def test_every_new_field_is_written() -> None:
    block = manifest_to_dict(replace(run_manifest(), rules=(suite_rule(_CORRECTED_FAIL),)))

    assert block["rules"][0]["suite"] == {  # type: ignore[index]
        "dataset": "support-answers@1",
        "dataset_digest": _DETERMINISTIC_PASS.dataset_digest,
        "sample_size": None,
        "sample_seed": None,
        "trials_per_case": 3,
        "cases": 40,
        "measured": 40,
        "ungraded": 0,
        "worst": 0.7,
        "best": 0.75,
        "low": 0.58,
        "high": 0.85,
        "min_pass_rate": 0.9,
        "min_sample": 30,
        "outcome": "fail",
        "reason": None,
        "correction": {
            "status": "corrected",
            "assessor": "llm_judge@2025.1",
            "reason": None,
            "worst": 0.72,
            "best": 0.78,
            "low": 0.6,
            "high": 0.88,
            "sensitivity": 0.9,
            "specificity": 0.95,
            "dataset_digest": "sha256:abab",
            "positives": 120,
            "negatives": 130,
        },
    }


def test_a_rule_that_is_not_a_suite_writes_a_null_suite() -> None:
    block = manifest_to_dict(run_manifest())

    assert [rule["suite"] is None for rule in block["rules"]] == [True, True, False]  # type: ignore[attr-defined]


# The summary refuses what its numbers do not support


@pytest.mark.parametrize("outcome", [SuiteOutcome.PASS, SuiteOutcome.FAIL])
def test_a_suite_concluding_below_min_sample_is_refused(outcome: SuiteOutcome) -> None:
    rates = {"worst": 0.5, "best": 0.6, "low": 0.4, "high": 0.7} if outcome == "fail" else {}
    with pytest.raises(ValueError, match="below min_sample"):
        suite_summary(outcome=outcome, measured=20, ungraded=20, **rates)


def test_a_pass_under_the_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="passes only"):
        suite_summary(worst=0.88, best=0.9, low=0.8, high=0.95)


def test_a_deterministic_pass_at_the_threshold_is_accepted() -> None:
    assert suite_summary(worst=0.9, best=0.9, low=0.8).outcome is SuiteOutcome.PASS


def test_a_corrected_pass_over_a_raw_worst_under_the_threshold_needs_its_low_above_it() -> None:
    # The correction lifted the rate over the line; only its lower limit says it stays there.
    raw = {"worst": 0.85, "best": 0.88, "low": 0.75, "high": 0.93}
    with pytest.raises(ValueError, match="passes only"):
        suite_summary(**raw, correction=_corrected(low=0.88))

    assert suite_summary(**raw, correction=_corrected(low=0.9)).outcome is SuiteOutcome.PASS


def test_a_corrected_pass_over_a_raw_worst_at_the_threshold_needs_no_corrected_low() -> None:
    summary = suite_summary(correction=_corrected(low=0.8))

    assert summary.outcome is SuiteOutcome.PASS


def test_a_corrected_pass_under_the_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="passes only"):
        suite_summary(correction=_corrected(worst=0.89, low=0.85))


@pytest.mark.parametrize(
    "fields",
    [
        {"worst": 0.85, "best": 0.9, "low": 0.75, "high": 0.95},
        {"worst": 0.7, "best": 0.8, "low": 0.6, "high": 0.9, "correction": _corrected()},
    ],
    ids=["raw best at the threshold", "corrected best above it"],
)
def test_a_fail_whose_best_rate_reaches_the_threshold_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="fails only"):
        suite_summary(outcome=SuiteOutcome.FAIL, **fields)


@pytest.mark.parametrize("reason", [None, ""])
def test_an_inconclusive_suite_without_a_reason_is_refused(reason: str | None) -> None:
    with pytest.raises(ValueError, match="must say why"):
        suite_summary(outcome=SuiteOutcome.INCONCLUSIVE, reason=reason)


@pytest.mark.parametrize("outcome", [SuiteOutcome.PASS, SuiteOutcome.FAIL])
def test_a_concluded_suite_stating_a_reason_is_refused(outcome: SuiteOutcome) -> None:
    rates = {"worst": 0.5, "best": 0.6, "low": 0.4, "high": 0.7} if outcome == "fail" else {}
    with pytest.raises(ValueError, match="states no reason"):
        suite_summary(outcome=outcome, reason="because", **rates)


@pytest.mark.parametrize(
    "fields",
    [{"measured": 30}, {"ungraded": 2}, {"cases": 41}],
)
def test_counts_that_do_not_add_up_are_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="do not make"):
        suite_summary(**fields)


@pytest.mark.parametrize(
    "fields",
    [{"ungraded": -1, "measured": 41}, {"cases": True}, {"measured": 40.0}],
)
def test_a_case_count_that_is_not_a_whole_number_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="case counts"):
        suite_summary(**fields)


@pytest.mark.parametrize(
    "fields",
    [{"trials_per_case": 0}, {"min_sample": 0}, {"min_sample": True}, {"trials_per_case": 1.5}],
)
def test_a_trial_count_or_min_sample_under_one_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        suite_summary(**fields)


@pytest.mark.parametrize("fields", [{"sample_size": 40}, {"sample_seed": 7}])
def test_a_sample_states_both_its_size_and_its_seed(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="size and its seed"):
        suite_summary(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"low": 0.96},
        {"worst": 0.96, "best": 0.95},
        {"high": 0.94},
    ],
    ids=["low above worst", "worst above best", "high below best"],
)
def test_bounds_out_of_order_are_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="a suite needs low <= worst <= best <= high"):
        suite_summary(**fields)


@pytest.mark.parametrize("fields", [{"high": 1.2}, {"low": -0.1}, {"worst": float("nan")}])
def test_a_rate_outside_zero_to_one_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"must lie in \[0, 1\]"):
        suite_summary(**fields)


@pytest.mark.parametrize("field", ["worst", "best", "low", "high"])
def test_a_suite_with_cases_states_every_rate(field: str) -> None:
    with pytest.raises(ValueError, match="states worst, best, low and high"):
        suite_summary(**{field: None})


def test_a_suite_with_no_case_declines_without_rates() -> None:
    summary = suite_summary(
        cases=0,
        measured=0,
        worst=None,
        best=None,
        low=None,
        high=None,
        outcome=SuiteOutcome.INCONCLUSIVE,
        reason="no case measured",
    )

    assert summary.worst is None


@pytest.mark.parametrize("threshold", [0.0, 1.1, float("nan")])
def test_a_threshold_outside_zero_to_one_is_refused(threshold: float) -> None:
    with pytest.raises(ValueError, match=r"min_pass_rate must lie in \(0, 1\]"):
        suite_summary(min_pass_rate=threshold)


def test_an_outcome_given_as_a_bare_string_is_refused() -> None:
    with pytest.raises(TypeError, match="SuiteOutcome"):
        suite_summary(outcome="pass")


@pytest.mark.parametrize("outcome", [SuiteOutcome.PASS, SuiteOutcome.FAIL])
def test_a_suite_graded_by_an_uncorrected_judge_cannot_conclude(outcome: SuiteOutcome) -> None:
    rates = {"worst": 0.5, "best": 0.6, "low": 0.4, "high": 0.7} if outcome == "fail" else {}
    uncorrected = SuiteCorrection(CorrectionStatus.UNCORRECTED, reason="no calibration")
    with pytest.raises(ValueError, match="uncorrected judge cannot conclude"):
        suite_summary(outcome=outcome, correction=uncorrected, **rates)


# The correction refuses what it cannot be


def test_a_correction_status_given_as_a_bare_string_is_refused() -> None:
    with pytest.raises(TypeError, match="CorrectionStatus"):
        SuiteCorrection(status="deterministic")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ["worst", "best", "low", "high", "sensitivity", "specificity", "assessor", "dataset_digest"],
)
def test_a_corrected_pass_rate_missing_any_part_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match="corrected pass rate needs its"):
        _corrected(**{field: None})


@pytest.mark.parametrize(
    "fields",
    [{"low": 0.93}, {"worst": 0.95}, {"high": 0.93}],
    ids=["low above worst", "worst above best", "high below best"],
)
def test_a_corrected_pass_rate_with_bounds_out_of_order_is_refused(
    fields: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="corrected pass rate needs low <= worst"):
        _corrected(**fields)


@pytest.mark.parametrize("field", ["worst", "best", "low", "high", "sensitivity", "specificity"])
def test_a_corrected_number_outside_zero_to_one_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=rf"{field} must lie in \[0, 1\]"):
        _corrected(**{field: 1.5})


@pytest.mark.parametrize(
    "fields",
    [{"positives": 29}, {"negatives": 29}, {"positives": None}, {"negatives": True}],
)
def test_a_corrected_pass_rate_under_30_per_class_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="at least 30 graded"):
        _corrected(**fields)


def test_a_correction_from_a_judge_below_the_youden_floor_is_refused() -> None:
    with pytest.raises(ValueError, match=r"sensitivity \+ specificity - 1"):
        _corrected(sensitivity=0.5, specificity=0.55)

    assert _corrected(sensitivity=0.6, specificity=0.55).status is CorrectionStatus.CORRECTED


@pytest.mark.parametrize("reason", [None, ""])
def test_an_uncorrected_pass_rate_naming_no_reason_is_refused(reason: str | None) -> None:
    with pytest.raises(ValueError, match="name why"):
        SuiteCorrection(CorrectionStatus.UNCORRECTED, reason=reason)


@pytest.mark.parametrize("field", ["worst", "best", "low", "high"])
def test_an_uncorrected_pass_rate_stating_a_corrected_number_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match="uncorrected rate states no corrected"):
        SuiteCorrection(CorrectionStatus.UNCORRECTED, reason="no calibration", **{field: 0.9})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assessor", "keyword@1"),
        ("reason", "why"),
        ("worst", 0.9),
        ("best", 0.9),
        ("low", 0.9),
        ("high", 0.9),
        ("sensitivity", 0.9),
        ("specificity", 0.9),
        ("dataset_digest", "sha256:abab"),
        ("positives", 30),
        ("negatives", 30),
    ],
)
def test_a_deterministic_grader_stating_a_number_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="deterministic grader has no"):
        SuiteCorrection(CorrectionStatus.DETERMINISTIC, **{field: value})  # type: ignore[arg-type]


# The loader, and the schema beside it


def _drop(*path: str) -> Callable[[dict[str, Any]], object]:
    def drop(document: dict[str, Any]) -> None:
        node: dict[str, Any] = document["run"]["rules"][_SUITE]
        for step in path[:-1]:
            node = node[step]
        del node[path[-1]]

    return drop


def _set(**fields: object) -> Callable[[dict[str, Any]], object]:
    return lambda document: _suite(document).update(fields)


def _set_correction(**fields: object) -> Callable[[dict[str, Any]], object]:
    return lambda document: _suite(document)["correction"].update(fields)


_BROKEN: dict[str, Callable[[dict[str, Any]], object]] = {
    "no suite key": _drop("suite"),
    "a suite missing a key": _drop("suite", "measured"),
    "a suite missing its reason": _drop("suite", "reason"),
    "a correction missing a key": _drop("suite", "correction", "reason"),
    "a suite that is not an object": lambda d: d["run"]["rules"][_SUITE].update(suite="yes"),
    "a null correction": _set(correction=None),
    "an unknown outcome": _set(outcome="passed"),
    "an outcome given as a boolean": _set(outcome=True),
    "a count given as text": _set(cases="40"),
    "a count given as a boolean": _set(trials_per_case=True),
    "a rate given as text": _set(worst="0.83"),
    "a rate above one": _set(high=1.5),
    "a threshold of zero": _set(min_pass_rate=0),
    "a dataset that is not text": _set(dataset=3),
    "a seed without a size": _set(sample_size=None),
    "a size without a seed": _set(sample_seed=None),
    "inconclusive without a reason": _set(reason=None),
    "a pass stating a reason": _set(outcome="pass"),
    "a pass under an uncorrected judge": _set(
        outcome="pass",
        reason=None,
        correction={
            "status": "uncorrected",
            "assessor": "llm_judge@2025.1",
            "reason": "no calibration",
            **dict.fromkeys(
                ("worst", "best", "low", "high", "sensitivity", "specificity", "dataset_digest")
            ),
            "positives": None,
            "negatives": None,
        },
    ),
    "an unknown correction status": _set_correction(status="probably"),
    "corrected without its worst": _set_correction(worst=None),
    "corrected without its assessor": _set_correction(assessor=None),
    "corrected over 29 positives": _set_correction(positives=29),
    "uncorrected with a corrected rate": _set_correction(
        status="uncorrected", reason="no calibration"
    ),
    "deterministic with a sensitivity": _set_correction(
        status="deterministic",
        **dict.fromkeys(
            ("assessor", "worst", "best", "low", "high", "specificity", "dataset_digest")
        ),
        positives=None,
        negatives=None,
    ),
}


@pytest.mark.parametrize("breakage", sorted(_BROKEN))
def test_the_loader_and_the_v9_schema_refuse_the_same_malformed_suite(breakage: str) -> None:
    document = _document()
    _BROKEN[breakage](document)

    with pytest.raises(ManifestLoadError, match="suite"):
        manifest_from_dict(document["run"])
    assert _errors(document), f"the v9 schema accepts {breakage}, which the loader refuses"


_CONTRADICTED: dict[str, dict[str, object]] = {
    "counts that do not add up": {"measured": 30},
    "bounds out of order": {"low": 0.85},
    "a pass below min_sample": {"outcome": "pass", "reason": None, "min_sample": 38},
    "a fail at the threshold": {"outcome": "fail", "reason": None, "min_pass_rate": 0.83},
}


@pytest.mark.parametrize("contradiction", sorted(_CONTRADICTED))
def test_the_loader_refuses_a_suite_its_own_numbers_contradict(contradiction: str) -> None:
    # JSON Schema cannot compare two fields; the loader must.
    document = _document()
    _suite(document).update(_CONTRADICTED[contradiction])

    with pytest.raises(ManifestLoadError, match=r"run\.rules\[\]\.suite"):
        manifest_from_dict(document["run"])


def test_a_saved_run_with_a_contradictory_suite_is_refused_by_the_report_reader(
    tmp_path: Path,
) -> None:
    document = _document()
    _suite(document).update(outcome="pass", reason=None, min_sample=38)

    with pytest.raises(ReportLoadError, match="suite"):
        load_report(_write(document, tmp_path))


@pytest.mark.parametrize("block", ["suite", "correction"])
def test_the_v9_schema_refuses_an_unknown_key_inside_a_suite(block: str) -> None:
    document = _document()
    target = _suite(document) if block == "suite" else _suite(document)["correction"]
    target["verdict"] = "pass"

    assert _errors(document)


# Version 8 forward


def test_a_v8_run_migrates_to_9_with_every_suite_null() -> None:
    v8 = saved_run_at_v8(_document())
    assert not _errors(v8, 8), "the fixture must be a real version-8 document"

    migrated = migrate_forward(v8, 8)

    assert migrated["schema_version"] == 9
    assert migrated["$schema"] == "https://guardana.dev/schemas/run/v9.schema.json"
    assert not _errors(migrated)
    assert [rule["suite"] for rule in migrated["run"]["rules"]] == [None, None, None]


def test_a_v8_run_reads_back_with_no_suite(tmp_path: Path) -> None:
    report = load_report(_write(saved_run_at_v8(_document()), tmp_path))

    assert [rule.suite for rule in report.manifest.rules] == [None, None, None]
    assert report.manifest.rules[1].trial_summary is not None


def test_the_migration_overwrites_a_suite_a_v8_document_should_not_hold() -> None:
    # No version-8 build ran a suite, so a summary found there was not written by one.
    injected = _suite(_document())
    v8 = saved_run_at_v8(_document())
    v8["run"]["rules"][_SUITE]["suite"] = injected
    v8["run"]["rules"][0]["suite"] = {"outcome": "pass"}

    migrated = migrate_v8(v8)

    assert [rule["suite"] for rule in migrated["run"]["rules"]] == [None, None, None]


def test_the_migration_recomputes_nothing_else() -> None:
    v8 = saved_run_at_v8(_document())
    before = copy.deepcopy(v8)

    migrated = migrate_v8(v8)

    assert v8 == before, "the migration must not edit the document it was handed"
    assert saved_run_at_v8(migrated) == v8


def test_the_migration_refuses_a_rule_that_is_not_an_object() -> None:
    v8 = saved_run_at_v8(_document())
    v8["run"]["rules"].append("acme.suite")

    with pytest.raises(ManifestLoadError, match=r"run\.rules"):
        migrate_v8(v8)


@pytest.mark.parametrize("rules", [None, "acme.suite", {"id": "acme.suite"}])
def test_the_migrations_refuse_a_rule_list_that_is_not_a_list(rules: object) -> None:
    """Migrated to an empty list, it would load as a run in which no rule ran."""
    v8 = saved_run_at_v8(_document())
    if rules is None:
        del v8["run"]["rules"]
    else:
        v8["run"]["rules"] = rules
    for migrate in (migrate_v6, migrate_v7, migrate_v8):
        with pytest.raises(ManifestLoadError, match=r"run\.rules must be a list"):
            migrate(v8)
