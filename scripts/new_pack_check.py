#!/usr/bin/env python3
"""Gate: `guardana new-pack` writes a pack that installs, validates and grades.

The fourth isolated suite. The other three prove a hand-written example still
works; this one proves the command that writes one from nothing does.

    uv run python scripts/new_pack_check.py
    uv run python scripts/new_pack_check.py --dir path/to/a/pack --name its-distribution-name

The engine is installed from this checkout, not from the index: installing the
published one would test the last release rather than this commit, and would put
a network fetch inside a gate that runs offline. "Uses no file from this
repository" is a claim about the generated pack's own content.

Exit codes: 0 the scaffold passes and the checks can still fail, 1 something
did not hold (the reason is printed).
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ("guardana-core", "guardana-rules", "guardana-cli", "guardana-report")
SHAPES = ("prompt", "scenario", "agent")


class CheckError(Exception):
    """A check did not hold. The message is what the reader needs."""


def _run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603


def _scaffold(name: str, into: Path, shapes: tuple[str, ...]) -> Path:
    # The console script beside the interpreter running us: the environment this
    # gate was started in, not whatever `guardana` happens to be on PATH.
    guardana = Path(sys.executable).parent / "guardana"
    argv = [str(guardana), "new-pack", name, "--dir", str(into)]
    for shape in shapes:
        argv += ["--shape", shape]
    done = _run(argv, cwd=ROOT)
    if done.returncode != 0:
        raise CheckError(f"new-pack {name} exited {done.returncode}:\n{done.stderr}")
    return into


def _install(pack: Path, venv: Path) -> Path:
    """Build a throwaway environment holding this checkout's engine and the pack."""
    created = _run(["uv", "venv", "--quiet", str(venv)])
    if created.returncode != 0:
        raise CheckError(f"uv venv failed:\n{created.stderr}")
    python = venv / "bin" / "python"
    # --no-cache is load-bearing: a cached wheel hides exactly the data files an
    # extension change touches, which is the whole subject of this check.
    installed = _run(
        [
            "uv",
            "pip",
            "install",
            "--quiet",
            "--no-cache",
            "--python",
            str(python),
            *[str(ROOT / "packages" / name) for name in ENGINE],
            str(pack),
            "pytest",
        ]
    )
    if installed.returncode != 0:
        raise CheckError(f"installing the generated pack failed:\n{installed.stderr}")
    return venv / "bin"


def _validate(bin_dir: Path, pack: Path, name: str, module: str) -> None:
    manifest = pack / "src" / module / "guardana-pack.yaml"
    named = _run([str(bin_dir / "guardana"), "pack", "validate", str(manifest)])
    if named.returncode != 0:
        raise CheckError(f"pack validate exited {named.returncode}:\n{named.stdout}{named.stderr}")
    if name not in named.stdout:
        raise CheckError(
            f"pack validate never named {name}; it checked something else:\n{named.stdout}"
        )

    # The hole this assertion exists for: an installed distribution shipping no
    # manifest is dropped before validation, so a pack whose manifest missed the
    # wheel is reported as nothing to check rather than as broken. Exit 0 alone
    # would not tell them apart; the pack's own name in the output does.
    discovered = _run([str(bin_dir / "guardana"), "pack", "validate"])
    if discovered.returncode != 0 or name not in discovered.stdout:
        raise CheckError(
            f"discovery over the installed packs did not come back clean about {name} "
            f"(exit {discovered.returncode}); the manifest inside the wheel is not the "
            f"one this pack was checked with:\n{discovered.stdout}{discovered.stderr}"
        )


_LIE = "nobody.registers.this"


def _detector_works(bin_dir: Path, pack: Path, module: str, tmp: Path) -> None:
    """Prove the validator would notice, by handing it a manifest that lies.

    The lie goes under `rules:` and the refusal has to name it. A non-zero exit
    alone would also be earned by a manifest this rewrite made unparseable, and
    then the gate would stay green while the detector it depends on went unused.
    """
    manifest = (pack / "src" / module / "guardana-pack.yaml").read_text()
    if "  rules:\n" not in manifest:
        raise CheckError("the generated manifest has no `rules:` block to corrupt")
    lying = tmp / "lying-pack.yaml"
    lying.write_text(manifest.replace("  rules:\n", f"  rules:\n    - {_LIE}\n", 1))

    done = _run([str(bin_dir / "guardana"), "pack", "validate", str(lying)])
    if done.returncode == 0:
        raise CheckError(
            f"a manifest promising {_LIE}, which nothing registers, was accepted; "
            f"the check that guards this gate does not work:\n{done.stdout}"
        )
    if _LIE not in done.stdout or "believes a check runs that does not" not in done.stdout:
        raise CheckError(
            f"the validator refused the lying manifest without naming {_LIE}; it "
            f"failed for some other reason, so the detector was not exercised:"
            f"\n{done.stdout}{done.stderr}"
        )


def _graded(bin_dir: Path, prefix: str, rules: int) -> None:
    done = _run([str(bin_dir / "guardana"), "rule", "test", f"{prefix}.*"])
    if done.returncode != 0:
        raise CheckError(f"rule test exited {done.returncode}:\n{done.stdout}{done.stderr}")
    summary = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    for expected in (
        f"{rules} rule(s)",
        f"{rules * 3} fixture(s) passed",
        "0 failed",
        "0 could not run",
        "0 rule(s) not fully sampled",
    ):
        if expected not in summary:
            raise CheckError(f"rule test summary lacks {expected!r}: {summary!r}")


def _suite(bin_dir: Path, pack: Path) -> None:
    done = _run([str(bin_dir / "pytest"), str(pack / "tests"), "-q", "-p", "no:cacheprovider"])
    if done.returncode != 0:
        raise CheckError(f"the generated test suite failed:\n{done.stdout[-2000:]}")


def _rules_in(pack: Path, module: str) -> int:
    """How many rules this tree actually carries.

    Read from the catalogue rather than from the shapes asked for, so checking a
    pack somebody else wrote cannot fail over a count it never promised — which
    would be a red the reader has to explain away, and a check that never reached
    what it was for.
    """
    declared = list((pack / "src" / module / "catalog").glob("*.yaml"))
    if not declared:
        raise CheckError(f"{pack} has no catalogue; there is nothing to grade")
    return len(declared)


def _check(pack: Path, name: str, tmp: Path) -> int:
    module = name.replace("-", "_")
    rules = _rules_in(pack, module)
    bin_dir = _install(pack, tmp / f"venv-{name}")
    _validate(bin_dir, pack, name, module)
    _detector_works(bin_dir, pack, module, tmp)
    _graded(bin_dir, name.split("-", maxsplit=1)[0], rules)
    _suite(bin_dir, pack)
    return rules


def main() -> int:
    """Scaffold, install and verify; or verify a tree somebody already has."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, help="check this existing pack instead of scaffolding")
    parser.add_argument("--name", help="the distribution name of the pack given by --dir")
    parser.add_argument("--keep", action="store_true", help="leave the temporary tree behind")
    args = parser.parse_args()

    if args.dir and not args.name:
        parser.error("--dir needs --name, which is what every check is keyed by")

    tmp = Path(tempfile.mkdtemp(prefix="guardana-new-pack-"))
    try:
        if args.dir:
            rules = _check(args.dir, args.name, tmp)
            print(f"✓ {args.name}: {rules} rule(s) install, validate and grade")
            return 0
        # The default: every shape, then one narrowed invocation, because a flag
        # whose output is never installed is machinery nothing verifies.
        for name, shapes in (("scaffolded-pack", SHAPES), ("narrowed-pack", ("agent",))):
            rules = _check(_scaffold(name, tmp / name, shapes), name, tmp)
            print(f"✓ {name}: {rules} rule(s) install, validate and grade")
    except CheckError as failure:
        print(f"✗ {failure}", file=sys.stderr)
        return 1
    else:
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
