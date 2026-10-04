"""Library behaviour: the id guard, the spec errors, the checker, the editable SVG, markdown."""
import os
import re

import pytest

from drawgen import Diagram, DiagramError, Document, SpecError, build, check_xml
from drawgen.export import embedded_diagram, render_builtin, target_path
from drawgen.markdown import add_diagram, diagrams_in, write_document

SPEC = {
    "title": "Order flow",
    "layout": "auto",
    "nodes": [
        {"id": "user", "label": "Shopper", "kind": "actor"},
        {"id": "api", "label": "Orders API", "kind": "service"},
        {"id": "db", "label": "Postgres", "kind": "datastore"},
    ],
    "edges": [{"from": "user", "to": "api", "label": "HTTPS"}, {"from": "api", "to": "db", "style": "data"}],
    "legend": True,
}


def codes(report):
    return sorted(i.code for i in report.issues)


# ------------------------------------------------------------------ builder
def test_duplicate_and_reserved_ids_raise():
    d = Diagram("t")
    d.node("a", "A", 40, 100)
    with pytest.raises(DiagramError, match="duplicate"):
        d.node("a", "Again", 300, 100)
    with pytest.raises(DiagramError, match="reserved"):
        d.node("1", "Root", 300, 100)


def test_two_legends_get_distinct_ids():
    d = Diagram("t")
    d.node("a", "A", 40, 100)
    d.legend(400, 100)
    with pytest.raises(DiagramError):
        d.legend(400, 400)  # the old drawgen wrote a broken file here
    d.legend(400, 400, lid="legend2")


def test_edge_to_missing_node_raises():
    d = Diagram("t")
    d.node("a", "A", 40, 100)
    with pytest.raises(DiagramError, match="does not exist"):
        d.edge("a", "ghost")


def test_zone_children_are_stored_relative_and_checked_absolute():
    d = Diagram("t", 800, 600)
    d.zone("z", "Zone", 100, 100, 400, 300, "blue")
    d.node("n", "Inside", 150, 160, zone="z")
    xml = d.xml()
    assert re.search(r'id="n"[^>]*parent="z"', xml)
    assert 'x="50" y="60"' in xml
    assert not check_xml(xml).issues


def test_labels_are_escaped():
    d = Diagram("t")
    d.node("a", "<script>&", 40, 100)
    assert "<script>" not in d.xml()


# --------------------------------------------------------------------- spec
def test_spec_builds_and_passes_check():
    xml = build(SPEC).xml()
    assert check_xml(xml).issues == []


def test_spec_reports_every_problem_with_its_path():
    bad = {"title": "x", "nodes": [{"id": "a", "label": "A", "kind": "servise", "x": 1, "y": 1},
                                   {"id": "a", "label": "B", "x": 1, "y": 1}],
           "edges": [{"from": "a", "to": "nowhere", "colour": "red"}]}
    with pytest.raises(SpecError) as e:
        build(bad)
    msg = str(e.value)
    assert "nodes[0].kind" in msg and "servise" in msg
    assert "used more than once" in msg
    assert "edges[0].to" in msg
    assert "unknown key 'colour'" in msg


def test_yaml_text_is_accepted():
    doc = build("title: T\nnodes:\n  - {id: a, label: A, x: 40, y: 100}\n")
    assert isinstance(doc, Document)


def test_unsized_page_fits_content():
    d = build(SPEC).pages[0]
    _, _, right, bottom = d.content_bounds()
    assert d.width == pytest.approx(right + 40, abs=1) and d.height == pytest.approx(bottom + 40, abs=1)


# ------------------------------------------------------------------ checker
def test_checker_finds_overlap_out_of_page_and_dangling_edge():
    d = Diagram("t", 400, 300)
    d.node("a", "A", 40, 100)
    d.node("b", "B", 60, 110)          # overlaps a
    d.node("c", "C", 350, 100)         # off the 400px page
    xml = d.xml().replace("</root>", '<mxCell id="x" edge="1" parent="1" source="a" target="ghost">'
                                     '<mxGeometry relative="1" as="geometry"/></mxCell></root>')
    assert {"overlap", "out-of-page", "dangling-edge"} <= set(codes(check_xml(xml)))


def test_checker_finds_edge_through_shape_and_waypoints_fix_it():
    d = Diagram("t", 900, 400)
    d.node("a", "A", 40, 150)
    d.node("mid", "In the way", 340, 150)
    d.node("b", "B", 640, 150)
    d.edge("a", "b", eid="ab")
    assert "edge-through-shape" in codes(check_xml(d.xml()))
    d2 = Diagram("t", 900, 400)
    d2.node("a", "A", 40, 150)
    d2.node("mid", "In the way", 340, 150)
    d2.node("b", "B", 640, 150)
    d2.edge("a", "b", exit="top", entry="top", points=[(125, 110), (725, 110)])
    assert "edge-through-shape" not in codes(check_xml(d2.xml()))


def test_checker_finds_label_overflow():
    d = Diagram("t", 900, 400)
    d.node("a", "A label far too long to fit in a box this narrow, wrapped or not", 40, 150, w=90, h=30)
    assert "label-overflow" in codes(check_xml(d.xml()))


def test_checker_reads_malformed_xml_as_an_error():
    assert codes(check_xml("<mxfile><diagram")) == ["malformed-xml"]


# ------------------------------------------------------------------- export
def test_target_names():
    assert target_path("/x/a.drawio", "svg").endswith("a.drawio.svg")
    assert target_path("/x/a.drawio", "svg", embed=False).endswith("a.svg")
    assert target_path("/x/a.drawio", "png", page=2).endswith("a-p2.drawio.png")


def test_builtin_svg_embeds_the_diagram(tmp_path):
    src = tmp_path / "a.drawio"
    xml = build(SPEC).xml()
    src.write_text(xml, encoding="utf-8")
    out = render_builtin(str(src))
    svg = open(out, encoding="utf-8").read()
    assert out.endswith(".drawio.svg") and svg.startswith("<svg")
    assert embedded_diagram(svg) == xml
    assert "Orders API" in svg


# ----------------------------------------------------------------- markdown
def test_markdown_document_links_relative_editable_assets(tmp_path):
    md = tmp_path / "docs" / "arch.md"
    path, assets = write_document(str(md), "# Arch\n\n{{diagram:orders}}\n", {"orders": SPEC}, renderer="builtin")
    text = md.read_text(encoding="utf-8")
    assert re.search(r"!\[Order flow\]\(assets/[0-9a-f]{8}-orders\.drawio\.svg\)", text)
    found = diagrams_in(str(md))
    assert found and found[0]["exists"] and found[0]["editable"]


def test_markdown_placeholders_must_match_diagrams(tmp_path):
    with pytest.raises(ValueError, match="no diagram"):
        write_document(str(tmp_path / "a.md"), "{{diagram:missing}}", {}, renderer="builtin")
    with pytest.raises(ValueError, match="never placed"):
        write_document(str(tmp_path / "a.md"), "text", {"x": SPEC}, renderer="builtin")


def test_add_and_replace_diagram(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# Intro\n\ntext\n\n# Design\n\nmore\n", encoding="utf-8")
    first = add_diagram(str(md), SPEC, after_heading="Design", renderer="builtin")[0]
    text = md.read_text(encoding="utf-8")
    assert text.index(first.link) > text.index("# Design")
    changed = dict(SPEC, title="Order flow v2")
    second = add_diagram(str(md), changed, replace_link=first.link, renderer="builtin")[0]
    text = md.read_text(encoding="utf-8")
    assert second.link in text and first.link not in text
    assert os.path.exists(first.path)  # left for any other document that links it


# ------------------------------------------------------------------ examples
@pytest.mark.parametrize("script", ["examples/clearline/build.py", "examples/bluefield/build.py"])
def test_examples_build_without_errors(script, tmp_path):
    import runpy
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    argv = sys.argv
    sys.argv = [script, "--renderer", "builtin"] + (["--check", "-o", str(tmp_path / "bf.drawio")]
                                                     if "bluefield" in script else [])
    try:
        with pytest.raises(SystemExit) as e:
            runpy.run_path(os.path.join(root, script), run_name="__main__")
        assert e.value.code in (0, None)
    finally:
        sys.argv = argv
