"""Rewrite the landing page's factual claims from the registry, and its diagrams from the docs.

`bump_version.py` keeps the page's *version* correct on every release. Everything
beside it was hand-maintained, which is how `site/index.html` advertised 25 rules
through three releases that took the real number to 32 — automation covering one
number and nothing else makes the stale prose next to it look maintained.

Two ways to run it, and both matter:

    python scripts/sync_site.py            # rewrite the page from the registry
    python scripts/sync_site.py --check    # exit 1 if it is out of date, change nothing

`release.py` runs the first so a release never ships a stale page. `--check` is
for anyone who wants the answer without a diff; the same claims are pinned by
`test_landing_page.py`, so a rule added between releases turns the suite red
immediately rather than waiting for someone to cut one.
"""

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PAGE = _REPO / "site" / "index.html"

sys.path.insert(0, str(_REPO / "packages" / "guardana-core" / "src"))
sys.path.insert(0, str(_REPO / "packages" / "guardana-rules" / "src"))

from guardana.core.surface import Surface  # noqa: E402
from guardana.rules import provide_rules  # noqa: E402

from sitegen.diagram import figure  # noqa: E402
from sitegen.errors import SiteBuildError  # noqa: E402
from sitegen.render import parser  # noqa: E402

# Each claim is (pattern with the number captured, template, what it counts).
# Kept next to each other so adding a claim to the page means adding one line
# here — the alternative is a fourth number nobody rewrites.
_CLAIMS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r">(\d+) rules · two surfaces<"), ">{n} rules · two surfaces<", "total"),
    (re.compile(r">(\d+) rules · your laptop"), ">{n} rules · your laptop", "build"),
    (
        re.compile(r">(\d+) rules · a served model, or a run it already performed<"),
        ">{n} rules · a served model, or a run it already performed<",
        "runtime",
    ),
    (re.compile(r"(\d+) rule\(s\) run, 0 skipped"), "{n} rule(s) run, 0 skipped", "build"),
)

_EVERY_OCCURRENCE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\d+)( security)? check(s?)\b"), "total"),
)
"""Claims the page states in prose, wherever it states them.

The eyebrows above were rewritten from the registry while the meta description, the
`og:description`, the hero and the threat-model section all still said 47 — four
sentences one element away from a number this script had just corrected. That is the
same failure the docstring opens with, one layer in: automation covering the labels
makes the prose beside them look maintained.
"""


_DIAGRAM = re.compile(
    r"(?P<open><!-- diagram: (?P<path>\S+) (?P<n>[1-9][0-9]*) -->)"
    r"(?P<body>.*?)(?P<close><!-- /diagram -->)",
    re.DOTALL,
)
"""A diagram drawn from the n-th `mermaid` block of a docs page, which stays its only source."""


def _diagram(path: str, number: int, index: int) -> str:
    source = _REPO / path
    if not source.is_file():
        sys.exit(f"error: site/index.html draws a diagram from {path}, which does not exist")
    blocks = [
        token.content
        for token in parser().parse(source.read_text(encoding="utf-8"))
        if token.type == "fence" and token.info.strip() == "mermaid"
    ]
    if number > len(blocks):
        sys.exit(f"error: {path} has {len(blocks)} mermaid block(s); the page asks for #{number}")
    try:
        return figure(blocks[number - 1], 100 + index)
    except SiteBuildError as exc:
        sys.exit(f"error: {path} mermaid block #{number}: {exc}")


def _rewrite_diagrams(text: str) -> tuple[str, list[str]]:
    matches = list(_DIAGRAM.finditer(text))
    opened, closed = text.count("<!-- diagram:"), text.count("<!-- /diagram -->")
    if not opened == closed == len(matches) or any("<!-- diagram:" in m["body"] for m in matches):
        sys.exit(
            f"error: site/index.html has {opened} diagram marker(s), {closed} closing "
            f"marker(s) and {len(matches)} well-formed pair(s); write each as "
            f"`<!-- diagram: docs/<page>.md <n> -->…<!-- /diagram -->`"
        )
    changed: list[str] = []
    index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal index
        drawn = f"\n{_diagram(match['path'], int(match['n']), index)}\n"
        index += 1
        if match["body"] != drawn:
            changed.append(f"diagram from {match['path']} #{match['n']}")
        return f"{match['open']}{drawn}{match['close']}"

    return _DIAGRAM.sub(replace, text), changed


def _counts() -> dict[str, int]:
    rules = list(provide_rules())
    return {
        "total": len(rules),
        "build": sum(1 for r in rules if r.meta.surface is Surface.BUILD),
        "runtime": sum(1 for r in rules if r.meta.surface is Surface.RUNTIME),
    }


def _replacement(want: int) -> Callable[[re.Match[str]], str]:
    """Rewrite one "N checks" occurrence, keeping the wording it was written with."""

    def replace(match: re.Match[str]) -> str:
        return f"{want}{match.group(2) or ''} check{match.group(3)}"

    return replace


def _rewrite(text: str, counts: dict[str, int]) -> tuple[str, list[str]]:
    """Return the page with every claim corrected, and a note per claim that moved."""
    changed: list[str] = []
    for pattern, template, kind in _CLAIMS:
        match = pattern.search(text)
        if match is None:
            # Loud, never a silent skip: a claim the page stopped stating in the
            # form this script recognises is a claim nothing is checking any more.
            sys.exit(
                f"error: site/index.html no longer states its {kind} count as "
                f"{pattern.pattern!r} — the page was reworded, so update this script "
                f"with it rather than letting the claim go unchecked"
            )
        want = counts[kind]
        if int(match.group(1)) != want:
            changed.append(f"{kind}: {match.group(1)} -> {want}")
        text = pattern.sub(template.format(n=want), text, count=1)
    for pattern, kind in _EVERY_OCCURRENCE:
        want = counts[kind]
        stale = {m.group(1) for m in pattern.finditer(text) if int(m.group(1)) != want}
        if stale:
            changed.append(f"{kind} in prose: {', '.join(sorted(stale))} -> {want}")
        text = pattern.sub(_replacement(want), text)
    return text, changed


def main() -> int:
    """Rewrite the page from the registry, or report that it is stale."""
    parser = argparse.ArgumentParser(description="Sync the landing page with the rule registry.")
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the page is stale; write nothing"
    )
    args = parser.parse_args()

    original = _PAGE.read_text(encoding="utf-8")
    updated, changed = _rewrite(original, _counts())
    updated, drawn = _rewrite_diagrams(updated)
    changed += drawn

    if not changed:
        print("site/index.html is current")
        return 0
    if args.check:
        print("site/index.html is out of date:")
        for note in changed:
            print(f"  {note}")
        print("run `python scripts/sync_site.py` to fix it")
        return 1
    _PAGE.write_text(updated, encoding="utf-8")
    print("updated site/index.html:")
    for note in changed:
        print(f"  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
