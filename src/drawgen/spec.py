"""Declarative diagrams: a YAML/JSON spec -> Document.

Claude writes data, not code, so a spec is reviewable, diffable and needs no
interpreter. Every mistake is reported with the path to the offending entry
and the values that would have been accepted, because the reader is usually a
model that will fix it and try again.

    title: Order flow
    subtitle: Optional one-liner
    width: 1400            # optional; omit both to size the page to the content
    height: 900
    layout: auto           # only nodes WITHOUT x/y are placed; omit for manual
    direction: right       # auto layout: right (default) or down
    zones:
      - {id: aws, label: AWS, x: 300, y: 120, w: 700, h: 500, colour: amber}
    nodes:
      - {id: user, label: Shopper, kind: actor, x: 40, y: 300}
      - {id: api, label: Orders API, kind: service, sub: "Node 24", zone: aws, x: 340, y: 200}
      - {id: db, label: Postgres, kind: datastore, zone: aws, x: 700, y: 200}
    entities:
      - {id: order, name: orders, fields: ["PK id", "FK customer_id", "total"], x: 40, y: 600}
    edges:
      - {from: user, to: api, label: HTTPS}
      - {from: api, to: db, label: SQL, style: data, exit: right, entry: left}
    texts:
      - {id: footnote, label: "Figures in AUD", x: 40, y: 860, w: 300}
    legend: {x: 1180, y: 120}   # or true: placed right of the content; kinds/edges default to those used

Leave out width and height and the page is sized to its content.

A file may hold several pages: `pages: [ {title: ..., nodes: ...}, ... ]`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .diagram import Diagram, DiagramError, Document
from .theme import EDGE_STYLES, KINDS, NODE_H, NODE_W, ZONE_COLOURS


class SpecError(ValueError):
    pass


PAGE_KEYS = {"title", "subtitle", "width", "height", "id", "layout", "direction", "zones", "nodes",
             "entities", "edges", "texts", "legend"}
ZONE_KEYS = {"id", "label", "x", "y", "w", "h", "colour", "color"}
NODE_KEYS = {"id", "label", "kind", "sub", "zone", "x", "y", "w", "h"}
ENTITY_KEYS = {"id", "name", "fields", "x", "y", "w", "zone"}
EDGE_KEYS = {"from", "to", "label", "style", "exit", "entry", "points", "both", "curved", "arrow", "id"}
TEXT_KEYS = {"id", "label", "x", "y", "w", "h", "size", "bold", "colour", "color", "align"}
LEGEND_KEYS = {"x", "y", "kinds", "edges"}


def load(text: str, fmt: str | None = None) -> dict:
    """Parse YAML or JSON text. JSON is tried first because it is valid YAML anyway."""
    if fmt != "yaml":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if fmt == "json":
                raise
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - yaml is a dependency
        raise SpecError("YAML specs need PyYAML (pip install pyyaml); JSON works without it") from e
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SpecError("a spec must be a mapping at the top level")
    return data


def load_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    fmt = "json" if path.endswith(".json") else ("yaml" if path.endswith((".yaml", ".yml")) else None)
    return load(text, fmt)


def build(spec: dict | str) -> Document:
    """A spec (mapping, or YAML/JSON text) to a Document, or SpecError naming every problem."""
    if isinstance(spec, str):
        spec = load(spec)
    if not isinstance(spec, dict):
        raise SpecError("a spec must be a mapping")
    pages = spec.get("pages")
    if pages is None:
        pages = [spec]
    elif not isinstance(pages, list) or not pages:
        raise SpecError("pages: must be a non-empty list of page specs")
    doc = Document()
    errors: list[str] = []
    for i, p in enumerate(pages):
        where = f"pages[{i}]" if "pages" in spec else "spec"
        try:
            doc.add(_page(p, where, i))
        except SpecError as e:
            errors.append(str(e))
    if errors:
        raise SpecError("\n".join(errors))
    return doc


# ---------------------------------------------------------------------------
def _page(p: Any, where: str, index: int) -> Diagram:
    if not isinstance(p, dict):
        raise SpecError(f"{where}: a page must be a mapping")
    problems: list[str] = []
    _keys(p, PAGE_KEYS, where, problems)
    title = p.get("title")
    if not title:
        problems.append(f"{where}.title: required")
    width, height = int(p.get("width", 1400)), int(p.get("height", 900))
    nodes = _list(p, "nodes", where, problems)
    zones = _list(p, "zones", where, problems)
    entities = _list(p, "entities", where, problems)
    edges = _list(p, "edges", where, problems)
    texts = _list(p, "texts", where, problems)

    for i, z in enumerate(zones):
        w = f"{where}.zones[{i}]"
        _keys(z, ZONE_KEYS, w, problems)
        _need(z, ("id", "label", "x", "y", "w", "h"), w, problems)
        col = z.get("colour", z.get("color", "grey"))
        if col not in ZONE_COLOURS:
            problems.append(f"{w}.colour: {col!r} is not one of {sorted(ZONE_COLOURS)}")
    for i, n in enumerate(nodes):
        w = f"{where}.nodes[{i}]"
        _keys(n, NODE_KEYS, w, problems)
        _need(n, ("id", "label"), w, problems)
        if n.get("kind", "service") not in KINDS:
            problems.append(f"{w}.kind: {n.get('kind')!r} is not one of {sorted(KINDS)}")
        if ("x" in n) != ("y" in n):
            problems.append(f"{w}: give both x and y, or neither (auto layout)")
        if "x" not in n and p.get("layout") != "auto":
            problems.append(f"{w}: no x/y; add coordinates or set layout: auto on the page")
        if "x" not in n and n.get("zone"):
            problems.append(f"{w}: a node in a zone needs x/y; auto layout only places top-level nodes")
    for i, e in enumerate(entities):
        w = f"{where}.entities[{i}]"
        _keys(e, ENTITY_KEYS, w, problems)
        _need(e, ("id", "name", "fields", "x", "y"), w, problems)
    for i, e in enumerate(edges):
        w = f"{where}.edges[{i}]"
        _keys(e, EDGE_KEYS, w, problems)
        _need(e, ("from", "to"), w, problems)
        if e.get("style", "sync") not in EDGE_STYLES:
            problems.append(f"{w}.style: {e.get('style')!r} is not one of {sorted(EDGE_STYLES)}")
        for k in ("exit", "entry"):
            if k in e and e[k] not in ("top", "bottom", "left", "right"):
                problems.append(f"{w}.{k}: {e[k]!r} must be top, bottom, left or right")
    for i, t in enumerate(texts):
        w = f"{where}.texts[{i}]"
        _keys(t, TEXT_KEYS, w, problems)
        _need(t, ("id", "label", "x", "y"), w, problems)
    legend = p.get("legend")
    if isinstance(legend, dict):
        _keys(legend, LEGEND_KEYS, f"{where}.legend", problems)

    ids = [x.get("id") for x in zones + nodes + entities + texts if isinstance(x, dict)]
    seen, dupes = set(), set()
    for i in ids:
        (dupes if i in seen else seen).add(i)
    for d in sorted(dupes, key=str):
        problems.append(f"{where}: id {d!r} is used more than once")
    known = set(ids)
    for i, e in enumerate(edges):
        for k in ("from", "to"):
            if isinstance(e, dict) and e.get(k) is not None and e.get(k) not in known:
                problems.append(f"{where}.edges[{i}].{k}: no node, zone, entity or text has id {e.get(k)!r}")
    zone_ids = {z.get("id") for z in zones if isinstance(z, dict)}
    for coll, name in ((nodes, "nodes"), (entities, "entities")):
        for i, n in enumerate(coll):
            if isinstance(n, dict) and n.get("zone") and n["zone"] not in zone_ids:
                problems.append(f"{where}.{name}[{i}].zone: no zone has id {n['zone']!r}")
    if problems:
        raise SpecError("\n".join(problems))

    if p.get("layout") == "auto":
        _auto_layout(nodes, edges, width, height, p.get("direction", "right"),
                     top=100 if p.get("subtitle") else 80)

    d = Diagram(str(title), width, height, p.get("subtitle"), page_id=str(p.get("id") or f"page-{index + 1}"))
    try:
        for z in zones:
            d.zone(str(z["id"]), str(z["label"]), z["x"], z["y"], z["w"], z["h"],
                   z.get("colour", z.get("color", "grey")))
        for n in nodes:
            d.node(str(n["id"]), str(n["label"]), n["x"], n["y"], n.get("w", NODE_W), n.get("h", NODE_H),
                   n.get("kind", "service"), n.get("sub"), n.get("zone"))
        for e in entities:
            d.entity(str(e["id"]), str(e["name"]), [str(f) for f in e["fields"]], e["x"], e["y"],
                     e.get("w", 230), e.get("zone"))
        for t in texts:
            d.text(str(t["id"]), str(t["label"]), t["x"], t["y"], t.get("w", 300), t.get("h", 24),
                   t.get("size", 11), bool(t.get("bold", False)), t.get("colour", t.get("color", "#4B5563")),
                   t.get("align", "left"))
        for e in edges:
            pts = [tuple(pt) for pt in e["points"]] if e.get("points") else None
            d.edge(str(e["from"]), str(e["to"]), str(e.get("label", "")), e.get("style", "sync"),
                   e.get("exit"), e.get("entry"), pts, e.get("arrow", "block"), bool(e.get("both", False)),
                   bool(e.get("curved", False)), eid=e.get("id"))
        if legend:
            lg = legend if isinstance(legend, dict) else {}
            if "x" in lg and "y" in lg:
                lx, ly = lg["x"], lg["y"]
            else:
                lx, ly = d.legend_slot()
            d.legend(lx, ly, lg.get("kinds"), lg.get("edges"))
        # A page whose size the author did not set is sized to what is on it.
        if "width" not in p and "height" not in p:
            d.fit_page()
    except DiagramError as e:
        raise SpecError(f"{where}: {e}") from e
    return d


def _auto_layout(nodes: list, edges: list, width: int, height: int, direction: str, top: int) -> None:
    """Layered placement for nodes without coordinates: rank by longest path from a source."""
    free = [n for n in nodes if "x" not in n]
    if not free:
        return
    ids = {n["id"] for n in free}
    succ = defaultdict(list)
    indeg = {i: 0 for i in ids}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a in ids and b in ids and a != b:
            succ[a].append(b)
            indeg[b] += 1
    rank = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0] or [free[0]["id"]]
    order_seen = 0
    # Kahn's algorithm; anything left in a cycle keeps the rank it reached.
    while queue and order_seen < len(ids) * 4:
        cur = queue.pop(0)
        order_seen += 1
        for nxt in succ[cur]:
            rank[nxt] = max(rank[nxt], rank[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    layers = defaultdict(list)
    for n in free:  # spec order within a layer keeps the author's intent
        layers[rank[n["id"]]].append(n)
    gap_major, gap_minor, margin = 80, 40, 40
    for r, layer in sorted(layers.items()):
        for j, n in enumerate(layer):
            w, h = n.get("w", NODE_W), n.get("h", NODE_H)
            if direction == "down":
                n["x"], n["y"] = margin + j * (w + gap_minor), top + r * (h + gap_major)
            else:
                n["x"], n["y"] = margin + r * (w + gap_major), top + j * (h + gap_minor)


def _list(p: dict, key: str, where: str, problems: list) -> list:
    v = p.get(key) or []
    if not isinstance(v, list):
        problems.append(f"{where}.{key}: must be a list")
        return []
    return v


def _keys(obj: Any, allowed: set, where: str, problems: list) -> None:
    if not isinstance(obj, dict):
        problems.append(f"{where}: must be a mapping")
        return
    for k in obj:
        if k not in allowed:
            problems.append(f"{where}: unknown key {k!r}; allowed: {sorted(allowed)}")


def _need(obj: Any, keys, where: str, problems: list) -> None:
    if not isinstance(obj, dict):
        return
    for k in keys:
        if obj.get(k) is None:
            problems.append(f"{where}.{k}: required")
