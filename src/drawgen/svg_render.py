"""A small mxGraph -> SVG renderer, standard library only.

Not a replacement for draw.io's engine: it draws the vocabulary drawgen emits
(rectangles, rounded boxes and pills, swimlanes, cylinders, diamonds, notes,
HTML labels with <b>, <br> and <font>, orthogonal edges with arrowheads and
labels) closely enough to read on GitHub. Anything else in a hand-made file
still gets its box and label. The output embeds the source diagram in the
root `content` attribute, so it stays editable whichever renderer drew it.
"""
from __future__ import annotations

import html
import math
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as _x

from .check import LINE_HEIGHT, _V, _f, _role, _route, _style, text_width

_BR = re.compile(r"<br\s*/?>|</div>|</p>", re.I)
_TAG = re.compile(r"<[^>]+>")


def _xa(s: str) -> str:
    return _x(str(s), {'"': "&quot;"})


def _colour(v: str | None, default: str) -> str | None:
    if v is None:
        return default
    if v in ("none", ""):
        return None
    return v


def render_svg(drawio_xml: str, page: int = 0, embed: str | None = None) -> str:
    root = ET.fromstring(drawio_xml)
    diagrams = root.findall("diagram") if root.tag == "mxfile" else [root]
    if not diagrams:
        raise ValueError("no pages in this file")
    d = diagrams[min(page, len(diagrams) - 1)]
    model = d.find("mxGraphModel") if d.tag != "mxGraphModel" else d
    if model is None:
        raise ValueError("compressed page; re-save it uncompressed in draw.io first")
    cells = model.findall(".//mxCell")

    raw: dict[str, _V] = {}
    for c in cells:
        if c.get("vertex") != "1":
            continue
        g = c.find("mxGeometry")
        if g is None:
            continue
        st_raw = c.get("style") or ""
        st = _style(st_raw)
        raw[c.get("id")] = _V(c.get("id"), c.get("parent") or "1", _f(g.get("x")), _f(g.get("y")),
                              _f(g.get("width")), _f(g.get("height")), _role(st, st_raw), st, c.get("value") or "")

    def absolute(v: _V, depth=0):
        if v.parent in raw and depth < 50:
            px, py = absolute(raw[v.parent], depth + 1)
            return v.x + px, v.y + py
        return v.x, v.y

    verts = {}
    for cid, v in raw.items():
        ax, ay = absolute(v)
        verts[cid] = _V(cid, v.parent, ax, ay, v.w, v.h, v.role, v.style, v.value)

    pw, ph = _f(model.get("pageWidth")), _f(model.get("pageHeight"))
    if verts:
        max_x = max(v.x + v.w for v in verts.values())
        max_y = max(v.y + v.h for v in verts.values())
    else:
        max_x = max_y = 0
    W = max(pw, max_x + 16) or 800
    H = max(ph, max_y + 16) or 600
    bg = model.get("background") or "#FFFFFF"

    out: list[str] = []
    defs: dict[str, str] = {}
    for c in cells:
        cid = c.get("id")
        if c.get("vertex") == "1" and cid in verts:
            out.append(_vertex(verts[cid]))
        elif c.get("edge") == "1":
            out.append(_edge(c, verts, defs))

    content = f' content="{_xa(embed)}"' if embed else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'version="1.1" width="{W:.0f}px" height="{H:.0f}px" viewBox="0 0 {W:.0f} {H:.0f}"{content}>'
        f"<defs>{''.join(defs.values())}</defs>"
        f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="{_xa(bg)}"/>'
        + "".join(out) + "</svg>\n"
    )


# ------------------------------------------------------------------ vertices
def _dash(st: dict) -> str:
    if st.get("dashed") != "1":
        return ""
    pat = st.get("dashPattern", "3 3").replace(" ", ",")
    return f' stroke-dasharray="{_xa(pat)}"'


def _vertex(v: _V) -> str:
    st = v.style
    x, y, w, h = v.x, v.y, v.w, v.h
    is_text = "text" in st and v.role != "zone"
    fill = _colour(st.get("fillColor"), "none" if is_text else "#FFFFFF")
    stroke = _colour(st.get("strokeColor"), "none" if is_text else "#000000")
    sw = _f(st.get("strokeWidth")) or 1
    paint = f'fill="{_xa(fill or "none")}" stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"{_dash(st)}'
    parts: list[str] = []
    shape = st.get("shape", "")
    label_box = (x, y, w, h)

    if is_text or w <= 0 or h <= 0:
        pass
    elif "swimlane" in st:
        start = _f(st.get("startSize")) or 30
        body = _colour(st.get("swimlaneFillColor"), "#FFFFFF") or "none"
        r = 6 if st.get("rounded") == "1" else 0
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r}" '
                     f'fill="{_xa(body)}" stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"{_dash(st)}/>')
        parts.append(f'<path d="M{x:g},{y + start:g} h{w:g}" stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"/>')
        if fill and fill != body:
            parts.append(f'<rect x="{x + sw / 2:g}" y="{y + sw / 2:g}" width="{w - sw:g}" height="{start - sw:g}" '
                         f'rx="{max(r - 1, 0)}" fill="{_xa(fill)}"/>')
        label_box = (x, y, w, start)
    elif "rhombus" in st or shape == "rhombus":
        parts.append(f'<polygon points="{x + w / 2:g},{y:g} {x + w:g},{y + h / 2:g} {x + w / 2:g},{y + h:g} '
                     f'{x:g},{y + h / 2:g}" {paint}/>')
    elif shape in ("cylinder3", "mxgraph.flowchart.direct_data"):
        s = _f(st.get("size")) or (min(w * 0.15, h / 2) if "direct_data" in shape else 10)
        if "direct_data" in shape or st.get("direction") in ("south", "north"):
            parts.append(f'<path d="M{x + s:g},{y:g} H{x + w - s:g} A{s:g},{h / 2:g} 0 0 1 {x + w - s:g},{y + h:g} '
                         f'H{x + s:g} A{s:g},{h / 2:g} 0 0 1 {x + s:g},{y:g} Z" {paint}/>')
            parts.append(f'<path d="M{x + w - s:g},{y:g} A{s:g},{h / 2:g} 0 0 0 {x + w - s:g},{y + h:g}" fill="none" '
                         f'stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"/>')
        else:
            parts.append(f'<path d="M{x:g},{y + s:g} A{w / 2:g},{s:g} 0 0 1 {x + w:g},{y + s:g} V{y + h - s:g} '
                         f'A{w / 2:g},{s:g} 0 0 1 {x:g},{y + h - s:g} Z" {paint}/>')
            parts.append(f'<path d="M{x:g},{y + s:g} A{w / 2:g},{s:g} 0 0 0 {x + w:g},{y + s:g}" fill="none" '
                         f'stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"/>')
            label_box = (x, y + 2 * s, w, h - 3 * s)
    elif shape == "note":
        s = _f(st.get("size")) or 14
        parts.append(f'<path d="M{x:g},{y:g} H{x + w - s:g} L{x + w:g},{y + s:g} V{y + h:g} H{x:g} Z" {paint}/>')
        parts.append(f'<path d="M{x + w - s:g},{y:g} V{y + s:g} H{x + w:g}" fill="none" '
                     f'stroke="{_xa(stroke or "none")}" stroke-width="{sw:g}"/>')
    elif st.get("ellipse") == "1" or shape == "ellipse" or "ellipse" in st:
        parts.append(f'<ellipse cx="{x + w / 2:g}" cy="{y + h / 2:g}" rx="{w / 2:g}" ry="{h / 2:g}" {paint}/>')
    else:
        r = 0.0
        if st.get("rounded") == "1":
            arc = _f(st.get("arcSize")) or 15
            r = min(min(w, h) * arc / 100, min(w, h) / 2)
        parts.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:g}" {paint}/>')

    if v.value:
        parts.append(_label(v.value, st, label_box, v.role == "zone" or "swimlane" in st))
    return "".join(parts)


# -------------------------------------------------------------------- labels
def _runs(line_html: str, base_size: float, base_colour: str, base_bold: bool):
    """Split one line of label HTML into (text, size, colour, bold) runs."""
    runs = []
    size, colour, bold = base_size, base_colour, base_bold
    stack = []
    pos = 0
    for m in re.finditer(r"<(/?)(\w+)([^>]*)>", line_html):
        if m.start() > pos:
            runs.append((html.unescape(line_html[pos:m.start()]), size, colour, bold))
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if not closing:
            stack.append((tag, size, colour, bold))
            if tag in ("b", "strong"):
                bold = True
            elif tag == "font":
                sm = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", attrs)
                cm = re.search(r'color=["\']?([#\w]+)', attrs)
                size = _f(sm.group(1)) if sm else size
                colour = cm.group(1) if cm else colour
        else:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    _, size, colour, bold = stack[i]
                    del stack[i:]
                    break
        pos = m.end()
    if pos < len(line_html):
        runs.append((html.unescape(line_html[pos:]), size, colour, bold))
    return [r for r in runs if r[0]]


def _width(runs) -> float:
    return sum(text_width(t, s, b) for t, s, _, b in runs)


def _wrap(runs, avail: float):
    """Greedy word wrap across runs; returns a list of lines (each a list of runs)."""
    if avail <= 0 or _width(runs) <= avail:
        return [runs]
    lines, cur, cur_w = [], [], 0.0
    for text, s, c, b in runs:
        for word in re.split(r"(\s+)", text):
            if not word:
                continue
            ww = text_width(word, s, b)
            if cur_w + ww > avail and cur and not word.isspace():
                lines.append(cur)
                cur, cur_w = [], 0.0
            if word.isspace() and not cur:
                continue
            cur.append((word, s, c, b))
            cur_w += ww
    if cur:
        lines.append(cur)
    return lines


def _label(value: str, st: dict, box, header: bool) -> str:
    x, y, w, h = box
    size = _f(st.get("fontSize")) or 11
    colour = st.get("fontColor") or "#000000"
    bold = (int(_f(st.get("fontStyle"))) & 1) == 1
    italic = (int(_f(st.get("fontStyle"))) & 2) == 2
    family = st.get("fontFamily") or "Helvetica"
    align = st.get("align") or ("left" if header else "center")
    valign = st.get("verticalAlign") or "middle"
    sl, sr = _f(st.get("spacingLeft")), _f(st.get("spacingRight"))
    stp = _f(st.get("spacingTop"))
    is_html = st.get("html") == "1"
    src_lines = _BR.split(value) if is_html else value.split("\n")
    lines = []
    avail = w - sl - sr - 8
    for ln in src_lines:
        runs = _runs(ln, size, colour, bold) if is_html else [(ln, size, colour, bold)]
        if not runs:
            lines.append([("", size, colour, bold)])
            continue
        lines.extend(_wrap(runs, avail) if st.get("whiteSpace") == "wrap" else [runs])
    heights = [max(s for _, s, _, _ in ln) * LINE_HEIGHT for ln in lines]
    total = sum(heights)
    if valign == "top":
        cy = y + 4 + stp
    elif valign == "bottom":
        cy = y + h - total - 4
    else:
        cy = y + (h - total) / 2
    if align == "left":
        ax, anchor = x + sl + 4, "start"
    elif align == "right":
        ax, anchor = x + w - sr - 4, "end"
    else:
        ax, anchor = x + w / 2 + (sl - sr) / 2, "middle"
    bgc = st.get("labelBackgroundColor")
    out = []
    if bgc and bgc != "none":
        bw = max((_width(ln) for ln in lines), default=0) + 6
        bx = ax - bw / 2 if anchor == "middle" else (ax - 3 if anchor == "start" else ax - bw + 3)
        out.append(f'<rect x="{bx:g}" y="{cy:g}" width="{bw:g}" height="{total:g}" fill="{_xa(bgc)}"/>')
    out.append(f'<text font-family="{_xa(family)}, Arial, sans-serif" text-anchor="{anchor}"'
               f'{" font-style=\"italic\"" if italic else ""}>')
    for ln, lh in zip(lines, heights):
        cy += lh
        out.append(f'<tspan x="{ax:g}" y="{cy - lh * 0.25:g}">')
        for text, s, c, b in ln:
            out.append(f'<tspan font-size="{s:g}" fill="{_xa(c)}"{" font-weight=\"bold\"" if b else ""}>'
                       f"{_x(text)}</tspan>")
        out.append("</tspan>")
    out.append("</text>")
    return "".join(out)


# --------------------------------------------------------------------- edges
def _marker(defs: dict, colour: str, start: bool) -> str:
    key = f"{colour}-{'s' if start else 'e'}"
    mid = "m" + re.sub(r"[^A-Za-z0-9]", "", key)
    if key not in defs:
        path = "M10,0 L0,5 L10,10 z" if start else "M0,0 L10,5 L0,10 z"
        defs[key] = (f'<marker id="{mid}" viewBox="0 0 10 10" refX="{0 if start else 10}" refY="5" '
                     f'markerWidth="7" markerHeight="7" orient="auto">'
                     f'<path d="{path}" fill="{_xa(colour)}"/></marker>')
    return mid


def _edge(c, verts: dict, defs: dict) -> str:
    st = _style(c.get("style") or "")
    src, tgt = c.get("source"), c.get("target")
    g = c.find("mxGeometry")
    if src in verts and tgt in verts:
        pts = _route(verts[src], verts[tgt], st, c)
    elif g is not None:
        sp, tp = g.find("mxPoint[@as='sourcePoint']"), g.find("mxPoint[@as='targetPoint']")
        if sp is None or tp is None:
            return ""
        pts = [(_f(sp.get("x")), _f(sp.get("y"))), (_f(tp.get("x")), _f(tp.get("y")))]
    else:
        return ""
    colour = _colour(st.get("strokeColor"), "#000000") or "none"
    sw = _f(st.get("strokeWidth")) or 1
    marks = ""
    if st.get("endArrow", "classic") != "none":
        marks += f' marker-end="url(#{_marker(defs, colour, False)})"'
    if st.get("startArrow", "none") != "none":
        marks += f' marker-start="url(#{_marker(defs, colour, True)})"'
    d = "M" + " L".join(f"{px:g},{py:g}" for px, py in pts)
    out = [f'<path d="{d}" fill="none" stroke="{_xa(colour)}" stroke-width="{sw:g}"{_dash(st)}{marks}/>']
    value = c.get("value") or ""
    if value:
        # Midpoint by length, where draw.io puts an edge label by default.
        segs = list(zip(pts, pts[1:]))
        total = sum(math.dist(p, q) for p, q in segs)
        acc, mx, my = 0.0, pts[0][0], pts[0][1]
        for p, q in segs:
            seg = math.dist(p, q)
            if seg and acc + seg >= total / 2:
                t = (total / 2 - acc) / seg
                mx, my = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                break
            acc += seg
        lst = dict(st)
        lst.setdefault("fontSize", "10")
        lst["align"], lst["verticalAlign"] = "center", "middle"
        lst.pop("whiteSpace", None)
        out.append(_label(value, lst, (mx - 100, my - 20, 200, 40), False))
    return "".join(out)
