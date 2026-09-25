"""Draw a subset of Mermaid flowcharts as static SVG in the site's own fonts and colours.

A diagram's source is a `mermaid` fenced block in a docs page, which GitHub renders
as it is. The site draws the same graph without a script, light and dark, and a
left-to-right diagram also gets a top-to-bottom drawing for narrow screens. Syntax
outside the subset raises `DiagramError`, so a diagram never ships as a code block.

The subset:

- `flowchart LR`, `flowchart TD` or `flowchart TB` on the first line;
- `accTitle: …` and `accDescr: …`, both required: they are the text alternative;
- nodes `id`, `id[label]`, `id(label)`, `id([label])` (drawn as a pill) and
  `id[(label)]` (a stored document), with an optional `:::class`;
- edges `-->`, `-.->` (optional) and `==>` (the main path), each with an optional
  `|label|`, chained on one line;
- `subgraph id [title]` … `end`, not nested, whose members share one rank;
- `classDef` lines, which style the GitHub rendering and are ignored here, and
  `class a,b name`. The classes drawn here are `accent`, `cmd` and `muted`.

Labels break at `<br>`.
"""

import hashlib
import re
from dataclasses import dataclass, field
from html import escape
from itertools import pairwise

from sitegen.errors import SiteBuildError


class DiagramError(SiteBuildError):
    """A diagram's source is outside the subset this module draws."""


_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CLASS = re.compile(r":::([A-Za-z_][A-Za-z0-9_-]*)")
_SHAPES = (("[(", ")]", "doc"), ("([", "])", "pill"), ("[", "]", "rect"), ("(", ")", "rect"))
_EDGES = (("-.->", "dot"), ("==>", "main"), ("-->", "solid"))
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_ENTITY = re.compile(r"#\w+;")
_DRAWN_CLASSES = frozenset({"accent", "cmd", "muted"})

_FONT = 13.0
_MONO = 12.5
_LINE = 18.0
_PAD_X = 16.0
_PAD_Y = 10.0
_NODE_GAP = 18.0
_RANK_GAP = 56.0
_GROUP_PAD = 14.0
_GROUP_TITLE = 20.0
_GROUP_FONT = 11.0
_LABEL_H = 18.0
_DOC_LIP = 6.0
_MARGIN = 4.0
_SWITCH_SCALE = 0.8
_MIN_SCALE = 0.75


@dataclass
class _Node:
    id: str
    lines: tuple[str, ...]
    shape: str = "rect"
    classes: set[str] = field(default_factory=set)
    group: str = ""
    labelled: bool = False


@dataclass(frozen=True)
class _Edge:
    src: str
    dst: str
    style: str
    label: str


@dataclass
class _Group:
    id: str
    title: str
    members: list[str] = field(default_factory=list)


@dataclass
class Graph:
    """A parsed diagram: direction, text alternative, nodes, edges and groups."""

    direction: str
    title: str
    description: str
    nodes: dict[str, _Node]
    edges: list[_Edge]
    groups: list[_Group]


def parse(source: str) -> Graph:
    """Read a diagram in the subset, or raise `DiagramError` naming the line."""
    lines = [
        (number, line.strip().rstrip(";").strip())
        for number, line in enumerate(source.splitlines(), 1)
        if line.strip() and not line.strip().startswith("%%")
    ]
    if not lines:
        raise DiagramError("mermaid block is empty")
    number, header = lines[0]
    match = re.fullmatch(r"flowchart\s+(LR|TD|TB)", header)
    if match is None:
        raise DiagramError(f"line {number}: expected `flowchart LR|TD|TB`, got {header!r}")
    graph = Graph("LR" if match[1] == "LR" else "TD", "", "", {}, [], [])
    group: _Group | None = None
    for number, line in lines[1:]:
        try:
            group = _statement(graph, line, group)
        except DiagramError as exc:
            raise DiagramError(f"line {number}: {exc}") from None
    if group is not None:
        raise DiagramError(f"subgraph {group.id} has no `end`")
    if not graph.title or not graph.description:
        raise DiagramError("a diagram needs `accTitle:` and `accDescr:`, its text alternative")
    if not graph.nodes:
        raise DiagramError("a diagram needs at least one node")
    empty = [g.id for g in graph.groups if not g.members]
    if empty:
        raise DiagramError(f"subgraph {empty[0]} has no node of its own")
    return graph


def _statement(graph: Graph, line: str, group: _Group | None) -> _Group | None:
    keyword = line.split(maxsplit=1)[0]
    rest = line[len(keyword) :].strip()
    if keyword in ("accTitle:", "accDescr:"):
        _accessible(graph, keyword, rest)
    elif keyword == "class":
        names, _, cls = rest.rpartition(" ")
        for name in names.split(","):
            _known(graph, name.strip()).classes.add(_drawn(cls))
    elif keyword == "subgraph":
        return _open_group(graph, rest, group)
    elif keyword == "end":
        if group is None:
            raise DiagramError("`end` without a subgraph")
        return None
    elif keyword != "classDef":
        _chain(graph, line, group)
    return group


def _accessible(graph: Graph, keyword: str, text: str) -> None:
    if not text:
        raise DiagramError(f"`{keyword}` is empty")
    if keyword == "accTitle:":
        graph.title = text
    else:
        graph.description = text


def _open_group(graph: Graph, rest: str, group: _Group | None) -> _Group:
    if group is not None:
        raise DiagramError("nested subgraphs are not drawn")
    found = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*\"?([^\]\"]+)\"?\s*\]", rest)
    if found is None:
        raise DiagramError("write a subgraph as `subgraph id [title]`")
    if found[1] in graph.nodes or any(g.id == found[1] for g in graph.groups):
        raise DiagramError(f"subgraph id {found[1]!r} is already taken")
    created = _Group(found[1], found[2].strip())
    graph.groups.append(created)
    return created


def _chain(graph: Graph, line: str, group: _Group | None) -> None:
    position = 0
    previous: str | None = None
    pending: tuple[str, str] | None = None
    while True:
        node_id, position = _node(graph, line, position, group)
        if previous is not None and pending is not None:
            graph.edges.append(_Edge(previous, node_id, pending[0], pending[1]))
        position = _skip(line, position)
        if position == len(line):
            return
        pending, position = _edge(line, position)
        previous = node_id
        position = _skip(line, position)


def _node(graph: Graph, line: str, position: int, group: _Group | None) -> tuple[str, int]:
    found = _ID.match(line, position)
    if found is None:
        raise DiagramError(f"expected a node id at {line[position:]!r}")
    node_id = found[0]
    shape, label, position = _shape_at(line, found.end(), node_id)
    if any(g.id == node_id for g in graph.groups):
        raise DiagramError(f"{node_id} is a subgraph; an edge cannot point at a subgraph")
    classes: set[str] = set()
    tag = _CLASS.match(line, position)
    if tag is not None:
        classes.add(_drawn(tag[1]))
        position = tag.end()
    node = _register(graph, node_id, shape, label)
    node.classes |= classes
    if group is not None and not node.group:
        node.group = group.id
        group.members.append(node_id)
    return node_id, position


def _shape_at(line: str, position: int, node_id: str) -> tuple[str, str, int]:
    """Read an optional `[label]`-style shape after a node id: (shape, label, end)."""
    for opener, closer, name in _SHAPES:
        if line.startswith(opener, position):
            end = line.find(closer, position + len(opener))
            if end < 0:
                raise DiagramError(f"node {node_id}: `{opener}` is never closed")
            label = line[position + len(opener) : end].strip().strip('"')
            if label.startswith(("/", "\\")) or _ENTITY.search(label):
                raise DiagramError(
                    f"node {node_id}: shapes and entity codes in {label!r} are not drawn"
                )
            return name, label, end + len(closer)
    return "", "", position


def _register(graph: Graph, node_id: str, shape: str, label: str) -> _Node:
    """Return the node, declaring it on first sight and refusing a conflicting redeclaration."""
    lines = tuple(part.strip() for part in _BREAK.split(label or node_id))
    node = graph.nodes.get(node_id)
    if node is None:
        node = _Node(node_id, lines, shape or "rect", labelled=bool(label))
        graph.nodes[node_id] = node
    elif label and not node.labelled:
        node.lines, node.shape, node.labelled = lines, shape or "rect", True
    elif label and lines != node.lines:
        raise DiagramError(f"node {node_id} is declared twice with different labels")
    elif shape and shape != node.shape:
        raise DiagramError(f"node {node_id} is declared twice with different shapes")
    return node


def _edge(line: str, position: int) -> tuple[tuple[str, str], int]:
    for operator, style in _EDGES:
        if line.startswith(operator, position):
            position += len(operator)
            label = ""
            if line.startswith("|", position):
                end = line.find("|", position + 1)
                if end < 0:
                    raise DiagramError("an edge label `|…` is never closed")
                label, position = line[position + 1 : end].strip(), end + 1
            return (style, label), position
    raise DiagramError(f"unsupported syntax at {line[position:]!r}; see sitegen/diagram.py")


def _skip(line: str, position: int) -> int:
    while position < len(line) and line[position] == " ":
        position += 1
    return position


def _known(graph: Graph, node_id: str) -> _Node:
    if node_id not in graph.nodes:
        raise DiagramError(f"`class` names {node_id!r} before it is declared")
    return graph.nodes[node_id]


def _drawn(name: str) -> str:
    if name not in _DRAWN_CLASSES:
        raise DiagramError(f"class {name!r} is not drawn; use one of {sorted(_DRAWN_CLASSES)}")
    return name


@dataclass
class _Box:
    """A placed node, dummy or group: centre and size in drawing coordinates."""

    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


def _text_width(text: str, mono: bool) -> float:
    if mono:
        return len(text) * _MONO * 0.6
    width = 0.0
    for char in text:
        if char in "il.,:;'|!·":
            width += 0.3
        elif char in "mwMW":
            width += 0.86
        elif char.isupper():
            width += 0.66
        elif char == " ":
            width += 0.28
        else:
            width += 0.55
    return width * _FONT


def _size(node: _Node, compact: bool) -> tuple[float, float]:
    mono = "cmd" in node.classes
    widest = max(_text_width(line, mono) for line in node.lines)
    pad = _PAD_X * (0.65 if compact else 1.0)
    width = max(64.0, widest + 2 * pad + (_LINE * 0.6 if node.shape == "pill" else 0.0))
    height = len(node.lines) * _LINE + 2 * _PAD_Y + (_DOC_LIP if node.shape == "doc" else 0.0)
    return round(width), round(height)


def _ranks(graph: Graph) -> dict[str, int]:
    """Longest path from the sources, with each source pulled next to its nearest target."""
    rank = _longest_paths(graph)
    targets = {node: [e.dst for e in graph.edges if e.src == node] for node in graph.nodes}
    sources = {node for node in graph.nodes if all(e.dst != node for e in graph.edges)}
    for node in sources:
        if targets[node]:
            rank[node] = min(rank[t] for t in targets[node]) - 1
    for group in graph.groups:
        if len({rank[member] for member in group.members}) > 1:
            raise DiagramError(f"subgraph {group.id} spans several ranks; keep a group in one")
    return rank


def _longest_paths(graph: Graph) -> dict[str, int]:
    incoming = dict.fromkeys(graph.nodes, 0)
    for edge in graph.edges:
        incoming[edge.dst] += 1
    rank = dict.fromkeys(graph.nodes, 0)
    ready = [node for node in graph.nodes if incoming[node] == 0]
    seen = 0
    while ready:
        node = ready.pop(0)
        seen += 1
        for edge in (e for e in graph.edges if e.src == node):
            rank[edge.dst] = max(rank[edge.dst], rank[node] + 1)
            incoming[edge.dst] -= 1
            if incoming[edge.dst] == 0:
                ready.append(edge.dst)
    if seen != len(graph.nodes):
        raise DiagramError("the diagram has a cycle; draw a directed acyclic graph")
    return rank


def _layers(graph: Graph, rank: dict[str, int]) -> tuple[list[list[str]], list[list[str]]]:
    """Return the rank layers, dummies included, and each edge's chain through them."""
    layers: list[list[str]] = [[] for _ in range(max(rank.values()) + 1)]
    for node in graph.nodes:
        layers[rank[node]].append(node)
    chains: list[list[str]] = []
    for index, edge in enumerate(graph.edges):
        chain = [edge.src]
        for step in range(rank[edge.src] + 1, rank[edge.dst]):
            dummy = f"~{index}~{step}"
            layers[step].append(dummy)
            chain.append(dummy)
        chain.append(edge.dst)
        chains.append(chain)
    up: dict[str, list[str]] = {}
    down: dict[str, list[str]] = {}
    for chain in chains:
        for a, b in pairwise(chain):
            down.setdefault(a, []).append(b)
            up.setdefault(b, []).append(a)
    groups = {node.id: node.group for node in graph.nodes.values()}
    for _ in range(4):
        for r in range(1, len(layers)):
            layers[r] = _order(layers[r], layers[r - 1], up, groups)
        for r in range(len(layers) - 2, -1, -1):
            layers[r] = _order(layers[r], layers[r + 1], down, groups)
    return layers, chains


def _order(
    layer: list[str], other: list[str], links: dict[str, list[str]], groups: dict[str, str]
) -> list[str]:
    """Sort a layer by the mean position of its neighbours, keeping each group together."""
    where = {item: index for index, item in enumerate(other)}
    centre = {}
    for index, item in enumerate(layer):
        linked = [where[n] for n in links.get(item, []) if n in where]
        centre[item] = sum(linked) / len(linked) if linked else float(index)
    anchor: dict[str, float] = {}
    for item in layer:
        members = [i for i in layer if groups.get(item) and groups.get(i) == groups.get(item)]
        members = members or [item]
        anchor[item] = sum(centre[m] for m in members) / len(members)
    return sorted(layer, key=lambda i: (anchor[i], groups.get(i, ""), centre[i]))


@dataclass
class _Drawing:
    boxes: dict[str, _Box]
    groups: dict[str, _Box]
    width: float
    height: float


@dataclass(frozen=True)
class _Axis:
    """Sizes seen along the rank axis and across it, for one direction."""

    sizes: dict[str, tuple[float, float]]
    groups: dict[str, str]
    vertical: bool
    gap: float

    def along(self, item: str) -> float:
        width, height = self.sizes.get(item, (0.0, 0.0))
        return height if self.vertical else width

    def across(self, item: str) -> float:
        if item.startswith("~"):
            return 8.0
        width, height = self.sizes[item]
        return width if self.vertical else height


def _place(graph: Graph, layers: list[list[str]], vertical: bool, compact: bool) -> _Drawing:
    """Lay the layers out along one axis; `compact` tightens a drawing meant for phones."""
    axis = _Axis(
        {node.id: _size(node, compact) for node in graph.nodes.values()},
        {node.id: node.group for node in graph.nodes.values()},
        vertical,
        _NODE_GAP * (0.65 if compact else 1.0),
    )
    gaps = _gaps(graph, layers, vertical)
    titles = {group.id: _title_width(group.title) for group in graph.groups}
    boxes: dict[str, _Box] = {}
    stacks: list[float] = []
    start = 0.0
    for r, layer in enumerate(layers):
        grouped = any(axis.groups.get(i) for i in layer)
        head = _GROUP_PAD + _GROUP_TITLE if vertical and grouped else 0.0
        tail = _GROUP_PAD if vertical and grouped else 0.0
        depth = max(_depth(axis, item, titles) for item in layer)
        stacks.append(_stack(layer, axis, start + head + depth / 2, boxes, titles))
        start += head + depth + tail + (gaps[r] if r < len(gaps) else 0.0)
    for r, layer in enumerate(layers):
        shift = (max(stacks) - stacks[r]) / 2
        for item in layer:
            if vertical:
                boxes[item].x += shift
            else:
                boxes[item].y += shift
    group_boxes = {group.id: _enclose(group, boxes) for group in graph.groups}
    _refuse_overlaps(graph, boxes, group_boxes)
    return _normalise(boxes, group_boxes)


def _depth(axis: _Axis, item: str, titles: dict[str, float]) -> float:
    """How much of the rank axis an item needs, its group's frame and title included."""
    group = axis.groups.get(item, "")
    if axis.vertical or not group:
        return axis.along(item)
    return max(axis.along(item) + 2 * _GROUP_PAD, titles[group])


def _gaps(graph: Graph, layers: list[list[str]], vertical: bool) -> list[float]:
    """Widen the gap after a rank so that an edge label leaving it fits between ranks."""
    gaps = [_RANK_GAP] * max(len(layers) - 1, 0)
    for edge in graph.edges:
        if edge.label:
            need = (_LABEL_H + 22) if vertical else (_text_width(edge.label, True) + 28)
            first = _rank_of(layers, edge.src)
            gaps[first] = max(gaps[first], need)
    return gaps


def _stack(
    layer: list[str],
    axis: _Axis,
    centre: float,
    boxes: dict[str, _Box],
    titles: dict[str, float],
) -> float:
    """Place one rank's items across the axis and return the length they take.

    Across a vertical drawing a group's title runs along the stack, so a title wider
    than its members gets its overhang reserved on both sides of the group.
    """
    cursor = 0.0
    overhang = 0.0
    for index, item in enumerate(layer):
        group = axis.groups.get(item, "")
        opens = bool(group) and (index == 0 or axis.groups.get(layer[index - 1], "") != group)
        closes = bool(group) and (
            index == len(layer) - 1 or axis.groups.get(layer[index + 1], "") != group
        )
        if opens:
            members = [i for i in layer if axis.groups.get(i) == group]
            span = sum(axis.across(m) for m in members) + axis.gap * (len(members) - 1)
            wanted = titles[group] - span - 2 * _GROUP_PAD
            overhang = max(0.0, wanted) / 2 if axis.vertical else 0.0
            cursor += _GROUP_PAD + overhang + (0.0 if axis.vertical else _GROUP_TITLE)
        size = axis.across(item)
        width, height = axis.sizes.get(item, (0.0, 0.0))
        middle = cursor + size / 2
        x, y = (middle, centre) if axis.vertical else (centre, middle)
        boxes[item] = _Box(x, y, width, height)
        cursor += size + (_GROUP_PAD + overhang if closes else 0.0) + axis.gap
    return cursor - axis.gap


def _title_width(title: str) -> float:
    return len(title) * _GROUP_FONT * 0.68 + 2 * _GROUP_PAD


def _enclose(group: _Group, boxes: dict[str, _Box]) -> _Box:
    members = [boxes[m] for m in group.members]
    left = min(b.x - b.w / 2 for b in members) - _GROUP_PAD
    right = max(b.x + b.w / 2 for b in members) + _GROUP_PAD
    short = _title_width(group.title) - (right - left)
    if short > 0:
        left, right = left - short / 2, right + short / 2
    top = min(b.y - b.h / 2 for b in members) - _GROUP_PAD - _GROUP_TITLE
    bottom = max(b.y + b.h / 2 for b in members) + _GROUP_PAD
    return _Box((left + right) / 2, (top + bottom) / 2, right - left, bottom - top)


def _normalise(boxes: dict[str, _Box], groups: dict[str, _Box]) -> _Drawing:
    items = [*boxes.values(), *groups.values()]
    min_x = min(b.x - b.w / 2 for b in items) - _MARGIN
    min_y = min(b.y - b.h / 2 for b in items) - _MARGIN
    for box in items:
        box.x -= min_x
        box.y -= min_y
    width = max(b.x + b.w / 2 for b in items) + _MARGIN
    height = max(b.y + b.h / 2 for b in items) + _MARGIN
    return _Drawing(boxes, groups, width, height)


def _rank_of(layers: list[list[str]], item: str) -> int:
    return next(r for r, layer in enumerate(layers) if item in layer)


def _overlap(a: _Box, b: _Box) -> bool:
    return abs(a.x - b.x) * 2 < a.w + b.w and abs(a.y - b.y) * 2 < a.h + b.h


def _refuse_overlaps(graph: Graph, boxes: dict[str, _Box], groups: dict[str, _Box]) -> None:
    for index, group in enumerate(graph.groups):
        area = groups[group.id]
        for node in graph.nodes.values():
            if node.group != group.id and _overlap(boxes[node.id], area):
                raise DiagramError(f"node {node.id} would be drawn inside subgraph {group.id}")
        for other in graph.groups[index + 1 :]:
            if _overlap(area, groups[other.id]):
                raise DiagramError(f"subgraphs {group.id} and {other.id} would overlap")


def _num(value: float) -> str:
    return f"{value:.1f}".removesuffix(".0")


@dataclass(frozen=True)
class _Variant:
    """One drawing of a diagram: its id prefix, its CSS class and its orientation."""

    uid: str
    css_class: str
    vertical: bool
    min_scale: float


def _svg(graph: Graph, drawing: _Drawing, chains: list[list[str]], variant: _Variant) -> str:
    uid, vertical = variant.uid, variant.vertical
    sizing = f"width:100%;max-width:{_num(drawing.width)}px"
    if variant.min_scale:
        sizing += f";min-width:{_num(drawing.width * variant.min_scale)}px"
    out = [
        f'<svg class="{variant.css_class}" style="{sizing}" '
        f'viewBox="0 0 {_num(drawing.width)} {_num(drawing.height)}" '
        f'width="{_num(drawing.width)}" height="{_num(drawing.height)}" role="img" '
        f'aria-labelledby="{uid}-t {uid}-d" xmlns="http://www.w3.org/2000/svg">',
        f'<title id="{uid}-t">{escape(graph.title)}</title>',
        f'<desc id="{uid}-d">{escape(graph.description)}</desc>',
        "<defs>",
        *(
            f'<marker id="{uid}-{kind}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path class="h {kind}" '
            f'd="M0 0L10 5L0 10z"/></marker>'
            for kind in ("solid", "main")
        ),
        "</defs>",
    ]
    for group in graph.groups:
        box = drawing.groups[group.id]
        out.append(
            f'<g class="g"><rect x="{_num(box.x - box.w / 2)}" y="{_num(box.y - box.h / 2)}" '
            f'width="{_num(box.w)}" height="{_num(box.h)}" rx="12"/>'
            f'<text x="{_num(box.x - box.w / 2 + _GROUP_PAD)}" '
            f'y="{_num(box.y - box.h / 2 + _GROUP_PAD + 4)}">{escape(group.title)}</text></g>'
        )
    labels = []
    for edge, chain in zip(graph.edges, chains, strict=True):
        points = [drawing.boxes[item] for item in chain]
        path, middle = _path(points, vertical)
        marker = "main" if edge.style == "main" else "solid"
        out.append(f'<path class="e {edge.style}" d="{path}" marker-end="url(#{uid}-{marker})"/>')
        if edge.label:
            width = _text_width(edge.label, True) + 12
            labels.append(
                f'<g class="l"><rect x="{_num(middle[0] - width / 2)}" '
                f'y="{_num(middle[1] - _LABEL_H / 2)}" width="{_num(width)}" '
                f'height="{_num(_LABEL_H)}" rx="5"/><text x="{_num(middle[0])}" '
                f'y="{_num(middle[1])}">{escape(edge.label)}</text></g>'
            )
    out.extend(labels)
    out.extend(_shape(node, drawing.boxes[node.id]) for node in graph.nodes.values())
    out.append("</svg>")
    return "".join(out)


def _path(points: list[_Box], vertical: bool) -> tuple[str, tuple[float, float]]:
    first, last = points[0], points[-1]
    coords = [
        (first.x, first.y + first.h / 2) if vertical else (first.x + first.w / 2, first.y),
        *((p.x, p.y) for p in points[1:-1]),
        (last.x, last.y - last.h / 2) if vertical else (last.x - last.w / 2, last.y),
    ]
    parts = [f"M{_num(coords[0][0])} {_num(coords[0][1])}"]
    for (ax, ay), (bx, by) in pairwise(coords):
        if vertical:
            bend = (by - ay) / 2
            c1, c2 = (ax, ay + bend), (bx, by - bend)
        else:
            bend = (bx - ax) / 2
            c1, c2 = (ax + bend, ay), (bx - bend, by)
        parts.append(
            f"C{_num(c1[0])} {_num(c1[1])} {_num(c2[0])} {_num(c2[1])} {_num(bx)} {_num(by)}"
        )
    middle = ((coords[0][0] + coords[1][0]) / 2, (coords[0][1] + coords[1][1]) / 2)
    return "".join(parts), middle


def _shape(node: _Node, box: _Box) -> str:
    classes = " ".join(["n", *sorted(node.classes)])
    left, top = box.x - box.w / 2, box.y - box.h / 2
    if node.shape == "doc":
        lip = _DOC_LIP
        outline = (
            f'<path d="M{_num(left)} {_num(top + lip)}'
            f"C{_num(left)} {_num(top - lip / 3)} {_num(left + box.w)} {_num(top - lip / 3)} "
            f"{_num(left + box.w)} {_num(top + lip)}V{_num(top + box.h - lip)}"
            f"C{_num(left + box.w)} {_num(top + box.h + lip / 3)} {_num(left)} "
            f'{_num(top + box.h + lip / 3)} {_num(left)} {_num(top + box.h - lip)}Z"/>'
            f'<path class="lip" d="M{_num(left)} {_num(top + lip)}'
            f"C{_num(left)} {_num(top + lip * 2.2)} {_num(left + box.w)} "
            f'{_num(top + lip * 2.2)} {_num(left + box.w)} {_num(top + lip)}"/>'
        )
    else:
        radius = box.h / 2 if node.shape == "pill" else 10.0
        outline = (
            f'<rect x="{_num(left)}" y="{_num(top)}" width="{_num(box.w)}" '
            f'height="{_num(box.h)}" rx="{_num(radius)}"/>'
        )
    offset = _DOC_LIP / 2 if node.shape == "doc" else 0.0
    first = box.y + offset - (len(node.lines) - 1) * _LINE / 2
    text = "".join(
        f'<text x="{_num(box.x)}" y="{_num(first + index * _LINE)}">{escape(line)}</text>'
        for index, line in enumerate(node.lines)
    )
    return f'<g class="{classes}">{outline}{text}</g>'


_STYLE = (
    "<style>"
    ".dg{margin:28px 0 32px;container-type:inline-size;overflow-x:auto}"
    ".dg svg{display:block;height:auto;margin:0 auto}"
    ".dg .dg-n{display:none}"
    ".dg text{text-anchor:middle;dominant-baseline:central}"
    ".dg .n rect,.dg .n path{fill:var(--panel,#fff);stroke:var(--line,#E6E8EF);stroke-width:1.2}"
    ".dg .n .lip{fill:none}"
    ".dg .n text{fill:var(--ink,#0F1115);font:500 13px var(--sans,system-ui,sans-serif)}"
    ".dg .accent rect,.dg .accent path{fill:var(--brand-soft,#F0ECFF);stroke:var(--brand,#5B3DF5)}"
    ".dg .accent .lip{fill:none}"
    ".dg .accent text{fill:var(--brand-ink,#4A2FE0)}"
    ".dg .cmd text{font:400 12.5px var(--mono,ui-monospace,monospace)}"
    ".dg .muted rect,.dg .muted path{stroke-dasharray:4 3}"
    ".dg .muted text{fill:var(--muted,#566070)}"
    ".dg .e{fill:none;stroke:var(--faint,#8A92A0);stroke-width:1.4}"
    ".dg .e.dot{stroke-dasharray:3 4}"
    ".dg .e.main{stroke:var(--brand,#5B3DF5);stroke-width:1.8;stroke-dasharray:7 5;"
    "animation:dg-flow 1.4s linear infinite}"
    ".dg .h{fill:var(--faint,#8A92A0)}.dg .h.main{fill:var(--brand,#5B3DF5)}"
    ".dg .g rect{fill:color-mix(in srgb,var(--brand-soft,#F0ECFF) 45%,transparent);"
    "stroke:var(--line,#E6E8EF)}"
    ".dg .g text{text-anchor:start;font:500 11px var(--mono,ui-monospace,monospace);"
    "letter-spacing:.08em;text-transform:uppercase;fill:var(--muted,#566070)}"
    ".dg .l rect{fill:var(--bg,#FBFBFD)}"
    ".dg .l text{font:400 11.5px var(--mono,ui-monospace,monospace);fill:var(--muted,#566070)}"
    "@keyframes dg-flow{to{stroke-dashoffset:-24}}"
    "@media (prefers-reduced-motion:reduce){.dg .e.main{animation:none}}"
    "</style>"
)


def figure(source: str, index: int = 0) -> str:
    """Render one diagram as a `<figure>`: its SVG drawings and the style they need.

    A left-to-right diagram gets a second, top-to-bottom drawing that replaces it
    once its figure is too narrow to show it at `_SWITCH_SCALE`. Below `_MIN_SCALE`
    a drawing scrolls inside its figure rather than shrinking its text further.
    """
    graph = parse(source)
    layers, chains = _layers(graph, _ranks(graph))
    uid = "dg" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:6] + str(index)
    if graph.direction == "TD":
        tall = _place(graph, layers, vertical=True, compact=False)
        drawings = [_svg(graph, tall, chains, _Variant(f"{uid}w", "dg-w", True, _MIN_SCALE))]
        switch = ""
    else:
        wide = _place(graph, layers, vertical=False, compact=False)
        tall = _place(graph, layers, vertical=True, compact=True)
        drawings = [
            _svg(graph, wide, chains, _Variant(f"{uid}w", "dg-w", False, 0.0)),
            _svg(graph, tall, chains, _Variant(f"{uid}n", "dg-n", True, _MIN_SCALE)),
        ]
        limit = _num(wide.width * _SWITCH_SCALE)
        switch = (
            f"<style>@container (max-width:{limit}px){{"
            f"#{uid} .dg-w{{display:none}}#{uid} .dg-n{{display:block}}}}</style>"
        )
    return f'<figure class="dg" id="{uid}">{_STYLE}{switch}{"".join(drawings)}</figure>'
