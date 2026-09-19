#!/usr/bin/env python3
"""PreToolUse guard: the repository rules a prompt cannot be trusted to hold.

Reads the hook payload on stdin and prints a permission decision (`deny` or
`ask`) with its reason, or nothing at all, which leaves the normal permission
flow alone. Any internal error exits 0 silently: a broken guard must never
block work.

Wired in `.claude/settings.json`; the case table lives in
`scripts/tests/test_guard_hook.py`.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Spelled in two halves so this file does not trip its own rule.
FORBIDDEN_MODEL = re.compile(
    r"claude-(?:fab" + r"le|myth" + r"os)|--model[= ]+(?:fab" + r"le|myth" + r"os)\b", re.IGNORECASE
)
ENV_FILE = r"(?<![\w.-])\.env(?!\.example)[\w.-]*"
ATTRIBUTION = re.compile(r"co-authored-by|generated with|claude\.ai/code|\U0001F916", re.IGNORECASE)
TAG_PUSH = re.compile(r"\bgit\s+push\b[^|;&]*(?:--tags\b|refs/tags/|\bv\d+\.\d+)")
# A push to `main` deploys guardana.dev straight from the tree, before CI has run.
SITE_CHECKS = ("generate_docs.py", "sync_site.py", "build_site.py", "generate_llms_txt.py")
SELF_EXEMPT = frozenset(
    {"scripts/guard_hook.py", "scripts/check_claude_setup.py", "scripts/tests/test_guard_hook.py"}
)


def decide(decision: str, reason: str) -> None:
    """Print the hook's decision and stop."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    # S603: every command here is a fixed literal (git / uv), never user input.
    return subprocess.run(  # noqa: S603
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )


def _site_in_sync() -> None:
    """Refuse to deploy a site that is stale relative to the docs and the registry."""
    for script in SITE_CHECKS:
        try:
            done = _run(["uv", "run", "python", f"scripts/{script}", "--check"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            decide("ask", f"A push to main deploys guardana.dev. Could not run {script} ({exc}).")
        if done.returncode != 0:
            out = (done.stdout + done.stderr).strip()[-600:]
            decide(
                "deny",
                f"A push to main deploys guardana.dev, and `{script} --check` says the "
                f"site is stale. Regenerate and commit first:\n{out}",
            )


def _pushes_main(command: str) -> bool:
    push = re.search(r"\bgit\s+push\b([^|;&]*)", command)
    if push is None:
        return False
    args = [arg for arg in push.group(1).split() if not arg.startswith("-")]
    if any(arg == "main" or arg.endswith(":main") for arg in args):
        return True
    if len(args) >= 2 and args[1] != "HEAD":  # noqa: PLR2004 — remote plus an explicit refspec
        return False
    try:
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return True
    return branch == "main"


def _guard_stage(command: str) -> None:
    if not re.search(r"\bgit\s+add\b", command):
        return
    if re.search(r"\bgit\s+add\s+(?:-A\b|--all\b|-u\b|--update\b|\.(?:\s|$))", command):
        decide("deny", "Stage explicit paths. Other sessions leave work in this tree.")
    if re.search(rf"\bgit\s+add\b[^|;&]*{ENV_FILE}", command):
        decide("deny", "Env files hold credentials and are never staged.")


def _guard_commit(command: str) -> None:
    if not re.search(r"\bgit\s+commit\b", command):
        return
    if re.search(r"\bgit\s+commit\s+(?:-\w*a\w*\b|--all\b)", command):
        decide("deny", "`git commit -a` stages every tracked change. Stage explicit paths.")
    if ATTRIBUTION.search(command):
        decide("deny", "No attribution in commits: no Co-Authored-By, no 'generated with'.")


def _guard_push(command: str) -> None:
    if not re.search(r"\bgit\s+push\b", command):
        return
    if re.search(r"--force\b|\s-f\b|--force-with-lease", command):
        decide("ask", "Force push to a shared branch.")
    if TAG_PUSH.search(command):
        decide(
            "ask",
            "Pushing a version tag publishes to PyPI after the approval click. "
            "Only after CI is green on this exact commit (`release` skill).",
        )
    if _pushes_main(command):
        _site_in_sync()


def _guard_tools(command: str) -> None:
    if re.search(rf"\b(?:cat|less|more|head|tail|bat|open)\s+[^|;&]*{ENV_FILE}", command):
        decide("deny", "Never print credential files. Source them: set -a; source .env; set +a")
    if re.search(r"\bclaude\s+(?:-p\b|--print\b)", command):
        decide(
            "ask",
            "`claude -p` boots a full session per call on the user's subscription. "
            "State the number of calls and the model first.",
        )
    if re.search(r"\bcodex\s+exec\b|\bagy\s+(?:-p\b|--print\b|--prompt\b)", command):
        decide(
            "ask",
            "Call GPT/Gemini through scripts/text_model.py, one call per batch; "
            "each call boots a full agent session on the other side.",
        )
    if re.search(r"scripts/release\.py\b", command) and "--dry-run" not in command:
        decide("ask", "release.py commits, tags and pushes; the tag publishes to PyPI.")
    if re.search(r"\bgh\s+(?:release\s+(?:create|delete|edit)|run\s+cancel)\b", command):
        decide("ask", "This changes a public release or a running publish.")


def guard_bash(command: str) -> None:
    """Decide on a Bash command; return silently when nothing applies."""
    if FORBIDDEN_MODEL.search(command):
        decide("deny", "Fable/Mythos models are never used from a command or script in this repo.")
    _guard_stage(command)
    _guard_commit(command)
    _guard_push(command)
    _guard_tools(command)


def _is_exempt(path: str) -> bool:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return candidate.resolve().relative_to(ROOT).as_posix() in SELF_EXEMPT
    except ValueError:
        return False


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def guard_write(tool_input: dict[str, object]) -> None:
    """Decide on a Write, Edit, MultiEdit or NotebookEdit; return silently when nothing applies."""
    if _is_exempt(str(tool_input.get("file_path", tool_input.get("notebook_path", "")))):
        return
    if FORBIDDEN_MODEL.search(" ".join(_strings(tool_input))):
        decide("deny", "Fable/Mythos model ids are never written into this repo.")


def main() -> None:
    """Read the payload, dispatch on the tool, print a decision if one applies."""
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool == "Bash":
        guard_bash(str(tool_input.get("command", "")))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        guard_write(tool_input)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # a broken guard must never block work
        sys.exit(0)
