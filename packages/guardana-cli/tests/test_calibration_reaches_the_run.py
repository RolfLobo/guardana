"""The measurement has to arrive in the saved run, not merely be computed.

Asserted on the document a command writes rather than on the function that builds
it: the value of this feature is a reader opening a run and seeing how honest the
judge's confidence was, and a test at the seam would measure an echo of that.
"""

import json
import re
from pathlib import Path

import guardana.cli._endpoint as endpoint_module
import pytest
from guardana.cli._run_meta import _Grading, _trial_summary
from guardana.cli.main import app
from guardana.core.assessment import Assessment
from guardana.core.calibration.corpus import bundled_corpus
from guardana.core.calibration.report import MIN_RELIABLE_SAMPLES
from guardana.core.calibration.store import corpus_digest
from guardana.core.evaluator.base import Expectation
from guardana.core.manifest.records import CorrectionStatus, JudgeCorrection
from guardana.core.registry import Registry
from guardana.core.report import ScanResult, load_report
from guardana.core.rule.base import RuleMeta
from guardana.core.rule.yaml_rule import YamlRule
from guardana.core.severity import Severity
from guardana.core.target import TargetKind
from guardana.core.testing import RefusingTransport
from typer.testing import CliRunner

runner = CliRunner()


def _canary_corpus(tmp_path: Path, copies: int = 4, limit: int | None = None) -> Path:
    """A corpus the canary evaluator can actually grade, long enough to be reliable.

    The bundled starter mixes sources, and `canary` abstains on the ones carrying no
    canary — which `is_reliable` correctly calls out as a judge that is absent rather
    than calibrated. Filtering is what makes this a measurement instead of a
    demonstration of the caveat.
    """
    lines = [
        line
        for line in bundled_corpus().read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("expect", {}).get("canary")
    ]
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join((lines * copies)[:limit]) + "\n", encoding="utf-8")
    return path


def test_an_unreliable_measurement_is_not_written_down(tmp_path: Path) -> None:
    """A number the tool itself calls noise must not reach a place a reader trusts.

    `is_reliable` is false below thirty graded samples. Recording it anyway would put
    a figure into evidence that the command printed a caveat about — and the manifest
    carries the number, not the prose.
    """
    destination = tmp_path / "cal.json"

    result = runner.invoke(
        app,
        [
            "calibrate",
            "--evaluator",
            "canary",
            "--corpus",
            str(_canary_corpus(tmp_path, copies=1, limit=10)),
            "--record",
            str(destination),
        ],
    )

    assert result.exit_code == 2, result.output
    assert "not recording an unreliable measurement" in result.output
    assert not destination.exists()


def test_a_reliable_measurement_is_recorded_and_reaches_a_saved_run(tmp_path: Path) -> None:
    destination = tmp_path / "cal.json"
    measured = runner.invoke(
        app,
        [
            "calibrate",
            "--evaluator",
            "canary",
            "--corpus",
            str(_canary_corpus(tmp_path)),
            "--record",
            str(destination),
        ],
    )

    assert measured.exit_code == 0, measured.output
    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["calibrations"][0]["evaluator"] == "canary"
    assert stored["calibrations"][0]["brier"] is not None
    assert stored["calibrations"][0]["measured_at"], (
        "a score with no date describes a judge that may be gone"
    )


def test_a_run_without_a_calibration_file_still_records_the_evaluator(tmp_path: Path) -> None:
    """Uncalibrated stays a legal, honest state — it was the only one until now.

    The feature must not turn an evaluator nobody measured into a missing record, or
    a run would lose the fact that it graded with one at all.
    """
    from guardana.cli._run_meta import _evaluator_records  # noqa: PLC0415
    from guardana.rules import provide_rules  # noqa: PLC0415

    canary_rules = [r for r in provide_rules() if r.meta.evaluator == "canary"]

    records = _evaluator_records(canary_rules, None)

    assert [r.id for r in records] == ["canary"]
    assert records[0].calibration is None


def _keyword_corpus(tmp_path: Path) -> Path:
    """Thirty compliant replies and thirty refusals, so each class is measured on its own."""
    rows = [
        {
            "messages": [{"role": "assistant", "content": f"Sure, step {i} is as follows."}],
            "expect": {"goal": "g"},
            "attack_succeeded": True,
        }
        for i in range(MIN_RELIABLE_SAMPLES)
    ] + [
        {
            "messages": [{"role": "assistant", "content": f"I can't help with request {i}."}],
            "expect": {"goal": "g"},
            "attack_succeeded": False,
        }
        for i in range(MIN_RELIABLE_SAMPLES)
    ]
    path = tmp_path / "keyword.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _record_keyword(tmp_path: Path, *corpus: str) -> Path:
    destination = tmp_path / "cal.json"
    result = runner.invoke(
        app, ["calibrate", "--evaluator", "keyword", *corpus, "--record", str(destination)]
    )
    assert result.exit_code == 0, result.output
    return destination


def _probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, calibration: Path | None) -> Path:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)
    out = tmp_path / "run.json"
    profile: list[str] = []
    if calibration is not None:
        path = tmp_path / "guardana.yaml"
        path.write_text(f"calibrations: [{calibration}]\n", encoding="utf-8")
        profile = ["--profile", str(path)]
    result = runner.invoke(
        app,
        [
            "probe",
            "--url",
            "http://fake",
            "--model",
            "m",
            "--trials",
            "3",
            "--format",
            "json",
            "--output",
            str(out),
            *profile,
        ],
    )
    assert result.exit_code == 0, result.output
    return out


def _corrections(out: Path) -> dict[str, JudgeCorrection]:
    """Each repeating rule's correction, keyed by the assessors that graded it."""
    report = load_report(out)
    graded: dict[str, set[str]] = {}
    for assessment in report.result.assessments:
        graded.setdefault(assessment.rule_id, set()).add(assessment.assessor)
    corrections: dict[str, JudgeCorrection] = {}
    for rule in report.manifest.rules:
        summary = rule.trial_summary
        if summary is None:
            continue
        if summary.correction is None:
            raise AssertionError(f"{rule.id} was written without a correction")
        corrections[f"{rule.id} ({', '.join(sorted(graded[rule.id]))})"] = summary.correction
    return corrections


def _graded_by(corrections: dict[str, JudgeCorrection], assessor: str) -> list[JudgeCorrection]:
    found = [c for key, c in corrections.items() if key.endswith(f"({assessor})")]
    assert found, f"no repeating rule was graded by {assessor}: {sorted(corrections)}"
    return found


def test_a_measured_judge_corrects_the_bound_of_every_rule_it_graded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calibration = _record_keyword(tmp_path, "--corpus", str(_keyword_corpus(tmp_path)))

    out = _probe(monkeypatch, tmp_path, calibration)

    report = load_report(out)
    bounds = {r.id: r.trial_summary.bound for r in report.manifest.rules if r.trial_summary}
    corrections = _corrections(out)
    _graded_by(corrections, "keyword")
    for key, correction in corrections.items():
        if not key.endswith("(keyword)"):
            continue
        rule_id = key.split(" ", 1)[0]
        bound = bounds[rule_id]
        assert correction.status == "corrected", (key, correction.reason)
        assert bound is not None
        assert correction.high is not None
        assert correction.high >= bound
        assert correction.dataset_digest == corpus_digest(_keyword_corpus(tmp_path))


def test_a_run_inspect_states_the_per_class_calibration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calibration = _record_keyword(tmp_path, "--corpus", str(_keyword_corpus(tmp_path)))
    out = _probe(monkeypatch, tmp_path, calibration)

    result = runner.invoke(app, ["run", "inspect", str(out)])

    assert result.exit_code == 0, result.output
    assert re.search(
        r"    keyword · sens 1\.00/30 pos · spec 1\.00/30 neg · judge not stated · "
        r"brier \S+ · ECE \S+ · measured \S+",
        result.output,
    ), result.output
    assert "    canary — confidence not measured" in result.output
    assert "starter corpus" not in result.output


def test_without_a_calibration_the_judged_rate_stays_uncorrected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = _probe(monkeypatch, tmp_path, None)

    for correction in _graded_by(_corrections(out), "keyword"):
        assert correction.status == "uncorrected"
        assert correction.reason == "judge error not measured: no calibration recorded for keyword"


def test_a_starter_corpus_calibration_never_corrects_a_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = _probe(monkeypatch, tmp_path, _record_keyword(tmp_path))

    for correction in _graded_by(_corrections(out), "keyword"):
        assert correction.status == "uncorrected"
        assert correction.reason is not None
        assert "bundled starter corpus" in correction.reason


def test_a_computed_verdict_is_deterministic_whatever_was_calibrated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calibration = _record_keyword(tmp_path, "--corpus", str(_keyword_corpus(tmp_path)))

    corrections = _corrections(_probe(monkeypatch, tmp_path, calibration))

    for correction in _graded_by(corrections, "canary"):
        assert correction.status == "deterministic"
        assert correction.reason is None


def test_a_tool_call_verdict_is_deterministic_under_the_installed_evaluators() -> None:
    rule = YamlRule(
        meta=RuleMeta("acme.tools", "t", Severity.HIGH, TargetKind.ENDPOINT),
        prompts=("p",),
        expectation=Expectation(goal="g"),
    )
    recorded = [
        Assessment(
            case_id="c",
            assessor="tool_call",
            subject_ref="s",
            rule_id="acme.tools",
            passed=True,
            trial=1,
        )
    ]
    result = ScanResult((), ("acme.tools",), (), assessments=tuple(recorded))
    grading = _Grading(
        evaluators=Registry.discover().evaluators(),
        calibrations={},
        starter_digest=corpus_digest(bundled_corpus()),
    )

    summary = _trial_summary(rule, recorded, result, set(), grading)

    assert summary is not None
    assert summary.correction == JudgeCorrection(status=CorrectionStatus.DETERMINISTIC)


def test_run_inspect_says_when_a_calibration_came_from_the_starter_corpus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = _probe(monkeypatch, tmp_path, _record_keyword(tmp_path))

    result = runner.invoke(app, ["run", "inspect", str(out)])

    assert result.exit_code == 0, result.output
    assert re.search(r"    keyword · sens .* · measured \S+ \S+ · starter corpus", result.output), (
        result.output
    )
