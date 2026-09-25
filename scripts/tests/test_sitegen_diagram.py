"""The diagram renderer: what it refuses, and what every published diagram looks like."""

from pathlib import Path

import pytest

from sitegen import diagram
from sitegen.render import parser

_REPO = Path(__file__).resolve().parents[2]
_HEAD = "flowchart LR\n  accTitle: t\n  accDescr: d\n"


def _published() -> list[tuple[str, str]]:
    return [
        (page.relative_to(_REPO).as_posix(), token.content)
        for page in sorted((_REPO / "docs").rglob("*.md"))
        for token in parser().parse(page.read_text(encoding="utf-8"))
        if token.type == "fence" and token.info.strip() == "mermaid"
    ]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("graph TD\n  A --> B\n", "flowchart"),
        ("flowchart LR\n  accDescr: d\n  A --> B\n", "accTitle"),
        ("flowchart LR\n  accTitle: t\n  A --> B\n", "accDescr"),
        (_HEAD + "  A -- label --> B\n", "unsupported"),
        (_HEAD + "  A & B --> C\n", "unsupported"),
        (_HEAD + "  A --> B\n  B --> A\n", "cycle"),
        (_HEAD + "  A[one] --> B\n  A[two] --> C\n", "twice"),
        (_HEAD + "  A:::loud --> B\n", "not drawn"),
        (_HEAD + "  subgraph G [g]\n    subgraph H [h]\n    end\n  end\n", "nested"),
        (_HEAD + "  subgraph G [g]\n    A --> B\n  end\n", "several ranks"),
        (_HEAD + "  subgraph G [g]\n    A\n", "no `end`"),
        (_HEAD + "  subgraph G [g]\n  end\n  A --> B\n", "no node of its own"),
        (_HEAD + "  subgraph G [g]\n    A\n  end\n  B --> G\n", "is a subgraph"),
        (_HEAD + "  subgraph G [g]\n    A\n  end\n  subgraph G [h]\n    B\n  end\n", "taken"),
        (_HEAD + "  A[/slanted/] --> B\n", "not drawn"),
        (_HEAD + "  A[say #quot;hi#quot;] --> B\n", "not drawn"),
        (_HEAD + "  A[x] --> B\n  A([x]) --> C\n", "different shapes"),
    ],
)
def test_a_diagram_outside_the_subset_fails_the_build(source: str, reason: str) -> None:
    with pytest.raises(diagram.DiagramError, match=reason):
        diagram.figure(source)


def test_every_published_diagram_parses() -> None:
    assert _published(), "no docs page carries a mermaid diagram — the site shows none"
    for page, source in _published():
        assert diagram.parse(source).title, page


@pytest.mark.parametrize(("vertical", "compact"), [(False, False), (True, True), (True, False)])
def test_no_two_nodes_of_a_published_diagram_overlap(vertical: bool, compact: bool) -> None:
    for page, source in _published():
        graph = diagram.parse(source)
        layers, _chains = diagram._layers(graph, diagram._ranks(graph))
        boxes = diagram._place(graph, layers, vertical=vertical, compact=compact).boxes
        nodes = [boxes[node] for node in graph.nodes]
        for index, a in enumerate(nodes):
            for b in nodes[index + 1 :]:
                apart = abs(a.x - b.x) * 2 >= a.w + b.w or abs(a.y - b.y) * 2 >= a.h + b.h
                assert apart, f"{page}: two nodes overlap in the {vertical=} drawing"


def test_a_left_to_right_diagram_also_ships_a_drawing_for_narrow_screens() -> None:
    wide = diagram.figure(_HEAD + "  A --> B\n")
    tall = diagram.figure("flowchart TD\n  accTitle: t\n  accDescr: d\n  A --> B\n")

    assert wide.count("<svg") == 2
    assert "@container" in wide
    assert tall.count("<svg") == 1
    assert "@container" not in tall


def test_a_drawing_names_its_text_alternative_and_carries_no_script() -> None:
    drawn = diagram.figure(_HEAD + "  A[Model <b>files</b>] --> B\n")

    assert 'role="img"' in drawn
    assert "<title" in drawn
    assert "<desc" in drawn
    assert "<script" not in drawn
    assert "&lt;b&gt;" in drawn


def test_the_same_source_draws_the_same_bytes() -> None:
    source = _published()[0][1]

    assert diagram.figure(source, 3) == diagram.figure(source, 3)


def test_a_node_named_before_it_is_labelled_takes_its_label() -> None:
    graph = diagram.parse(_HEAD + "  A --> B\n  B([Later label])\n")

    assert graph.nodes["B"].lines == ("Later label",)
    assert graph.nodes["B"].shape == "pill"


def test_side_by_side_groups_with_long_titles_still_fit_the_narrow_drawing() -> None:
    source = _HEAD + (
        "  subgraph S [A title much wider than its one node]\n    A\n  end\n"
        "  subgraph T [Another title much wider than its node]\n    B\n  end\n"
        "  A --> C\n  B --> C\n"
    )

    assert diagram.figure(source).count("<svg") == 2


@pytest.mark.parametrize(
    "page",
    [
        "<!-- diagram: docs/how-it-works.md 0 -->stale<!-- /diagram -->",
        "<!-- diagram: docs/how-it-works.md 1 -->stale<!-- /diagram-->",
        "<!-- diagram: docs/how-it-works.md 1 -->a<!-- diagram: docs/how-it-works.md 1 -->"
        "b<!-- /diagram -->",
    ],
)
def test_a_malformed_diagram_marker_stops_the_landing_page_sync(page: str) -> None:
    import sync_site  # noqa: PLC0415 — loads the rule registry, needed by this test only

    with pytest.raises(SystemExit, match="diagram marker"):
        sync_site._rewrite_diagrams(page)
