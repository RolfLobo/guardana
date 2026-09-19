"""`docs/work/` is work in flight, not documentation: the site build leaves it out.

A work file has no front matter and no entry in `docs/index.md`, so without this
exclusion the first `/plan` would break the site build — or, worse, publish a
half-finished plan on guardana.dev.
"""

from pathlib import Path

from sitegen.page import read_pages

PAGE = '---\ntitle: "Scan"\nnav_order: 10\nsummary: "s"\nstatus: stable\n---\n# Scan\n'


def test_work_files_are_not_pages(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "work").mkdir(parents=True)
    (docs / "usage-scan.md").write_text(PAGE, encoding="utf-8")
    (docs / "work" / "2026-09-18-thing.md").write_text("# A plan\n\nNo front matter.\n")
    (docs / "work" / "BACKLOG.md").write_text("# Backlog\n")

    pages = read_pages(docs)

    assert [page.relative.as_posix() for page in pages] == ["usage-scan.md"]
