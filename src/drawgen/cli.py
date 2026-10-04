"""drawgen command line. The MCP server and this CLI call the same functions.

  drawgen build SPEC.yaml [-o out.drawio.svg] [--format png]   spec -> diagram
  drawgen doc TEMPLATE.md -d NAME=SPEC.yaml [-o out.md]          markdown with {{diagram:NAME}}
  drawgen check FILE... [--json] [--strict]                      .drawio / .drawio.svg / .md
  drawgen export FILE.drawio [-f svg,png] [--no-embed]
  drawgen extract FILE.drawio.svg [-o FILE.drawio]               the embedded diagram
  drawgen kinds                                                  theme reference
  drawgen install-drawio | drawio-status
  drawgen hook                                                   Claude Code PostToolUse hook
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import install as installer
from .check import check_xml
from .diagram import DiagramError
from .export import ExportError, embedded_diagram, find_drawio, render_all
from .markdown import diagrams_in, write_document
from .spec import SpecError, build, load_file
from .theme import describe


def _read_source(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if path.lower().endswith(".svg"):
        xml = embedded_diagram(text)
        if xml is None:
            raise ValueError(f"{path}: no embedded diagram (not an editable .drawio.svg)")
        return xml
    return text


def cmd_build(a) -> int:
    from .mcp_server import _write_xml_to  # same writer the MCP tool uses

    spec = load_file(a.spec)
    xml = build(spec).xml()
    out = a.output or os.path.splitext(a.spec)[0] + ".drawio.svg"
    res = _write_xml_to(xml, os.path.abspath(out), a.renderer, a.format.split(",") if a.format else None)
    report = check_xml(xml, path=out)
    for f in res["files"]:
        print(f"wrote {f}" + (f" ({res['renderer']} renderer)" if res["renderer"] else ""))
    print(report.to_text())
    return 0 if report.ok(a.strict) else 1


def cmd_doc(a) -> int:
    diagrams = {}
    for item in a.diagram or []:
        name, _, path = item.partition("=")
        if not path:
            raise ValueError(f"--diagram takes NAME=SPEC_PATH, got {item!r}")
        diagrams[name] = load_file(path)
    with open(a.template, encoding="utf-8") as fh:
        text = fh.read()
    out = a.output or a.template.replace(".tmpl", "")
    if os.path.abspath(out) == os.path.abspath(a.template):
        raise ValueError("give -o, or name the template *.md.tmpl, so it is not overwritten")
    md, assets = write_document(out, text, diagrams, a.renderer)
    print(f"wrote {md}")
    for x in assets:
        print(f"  {x.link} ({x.renderer})")
    bad = 0
    for name, spec in diagrams.items():
        r = check_xml(build(spec).xml(), path=name)
        print(r.to_text())
        bad += not r.ok(a.strict)
    return 1 if bad else 0


def cmd_check(a) -> int:
    reports = []
    for path in a.files:
        if path.lower().endswith(".md"):
            for d in diagrams_in(path):
                if not d["exists"]:
                    print(f"{path}: {d['link']} does not exist", file=sys.stderr)
                    reports.append(None)
                    continue
                reports.append(check_xml(_read_source(d["path"]), path=d["path"]))
        else:
            reports.append(check_xml(_read_source(path), path=path))
    if a.json:
        print(json.dumps([r.to_dict() for r in reports if r], indent=2))
    else:
        for r in reports:
            if r:
                print(r.to_text())
    return 0 if all(r and r.ok(a.strict) for r in reports) else 1


def cmd_export(a) -> int:
    rs = render_all(a.file, a.format.split(","), embed=not a.no_embed, renderer=a.renderer)
    for r in rs:
        print(f"wrote {r.path} ({r.renderer})")
    return 0


def cmd_extract(a) -> int:
    xml = _read_source(a.file)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as fh:
            fh.write(xml)
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(xml)
    return 0


def cmd_kinds(a) -> int:
    print(json.dumps(describe(), indent=2))
    return 0


def cmd_install(a) -> int:
    installer.install()
    return 0


def cmd_status(a) -> int:
    exe = find_drawio()
    print(f"draw.io Desktop: {exe or 'not found (built-in renderer will be used)'}")
    print(f"pinned version for install-drawio: {installer.VERSION} -> {installer.install_dir()}")
    return 0


def cmd_hook(a) -> int:
    """Claude Code PostToolUse hook: check a diagram Claude just wrote.

    Reads the hook event on stdin. Exit 2 with the report on stderr hands the
    problems back to Claude, which then fixes them; anything else stays quiet.
    """
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith((".drawio", ".drawio.svg")) or not os.path.exists(path):
        return 0
    try:
        report = check_xml(_read_source(path), path=path)
    except (OSError, ValueError) as e:
        print(f"drawgen: could not check {path}: {e}", file=sys.stderr)
        return 2
    if report.issues:
        print("drawgen check found problems in the diagram you just wrote; fix them:\n" + report.to_text(),
              file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="drawgen", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="spec (YAML/JSON) -> .drawio.svg or .drawio")
    b.add_argument("spec")
    b.add_argument("-o", "--output", help="NAME.drawio.svg (default) or NAME.drawio")
    b.add_argument("--format", help="extra formats, comma separated: png,pdf (draw.io Desktop)")
    b.set_defaults(fn=cmd_build)

    d = sub.add_parser("doc", help="markdown template with {{diagram:NAME}} -> markdown + assets/")
    d.add_argument("template")
    d.add_argument("-d", "--diagram", action="append", metavar="NAME=SPEC")
    d.add_argument("-o", "--output")
    d.set_defaults(fn=cmd_doc)

    c = sub.add_parser("check", help="check .drawio, .drawio.svg, or the diagrams a .md links")
    c.add_argument("files", nargs="+")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    e = sub.add_parser("export", help=".drawio -> svg/png/pdf")
    e.add_argument("file")
    e.add_argument("-f", "--format", default="svg")
    e.add_argument("--no-embed", action="store_true", help="plain images, not editable")
    e.set_defaults(fn=cmd_export)

    x = sub.add_parser("extract", help="the diagram embedded in a .drawio.svg")
    x.add_argument("file")
    x.add_argument("-o", "--output")
    x.set_defaults(fn=cmd_extract)

    sub.add_parser("kinds", help="component kinds, zone colours, edge styles").set_defaults(fn=cmd_kinds)
    sub.add_parser("install-drawio", help="download pinned draw.io Desktop").set_defaults(fn=cmd_install)
    sub.add_parser("drawio-status", help="which renderer will be used").set_defaults(fn=cmd_status)
    sub.add_parser("hook", help="Claude Code PostToolUse hook (reads stdin)").set_defaults(fn=cmd_hook)

    for p in (b, d, c):
        p.add_argument("--strict", action="store_true", help="fail on warnings too")
    for p in (b, d, e):
        p.add_argument("--renderer", default="auto", choices=["auto", "drawio", "builtin"])

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (SpecError, DiagramError, ExportError, ValueError, OSError, RuntimeError) as err:
        print(f"drawgen: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
