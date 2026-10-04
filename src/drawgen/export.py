"""Turn a .drawio file into pictures, and pictures into editable ones.

The format that matters is `<name>.drawio.svg`: an ordinary SVG whose root
element carries the whole mxfile in its `content` attribute. GitHub renders it
as an image; draw.io, its VS Code extension and GuardStein open it as the
diagram it is. One file, both jobs, which is why it is the default output.

Two renderers:

- draw.io Desktop (`render_drawio`): exact, the real layout engine. Found on
  PATH, in the usual install locations, or via DRAWIO_BIN. Headless on Linux
  through xvfb-run when there is no display. `drawgen install-drawio` fetches
  a pinned, checksum-verified copy if none is installed (install.py).
- Built in (`render_builtin`, svg_render.py): standard library only, so it
  works in Claude Desktop, CI and anywhere draw.io is not installed. It draws
  what drawgen emits (boxes, cylinders, diamonds, notes, text, orthogonal
  edges) approximately. The diagram is embedded either way, so the first save
  in draw.io replaces the approximation with the exact drawing.

`render` picks draw.io when it can and says which one ran.
"""
from __future__ import annotations

import hashlib
import html
import os
import platform
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .svg_render import render_svg


class ExportError(RuntimeError):
    pass


@dataclass
class Rendered:
    path: str
    renderer: str  # "drawio" | "builtin"
    editable: bool


def find_drawio() -> str | None:
    """Locate the draw.io Desktop executable, or None."""
    env = os.environ.get("DRAWIO_BIN")
    if env and os.path.exists(env):
        return env
    for name in ("drawio", "draw.io"):
        found = shutil.which(name)
        if found:
            return found
    candidates: list[str] = []
    system = platform.system()
    if system == "Windows":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            if base:
                candidates.append(os.path.join(base, "draw.io", "draw.io.exe"))
    elif system == "Darwin":
        candidates.append("/Applications/draw.io.app/Contents/MacOS/draw.io")
    else:
        candidates += ["/opt/drawio/drawio", "/usr/bin/drawio", "/snap/bin/drawio"]
    found = next((c for c in candidates if os.path.exists(c)), None)
    if found:
        return found
    from .install import cached_executable  # `drawgen install-drawio` puts it here
    return cached_executable()


def page_count(drawio_xml: str) -> int:
    root = ET.fromstring(drawio_xml)
    return len(root.findall("diagram")) if root.tag == "mxfile" else 1


def target_path(drawio_path: str, fmt: str, embed: bool = True, page: int | None = None,
                out_dir: str | None = None) -> str:
    """`x.drawio` -> `x.drawio.svg` (editable) or `x.svg`; `-p2` before the suffix for page 2."""
    base = os.path.basename(drawio_path)
    stem = base[:-len(".drawio")] if base.endswith(".drawio") else os.path.splitext(base)[0]
    if page:
        stem = f"{stem}-p{page}"
    name = f"{stem}.drawio.{fmt}" if embed and fmt in ("svg", "png") else f"{stem}.{fmt}"
    return os.path.join(out_dir or os.path.dirname(os.path.abspath(drawio_path)), name)


def render_drawio(drawio_path: str, fmt: str = "svg", out: str | None = None, *, embed: bool = True,
                  page: int | None = None, scale: float = 2.0, border: int = 16, theme: str = "light",
                  timeout: int = 180) -> str:
    """Export one page through draw.io Desktop. `page` is 1-based."""
    exe = find_drawio()
    if not exe:
        raise ExportError(
            "draw.io Desktop was not found. Run `drawgen install-drawio` (or the install_drawio MCP tool), "
            "install it yourself (Windows: winget install JGraph.Draw; "
            "macOS: brew install --cask drawio; Linux: the .deb/.rpm from github.com/jgraph/drawio-desktop) "
            "or set DRAWIO_BIN to the executable.")
    out = out or target_path(drawio_path, fmt, embed, page)
    cmd = [exe, "--export", "--format", fmt, "--border", str(border), "--output", out,
           # Light, not "auto": an adaptive SVG goes dark on GitHub's dark theme behind a
           # palette designed for white, and a document should look the same for everyone.
           "--theme", theme]
    if embed and fmt in ("svg", "png"):
        cmd.append("--embed-diagram")
    if fmt == "svg":
        # Plain XML inside, so GuardStein, `drawgen extract` and diff tools can read it;
        # no embedded font, which is most of a 280 KB file for a Helvetica diagram.
        cmd += ["--uncompressed", "--embed-svg-fonts", "false"]
    if fmt == "png":
        cmd += ["--scale", str(scale)]
    if page:
        cmd += ["--page-index", str(page)]  # 1-based since draw.io 2x
    cmd.append(drawio_path)
    if platform.system() == "Linux":
        cmd.insert(1, "--no-sandbox")
        if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
    env = dict(os.environ)
    if exe.endswith(".AppImage"):
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"  # no FUSE needed, which containers and CI lack
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0 or not os.path.exists(out):
        detail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise ExportError(f"draw.io export failed ({proc.returncode}): {detail or 'no output file'}")
    return out


def render_builtin(drawio_path: str, out: str | None = None, *, page: int | None = None,
                   embed: bool = True) -> str:
    """Draw an SVG with the built-in renderer, embedding the diagram for editing."""
    with open(drawio_path, encoding="utf-8") as fh:
        xml = fh.read()
    svg = render_svg(xml, page=(page or 1) - 1, embed=xml if embed else None)
    out = out or target_path(drawio_path, "svg", embed, page)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return out


def render(drawio_path: str, fmt: str = "svg", out: str | None = None, *, embed: bool = True,
           page: int | None = None, renderer: str = "auto", scale: float = 2.0) -> Rendered:
    """Render with draw.io when available ("auto"), or force "drawio" / "builtin"."""
    if renderer not in ("auto", "drawio", "builtin"):
        raise ExportError(f"renderer must be auto, drawio or builtin, not {renderer!r}")
    if renderer == "drawio" or (renderer == "auto" and find_drawio()):
        return Rendered(render_drawio(drawio_path, fmt, out, embed=embed, page=page, scale=scale),
                        "drawio", embed and fmt in ("svg", "png"))
    if fmt != "svg":
        raise ExportError(f"the built-in renderer only writes SVG; {fmt.upper()} needs draw.io Desktop")
    return Rendered(render_builtin(drawio_path, out, page=page, embed=embed), "builtin", embed)


def render_all(drawio_path: str, formats=("svg",), *, embed: bool = True, renderer: str = "auto",
               out_dir: str | None = None) -> list[Rendered]:
    """Every format for every page. A one-page file keeps the plain name."""
    with open(drawio_path, encoding="utf-8") as fh:
        n = page_count(fh.read())
    results = []
    for fmt in formats:
        for p in range(1, n + 1):
            page = p if n > 1 else None
            out = target_path(drawio_path, fmt, embed, page, out_dir)
            results.append(render(drawio_path, fmt, out, embed=embed, page=page, renderer=renderer))
    return results


# ---------------------------------------------------------------- inspection
_CONTENT = re.compile(r'<svg\b[^>]*\scontent="([^"]*)"', re.S)


def embedded_diagram(svg_text: str) -> str | None:
    """The mxfile inside an editable SVG, or None. Plain (uncompressed) content only."""
    m = _CONTENT.search(svg_text)
    if not m:
        return None
    content = html.unescape(m.group(1))
    return content if content.lstrip().startswith("<mxfile") else None


def content_hash(drawio_xml: str) -> str:
    """8 hex chars of the diagram, the prefix GuardStein uses so a changed diagram gets a new name."""
    return hashlib.sha256(drawio_xml.encode("utf-8")).hexdigest()[:8]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "diagram"


def temp_drawio(xml: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".drawio")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return path
