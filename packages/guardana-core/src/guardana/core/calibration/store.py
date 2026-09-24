"""Recorded evaluator calibrations, so a run can carry the measurement into its evidence.

`CalibrationRecord` has been in the run manifest since the manifest existed, has
always been serialized, and until now nothing outside tests ever constructed one:
every saved run said `"calibration": null` for every evaluator. A field in a
persisted schema that no production path fills is a promise the document makes and
never keeps — and here the promise is the one a judge-graded verdict most needs,
because a confidence nobody measured is the unbacked claim `calibrate` exists to
expose.

This is the file in between. `guardana calibrate --record` writes it, a profile
points at it with `calibrations:`, and every run that grades with a recorded
evaluator carries the number, its date and the digest of the set it was measured on.

Versioned and migratable, because it is a document a user keeps (principle 11).
"""

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from guardana.core.fingerprint import digest_of
from guardana.core.manifest.records import CalibrationRecord

STORE_SCHEMA_VERSION = 2
"""Bump when the shape below changes, and add the migration that reads the old one."""

_V1_KEYS = frozenset({"evaluator", "dataset_digest", "measured_at", "brier", "ece", "samples"})
_COUNTS = ("positives", "negatives", "positives_inconclusive", "negatives_inconclusive")
_RATES = ("sensitivity", "specificity")
_PER_CLASS = ("assessor", *_COUNTS)
_V2_KEYS = _V1_KEYS | {"judge_identity", "starter_corpus", *_PER_CLASS, *_RATES}
_KEYS = {1: _V1_KEYS, 2: _V2_KEYS}


class CalibrationStoreError(Exception):
    """Raised when a calibration file cannot be read as measurements."""


@dataclass(frozen=True, slots=True)
class RecordedCalibration:
    """One evaluator's measurement, as written down.

    The per-class fields are None for a measurement taken before store schema 2, and stay
    None when such an entry is rewritten: a count nobody took is not reconstructed, and an
    entry without them never corrects a rate.
    """

    evaluator: str
    dataset_digest: str
    measured_at: datetime
    brier: float | None
    ece: float | None
    samples: int
    assessor: str | None = None
    """The id the evaluator's verdicts carried, which a versioned rubric changes."""

    judge_identity: str | None = None
    starter_corpus: bool | None = None
    """Whether the bundled starter corpus was measured; None when that was not recorded."""

    positives: int | None = None
    negatives: int | None = None
    positives_inconclusive: int | None = None
    negatives_inconclusive: int | None = None
    sensitivity: float | None = None
    specificity: float | None = None

    def as_record(self) -> CalibrationRecord:
        """Render this into the shape a run manifest carries."""
        return CalibrationRecord(
            dataset_digest=self.dataset_digest,
            measured_at=self.measured_at,
            brier=self.brier,
            ece=self.ece,
            assessor=self.assessor,
            judge_identity=self.judge_identity,
            starter_corpus=self.starter_corpus,
            positives=self.positives,
            negatives=self.negatives,
            positives_inconclusive=self.positives_inconclusive,
            negatives_inconclusive=self.negatives_inconclusive,
            sensitivity=self.sensitivity,
            specificity=self.specificity,
        )


def corpus_digest(path: Path) -> str:
    """Digest the corpus a measurement was taken on.

    Recorded beside the numbers because a Brier score describes a judge *against a
    particular set*. Without it a reader cannot ask the one question that decides
    whether the number transfers: was it measured on anything resembling the traffic
    being graded here.
    """
    return digest_of(path.read_text(encoding="utf-8"))


def load_calibrations(path: Path) -> dict[str, RecordedCalibration]:
    """Read a calibration file, keyed by evaluator id, failing loudly on anything odd.

    Loudly rather than skipping: a measurement quietly dropped leaves a run claiming
    an uncalibrated judge where the operator believes one was measured, which is the
    direction that matters.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CalibrationStoreError(f"could not read calibrations {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CalibrationStoreError(f"{path} must be a JSON object")
    version = raw.get("schema_version")
    if isinstance(version, bool) or version not in _KEYS:
        raise CalibrationStoreError(
            f"{path} declares schema_version {version!r}; this build reads "
            f"{', '.join(str(v) for v in sorted(_KEYS))}. A file this build cannot read is "
            f"not a file it may read optimistically"
        )
    entries = raw.get("calibrations")
    if not isinstance(entries, list):
        raise CalibrationStoreError(f"{path} needs a 'calibrations' list")
    return {entry.evaluator: entry for entry in (_entry(e, path, version) for e in entries)}


def write_calibrations(path: Path, measurements: dict[str, RecordedCalibration]) -> None:
    """Write the file, ordered by evaluator id so a re-record produces a readable diff."""
    document = {
        "schema_version": STORE_SCHEMA_VERSION,
        "calibrations": [
            {
                "evaluator": entry.evaluator,
                "dataset_digest": entry.dataset_digest,
                "measured_at": entry.measured_at.astimezone(UTC).isoformat(),
                "brier": entry.brier,
                "ece": entry.ece,
                "samples": entry.samples,
                "assessor": entry.assessor,
                "judge_identity": entry.judge_identity,
                "starter_corpus": entry.starter_corpus,
                "positives": entry.positives,
                "negatives": entry.negatives,
                "positives_inconclusive": entry.positives_inconclusive,
                "negatives_inconclusive": entry.negatives_inconclusive,
                "sensitivity": entry.sensitivity,
                "specificity": entry.specificity,
            }
            for entry in sorted(measurements.values(), key=lambda e: e.evaluator)
        ],
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _entry(raw: object, path: Path, version: int) -> RecordedCalibration:
    if not isinstance(raw, dict):
        raise CalibrationStoreError(f"{path} has a calibration that is not an object")
    unknown = sorted(set(raw) - _KEYS[version])
    if unknown:
        raise CalibrationStoreError(f"{path} has unknown calibration key(s): {', '.join(unknown)}")
    evaluator = raw.get("evaluator")
    digest = raw.get("dataset_digest")
    if not isinstance(evaluator, str) or not isinstance(digest, str):
        raise CalibrationStoreError(
            f"{path} needs a string 'evaluator' and 'dataset_digest' on every calibration"
        )
    entry = RecordedCalibration(
        evaluator=evaluator,
        dataset_digest=digest,
        measured_at=_when(raw.get("measured_at"), path),
        brier=_number(raw.get("brier")),
        ece=_number(raw.get("ece")),
        samples=int(raw.get("samples") or 0),
    )
    if version == 1:
        return entry
    missing = sorted(_V2_KEYS - set(raw))
    if missing:
        raise CalibrationStoreError(
            f"{path} has a calibration for {evaluator} missing {', '.join(missing)}; null "
            f"says a value was not recorded"
        )
    return _per_class(entry, raw, path)


def _per_class(
    entry: RecordedCalibration, raw: dict[str, object], path: Path
) -> RecordedCalibration:
    """Read the schema-2 fields, refusing counts and rates that contradict each other.

    The assessor and the four counts are recorded together or not at all: an entry carried
    over from schema 1 has none, and a partial set is a file somebody edited into a state no
    measurement produced. A rate is stated exactly when its class had a graded sample.
    """
    where = f"{path} ({entry.evaluator})"
    identity = raw["judge_identity"]
    starter = raw["starter_corpus"]
    if identity is not None and not isinstance(identity, str):
        raise CalibrationStoreError(f"{where}: 'judge_identity' must be a string or null")
    if starter is not None and not isinstance(starter, bool):
        raise CalibrationStoreError(f"{where}: 'starter_corpus' must be true, false or null")
    recorded = [key for key in _PER_CLASS if raw[key] is not None]
    if not recorded:
        stated = [key for key in _RATES if raw[key] is not None]
        if stated:
            raise CalibrationStoreError(f"{where} states {', '.join(stated)} without its counts")
        return replace(entry, judge_identity=identity, starter_corpus=starter)
    if len(recorded) != len(_PER_CLASS):
        raise CalibrationStoreError(
            f"{where} records {', '.join(recorded)} without "
            f"{', '.join(k for k in _PER_CLASS if k not in recorded)}"
        )
    assessor = raw["assessor"]
    if not isinstance(assessor, str) or not assessor:
        raise CalibrationStoreError(f"{where}: 'assessor' must be a non-empty string")
    counts = {key: _count(raw[key], key, where) for key in _COUNTS}
    rates = {
        key: _rate(raw[key], key, counts[graded], where)
        for key, graded in (("sensitivity", "positives"), ("specificity", "negatives"))
    }
    if counts["positives"] + counts["negatives"] != entry.samples:
        raise CalibrationStoreError(
            f"{where}: {counts['positives']} positives and {counts['negatives']} negatives "
            f"do not add up to {entry.samples} samples"
        )
    return replace(
        entry,
        assessor=assessor,
        judge_identity=identity,
        starter_corpus=starter,
        positives=counts["positives"],
        negatives=counts["negatives"],
        positives_inconclusive=counts["positives_inconclusive"],
        negatives_inconclusive=counts["negatives_inconclusive"],
        sensitivity=rates["sensitivity"],
        specificity=rates["specificity"],
    )


def _count(value: object, key: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CalibrationStoreError(f"{where}: '{key}' must be a whole number of at least 0")
    return value


def _rate(value: object, key: str, graded: int, where: str) -> float | None:
    if graded == 0:
        if value is not None:
            raise CalibrationStoreError(f"{where}: '{key}' is stated over a class nothing graded")
        return None
    if value is None:
        raise CalibrationStoreError(f"{where}: '{key}' is missing over {graded} graded samples")
    return _share(value, key, where)


def _share(value: object, key: str, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
        raise CalibrationStoreError(f"{where}: '{key}' must be a number between 0 and 1")
    return float(value)


def _when(value: object, path: Path) -> datetime:
    if not isinstance(value, str):
        raise CalibrationStoreError(
            f"{path} needs a 'measured_at' timestamp — a calibration with no date "
            f"describes a judge model that may since have been replaced under the "
            f"same name"
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CalibrationStoreError(f"{path} has an unreadable 'measured_at': {value!r}") from exc


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None
