"""A measured judge, written down and carried into a run's evidence.

`CalibrationRecord` sat in the run manifest, serialized, for four releases, and
nothing outside a test ever constructed one — so every saved run said
`"calibration": null` for every evaluator. A field in a persisted schema that no
production path fills is a promise the document makes and never keeps, and here it
is the promise a judge-graded verdict most needs.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from guardana.core.calibration.store import (
    STORE_SCHEMA_VERSION,
    CalibrationStoreError,
    RecordedCalibration,
    corpus_digest,
    load_calibrations,
    write_calibrations,
)
from guardana.core.evaluator.keyword import KeywordEvaluator
from guardana.core.judge_error import correct, grading_of
from guardana.core.manifest.records import CorrectionStatus, TrialSummary
from guardana.core.trials import clean_bound


def _measurement(evaluator: str = "canary", digest: str = "sha256:abc") -> RecordedCalibration:
    return RecordedCalibration(
        evaluator=evaluator,
        dataset_digest=digest,
        measured_at=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
        brier=0.08,
        ece=0.03,
        samples=64,
    )


def test_a_measurement_survives_a_write_and_a_read(tmp_path: Path) -> None:
    path = tmp_path / "cal.json"

    write_calibrations(path, {"canary": _measurement()})

    assert load_calibrations(path)["canary"] == _measurement()


def test_recording_the_same_evaluator_twice_replaces_rather_than_appends(tmp_path: Path) -> None:
    """Two measurements of one judge are one fact with a date, not two facts."""
    path = tmp_path / "cal.json"
    write_calibrations(path, {"canary": _measurement()})

    stored = load_calibrations(path)
    stored["canary"] = _measurement(digest="sha256:def")
    write_calibrations(path, stored)

    assert len(load_calibrations(path)) == 1
    assert load_calibrations(path)["canary"].dataset_digest == "sha256:def"


def test_a_version_this_build_cannot_read_is_refused(tmp_path: Path) -> None:
    """Principle 11: a document a user keeps is a contract, and an unknown one is not read."""
    path = tmp_path / "cal.json"
    path.write_text(f'{{"schema_version": {STORE_SCHEMA_VERSION + 99}, "calibrations": []}}')

    with pytest.raises(CalibrationStoreError, match="this build reads"):
        load_calibrations(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('{"calibrations": []}', "schema_version"),
        (f'{{"schema_version": {STORE_SCHEMA_VERSION}}}', "needs a 'calibrations' list"),
        (
            f'{{"schema_version": {STORE_SCHEMA_VERSION}, "calibrations": '
            f'[{{"evaluator": "c", "dataset_digest": "d", "typo": 1}}]}}',
            "unknown calibration key",
        ),
        (
            f'{{"schema_version": {STORE_SCHEMA_VERSION}, "calibrations": '
            f'[{{"evaluator": "c", "dataset_digest": "d"}}]}}',
            "measured_at",
        ),
    ],
)
def test_a_malformed_calibration_file_raises_rather_than_yielding_nothing(
    tmp_path: Path, body: str, message: str
) -> None:
    """Yielding nothing would leave every evaluator recorded unmeasured.

    Which reads as "nobody checked this judge" — the opposite of what an operator
    who configured a calibration file asked to have in their evidence.
    """
    path = tmp_path / "cal.json"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(CalibrationStoreError, match=message):
        load_calibrations(path)


def test_a_measurement_with_no_date_is_refused(tmp_path: Path) -> None:
    """`measured_at` matters as much as the score.

    A judge model is replaced under the same name, so a Brier score with no date is
    a claim about an evaluator that may not exist any more.
    """
    path = tmp_path / "cal.json"
    path.write_text(
        f'{{"schema_version": {STORE_SCHEMA_VERSION}, "calibrations": '
        f'[{{"evaluator": "c", "dataset_digest": "d", "measured_at": null}}]}}',
        encoding="utf-8",
    )

    with pytest.raises(CalibrationStoreError, match="replaced under the"):
        load_calibrations(path)


def test_the_corpus_digest_changes_with_the_corpus(tmp_path: Path) -> None:
    """It is what lets a reader ask whether the number was measured on relevant traffic."""
    first = tmp_path / "a.jsonl"
    first.write_text('{"a": 1}\n', encoding="utf-8")
    second = tmp_path / "b.jsonl"
    second.write_text('{"a": 2}\n', encoding="utf-8")

    assert corpus_digest(first) != corpus_digest(second)
    assert corpus_digest(first).startswith("sha256:")


def _v2_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "evaluator": "keyword",
        "dataset_digest": "sha256:abc",
        "measured_at": "2026-09-24T10:00:00+00:00",
        "brier": 0.2,
        "ece": 0.1,
        "samples": 60,
        "assessor": "keyword",
        "judge_identity": None,
        "starter_corpus": False,
        "positives": 30,
        "negatives": 30,
        "positives_inconclusive": 0,
        "negatives_inconclusive": 1,
        "sensitivity": 0.8,
        "specificity": 0.9,
    }
    return {**entry, **overrides}


def _write(path: Path, version: int, *entries: dict[str, object]) -> Path:
    path.write_text(
        json.dumps({"schema_version": version, "calibrations": list(entries)}), encoding="utf-8"
    )
    return path


def _corrects(entry: RecordedCalibration) -> bool:
    summary = TrialSummary(
        trials_per_case=1,
        cases=12,
        cases_failed=0,
        cases_incomplete=0,
        bound=clean_bound(12),
        mean_success_rate=0.0,
    )
    evaluators = {"keyword": KeywordEvaluator()}
    grading = grading_of("acme.rule", False, ("keyword",), evaluators)
    return (
        correct(summary, grading, evaluators, {"keyword": entry.as_record()}).status
        is CorrectionStatus.CORRECTED
    )


def test_a_schema_2_entry_reads_back_its_error_per_class(tmp_path: Path) -> None:
    entry = load_calibrations(_write(tmp_path / "cal.json", 2, _v2_entry()))["keyword"]

    assert (entry.positives, entry.negatives) == (30, 30)
    assert (entry.sensitivity, entry.specificity) == (0.8, 0.9)
    assert entry.assessor == "keyword"
    assert entry.starter_corpus is False


def test_a_schema_1_file_still_loads_and_never_corrects(tmp_path: Path) -> None:
    v1 = {
        k: v
        for k, v in _v2_entry().items()
        if k in {"evaluator", "dataset_digest", "measured_at", "brier", "ece", "samples"}
    }
    path = _write(tmp_path / "cal.json", 1, v1)

    entry = load_calibrations(path)["keyword"]

    assert entry.samples == 60
    assert entry.positives is None
    assert entry.assessor is None
    assert not _corrects(entry)


def test_a_schema_1_entry_rewritten_as_schema_2_still_never_corrects(tmp_path: Path) -> None:
    v1 = {
        k: v
        for k, v in _v2_entry().items()
        if k in {"evaluator", "dataset_digest", "measured_at", "brier", "ece", "samples"}
    }
    path = _write(tmp_path / "cal.json", 1, v1)

    write_calibrations(path, load_calibrations(path))
    rewritten = json.loads(path.read_text(encoding="utf-8"))
    entry = load_calibrations(path)["keyword"]

    assert rewritten["schema_version"] == 2
    assert rewritten["calibrations"][0]["assessor"] is None
    assert entry.positives is None
    assert not _corrects(entry)


def test_a_schema_2_entry_that_measured_both_classes_can_correct(tmp_path: Path) -> None:
    # The positive control for the two tests above: without it they could pass because
    # nothing ever corrects.
    entry = load_calibrations(_write(tmp_path / "cal.json", 2, _v2_entry()))["keyword"]

    assert _corrects(entry)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"positives": 29}, "do not add up"),
        ({"sensitivity": 1.2}, "between 0 and 1"),
        ({"negatives_inconclusive": -1}, "at least 0"),
        ({"positives": True}, "whole number"),
        ({"starter_corpus": "yes"}, "starter_corpus"),
        ({"assessor": ""}, "assessor"),
        ({"specificity": None}, "missing over 30"),
        ({"positives": 0, "positives_inconclusive": 0, "samples": 30}, "nothing graded"),
        ({"assessor": None}, "without assessor"),
    ],
)
def test_a_schema_2_entry_that_contradicts_itself_is_refused(
    tmp_path: Path, overrides: dict[str, object], match: str
) -> None:
    path = _write(tmp_path / "cal.json", 2, _v2_entry(**overrides))

    with pytest.raises(CalibrationStoreError, match=match):
        load_calibrations(path)


def test_a_schema_2_entry_missing_a_key_is_refused(tmp_path: Path) -> None:
    entry = {k: v for k, v in _v2_entry().items() if k != "judge_identity"}

    with pytest.raises(CalibrationStoreError, match="judge_identity"):
        load_calibrations(_write(tmp_path / "cal.json", 2, entry))


def test_a_class_nothing_graded_is_recorded_without_its_rate(tmp_path: Path) -> None:
    # A corpus of negatives alone is a reliable measurement of specificity and of nothing else.
    entry = _v2_entry(positives=0, positives_inconclusive=0, sensitivity=None, samples=30)

    loaded = load_calibrations(_write(tmp_path / "cal.json", 2, entry))["keyword"]

    assert loaded.sensitivity is None
    assert loaded.specificity == 0.9
    assert not _corrects(loaded)
