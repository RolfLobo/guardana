"""The one door to GPT and Gemini: it routes, it refuses, it never writes the text itself.

No engine is called here. What is pinned is the routing — which engine answers which
request, what happens when none is installed, that `both` writes two files — and the
refusals that keep the door honest: a non-Gemini model through the Gemini door, an
answer that is not JSON when a schema was given.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import text_model


def _argv(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["text_model.py", *args])


def test_detect_reports_installed_engines_and_exits_3_when_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(text_model, "_available", lambda: {"gpt": None, "gemini": None})
    _argv(monkeypatch, "--detect")
    assert text_model.main() == 3
    assert json.loads(capsys.readouterr().out) == {"gpt": None, "gemini": None}


def test_engine_selection() -> None:
    both: dict[str, str | None] = {"gpt": "/bin/codex", "gemini": "/bin/agy"}
    assert text_model._engines("both", both) == ["gpt", "gemini"]
    assert text_model._engines("auto", both) == ["gpt"]
    assert text_model._engines("auto", {"gpt": None, "gemini": "/bin/agy"}) == ["gemini"]
    assert text_model._engines("auto", {"gpt": None, "gemini": None}) == []
    assert text_model._engines("gemini", both) == ["gemini"]


def test_a_missing_engine_stops_instead_of_writing_the_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("Rewrite.", encoding="utf-8")
    monkeypatch.setattr(text_model, "_available", lambda: {"gpt": None, "gemini": None})
    _argv(monkeypatch, "--prompt", str(prompt), "--out", str(tmp_path / "out.md"))
    assert text_model.main() == 3
    assert "Do not write this text yourself" in capsys.readouterr().err
    assert not (tmp_path / "out.md").exists()


def test_inputs_are_appended_as_named_files(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("Task.\n", encoding="utf-8")
    page = tmp_path / "page.md"
    page.write_text("# Page\n", encoding="utf-8")
    text = text_model._assemble(prompt, [page])
    assert text == 'Task.\n\n<file name="page.md">\n# Page\n</file>\n'


def test_both_writes_one_file_per_engine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("Task.", encoding="utf-8")
    calls: list[str] = []

    def _fake(name: str) -> Callable[[str, Path, Path | None, str], None]:
        def run(text: str, out: Path, schema: Path | None, effort: str) -> None:
            calls.append(f"{name}:{effort}")
            out.write_text(json.dumps({"engine": name}), encoding="utf-8")

        return run

    monkeypatch.setattr(text_model, "_available", lambda: {"gpt": "/c", "gemini": "/a"})
    monkeypatch.setattr(text_model, "RUNNERS", {"gpt": _fake("gpt"), "gemini": _fake("gemini")})
    schema = tmp_path / "s.json"
    schema.write_text("{}", encoding="utf-8")
    out = tmp_path / "out.json"
    _argv(
        monkeypatch,
        "--prompt",
        str(prompt),
        "--out",
        str(out),
        "--engine",
        "both",
        "--schema",
        str(schema),
        "--effort",
        "high",
    )
    assert text_model.main() == 0
    assert calls == ["gpt:high", "gemini:high"]
    assert (tmp_path / "out.gpt.json").exists()
    assert (tmp_path / "out.gemini.json").exists()
    assert "gpt: " in capsys.readouterr().out


def test_a_failing_engine_is_reported_and_exits_4(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("Task.", encoding="utf-8")

    def boom(text: str, out: Path, schema: Path | None, effort: str) -> None:
        raise RuntimeError("codex exited 1: quota")

    monkeypatch.setattr(text_model, "_available", lambda: {"gpt": "/c", "gemini": None})
    monkeypatch.setattr(text_model, "RUNNERS", {"gpt": boom, "gemini": boom})
    _argv(monkeypatch, "--prompt", str(prompt), "--out", str(tmp_path / "o.md"))
    assert text_model.main() == 4
    assert "gpt: FAILED — codex exited 1: quota" in capsys.readouterr().err


def test_the_gemini_door_refuses_other_vendors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEXT_MODEL_GEMINI", "gpt-oss-120b-medium")
    with pytest.raises(RuntimeError, match="must be a gemini-\\* model"):
        text_model._run_gemini("x", tmp_path / "o.md", None, "medium")


def test_an_answer_that_is_not_json_fails_when_a_schema_was_given(tmp_path: Path) -> None:
    out = tmp_path / "o.json"
    out.write_text("Sure! Here is the JSON you asked for: {", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        text_model._check_json(out)
