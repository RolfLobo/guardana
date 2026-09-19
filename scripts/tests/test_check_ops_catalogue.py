"""The ops catalogue gate: every script has one row, every row has a script."""

from pathlib import Path

import pytest

import check_ops_catalogue

HEADER = "# Operations catalogue\n\n## Scripts — `scripts/`\n\n| script | purpose |\n|---|---|\n"


def _tree(root: Path, rows: list[str], scripts: list[str]) -> None:
    (root / "scripts").mkdir()
    for name in scripts:
        (root / "scripts" / name).write_text("", encoding="utf-8")
    (root / "docs" / "maintainers").mkdir(parents=True)
    body = HEADER + "".join(f"| `{row}` | does a thing |\n" for row in rows)
    (root / "docs" / "maintainers" / "ops-catalogue.md").write_text(body, encoding="utf-8")


def _run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], root: Path
) -> tuple[int, str]:
    monkeypatch.setattr(check_ops_catalogue, "ROOT", root)
    monkeypatch.setattr(
        check_ops_catalogue, "CATALOGUE", root / "docs" / "maintainers" / "ops-catalogue.md"
    )
    monkeypatch.setattr(
        check_ops_catalogue, "SECTIONS", {"## Scripts": (root / "scripts", ("*.py", "*.sh"))}
    )
    code = check_ops_catalogue.main()
    return code, capsys.readouterr().out


def test_the_real_catalogue_is_in_sync(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_ops_catalogue.main() == 0
    assert "ops catalogue in sync" in capsys.readouterr().out


def test_a_matching_tree_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, rows=["a.py", "b.sh"], scripts=["a.py", "b.sh"])
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 0
    assert "in sync: 2 scripts" in out


def test_a_script_without_a_row_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, rows=["a.py"], scripts=["a.py", "new.py"])
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "no row for scripts/new.py" in out


def test_a_row_without_a_script_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, rows=["a.py", "gone.py"], scripts=["a.py"])
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "row without a script: scripts/gone.py" in out


def test_a_duplicate_row_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, rows=["a.py", "a.py"], scripts=["a.py"])
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "duplicate row: scripts/a.py" in out


def test_rows_outside_the_scripts_section_do_not_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, rows=["a.py"], scripts=["a.py"])
    catalogue = tmp_path / "docs" / "maintainers" / "ops-catalogue.md"
    extra = "\n## For decision\n\n| `other.py` | not a script |\n"
    catalogue.write_text(catalogue.read_text(encoding="utf-8") + extra, encoding="utf-8")
    code, _ = _run(monkeypatch, capsys, tmp_path)
    assert code == 0
