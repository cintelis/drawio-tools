"""Check a .drawio file for the problems that make generated diagrams look wrong.

Works on any draw.io file, not only ones drawgen wrote: roles come from the
`drawgenRole=` style key when present and from the style otherwise.

Errors (the file is broken or misleading):
  duplicate-id, missing-parent, dangling-edge, out-of-page, overlap
Warnings (it opens fine but reads badly):
  edge-through-shape, label-overflow

The two warnings are estimates. draw.io routes orthogonal edges itself when the
diagram is drawn, so the checker approximates the route from the ports and
waypoints; and it has no font metrics, so text width is estimated from
character counts. Both err toward reporting, and fixing a warning usually
means a waypoint or a wider box.
"""
from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

PORTS = {"exit": None, "entry": None}


@dataclass
class Issue:
    page: str
    severity: str  # "error" | "warning"
    code: str
    cell: str
    message: str

    def __str__(self) -> str:
        return f"[{self.page}] {self.severity} {self.code} {self.cell}: {self.message}"


@dataclass
class Report:
    path: str
    pages: int
    cells: int
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def ok(self, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)

    def to_dict(self) -> dict:
        return {
            "path": self.path, "pages": self.pages, "cells": self.cells,
            "errors": len(self.errors), "warnings": len(self.warnings),
            "issues": [asdict(i) for i in self.issues],
        }

    def to_text(self) -> str:
        lines = [str(i) for i in self.issues]
        lines.append(f"{self.path}: {self.pages} page(s), {self.cells} cells, "
                     f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ------------------------------------------------------------------ parsing
def _style(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (s or "").split(";"):
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k] = v if _ else "1"
    return out


def _role(st: dict[str, str], raw: str) -> str:
    if "drawgenRole" in st:
        return st["drawgenRole"]
    if raw.startswith("text;") or st.get("text") == "1":
        return "text"
    if "swimlane" in st or st.get("container") == "1" or st.get("group") == "1":
        return "zone"
    return "node"


@dataclass
class _V:
    id: str
    parent: str
    x: float
    y: float
    w: float
    h: float
    role: str
    style: dict
    value: str

    def rect(self, inset: float = 0.0):
        return (self.x + inset, self.y + inset, self.x + self.w - inset, self.y + self.h - inset)


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def check_file(path: str) -> Report:
    with open(path, encoding="utf-8") as fh:
        return check_xml(fh.read(), path=str(path))


def check_xml(xml: str, path: str = "<memory>") -> Report:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return Report(path, 0, 0, [Issue("-", "error", "malformed-xml", "-", str(e))])
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root]
    issues: list[Issue] = []
    cells_total = 0
    for i, d in enumerate(diagrams):
        name = d.get("name") or f"page {i + 1}"
        model = d.find("mxGraphModel") if d.tag != "mxGraphModel" else d
        if model is None:
            issues.append(Issue(name, "error", "unreadable-page", "-",
                                "page has no plain mxGraphModel (compressed? re-save uncompressed in draw.io)"))
            continue
        cells = model.findall(".//mxCell")
        cells_total += len(cells)
        issues += _check_page(name, model, cells)
    return Report(path, len(diagrams), cells_total, issues)


# ------------------------------------------------------------------- checks
def _check_page(name: str, model, cells) -> list[Issue]:
    out: list[Issue] = []
    pw, ph = _f(model.get("pageWidth")), _f(model.get("pageHeight"))

    ids: dict[str, ET.Element] = {}
    for c in cells:
        cid = c.get("id") or ""
        if cid in ids:
            out.append(Issue(name, "error", "duplicate-id", cid, "two cells share this id; draw.io keeps one"))
        ids[cid] = c

    raw: dict[str, _V] = {}
    edges = []
    for c in cells:
        cid = c.get("id") or ""
        parent = c.get("parent")
        if cid not in ("0",) and parent is not None and parent not in ids:
            out.append(Issue(name, "error", "missing-parent", cid, f"parent {parent!r} does not exist"))
        if c.get("edge") == "1":
            edges.append(c)
            continue
        if c.get("vertex") != "1":
            continue
        g = c.find("mxGeometry")
        if g is None:
            continue
        st_raw = c.get("style") or ""
        st = _style(st_raw)
        raw[cid] = _V(cid, parent or "1", _f(g.get("x")), _f(g.get("y")), _f(g.get("width")),
                      _f(g.get("height")), _role(st, st_raw), st, c.get("value") or "")

    # Absolute coordinates: children of a vertex are stored relative to it.
    def absolute(v: _V, seen=()) -> tuple[float, float]:
        if v.parent in raw and v.parent not in seen:
            px, py = absolute(raw[v.parent], seen + (v.id,))
            return v.x + px, v.y + py
        return v.x, v.y

    verts: dict[str, _V] = {}
    for cid, v in raw.items():
        ax, ay = absolute(v)
        verts[cid] = _V(cid, v.parent, ax, ay, v.w, v.h, v.role, v.style, v.value)

    def ancestors(cid: str) -> set[str]:
        seen, cur = set(), verts.get(cid)
        while cur and cur.parent in verts and cur.parent not in seen:
            seen.add(cur.parent)
            cur = verts[cur.parent]
        return seen

    # Bounds.
    if pw and ph:
        for v in verts.values():
            if v.x < -0.5 or v.y < -0.5 or v.x + v.w > pw + 0.5 or v.y + v.h > ph + 0.5:
                out.append(Issue(name, "error", "out-of-page", v.id,
                                 f"({v.x:.0f},{v.y:.0f} {v.w:.0f}x{v.h:.0f}) is outside the {pw:.0f}x{ph:.0f} page"))

    # Overlaps between solid shapes. Containers hold things by design, text and
    # legend parts sit on top of other cells by design, and a cell never
    # overlaps its own ancestors.
    solid = [v for v in verts.values() if v.role in ("node", "entity", "shape", "legend-box")]
    for a_i in range(len(solid)):
        for b_i in range(a_i + 1, len(solid)):
            a, b = solid[a_i], solid[b_i]
            if a.id in ancestors(b.id) or b.id in ancestors(a.id):
                continue
            ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
            oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
            if ox > 4 and oy > 4:
                out.append(Issue(name, "error", "overlap", f"{a.id},{b.id}",
                                 f"shapes overlap by {ox:.0f}x{oy:.0f}px"))

    # Edges.
    for e in edges:
        eid = e.get("id") or ""
        src, tgt = e.get("source"), e.get("target")
        if src is None and tgt is None:
            continue  # free-standing line (legend swatch)
        missing = [x for x in (src, tgt) if x is None or x not in ids]
        if missing:
            out.append(Issue(name, "error", "dangling-edge", eid,
                             f"endpoint(s) {missing} do not exist; the edge floats or vanishes"))
            continue
        if src not in verts or tgt not in verts:
            continue
        route = _route(verts[src], verts[tgt], _style(e.get("style") or ""), e)
        skip = {src, tgt} | ancestors(src) | ancestors(tgt)
        for v in solid:
            if v.id in skip or v.id in ancestors(src) or src in ancestors(v.id) or tgt in ancestors(v.id):
                continue
            if any(_seg_hits(p, q, v.rect(inset=3)) for p, q in zip(route, route[1:])):
                out.append(Issue(name, "warning", "edge-through-shape", eid,
                                 f"{src} -> {tgt} likely crosses {v.id}; add waypoints or set exit/entry"))

    # Label fit.
    for v in verts.values():
        if v.role in ("legend", "legend-box", "title") or not v.value or v.w <= 0 or v.h <= 0:
            continue
        msg = _label_overflow(v)
        if msg:
            out.append(Issue(name, "warning", "label-overflow", v.id, msg))
    return out


def _port(v: _V, fx: float, fy: float):
    return (v.x + v.w * fx, v.y + v.h * fy)


def _route(s: _V, t: _V, st: dict, e) -> list[tuple[float, float]]:
    """Approximate the drawn route: ports, waypoints, and orthogonal elbows between them.

    The first leg leaves along the side it exits from and the last leg arrives
    perpendicular to the side it enters, which is what draw.io's orthogonal
    router does and what makes an arrowhead point into the shape.
    """
    def pinned(key: str):
        if f"{key}X" in st and f"{key}Y" in st:
            return _f(st[f"{key}X"]), _f(st[f"{key}Y"])
        return None

    def side_of(fx: float, fy: float) -> bool:
        return fx in (0, 1) and fy not in (0, 1)

    def end(v: _V, key: str, other: _V, other_key: str):
        fixed = pinned(key)
        if fixed:
            fx, fy = fixed
            return _port(v, fx, fy), side_of(fx, fy)
        other_fixed = pinned(other_key)
        if other_fixed:
            # Leave toward the other end's pinned port, in the direction that port
            # faces, the way draw.io's orthogonal router does; comparing centres
            # instead picks a side that runs the edge through its neighbours.
            ox, oy = _port(other, *other_fixed)
            if side_of(*other_fixed):
                if ox >= v.x + v.w:
                    return _port(v, 1, 0.5), True
                if ox <= v.x:
                    return _port(v, 0, 0.5), True
            else:
                if oy >= v.y + v.h:
                    return _port(v, 0.5, 1), False
                if oy <= v.y:
                    return _port(v, 0.5, 0), False
            tx, ty = ox, oy
        else:
            tx, ty = other.x + other.w / 2, other.y + other.h / 2
        dx, dy = tx - (v.x + v.w / 2), ty - (v.y + v.h / 2)
        if abs(dx) >= abs(dy):
            return _port(v, 1 if dx > 0 else 0, 0.5), True
        return _port(v, 0.5, 1 if dy > 0 else 0), False

    (a, a_h), (b, b_h) = end(s, "exit", t, "entry"), end(t, "entry", s, "exit")
    g = e.find("mxGeometry")
    arr = g.find("Array") if g is not None else None
    mids = [(_f(p.get("x")), _f(p.get("y"))) for p in arr.findall("mxPoint")] if arr is not None else []
    pts = [a, *mids, b]
    if st.get("edgeStyle", "none") == "none":
        return pts
    out = [a]
    for i, q in enumerate(pts[1:], start=1):
        p = out[-1]
        if abs(p[0] - q[0]) > 1 and abs(p[1] - q[1]) > 1:
            first, last = i == 1, i == len(pts) - 1
            leave_h = a_h if first else abs(q[0] - p[0]) >= abs(q[1] - p[1])
            arrive_h = b_h if last else leave_h
            if leave_h and arrive_h:
                mx = (p[0] + q[0]) / 2
                out += [(mx, p[1]), (mx, q[1])]
            elif not leave_h and not arrive_h:
                my = (p[1] + q[1]) / 2
                out += [(p[0], my), (q[0], my)]
            elif leave_h:
                out.append((q[0], p[1]))
            else:
                out.append((p[0], q[1]))
        out.append(q)
    return out


def _seg_hits(p, q, rect) -> bool:
    """Liang-Barsky: does segment p-q pass through the rectangle's interior?"""
    x0, y0, x1, y1 = rect
    if x1 <= x0 or y1 <= y0:
        return False
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk < 0:
                return False
            continue
        r = qk / pk
        if pk < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return t1 - t0 > 1e-6


# Measured against draw.io 31 renders of Helvetica labels: mixed-case text runs
# about 0.44-0.49 em per character, bold a little wider. With the 5% tolerance
# below the estimate is slightly generous, so a
# warning means "probably clipped", not "might be tight".
EM_REGULAR, EM_BOLD, LINE_HEIGHT = 0.46, 0.5, 1.2


def text_width(text: str, size: float, bold: bool = False) -> float:
    return len(text) * size * (EM_BOLD if bold else EM_REGULAR)


_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>|</div>|</p>", re.I)
_SIZE = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)px", re.I)


def _label_overflow(v: _V) -> str | None:
    size = _f(v.style.get("fontSize")) or 11
    bold = (int(_f(v.style.get("fontStyle"))) & 1) == 1
    is_html = v.style.get("html") == "1"
    text = v.value
    lines_html = _BR.split(text) if is_html else text.split("\n")
    wrap = v.style.get("whiteSpace") == "wrap"
    pad_x = _f(v.style.get("spacingLeft")) + _f(v.style.get("spacingRight")) + 8
    shape = v.style.get("shape", "")
    avail_w = v.w - pad_x
    if "rhombus" in v.style:
        avail_w *= 0.6
    if v.role == "zone" or "swimlane" in v.style:
        # Only the header has to fit.
        lines_html = lines_html[:1]
    avail_h = (_f(v.style.get("startSize")) or 30) if (v.role == "zone" or "swimlane" in v.style) else v.h - 4
    if shape == "cylinder3":
        avail_h -= 20
    total_h = 0.0
    for raw_line in lines_html:
        m = _SIZE.search(raw_line)
        line_size = _f(m.group(1)) if m else size
        line_bold = bold or "<b>" in raw_line.lower()
        plain = html.unescape(_TAG.sub("", raw_line)) if is_html else raw_line
        width = text_width(plain, line_size, line_bold)
        line_h = line_size * LINE_HEIGHT
        if width > avail_w:
            if not wrap or avail_w <= 0:
                return f"text is about {width:.0f}px wide in a {avail_w:.0f}px box and does not wrap; widen it"
            total_h += math.ceil(width / avail_w) * line_h
        else:
            total_h += line_h
    if total_h > avail_h * 1.05 + 2:
        return f"text needs about {total_h:.0f}px of height, the box has {avail_h:.0f}px; enlarge it or shorten the label"
    return None
