"""Build draw.io (mxGraph XML) files from Python.

Two layers on one page model:

- The THEMED API (`node`, `zone`, `entity`, `edge`, `text`, `legend`) places
  components by kind, so colour, shape and type sizes come from `theme.py`.
  This is what the spec format and the MCP server drive.
- The RAW API (`add_vertex`, `add_edge`) takes a style string and HTML value as
  given, for diagrams with a palette of their own (see examples/bluefield).

Every cell id is claimed once per page; a duplicate raises instead of writing a
file draw.io opens with cells silently missing. Each cell the themed API makes
carries a `drawgenRole=` style key, which draw.io ignores and keeps, so the
checker can tell a container from a component without guessing from styles.

Coordinates are absolute page coordinates throughout. A node placed in a zone
is converted to the zone-relative geometry draw.io stores.
"""
from __future__ import annotations

import html
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, Sequence

from .theme import (
    EDGE_SIZE,
    EDGE_STYLES,
    FONT,
    KINDS,
    NODE_H,
    NODE_SIZE,
    NODE_W,
    TITLE_SIZE,
    ZONE_COLOURS,
)

PORTS = {"top": (0.5, 0), "bottom": (0.5, 1), "left": (0, 0.5), "right": (1, 0.5)}
RESERVED_IDS = {"0", "1"}


def esc(text: str) -> str:
    """Plain text to label HTML; '\\n' becomes <br> (HTML labels ignore raw newlines)."""
    return "<br>".join(html.escape(part, quote=False) for part in str(text).split("\n"))


def _attr(value: str) -> str:
    return html.escape(str(value), quote=True)


class DiagramError(ValueError):
    """A diagram that would be malformed or misleading if written."""


@dataclass
class Box:
    id: str
    x: float
    y: float
    w: float
    h: float
    role: str
    parent: str = "1"


class Diagram:
    """One draw.io page. Save it alone, or add several to a `Document`."""

    def __init__(
        self,
        name: str,
        width: int = 1400,
        height: int = 900,
        subtitle: str | None = None,
        *,
        page_id: str | None = None,
        show_title: bool = True,
    ) -> None:
        self.name = name
        self.width = width
        self.height = height
        self.subtitle = subtitle
        self.page_id = page_id or "page-1"
        self._cells: list[str] = []
        self._ids: set[str] = set()
        self._boxes: dict[str, Box] = {}
        self._edge_n = 0
        self._title_w = width - 60
        self.kinds_used: list[str] = []
        self.edge_styles_used: list[str] = []
        if show_title:
            self.add_vertex(
                "title", esc(name),
                f"text;html=1;fontFamily={FONT};fontSize={TITLE_SIZE};fontStyle=1;fontColor=#111827;"
                "align=left;verticalAlign=middle;drawgenRole=title;",
                30, 20, width - 60, 32, role="title",
            )
            if subtitle:
                self.add_vertex(
                    "subtitle", esc(subtitle),
                    f"text;html=1;fontFamily={FONT};fontSize=12;fontColor=#4B5563;"
                    "align=left;verticalAlign=top;whiteSpace=wrap;drawgenRole=title;",
                    30, 52, width - 60, 36, role="title",
                )

    # ------------------------------------------------------------- raw API
    def claim(self, cid: str) -> str:
        cid = str(cid)
        if not cid or cid in RESERVED_IDS:
            raise DiagramError(f"cell id {cid!r} is empty or reserved (0 and 1 belong to draw.io)")
        if cid in self._ids:
            raise DiagramError(f"duplicate cell id {cid!r} on page {self.name!r}")
        self._ids.add(cid)
        return cid

    def has(self, cid: str) -> bool:
        return cid in self._ids

    def add_vertex(self, cid, value_html, style, x, y, w, h, parent: str = "1", role: str = "shape") -> str:
        """A vertex with a raw style and an HTML value. x/y are relative to `parent`."""
        self.claim(cid)
        if parent != "1" and parent not in self._ids:
            raise DiagramError(f"cell {cid!r}: parent {parent!r} does not exist (add it first)")
        self._cells.append(
            f'<mxCell id="{_attr(cid)}" value="{_attr(value_html)}" style="{_attr(style)}" '
            f'vertex="1" parent="{_attr(parent)}">'
            f'<mxGeometry x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" as="geometry"/></mxCell>'
        )
        ax, ay = x, y
        if parent in self._boxes:
            ax, ay = x + self._boxes[parent].x, y + self._boxes[parent].y
        self._boxes[cid] = Box(cid, ax, ay, w, h, role, parent)
        return cid

    def add_edge(self, cid, src, tgt, style, points: Iterable[tuple[float, float]] | None = None,
                 value_html: str = "") -> str:
        """An edge between two existing cells, with optional absolute waypoints."""
        self.claim(cid)
        for end in (src, tgt):
            if end not in self._ids:
                raise DiagramError(f"edge {cid!r}: endpoint {end!r} does not exist (add it before the edge)")
        pts = ""
        if points:
            pts = '<Array as="points">' + "".join(
                f'<mxPoint x="{_num(px)}" y="{_num(py)}"/>' for px, py in points) + "</Array>"
        self._cells.append(
            f'<mxCell id="{_attr(cid)}" value="{_attr(value_html)}" style="{_attr(style)}" edge="1" '
            f'parent="1" source="{_attr(src)}" target="{_attr(tgt)}">'
            f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>'
        )
        return cid

    # --------------------------------------------------------- themed API
    def zone(self, zid: str, label: str, x, y, w, h, colour: str = "grey") -> str:
        """A titled container (swimlane). Nodes placed in it keep absolute coordinates."""
        if colour not in ZONE_COLOURS:
            raise DiagramError(f"zone {zid!r}: unknown colour {colour!r}; use one of {sorted(ZONE_COLOURS)}")
        fill, stroke = ZONE_COLOURS[colour]
        style = (
            f"swimlane;html=1;startSize=30;rounded=1;arcSize=4;fontFamily={FONT};fontSize=13;"
            f"fontStyle=1;fillColor={fill};swimlaneFillColor={fill};strokeColor={stroke};"
            f"fontColor=#1F2937;align=left;spacingLeft=12;collapsible=0;container=1;drawgenRole=zone;"
        )
        return self.add_vertex(zid, esc(label), style, x, y, w, h, role="zone")

    def node(self, nid: str, label: str, x: float, y: float, w: float = NODE_W, h: float = NODE_H,
             kind: str = "service", sub: str | None = None, zone: str | None = None) -> str:
        """A themed component at absolute page coordinates."""
        if kind not in KINDS:
            raise DiagramError(f"node {nid!r}: unknown kind {kind!r}; use one of {sorted(KINDS)}")
        k = KINDS[kind]
        text = f"<b>{esc(label)}</b>"
        if sub:
            sub_col = {"terminal": "#D1D5DB", "note": "#3D3000"}.get(kind, "#4B5563")
            sub_size = 11 if kind == "note" else 10
            text += f"<br><font style=\"font-size:{sub_size}px\" color=\"{sub_col}\">{esc(sub)}</font>"
        style = (
            f"html=1;whiteSpace=wrap;fontFamily={FONT};fontSize={NODE_SIZE};fillColor={k['fill']};"
            f"strokeColor={k['stroke']};fontColor={k['font']};strokeWidth=1.5;"
        )
        style += {
            "box": "rounded=1;arcSize=12;",
            "cylinder": "shape=cylinder3;boundedLbl=1;size=10;",
            # A horizontal cylinder drawn as one, not a rotated vertical one: draw.io
            # rotates connection ports with direction=, so "bottom" became an end.
            "queue": "shape=mxgraph.flowchart.direct_data;",
            "actor": "rounded=1;arcSize=50;",
            "pill": "rounded=1;arcSize=50;",
            "rhombus": "rhombus;",
            "note": "shape=note;size=14;align=left;spacingLeft=8;spacingRight=8;",
        }.get(k["shape"], "")
        if k["shape"] == "note" and not sub:
            text = esc(label)
        if k.get("dashed"):
            style += "dashed=1;dashPattern=6 4;"
        style += "drawgenRole=node;"
        parent, px, py = self._in_zone(zone, x, y, nid)
        self.add_vertex(nid, text, style, px, py, w, h, parent=parent, role="node")
        if kind not in self.kinds_used:
            self.kinds_used.append(kind)
        return nid

    def entity(self, nid: str, name: str, fields: Sequence[str], x, y, w: float = 230,
               zone: str | None = None) -> str:
        """An ER table: header plus one row per field. Prefix 'PK ' / 'FK ' to mark keys."""
        row_h = 20
        h = 30 + row_h * len(fields)
        stroke = KINDS["datastore"]["stroke"]
        style = (
            f"swimlane;html=1;fontStyle=1;startSize=30;fontFamily={FONT};fontSize={NODE_SIZE};"
            f"fillColor={stroke};swimlaneFillColor=#FFFFFF;strokeColor={stroke};"
            f"fontColor=#FFFFFF;rounded=1;arcSize=4;collapsible=0;childLayout=stackLayout;"
            f"horizontal=1;resizeParent=1;drawgenRole=entity;"
        )
        parent, px, py = self._in_zone(zone, x, y, nid)
        self.add_vertex(nid, esc(name), style, px, py, w, h, parent=parent, role="entity")
        for i, f in enumerate(fields):
            fs = 1 if f.startswith("PK ") else (2 if f.startswith("FK ") else 0)
            self.add_vertex(
                f"{nid}_f{i}", esc(f),
                f"text;html=1;fontFamily={FONT};fontSize=11;align=left;verticalAlign=middle;"
                f"spacingLeft=8;fontColor=#1F2937;fontStyle={fs};strokeColor=none;fillColor=none;"
                f"drawgenRole=field;",
                0, 30 + i * row_h, w, row_h, parent=nid, role="field",
            )
        return nid

    def edge(self, src: str, dst: str, label: str = "", style: str = "sync", exit=None, entry=None,
             points: Iterable[tuple[float, float]] | None = None, arrow: str = "block",
             both: bool = False, curved: bool = False, eid: str | None = None) -> str:
        """A themed, labelled edge. exit/entry: 'top' | 'bottom' | 'left' | 'right' or (x, y) fractions."""
        if style not in EDGE_STYLES:
            raise DiagramError(f"edge {src}->{dst}: unknown style {style!r}; use one of {sorted(EDGE_STYLES)}")
        if eid is None:
            while True:
                self._edge_n += 1
                eid = f"edge-{self._edge_n}"
                if eid not in self._ids:
                    break
        s = EDGE_STYLES[style]
        st = (
            f"html=1;edgeStyle={'none' if curved else 'orthogonalEdgeStyle'};rounded=1;"
            f"orthogonalLoop=1;jettySize=auto;fontFamily={FONT};fontSize={EDGE_SIZE};"
            f"fontColor=#374151;strokeColor={s['stroke']};strokeWidth={s['width']};"
            f"endArrow={arrow};endFill=1;labelBackgroundColor=#FFFFFF;"
        )
        if both:
            st += "startArrow=block;startFill=1;"
        if s["dashed"]:
            st += "dashed=1;dashPattern=6 4;"
        if curved:
            st += "curved=1;"
        for key, port in (("exit", exit), ("entry", entry)):
            if port is None:
                continue
            if isinstance(port, str):
                if port not in PORTS:
                    raise DiagramError(f"edge {src}->{dst}: {key} {port!r} must be one of {sorted(PORTS)}")
                port = PORTS[port]
            px, py = port
            st += f"{key}X={px};{key}Y={py};{key}Dx=0;{key}Dy=0;"
        st += "drawgenRole=edge;"
        self.add_edge(eid, src, dst, st, points, esc(label) if label else "")
        if style not in self.edge_styles_used:
            self.edge_styles_used.append(style)
        return eid

    def text(self, tid: str, label: str, x, y, w: float = 300, h: float = 24, size: int = 11,
             bold: bool = False, colour: str = "#4B5563", align: str = "left") -> str:
        return self.add_vertex(
            tid, esc(label),
            f"text;html=1;fontFamily={FONT};fontSize={size};fontStyle={1 if bold else 0};"
            f"fontColor={colour};align={align};verticalAlign=middle;whiteSpace=wrap;drawgenRole=text;",
            x, y, w, h, role="text",
        )

    def legend(self, x: float, y: float, kinds: Sequence[str] | None = None,
               edges: Sequence[str] | None = None, lid: str = "legend") -> str:
        """A legend box. With no lists it shows the kinds and edge styles this page used."""
        kinds = list(self.kinds_used if kinds is None else kinds)
        edges = list(self.edge_styles_used if edges is None else edges)
        h = 36 + (len(kinds) + len(edges)) * 24
        self.add_vertex(
            lid, "<b>Legend</b>",
            f"rounded=1;arcSize=6;html=1;fillColor=#FFFFFF;strokeColor=#D1D5DB;fontFamily={FONT};"
            f"fontSize=11;align=left;verticalAlign=top;spacingLeft=10;spacingTop=6;drawgenRole=legend-box;",
            x, y, 200, h, role="legend-box",
        )
        cy = y + 30
        for k in kinds:
            c = KINDS[k]
            self.add_vertex(
                f"{lid}_k_{k}", "",
                f"rounded=1;arcSize=20;fillColor={c['fill']};strokeColor={c['stroke']};"
                f"{'dashed=1;' if c.get('dashed') else ''}drawgenRole=legend;",
                x + 10, cy + 3, 26, 16, role="legend",
            )
            self.add_vertex(
                f"{lid}_kt_{k}", esc(c["label"]),
                f"text;html=1;fontFamily={FONT};fontSize=10;fontColor=#4B5563;align=left;"
                f"verticalAlign=middle;drawgenRole=legend;",
                x + 44, cy, 150, 22, role="legend",
            )
            cy += 24
        for e in edges:
            s = EDGE_STYLES[e]
            cid = self.claim(f"{lid}_e_{e}")
            self._cells.append(
                f'<mxCell id="{_attr(cid)}" value="" style="endArrow=block;endFill=1;html=1;'
                f'strokeColor={s["stroke"]};strokeWidth={s["width"]};'
                f'{"dashed=1;dashPattern=6 4;" if s["dashed"] else ""}drawgenRole=legend;" edge="1" parent="1">'
                f'<mxGeometry relative="1" as="geometry"><mxPoint x="{_num(x + 10)}" y="{_num(cy + 11)}" as="sourcePoint"/>'
                f'<mxPoint x="{_num(x + 36)}" y="{_num(cy + 11)}" as="targetPoint"/></mxGeometry></mxCell>'
            )
            self.add_vertex(
                f"{lid}_et_{e}", esc(s["label"]),
                f"text;html=1;fontFamily={FONT};fontSize=10;fontColor=#4B5563;align=left;"
                f"verticalAlign=middle;drawgenRole=legend;",
                x + 44, cy, 150, 22, role="legend",
            )
            cy += 24
        return lid

    def content_bounds(self) -> tuple[float, float, float, float]:
        """(left, top, right, bottom) of every top-level shape except the title."""
        boxes = [b for b in self._boxes.values() if b.parent == "1" and b.role != "title"]
        if not boxes:
            return (0, 0, 0, 0)
        return (min(b.x for b in boxes), min(b.y for b in boxes),
                max(b.x + b.w for b in boxes), max(b.y + b.h for b in boxes))

    def fit_page(self, margin: float = 40) -> None:
        """Size the page to its content, so nothing is off-page and there is no empty acre."""
        _, _, right, bottom = self.content_bounds()
        self.width = int(max(right + margin, 480))
        self.height = int(max(bottom + margin, 240))
        for cid in ("title", "subtitle"):
            if cid in self._boxes:
                self._boxes[cid].w = self.width - 60
        self._cells = [
            c.replace(f'width="{_num(self._title_w)}"', f'width="{_num(self.width - 60)}"', 1)
            if c.startswith(('<mxCell id="title"', '<mxCell id="subtitle"')) else c
            for c in self._cells
        ]
        self._title_w = self.width - 60

    def legend_slot(self, gap: float = 40) -> tuple[float, float]:
        """Where a legend fits without covering anything: right of the content, at its top."""
        left, top, right, _ = self.content_bounds()
        return (right + gap, top if right else 100)

    # ------------------------------------------------------------- output
    def _in_zone(self, zone: str | None, x, y, cid: str):
        if not zone:
            return "1", x, y
        z = self._boxes.get(zone)
        if z is None or z.role != "zone":
            raise DiagramError(f"{cid!r}: zone {zone!r} does not exist (add the zone first)")
        return zone, x - z.x, y - z.y

    def diagram_xml(self) -> str:
        return (
            f'<diagram id="{_attr(self.page_id)}" name="{_attr(self.name)}">'
            f'<mxGraphModel dx="{self.width}" dy="{self.height}" grid="1" gridSize="10" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{self.width}" pageHeight="{self.height}" background="#FFFFFF" math="0" shadow="0">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            + "".join(self._cells)
            + "</root></mxGraphModel></diagram>"
        )

    def xml(self) -> str:
        return Document([self]).xml()

    def save(self, path: str | os.PathLike) -> str:
        return Document([self]).save(path)


class Document:
    """A .drawio file: one or more pages, in tab order."""

    def __init__(self, pages: Sequence[Diagram] | None = None) -> None:
        self.pages: list[Diagram] = list(pages or [])

    def add(self, page: Diagram) -> Diagram:
        self.pages.append(page)
        return page

    def xml(self) -> str:
        ids = [p.page_id for p in self.pages]
        if len(set(ids)) != len(ids):
            raise DiagramError(f"page ids must be unique: {ids}")
        doc = ('<mxfile host="drawgen" type="device">'
               + "".join(p.diagram_xml() for p in self.pages) + "</mxfile>\n")
        ET.fromstring(doc)  # fail loudly on malformed XML before anything is written
        return doc

    def save(self, path: str | os.PathLike) -> str:
        path = os.fspath(path)
        doc = self.xml()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc)
        return path


def _num(v) -> str:
    """Geometry without a trailing '.0', so files diff cleanly between runs."""
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:.2f}".rstrip("0")
