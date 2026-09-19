#!/usr/bin/env python3
"""Gate: every script under scripts/ has exactly one row in the ops catalogue.

The catalogue (docs/maintainers/ops-catalogue.md) is what an agent reads
instead of the scripts themselves, so a script without a row is invisible and
a row without a script is a lie.

    uv run python scripts/check_ops_catalogue.py

Exit codes: 0 in sync, 1 drift (the differences are printed).
"""

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "docs" / "maintainers" / "ops-catalogue.md"
SECTIONS = {"## Scripts": (ROOT / "scripts", ("*.py", "*.sh", "*.html"))}
ROW = re.compile(r"^\| `([^`]+)` \|")


def _on_disk(base: Path, patterns: tuple[str, ...]) -> set[str]:
    return {
        path.relative_to(base).as_posix() for pattern in patterns for path in base.glob(pattern)
    }


def _rows_by_section(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {name: [] for name in SECTIONS}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = next((name for name in SECTIONS if line.startswith(name)), None)
        elif current and (match := ROW.match(line)):
            rows[current].append(match.group(1))
    return rows


def main() -> int:
    """Compare the catalogue's rows with the scripts on disk."""
    rows = _rows_by_section(CATALOGUE.read_text(encoding="utf-8"))
    problems: list[str] = []
    for name, (base, patterns) in SECTIONS.items():
        listed = Counter(rows[name])
        present = _on_disk(base, patterns)
        where = base.relative_to(ROOT).as_posix()
        problems += [f"no row for {where}/{script}" for script in sorted(present - set(listed))]
        problems += [
            f"row without a script: {where}/{script}" for script in sorted(set(listed) - present)
        ]
        problems += [
            f"duplicate row: {where}/{script}" for script, n in sorted(listed.items()) if n > 1
        ]
    if problems:
        print(f"{CATALOGUE.relative_to(ROOT).as_posix()} is out of sync ({len(problems)}):")
        print("\n".join(f"  {problem}" for problem in problems))
        return 1
    print(f"ops catalogue in sync: {sum(len(found) for found in rows.values())} scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
