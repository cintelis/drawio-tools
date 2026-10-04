"""drawgen as an MCP server: the one interface Claude Desktop and Claude Code share.

Run:  drawgen-mcp                 (stdio; what both apps launch)

Relative paths resolve against DRAWGEN_WORKDIR, else the server's working
directory. Claude Desktop starts servers in an arbitrary directory, so its
config should set DRAWGEN_WORKDIR (see README).
"""
from __future__ import annotations

import functools
import os
import tempfile
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import install as installer
from .check import check_file, check_xml
from .diagram import DiagramError
from .export import ExportError, embedded_diagram, find_drawio, render, render_all, temp_drawio
from .markdown import add_diagram, diagrams_in, write_document
from .spec import SpecError, build
from .spec import __doc__ as SPEC_DOC
from .theme import describe

INSTRUCTIONS = """\
Generate draw.io diagrams that stay editable. The output format is NAME.drawio.svg:
an SVG GitHub renders as an image, with the diagram embedded so draw.io, its VS Code
extension and GuardStein reopen it for editing. Markdown documents link them as
![Alt](assets/<hash>-<name>.drawio.svg), the layout GitHub and GuardStein share.

Workflow:
1. Call spec_reference once for the spec format, component kinds and edge styles.
2. Write a spec: pick a `kind` per component (colour comes from the theme, never set it),
   label every edge, give coordinates or use layout: auto.
3. create_diagram or create_markdown_document. Read the returned `check` report and fix
   every error and warning (move or widen shapes, add edge waypoints), then regenerate.
4. If draw.io Desktop is available, preview_diagram shows you the exact rendering; look at it.
To change an existing diagram, read_diagram returns its XML; edit it and call update_diagram.
install_drawio downloads about 150-180 MB: ask the user before calling it.
"""

server = MCPServer(name="drawgen", instructions=INSTRUCTIONS, version="0.1.0")

_RW = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
_RO = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _tool(annotations=_RW):
    """Register a tool whose expected failures reach the model as readable errors."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ToolError:
                raise
            except (SpecError, DiagramError, ExportError, ValueError, OSError, RuntimeError) as e:
                raise ToolError(str(e)) from e
        return server.tool(annotations=annotations)(inner)
    return wrap


def _path(p: str) -> str:
    p = os.path.expanduser(p)
    if os.path.isabs(p):
        return p
    return os.path.abspath(os.path.join(os.environ.get("DRAWGEN_WORKDIR") or os.getcwd(), p))


def _source(path: str) -> str:
    """The mxfile XML from a .drawio or an editable .svg/.png file."""
    path = _path(path)
    if path.lower().endswith(".svg"):
        with open(path, encoding="utf-8") as fh:
            xml = embedded_diagram(fh.read())
        if xml is None:
            raise ValueError(f"{path} is an SVG without an (uncompressed) embedded diagram, so it is not editable")
        return xml
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write_xml_to(xml: str, out: str, renderer: str, formats: list[str] | None = None) -> dict:
    """Write mxfile XML to `out` (.drawio or .drawio.svg), plus any extra formats."""
    out = _path(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    written, used = [], None
    if out.endswith(".drawio"):
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(xml)
        written.append(out)
        for r in render_all(out, formats or [], renderer=renderer):
            written.append(r.path)
            used = r.renderer
    elif out.endswith(".drawio.svg"):
        tmp = temp_drawio(xml)
        try:
            r = render(tmp, "svg", out, embed=True, renderer=renderer)
            written.append(r.path)
            used = r.renderer
            for fmt in [f for f in (formats or []) if f != "svg"]:
                extra = render(tmp, fmt, out[: -len(".svg")] + "." + fmt, embed=True, renderer=renderer)
                written.append(extra.path)
        finally:
            os.remove(tmp)
    else:
        raise ValueError("output_path must end in .drawio.svg (editable image, recommended) or .drawio")
    return {"files": written, "renderer": used}


# -------------------------------------------------------------------- tools
@_tool(_RO)
def spec_reference() -> dict:
    """The diagram spec format, the component kinds, zone colours and edge styles. Read this first."""
    return {"spec_format": SPEC_DOC, **describe(),
            "drawio_desktop": find_drawio() or "not installed: SVGs use the built-in renderer"}


@_tool()
def create_diagram(spec: dict | str, output_path: str, extra_formats: list[str] | None = None,
                   renderer: str = "auto") -> dict:
    """Build a diagram from a spec (mapping, or YAML/JSON text) and write it.

    output_path: NAME.drawio.svg for an editable image (recommended), or NAME.drawio.
    extra_formats: e.g. ["png"] (needs draw.io Desktop). renderer: auto | drawio | builtin.
    Returns the files written and a check report; fix every issue it lists.
    """
    doc = build(spec)
    xml = doc.xml()
    result = _write_xml_to(xml, output_path, renderer, extra_formats)
    result["check"] = check_xml(xml, path=output_path).to_dict()
    if result["renderer"] == "builtin":
        result["note"] = ("Rendered with the built-in renderer (approximate, still editable). "
                          "Exact rendering needs draw.io Desktop: see install_drawio.")
    return result


@_tool()
def create_markdown_document(path: str, markdown: str, diagrams: dict[str, Any],
                             renderer: str = "auto") -> dict:
    """Write a markdown file whose diagrams are editable .drawio.svg files beside it in assets/.

    Put {{diagram:NAME}} in the markdown where each figure goes; `diagrams` maps NAME to a spec.
    The links are relative (assets/<hash>-<name>.drawio.svg), so they render on GitHub.
    """
    md, assets = write_document(_path(path), markdown, diagrams, renderer)
    report = []
    for name, spec in diagrams.items():
        report.append({"diagram": name, **check_xml(build(spec).xml(), path=name).to_dict()})
    return {"markdown": md, "assets": [{"link": a.link, "path": a.path, "renderer": a.renderer} for a in assets],
            "check": report}


@_tool()
def add_diagram_to_markdown(path: str, spec: dict | str, after_heading: str | None = None,
                            replace_link: str | None = None, alt: str | None = None,
                            renderer: str = "auto") -> dict:
    """Add a diagram to a markdown file (created if missing).

    replace_link: an existing assets/....drawio.svg link to swap for the new diagram (a re-edit).
    after_heading: insert under the first heading with this text. Otherwise appended.
    """
    assets = add_diagram(_path(path), spec, after_heading=after_heading, replace_link=replace_link,
                         alt=alt, renderer=renderer)
    return {"markdown": _path(path), "inserted": [a.markdown for a in assets],
            "check": check_xml(build(spec).xml()).to_dict()}


@_tool(_RO)
def check_diagram(path: str) -> dict:
    """Check a .drawio or editable .drawio.svg for overlaps, off-page shapes, broken edges,
    edges through shapes and labels that do not fit."""
    return check_xml(_source(path), path=_path(path)).to_dict()


@_tool(_RO)
def read_diagram(path: str) -> dict:
    """The draw.io XML of a .drawio or .drawio.svg file, or the editable diagrams a markdown file links."""
    p = _path(path)
    if p.lower().endswith(".md"):
        return {"markdown": p, "diagrams": diagrams_in(p)}
    return {"path": p, "xml": _source(p)}


@_tool()
def update_diagram(path: str, xml: str, renderer: str = "auto") -> dict:
    """Replace a diagram with edited draw.io XML (from read_diagram) and re-render it in place.

    For a .drawio.svg the image is redrawn and the new XML embedded. Use this for
    diagrams that were not made from a spec, or for edits a spec cannot express.
    """
    report = check_xml(xml, path=path)
    if any(i.code == "malformed-xml" for i in report.issues):
        raise ValueError(f"not valid draw.io XML: {report.issues[0].message}")
    result = _write_xml_to(xml, path, renderer)
    result["check"] = report.to_dict()
    return result


@_tool()
def export_diagram(path: str, formats: list[str] | None = None, renderer: str = "auto",
                   embed: bool = True) -> dict:
    """Export a .drawio file to svg/png/pdf next to it. embed=True keeps svg/png editable."""
    rs = render_all(_path(path), formats or ["svg"], embed=embed, renderer=renderer)
    return {"files": [r.path for r in rs], "renderer": rs[0].renderer if rs else None}


@_tool(_RO)
def preview_diagram(path: str, page: int = 1) -> Image:
    """A PNG of the diagram as draw.io draws it, so you can look at the result. Needs draw.io Desktop."""
    if not find_drawio():
        raise ToolError("Preview needs draw.io Desktop, which is not installed. Ask the user whether to run "
                        "install_drawio (about 150-180 MB), or rely on check_diagram.")
    tmp = temp_drawio(_source(path))
    out = tempfile.mktemp(suffix=".png")
    try:
        r = render(tmp, "png", out, embed=False, page=page if page > 1 else None, renderer="drawio", scale=1.0)
        with open(r.path, "rb") as fh:
            data = fh.read()
        return Image(data=data, format="png")
    finally:
        os.remove(tmp)
        if os.path.exists(out):
            os.remove(out)


@_tool(_RO)
def drawio_status() -> dict:
    """Whether draw.io Desktop is available for exact rendering, and where."""
    exe = find_drawio()
    return {"installed": bool(exe), "executable": exe, "pinned_version": installer.VERSION,
            "cache": installer.install_dir()}


@_tool(ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
def install_drawio() -> dict:
    """Download draw.io Desktop (pinned version, SHA-256 verified, ~150-180 MB) into drawgen's cache.
    Ask the user before calling this."""
    lines: list[str] = []
    exe = installer.install(progress=lines.append)
    return {"executable": exe, "log": lines}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
