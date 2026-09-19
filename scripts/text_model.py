#!/usr/bin/env python3
"""Route a text task to GPT (codex CLI) or Gemini (agy CLI) from an agent session.

Wording a reader of this project sees — landing copy, README and docs prose,
the prompts inside rules, release notes — and any verdict ABOUT such wording is
not authored by the coding agent. This is the one door to the models that do
it, so the routing rule lives in code instead of in a prompt.

    text_model.py --detect
    text_model.py --prompt P.md --out OUT.md [--input FILE ...] [--schema S.json]
                  [--engine auto|gpt|gemini|both] [--effort low|medium|high]

`--engine both` asks each engine independently and writes OUT.gpt.* and
OUT.gemini.*; agreement between two model families is the bar for a verdict
that removes, rejects or rewrites something.

Every call starts a whole agent session on the other side, with a fixed
overhead of several thousand tokens: send one call per BATCH of items, never
one call per item.

Exit codes: 0 ok, 2 usage, 3 no engine installed, 4 the engine failed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

GPT = "gpt"
GEMINI = "gemini"
# agy spells the effort inside the model id and rejects a separate --effort beside it.
GEMINI_MODEL_BY_EFFORT = {
    "low": "gemini-3.1-pro-low",
    "medium": "gemini-3.1-pro-high",
    "high": "gemini-3.1-pro-high",
}
TIMEOUT_S = 900


def _available() -> dict[str, str | None]:
    return {GPT: shutil.which("codex"), GEMINI: shutil.which("agy")}


def _assemble(prompt: Path, inputs: list[Path]) -> str:
    parts = [prompt.read_text(encoding="utf-8").rstrip()]
    for path in inputs:
        body = path.read_text(encoding="utf-8")
        parts.append(f'<file name="{path.name}">\n{body.rstrip()}\n</file>')
    return "\n\n".join(parts) + "\n"


def _run_gpt(text: str, out: Path, schema: Path | None, effort: str) -> None:
    # An empty working root: the task is the prompt, not a repository to explore.
    with tempfile.TemporaryDirectory(prefix="text_model_") as root:
        cmd = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--skip-git-repo-check",
            "--color",
            "never",
            "-c",
            f'model_reasoning_effort="{effort}"',
            "-C",
            root,
            "-o",
            str(out),
        ]
        model = os.environ.get("TEXT_MODEL_GPT")
        if model:
            cmd += ["-m", model]
        if schema:
            cmd += ["--output-schema", str(schema)]
        cmd.append("-")
        done = subprocess.run(  # noqa: S603 — a fixed literal command, the prompt goes on stdin
            cmd, input=text, text=True, capture_output=True, timeout=TIMEOUT_S, check=False
        )
    if done.returncode != 0 or not out.exists():
        raise RuntimeError(f"codex exited {done.returncode}: {done.stderr.strip()[-800:]}")


def _run_gemini(text: str, out: Path, schema: Path | None, effort: str) -> None:
    model = os.environ.get("TEXT_MODEL_GEMINI") or GEMINI_MODEL_BY_EFFORT[effort]
    # agy also serves other vendors' models; this door is for Gemini only.
    if not model.startswith("gemini-"):
        raise RuntimeError(f"TEXT_MODEL_GEMINI must be a gemini-* model, got {model!r}")
    cmd = [
        "agy",
        f"--print={text}",
        "--model",
        model,
        "--output-format",
        "json" if schema else "text",
        "--disable-slash-commands",
        "--sandbox",
        "--print-timeout",
        f"{TIMEOUT_S}s",
    ]
    if schema:
        cmd += ["--json-schema", str(schema.resolve())]
    with tempfile.TemporaryDirectory(prefix="text_model_") as root:
        done = subprocess.run(  # noqa: S603 — a fixed literal command
            cmd,
            cwd=root,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=TIMEOUT_S + 30,
            check=False,
        )
    if done.returncode != 0 or not done.stdout.strip():
        raise RuntimeError(f"agy exited {done.returncode}: {done.stderr.strip()[-800:]}")
    if not schema:
        out.write_text(done.stdout, encoding="utf-8")
        return
    # With a schema agy answers in an envelope; the answer itself is `structured_output`.
    envelope = json.loads(done.stdout)
    if envelope.get("status") != "SUCCESS" or "structured_output" not in envelope:
        raise RuntimeError(f"agy returned no structured output: {done.stdout[-800:]}")
    out.write_text(
        json.dumps(envelope["structured_output"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


RUNNERS: dict[str, Callable[[str, Path, Path | None, str], None]] = {
    GPT: _run_gpt,
    GEMINI: _run_gemini,
}


def _check_json(out: Path) -> None:
    try:
        json.loads(out.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{out} is not valid JSON although a schema was given: {exc}") from exc


def _engines(requested: str, found: dict[str, str | None]) -> list[str]:
    if requested == "both":
        return [GPT, GEMINI]
    if requested == "auto":
        return [name for name in (GPT, GEMINI) if found[name]][:1]
    return [requested]


def main() -> int:
    """Parse the arguments, pick the engines, run each one and report."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--detect", action="store_true", help="print which engines are installed")
    parser.add_argument("--prompt", type=Path, help="file holding the instructions")
    parser.add_argument("--input", type=Path, action="append", default=[], help="file to append")
    parser.add_argument("--out", type=Path, help="where the answer is written")
    parser.add_argument("--schema", type=Path, help="JSON Schema the answer must follow")
    parser.add_argument("--engine", choices=["auto", GPT, GEMINI, "both"], default="auto")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="medium")
    args = parser.parse_args()

    found = _available()
    if args.detect:
        print(json.dumps(found))
        return 0 if any(found.values()) else 3
    if not args.prompt or not args.out:
        parser.error("--prompt and --out are required")

    engines = _engines(args.engine, found)
    missing = [name for name in engines if not found[name]]
    if not engines or missing:
        print(
            f"text_model: engine not installed: {missing or 'codex, agy'}. "
            "Do not write this text yourself — stop and report.",
            file=sys.stderr,
        )
        return 3

    text = _assemble(args.prompt, args.input)
    failed = False
    for name in engines:
        out = args.out
        if args.engine == "both":
            out = args.out.with_name(f"{args.out.stem}.{name}{args.out.suffix}")
        try:
            RUNNERS[name](text, out, args.schema, args.effort)
            if args.schema:
                _check_json(out)
            print(f"{name}: {out} ({out.stat().st_size} bytes)")
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            failed = True
            print(f"{name}: FAILED — {exc}", file=sys.stderr)
    return 4 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
