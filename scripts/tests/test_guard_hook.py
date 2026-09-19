"""The PreToolUse guard: the repository rules a prompt cannot be trusted to hold.

Each row is one command an agent might type and the decision the guard must print.
The negative rows matter as much as the positive ones: a guard that denies
`git add scripts/x.py` is a guard people disable.
"""

import contextlib
import io
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

import guard_hook

# Assembled at run time so this file does not carry the id it exists to refuse.
FORBIDDEN_ID = "claude-" + "fab" + "le-5-1"


def _decision(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool: str,
    tool_input: Mapping[str, object],
) -> str | None:
    payload = {"tool_name": tool, "tool_input": tool_input}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    with contextlib.suppress(SystemExit):
        guard_hook.main()
    out = capsys.readouterr().out
    if not out:
        return None
    decision: str = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    return decision


@pytest.fixture(autouse=True)
def _no_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Branch lookups say `main`; the site checks pass unless a test says otherwise."""

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, "main\n", "")
        return subprocess.CompletedProcess(cmd, 0, "current\n", "")

    monkeypatch.setattr(guard_hook, "_run", _run)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git add -A", "deny"),
        ("git add --all", "deny"),
        ("git add .", "deny"),
        ("git add -u", "deny"),
        ("git add scripts/guard_hook.py docs/work/README.md", None),
        ("git add .env", "deny"),
        ("git add deploy/.env.production", "deny"),
        ("git add deploy/env.example", None),
        ('git commit -am "fix: x"', "deny"),
        ('git commit --all -m "fix: x"', "deny"),
        ('git commit -m "feat: x" -m "Co-Authored-By: Someone <x@y>"', "deny"),
        ('git commit -m "docs: generated with a tool"', "deny"),
        ('git commit -m "feat(cli): add --target-option"', None),
        ("git push --force origin main", "ask"),
        ("git push -f origin main", "ask"),
        ("git push origin v0.25.0", "ask"),
        ("git push origin --tags", "ask"),
        ("git push origin feature/x", None),
        ("git push origin main", None),
        ("git push", None),
        ("cat .env", "deny"),
        ("head -5 deploy/.env", "deny"),
        ("cat deploy/env.example", None),
        ('claude -p "summarise this"', "ask"),
        ("codex exec --sandbox read-only -", "ask"),
        ("agy --print='hello' --model gemini-3.1-pro-high", "ask"),
        ("uv run python scripts/release.py patch", "ask"),
        ("uv run python scripts/release.py patch --dry-run", None),
        ("gh run cancel 12345", "ask"),
        ("gh release create v0.25.0", "ask"),
        ("gh run list --limit 3", None),
        ("uv run pytest packages/guardana-core/tests -q", None),
        (f"uv run something --model {FORBIDDEN_ID}", "deny"),
        ("scripts/ci_local.sh --quiet", None),
    ],
)
def test_bash_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    expected: str | None,
) -> None:
    assert _decision(monkeypatch, capsys, "Bash", {"command": command}) == expected


def test_a_push_to_main_is_refused_while_the_site_is_stale(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, "main\n", "")
        if "build_site.py" in cmd[3]:
            return subprocess.CompletedProcess(cmd, 1, "site/docs is stale (3 files)\n", "")
        return subprocess.CompletedProcess(cmd, 0, "current\n", "")

    monkeypatch.setattr(guard_hook, "_run", _run)
    assert _decision(monkeypatch, capsys, "Bash", {"command": "git push origin main"}) == "deny"


def test_a_push_to_main_asks_when_the_site_cannot_be_checked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, "main\n", "")
        raise OSError("uv: command not found")

    monkeypatch.setattr(guard_hook, "_run", _run)
    assert _decision(monkeypatch, capsys, "Bash", {"command": "git push"}) == "ask"


def test_a_push_from_a_feature_branch_does_not_run_the_site_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "feature/x\n", "")

    monkeypatch.setattr(guard_hook, "_run", _run)
    assert _decision(monkeypatch, capsys, "Bash", {"command": "git push"}) is None
    assert all(cmd[:2] == ["git", "rev-parse"] for cmd in calls)


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        ("packages/guardana-cli/src/guardana/cli/x.py", f'MODEL = "{FORBIDDEN_ID}"', "deny"),
        (".claude/agents/coder.md", f"model: {FORBIDDEN_ID}", "deny"),
        ("scripts/guard_hook.py", f"pattern = '{FORBIDDEN_ID}'", None),
        (str(Path.cwd() / "scripts" / "check_claude_setup.py"), f"alias = '{FORBIDDEN_ID}'", None),
        ("examples/evil/guard_hook.py", f"pattern = '{FORBIDDEN_ID}'", "deny"),
        ("docs/usage-scan.md", "guardana scan . --format sarif", None),
    ],
)
def test_written_files(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path: str,
    content: str,
    expected: str | None,
) -> None:
    tool_input = {"file_path": path, "content": content}
    assert _decision(monkeypatch, capsys, "Write", tool_input) == expected


def test_an_edit_is_checked_on_its_new_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool_input = {"file_path": "README.md", "old_string": "x", "new_string": FORBIDDEN_ID}
    assert _decision(monkeypatch, capsys, "Edit", tool_input) == "deny"


def test_a_multi_edit_and_a_notebook_edit_are_checked_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    edits = {"file_path": "x.py", "edits": [{"old_string": "a", "new_string": FORBIDDEN_ID}]}
    assert _decision(monkeypatch, capsys, "MultiEdit", edits) == "deny"
    cell = {"notebook_path": "n.ipynb", "new_source": f"model = '{FORBIDDEN_ID}'"}
    assert _decision(monkeypatch, capsys, "NotebookEdit", cell) == "deny"


def test_a_broken_payload_never_blocks_work() -> None:
    """The guard runs as a subprocess in the harness; an internal error must exit 0 silently."""
    hook = Path(__file__).resolve().parents[1] / "guard_hook.py"
    done = subprocess.run(  # noqa: S603 — the interpreter and a checked-in script
        [sys.executable, str(hook)], input="not json", capture_output=True, text=True, check=False
    )
    assert done.returncode == 0
    assert done.stdout == ""
