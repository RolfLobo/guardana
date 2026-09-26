"""The setup gate: the agent instructions still describe this repository.

The positive case runs against the real tree. Every other case builds a small
broken tree and expects the gate to name the drift — a gate that only ever says
"in sync" has never been shown to notice anything.
"""

import json
import subprocess
from pathlib import Path

import pytest

import check_claude_setup

SKILL = "---\nname: {name}\ndescription: Does a thing.\n---\n# Body\n"
AGENT = "---\nname: {name}\ndescription: Looks things up.\nmodel: {model}\n---\nBody.\n"


def _tree(root: Path, *, claude_md: str = "# Guardana\n") -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)  # noqa: S603, S607
    (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (root / ".claude" / "skills" / "work").mkdir(parents=True)
    (root / ".claude" / "skills" / "work" / "SKILL.md").write_text(
        SKILL.format(name="work"), encoding="utf-8"
    )
    (root / ".claude" / "agents").mkdir()
    (root / ".claude" / "agents" / "scout.md").write_text(
        AGENT.format(name="scout", model="haiku"), encoding="utf-8"
    )
    (root / ".claude" / "rules").mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "x.py").write_text("", encoding="utf-8")
    (root / ".claude" / "rules" / "scripts.md").write_text(
        '---\npaths:\n  - "scripts/**"\n---\n# Scripts\n', encoding="utf-8"
    )


def _problems(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], root: Path
) -> str:
    monkeypatch.setattr(check_claude_setup, "ROOT", root)
    assert check_claude_setup.main() == 1
    return capsys.readouterr().out


def test_the_real_setup_is_in_sync(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_claude_setup.main() == 0
    assert "agent setup in sync" in capsys.readouterr().out


def test_a_clean_tree_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    monkeypatch.setattr(check_claude_setup, "ROOT", tmp_path)
    assert check_claude_setup.main() == 0
    assert "in sync" in capsys.readouterr().out


def test_a_rule_without_paths_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "rules" / "always.md").write_text(
        "---\ndescription: x\n---\n# Always\n", encoding="utf-8"
    )
    assert "always.md: a rule without `paths`" in _problems(monkeypatch, capsys, tmp_path)


def test_a_glob_that_matches_nothing_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "rules" / "gone.md").write_text(
        '---\npaths:\n  - "apps/{api,ui}/**"\n---\n# Gone\n', encoding="utf-8"
    )
    assert "glob matches no file: apps/{api,ui}/**" in _problems(monkeypatch, capsys, tmp_path)


def test_a_quoted_path_that_does_not_exist_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, claude_md="# Guardana\n\nRead `docs/nowhere.md` and `scripts/x.py`.\n")
    out = _problems(monkeypatch, capsys, tmp_path)
    assert "CLAUDE.md: points at a path that does not exist: docs/nowhere.md" in out
    assert "scripts/x.py" not in out


def test_placeholders_are_not_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, claude_md="# G\n\n`docs/usage-<command>.md`, `packages/*/tests/**`, `docs/…`\n")
    monkeypatch.setattr(check_claude_setup, "ROOT", tmp_path)
    assert check_claude_setup.main() == 0


def test_the_line_budget_is_enforced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path, claude_md="# Guardana\n" * (check_claude_setup.CLAUDE_MD_MAX_LINES + 1))
    assert "CLAUDE.md is 151 lines (budget 150)" in _problems(monkeypatch, capsys, tmp_path)


def test_an_agent_on_the_forbidden_model_family_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "agents" / "big.md").write_text(
        AGENT.format(name="big", model="fab" + "le"), encoding="utf-8"
    )
    out = _problems(monkeypatch, capsys, tmp_path)
    assert "big.md: this model family is never configured" in out


def test_a_skill_whose_name_disagrees_with_its_directory_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "skills" / "ship").mkdir()
    (tmp_path / ".claude" / "skills" / "ship" / "SKILL.md").write_text(
        SKILL.format(name="shipit"), encoding="utf-8"
    )
    assert "`name` is 'shipit', the file says 'ship'" in _problems(monkeypatch, capsys, tmp_path)


def test_a_skill_that_runs_as_a_missing_agent_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "skills" / "review").mkdir()
    (tmp_path / ".claude" / "skills" / "review" / "SKILL.md").write_text(
        "---\nname: review\ndescription: Reviews.\ncontext: fork\nagent: judge\n---\nBody.\n",
        encoding="utf-8",
    )
    assert "runs as agent 'judge', which does not exist" in _problems(monkeypatch, capsys, tmp_path)


def test_frontmatter_that_does_not_parse_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "agents" / "broken.md").write_text(
        "---\nname: broken\ndescription: has: a colon: in it [and\n---\n", encoding="utf-8"
    )
    assert "broken.md: frontmatter does not parse" in _problems(monkeypatch, capsys, tmp_path)


def test_a_hook_pointing_at_a_missing_script_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "${CLAUDE_PROJECT_DIR:-.}/scripts/gone_hook.py"',
                        }
                    ],
                }
            ]
        }
    }
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    assert "hook points at a missing file: scripts/gone_hook.py" in _problems(
        monkeypatch, capsys, tmp_path
    )


def test_a_missing_settings_file_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "settings.json").unlink()
    assert ".claude/settings.json is missing" in _problems(monkeypatch, capsys, tmp_path)


def test_an_empty_kind_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".claude" / "rules" / "scripts.md").unlink()
    assert "no rule matches .claude/rules/*.md" in _problems(monkeypatch, capsys, tmp_path)


def test_a_gitignored_file_under_claude_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A skill directory named like a build artifact vanished this way once, unseen by git."""
    _tree(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / ".claude" / "skills" / "build").mkdir()
    (tmp_path / ".claude" / "skills" / "build" / "SKILL.md").write_text(
        SKILL.format(name="build"), encoding="utf-8"
    )
    out = _problems(monkeypatch, capsys, tmp_path)
    assert ".claude/skills/build/SKILL.md: gitignored" in out


def test_the_harness_local_files_are_not_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A live session's lock, local settings or worktree must not turn the gate red."""
    _tree(tmp_path)
    (tmp_path / ".gitignore").write_text(
        ".claude/scheduled_tasks.lock\n.claude/settings.local.json\n.claude/worktrees/\n",
        encoding="utf-8",
    )
    (tmp_path / ".claude" / "scheduled_tasks.lock").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude" / "worktrees" / "lane").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "lane" / "x.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(check_claude_setup, "ROOT", tmp_path)
    assert check_claude_setup.main() == 0
    assert "in sync" in capsys.readouterr().out


def test_a_file_named_like_a_harness_file_elsewhere_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "*.lock\nworktrees/\nworktrees2/\n*.orig\n", encoding="utf-8"
    )
    (tmp_path / ".claude" / "scheduled_tasks.lock").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude" / "settings.local.json.orig").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude" / "worktrees2").mkdir()
    (tmp_path / ".claude" / "worktrees2" / "x").write_text("", encoding="utf-8")
    (tmp_path / ".claude" / "skills" / "work" / "scheduled_tasks.lock").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / ".claude" / "skills" / "worktrees").mkdir()
    (tmp_path / ".claude" / "skills" / "worktrees" / "SKILL.md").write_text(
        SKILL.format(name="worktrees"), encoding="utf-8"
    )
    out = _problems(monkeypatch, capsys, tmp_path)
    assert ".claude/skills/work/scheduled_tasks.lock: gitignored" in out
    assert ".claude/skills/worktrees/SKILL.md: gitignored" in out
    assert ".claude/settings.local.json.orig: gitignored" in out
    assert ".claude/worktrees2/x: gitignored" in out
    assert ".claude/scheduled_tasks.lock:" not in out


def test_a_path_git_would_quote_is_matched_unquoted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _tree(tmp_path)
    (tmp_path / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    (tmp_path / ".claude" / "worktrees").mkdir()
    (tmp_path / ".claude" / "worktrees" / "\u00e9.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(check_claude_setup, "ROOT", tmp_path)
    assert check_claude_setup.main() == 0
    assert "in sync" in capsys.readouterr().out
