"""Markdown documents with editable diagrams, in the layout GitHub and GuardStein share.

    docs/architecture.md                       ![Order flow](assets/3f9c21ab-order-flow.drawio.svg)
    docs/assets/3f9c21ab-order-flow.drawio.svg  an SVG with the diagram embedded

The link is relative, so it resolves the same on GitHub, in a clone, and in a
GuardStein note published to or imported from the repository. The file name
starts with 8 hex characters of the diagram's content, the convention
GuardStein uses: a changed diagram gets a new name, so no cache, CDN or
reviewer ever sees a stale picture under an old URL.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .diagram import Document
from .export import (
    Rendered,
    content_hash,
    embedded_diagram,
    page_count,
    render,
    slugify,
    temp_drawio,
)
from .spec import build

PLACEHOLDER = re.compile(r"\{\{\s*diagram:\s*([A-Za-z0-9_.-]+)\s*\}\}")
IMAGE_LINK = re.compile(r"!\[([^\]]*)\]\((assets/[^)\s]+\.drawio\.svg)\)")


@dataclass
class Asset:
    name: str
    path: str          # absolute
    link: str          # relative, as written in the markdown
    alt: str
    renderer: str
    markdown: str = field(init=False)

    def __post_init__(self) -> None:
        self.markdown = f"![{self.alt}]({self.link})"


def write_assets(doc: Document, md_dir: str, name: str | None = None, renderer: str = "auto",
                 assets_dir: str = "assets") -> list[Asset]:
    """Render every page of `doc` to `<md_dir>/<assets_dir>/<hash>-<slug>.drawio.svg`."""
    xml = doc.xml()
    out_dir = os.path.join(md_dir, assets_dir)
    os.makedirs(out_dir, exist_ok=True)
    tmp = temp_drawio(xml)
    try:
        n = page_count(xml)
        assets = []
        for i, page in enumerate(doc.pages):
            # Each page is its own image with only its own page embedded, so
            # opening the picture opens that diagram and nothing else.
            single = Document([page]).xml() if n > 1 else xml
            src = temp_drawio(single) if n > 1 else tmp
            try:
                slug = slugify(name if (name and n == 1) else f"{name + '-' if name else ''}{page.name}")
                fname = f"{content_hash(single)}-{slug}.drawio.svg"
                target = os.path.join(out_dir, fname)
                r: Rendered = render(src, "svg", target, embed=True, renderer=renderer)
                link = f"{assets_dir}/{fname}".replace(os.sep, "/")
                assets.append(Asset(page.name, os.path.abspath(target), link, page.name, r.renderer))
            finally:
                if src is not tmp:
                    os.remove(src)
        return assets
    finally:
        os.remove(tmp)


def write_document(md_path: str, markdown: str, diagrams: dict[str, dict | str],
                   renderer: str = "auto") -> tuple[str, list[Asset]]:
    """Write a markdown file, replacing each `{{diagram:name}}` with that diagram's image link(s).

    `diagrams` maps a name to a spec (mapping or YAML/JSON text). A name used in
    the text with no spec, or a spec the text never places, is an error rather
    than a silently missing figure.
    """
    used = PLACEHOLDER.findall(markdown)
    missing = sorted(set(used) - set(diagrams))
    unused = sorted(set(diagrams) - set(used))
    if missing or unused:
        parts = []
        if missing:
            parts.append(f"placeholders with no diagram: {missing}")
        if unused:
            parts.append(f"diagrams never placed (add {{{{diagram:NAME}}}} to the text): {unused}")
        raise ValueError("; ".join(parts))
    md_dir = os.path.dirname(os.path.abspath(md_path))
    rendered: dict[str, list[Asset]] = {}
    for name, spec in diagrams.items():
        rendered[name] = write_assets(build(spec), md_dir, name, renderer)
    text = PLACEHOLDER.sub(lambda m: "\n\n".join(a.markdown for a in rendered[m.group(1)]), markdown)
    os.makedirs(md_dir, exist_ok=True)
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")
    return md_path, [a for v in rendered.values() for a in v]


def add_diagram(md_path: str, spec: dict | str, *, after_heading: str | None = None,
                replace_link: str | None = None, alt: str | None = None,
                renderer: str = "auto") -> list[Asset]:
    """Add a diagram to an existing (or new) markdown file.

    - replace_link: swap the image link that points at this asset (a re-edit).
      The old file is left in place: another document may link to it.
    - after_heading: insert below the first heading with this text.
    - otherwise append at the end.
    """
    md_dir = os.path.dirname(os.path.abspath(md_path))
    doc = build(spec)
    assets = write_assets(doc, md_dir, alt, renderer)
    if alt and len(assets) == 1:
        assets[0].alt = alt
        assets[0].__post_init__()
    block = "\n\n".join(a.markdown for a in assets)
    text = ""
    if os.path.exists(md_path):
        with open(md_path, encoding="utf-8") as fh:
            text = fh.read()
    if replace_link:
        pat = re.compile(r"!\[([^\]]*)\]\(" + re.escape(replace_link) + r"\)")
        if not pat.search(text):
            raise ValueError(f"no image link to {replace_link!r} in {md_path}")
        text = pat.sub(lambda m: block, text, count=1)
    elif after_heading:
        pat = re.compile(r"^(#{1,6})\s+" + re.escape(after_heading.strip()) + r"\s*$", re.M)
        m = pat.search(text)
        if not m:
            raise ValueError(f"no heading {after_heading!r} in {md_path}")
        text = text[:m.end()] + "\n\n" + block + "\n" + text[m.end():]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return assets


def diagrams_in(md_path: str) -> list[dict]:
    """Every editable diagram a markdown file links to, with whether its source is readable."""
    md_dir = os.path.dirname(os.path.abspath(md_path))
    with open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    out = []
    for alt, link in IMAGE_LINK.findall(text):
        path = os.path.join(md_dir, link)
        source = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                source = embedded_diagram(fh.read())
        out.append({"alt": alt, "link": link, "path": path, "exists": os.path.exists(path),
                    "editable": source is not None})
    return out
