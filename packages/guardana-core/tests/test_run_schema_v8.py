"""Run schema 8 records whether a judge-graded rate was corrected, and carries a v7 run forward.

Two new facts: each repeating rule's `trial_summary.correction` (deterministic, corrected
with its interval and the judge's error, or uncorrected with the reason), and the
per-class calibration a correction reads, on `evaluators[].calibration`. A version-7 run
arrives with both null, whatever it held: nothing is recomputed on the way.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from _documents import run_manifest, saved_run_at_v7, scan_result
from guardana.core.manifest.load import ManifestLoadError, manifest_from_dict
from guardana.core.manifest.migrations import migrate_v7
from guardana.core.manifest.records import (
    CalibrationRecord,
    CorrectionStatus,
    JudgeCorrection,
    TrialSummary,
)
from guardana.core.manifest.serialize import manifest_to_dict
from guardana.core.report.load import ReportLoadError, load_report, migrate_forward
from guardana.core.report.serialize import run_to_dict
from jsonschema import Draft202012Validator

_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
_JUDGED = 1
"""Index of the rule in the shared fixture whose summary carries a correction."""

_PER_CLASS = (
    "assessor",
    "judge_identity",
    "starter_corpus",
    "positives",
    "negatives",
    "positives_inconclusive",
    "negatives_inconclusive",
    "sensitivity",
    "specificity",
)

_CORRECTED: dict[str, Any] = {
    "status": "corrected",
    "assessor": "llm_judge@2025.1",
    "reason": None,
    "rate": 0.25,
    "low": 0.04,
    "high": 0.57,
    "sensitivity": 0.9,
    "specificity": 0.95,
    "dataset_digest": "sha256:abab",
    "positives": 120,
    "negatives": 130,
}
_UNCORRECTED: dict[str, Any] = {
    **dict.fromkeys(_CORRECTED),
    "status": "uncorrected",
    "assessor": "llm_judge@2025.1",
    "reason": "no calibration recorded for llm_judge@2025.1",
}
_DETERMINISTIC: dict[str, Any] = {**dict.fromkeys(_CORRECTED), "status": "deterministic"}


def _errors(document: dict[str, Any], version: int = 8) -> list[str]:
    schema = json.loads((_SCHEMAS / f"run-v{version}.schema.json").read_text(encoding="utf-8"))
    return [error.message for error in Draft202012Validator(schema).iter_errors(document)]


def _document() -> dict[str, Any]:
    return run_to_dict(scan_result(), run_manifest())


def _write(document: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _summary(document: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = document["run"]["rules"][_JUDGED]["trial_summary"]
    return summary


def _calibration(document: dict[str, Any]) -> dict[str, Any]:
    calibration: dict[str, Any] = document["run"]["evaluators"][0]["calibration"]
    return calibration


def _with_correction(correction: dict[str, Any] | None, **summary: object) -> dict[str, Any]:
    """The fixture with one rule's correction, and optionally its counts, replaced."""
    document = _document()
    _summary(document).update(summary, correction=correction)
    return document


def _correction(fields: dict[str, Any] | None = None) -> JudgeCorrection:
    base: dict[str, Any] = {**_CORRECTED, "status": CorrectionStatus.CORRECTED}
    return JudgeCorrection(**{**base, **(fields or {})})


# The document this build writes


def test_the_written_document_satisfies_the_v8_schema() -> None:
    assert not _errors(_document())


@pytest.mark.parametrize("correction", [_CORRECTED, _UNCORRECTED, _DETERMINISTIC, None])
def test_every_status_a_writer_can_produce_satisfies_the_schema_and_reads_back(
    correction: dict[str, Any] | None,
) -> None:
    document = _with_correction(correction)

    assert not _errors(document)
    rewritten = manifest_to_dict(manifest_from_dict(document["run"]))
    assert rewritten["rules"][_JUDGED]["trial_summary"]["correction"] == correction  # type: ignore[index]


def test_every_new_field_is_written_and_read_back() -> None:
    manifest = run_manifest()
    block = manifest_to_dict(manifest)

    assert block["rules"][_JUDGED]["trial_summary"]["correction"] == {  # type: ignore[index]
        "status": "corrected",
        "assessor": "llm_judge@2025.1",
        "reason": None,
        "rate": 0.0,
        "low": 0.0,
        "high": 0.97,
        "sensitivity": 0.9,
        "specificity": 0.95,
        "dataset_digest": "sha256:abab",
        "positives": 120,
        "negatives": 130,
    }
    calibration = block["evaluators"][0]["calibration"]  # type: ignore[index]
    assert {key: calibration[key] for key in _PER_CLASS} == {
        "assessor": "llm_judge@2025.1",
        "judge_identity": "model=m;endpoint=sha256:acac;samples=1",
        "starter_corpus": False,
        "positives": 30,
        "negatives": 31,
        "positives_inconclusive": 2,
        "negatives_inconclusive": 1,
        "sensitivity": 0.9,
        "specificity": 0.95,
    }
    assert manifest_from_dict(block) == manifest


# The correction refuses what it cannot be


@pytest.mark.parametrize(
    "fields",
    [
        {"rate": None},
        {"low": None},
        {"high": None},
        {"sensitivity": None},
        {"specificity": None},
        {"assessor": None},
        {"dataset_digest": None},
    ],
)
def test_a_corrected_rate_missing_any_part_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="corrected rate needs"):
        _correction(fields)


@pytest.mark.parametrize(
    "fields",
    [{"rate": 1.2}, {"low": -0.1}, {"high": float("nan")}, {"sensitivity": True}],
)
def test_a_number_outside_zero_to_one_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _correction(fields)


@pytest.mark.parametrize(
    "fields",
    [{"rate": 0.6, "high": 0.57}, {"rate": 0.02, "low": 0.04}],
)
def test_a_corrected_rate_outside_its_own_interval_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="low <= rate <= high"):
        _correction(fields)


def test_a_correction_from_a_judge_below_the_youden_floor_is_refused() -> None:
    # Se + Sp - 1 = 0.05: dividing by it turns a judge's noise into a rate.
    with pytest.raises(ValueError, match="sensitivity \\+ specificity - 1"):
        _correction({"sensitivity": 0.5, "specificity": 0.55})


def test_a_correction_from_a_judge_just_above_the_youden_floor_is_accepted() -> None:
    correction = _correction({"sensitivity": 0.6, "specificity": 0.55})

    assert correction.status is CorrectionStatus.CORRECTED


@pytest.mark.parametrize("reason", [None, ""])
def test_an_uncorrected_rate_that_names_no_reason_is_refused(reason: str | None) -> None:
    with pytest.raises(ValueError, match="name why"):
        JudgeCorrection(status=CorrectionStatus.UNCORRECTED, reason=reason)


@pytest.mark.parametrize("field", ["rate", "low", "high"])
def test_an_uncorrected_rate_that_states_a_corrected_number_is_refused(field: str) -> None:
    # A reader looking for a corrected rate must not find one on a rate that was not.
    with pytest.raises(ValueError, match="uncorrected rate states no corrected"):
        JudgeCorrection(**{**_UNCORRECTED, "status": CorrectionStatus.UNCORRECTED, field: 0.2})


@pytest.mark.parametrize(
    "fields",
    [
        {"reason": "no judge"},
        {"rate": 0.1},
        {"sensitivity": 0.9},
        {"specificity": 0.9},
        {"dataset_digest": "sha256:abab"},
    ],
)
def test_a_deterministic_grader_that_states_a_correction_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="deterministic grader has no"):
        JudgeCorrection(status=CorrectionStatus.DETERMINISTIC, **fields)


def test_a_status_given_as_a_bare_string_is_refused() -> None:
    # Compared by identity, a plain "corrected" would fall through to the deterministic checks.
    with pytest.raises(TypeError, match="CorrectionStatus"):
        JudgeCorrection(status="corrected")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cases", "failed", "incomplete"),
    [
        (4, 0, 0),
        (4, 0, 2),
    ],
    ids=["a finding its cases do not show", "incomplete cases, none failed"],
)
def test_a_summary_stating_no_rate_cannot_carry_a_corrected_one(
    cases: int, failed: int, incomplete: int
) -> None:
    with pytest.raises(ValueError, match="neither"):
        TrialSummary(3, cases, failed, incomplete, None, 0.0, correction=_correction())


def test_a_corrected_rate_rests_on_a_failed_case_or_a_stated_bound() -> None:
    failed = TrialSummary(3, 4, 1, 0, None, 0.25, correction=_correction())
    clean = TrialSummary(
        3, 4, 0, 0, 0.53, 0.0, correction=_correction({"rate": 0.0, "low": 0.0, "high": 0.6})
    )
    uncorrected = TrialSummary(
        3, 4, 0, 2, None, 0.0, correction=JudgeCorrection(CorrectionStatus.UNCORRECTED, reason="x")
    )

    assert failed.correction is not None
    assert clean.correction is not None
    assert uncorrected.correction is not None


@pytest.mark.parametrize(
    "fields",
    [{"positives": -1}, {"negatives": True}, {"positives_inconclusive": 1.5}, {"specificity": 1.2}],
)
def test_a_calibration_with_an_impossible_count_or_rate_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"positives|negatives|specificity"):
        CalibrationRecord(**fields)


# The loader, and the schema beside it


def test_a_document_claiming_a_correction_from_a_judge_below_the_floor_is_refused() -> None:
    document = _with_correction({**_CORRECTED, "sensitivity": 0.5, "specificity": 0.55})

    with pytest.raises(ManifestLoadError, match="correction"):
        manifest_from_dict(document["run"])


def test_a_saved_run_with_a_contradictory_correction_is_refused_by_the_report_reader(
    tmp_path: Path,
) -> None:
    document = _with_correction({**_UNCORRECTED, "rate": 0.1})

    with pytest.raises(ReportLoadError, match="correction"):
        load_report(_write(document, tmp_path))


def _drop_correction(document: dict[str, Any]) -> None:
    del _summary(document)["correction"]


def _drop_correction_key(document: dict[str, Any]) -> None:
    del _summary(document)["correction"]["reason"]


def _drop_calibration_key(document: dict[str, Any]) -> None:
    del _calibration(document)["positives"]


_BROKEN: dict[str, Callable[[dict[str, Any]], object]] = {
    "corrected without its rate": lambda d: _summary(d)["correction"].update(rate=None),
    "corrected without its assessor": lambda d: _summary(d)["correction"].update(assessor=None),
    "a rate above one": lambda d: _summary(d)["correction"].update(high=1.5),
    "a rate given as text": lambda d: _summary(d)["correction"].update(rate="0.1"),
    "an unknown status": lambda d: _summary(d)["correction"].update(status="probably"),
    "uncorrected without a reason": lambda d: _summary(d)["correction"].update(
        {**_UNCORRECTED, "reason": None}
    ),
    "uncorrected with a corrected rate": lambda d: _summary(d)["correction"].update(
        {**_UNCORRECTED, "rate": 0.1}
    ),
    "deterministic with a reason": lambda d: _summary(d)["correction"].update(
        {**_DETERMINISTIC, "reason": "why"}
    ),
    "deterministic with an error rate": lambda d: _summary(d)["correction"].update(
        {**_DETERMINISTIC, "sensitivity": 0.9}
    ),
    "corrected on a summary stating no rate": lambda d: _summary(d).update(bound=None),
    "no correction key": _drop_correction,
    "a correction missing a key": _drop_correction_key,
    "a calibration missing a key": _drop_calibration_key,
    "a starter flag given as text": lambda d: _calibration(d).update(starter_corpus="yes"),
    "a negative class count": lambda d: _calibration(d).update(positives=-1),
    "a fractional class count": lambda d: _calibration(d).update(negatives=30.5),
    "a sensitivity above one": lambda d: _calibration(d).update(sensitivity=1.1),
    "an assessor given as a number": lambda d: _calibration(d).update(assessor=3),
}


@pytest.mark.parametrize("breakage", sorted(_BROKEN))
def test_the_loader_and_the_v8_schema_refuse_the_same_malformed_block(breakage: str) -> None:
    document = _document()
    _BROKEN[breakage](document)

    with pytest.raises(ManifestLoadError):
        manifest_from_dict(document["run"])
    assert _errors(document), f"the v8 schema accepts {breakage}, which the loader refuses"


def test_a_calibration_that_is_not_an_object_is_refused() -> None:
    document = _document()
    document["run"]["evaluators"][0]["calibration"] = "measured"

    with pytest.raises(ManifestLoadError, match="calibration"):
        manifest_from_dict(document["run"])
    assert _errors(document)


def test_a_calibration_recorded_without_per_class_counts_reads_back_as_such() -> None:
    document = _document()
    _calibration(document).update(dict.fromkeys(_PER_CLASS))

    calibration = manifest_from_dict(document["run"]).evaluators[0].calibration

    assert not _errors(document)
    assert calibration is not None
    assert calibration.brier == 0.08
    assert all(getattr(calibration, key) is None for key in _PER_CLASS)


def test_the_v8_schema_refuses_what_the_loader_refuses_about_trials() -> None:
    document = _document()
    document["run"]["execution"]["trials"] = 0

    assert _errors(document)


def test_the_v8_schema_refuses_the_old_field_name() -> None:
    document = _document()
    document["run"]["rules"][0]["trials"] = 4

    assert _errors(document)


# Version 7 forward


def test_a_v7_run_migrates_to_8_with_every_correction_and_per_class_field_null() -> None:
    v7 = saved_run_at_v7(_document())
    assert not _errors(v7, 7), "the fixture must be a real version-7 document"

    migrated = migrate_forward(v7, 7)

    assert migrated["schema_version"] == 8
    assert migrated["$schema"].endswith("/v8.schema.json")
    assert not _errors(migrated)
    assert _summary(migrated)["correction"] is None
    assert migrated["run"]["rules"][0]["trial_summary"] is None
    assert all(_calibration(migrated)[key] is None for key in _PER_CLASS)
    assert _calibration(migrated)["brier"] == 0.08


def test_the_migration_overwrites_a_correction_a_v7_document_should_not_hold() -> None:
    # No version-7 build could correct a rate, so a value found there was not written by one.
    v7 = saved_run_at_v7(_document())
    _summary(v7)["correction"] = dict(_CORRECTED)
    _calibration(v7).update(sensitivity=0.99, specificity=0.99, starter_corpus=False)

    migrated = migrate_v7(v7)

    assert _summary(migrated)["correction"] is None
    assert all(_calibration(migrated)[key] is None for key in _PER_CLASS)


def test_the_migration_recomputes_nothing_else() -> None:
    v7 = saved_run_at_v7(_document())
    before = copy.deepcopy(v7)

    migrated = migrate_v7(v7)

    assert v7 == before, "the migration must not edit the document it was handed"
    assert saved_run_at_v7(migrated) == v7


def test_a_migrated_v7_run_reads_back_with_no_correction(tmp_path: Path) -> None:
    report = load_report(_write(saved_run_at_v7(_document()), tmp_path))

    summary = report.manifest.rules[_JUDGED].trial_summary
    calibration = report.manifest.evaluators[0].calibration
    assert summary is not None
    assert summary.correction is None
    assert summary.bound == 0.95
    assert calibration is not None
    assert calibration.sensitivity is None
    assert calibration.dataset_digest == "sha256:aaaa"


def test_the_migration_refuses_a_rule_that_is_not_an_object() -> None:
    v7 = saved_run_at_v7(_document())
    v7["run"]["rules"].append("guardana.demo")

    with pytest.raises(ManifestLoadError, match=r"run\.rules"):
        migrate_v7(v7)


@pytest.mark.parametrize(("positives", "negatives"), [(8, 130), (120, 29), (None, 130)])
def test_a_corrected_rate_over_a_class_too_small_to_measure_is_refused(
    positives: int | None, negatives: int | None
) -> None:
    document = _with_correction({**_CORRECTED, "positives": positives, "negatives": negatives})

    assert _errors(document)
    with pytest.raises(ManifestLoadError, match="graded"):
        manifest_from_dict(document["run"])
