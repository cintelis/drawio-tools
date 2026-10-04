"""The MCP server over real stdio, the way Claude Desktop and Claude Code launch it."""
import json
import os
import sys

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from drawgen.export import find_drawio

SPEC = {"title": "Tiny", "nodes": [{"id": "a", "label": "A", "x": 40, "y": 100},
                                  {"id": "b", "label": "B", "x": 300, "y": 100}],
        "edges": [{"from": "a", "to": "b", "label": "calls"}]}


def _structured(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


async def _session_run(workdir, fn, with_drawio=False):
    env = dict(os.environ, DRAWGEN_WORKDIR=str(workdir))
    if not with_drawio:
        # Hide every draw.io, including one `drawgen install-drawio` cached, and PATH.
        env.update(DRAWIO_BIN=os.devnull + "-none", DRAWGEN_CACHE=str(workdir / ".no-cache"), PATH="")
    params = StdioServerParameters(command=sys.executable, args=["-m", "drawgen.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


@pytest.fixture
def run(tmp_path):
    return lambda fn, with_drawio=False: anyio.run(_session_run, tmp_path, fn, with_drawio)


def test_tools_are_listed(run):
    async def go(s):
        return {t.name for t in (await s.list_tools()).tools}
    names = run(go)
    assert {"spec_reference", "create_diagram", "create_markdown_document", "add_diagram_to_markdown",
            "check_diagram", "read_diagram", "update_diagram", "preview_diagram", "install_drawio"} <= names


def test_create_markdown_document_round_trip(run, tmp_path):
    async def go(s):
        r = await s.call_tool("create_markdown_document", {
            "path": "docs/readme.md", "markdown": "# Hi\n\n{{diagram:tiny}}\n", "diagrams": {"tiny": SPEC},
            "renderer": "builtin"})
        assert not r.is_error, r.content
        made = _structured(r)
        r2 = await s.call_tool("read_diagram", {"path": "docs/readme.md"})
        return made, _structured(r2)
    made, listing = run(go)
    md = tmp_path / "docs" / "readme.md"
    assert md.exists() and "assets/" in md.read_text(encoding="utf-8")
    assert listing["diagrams"][0]["editable"] is True
    assert made["check"][0]["errors"] == 0


def test_spec_errors_reach_the_model_readably(run):
    async def go(s):
        return await s.call_tool("create_diagram", {"spec": {"title": "x", "nodes": [{"id": "a", "label": "A",
                                                    "kind": "nope", "x": 1, "y": 1}]}, "output_path": "x.drawio.svg"})
    r = run(go)
    assert r.is_error
    assert "nodes[0].kind" in r.content[0].text  # not just "Error executing tool"


def test_preview_explains_missing_drawio(run):
    async def go(s):
        await s.call_tool("create_diagram", {"spec": SPEC, "output_path": "t.drawio.svg", "renderer": "builtin"})
        return await s.call_tool("preview_diagram", {"path": "t.drawio.svg"})
    r = run(go)
    assert r.is_error and "install_drawio" in r.content[0].text


@pytest.mark.skipif(not find_drawio(), reason="draw.io Desktop not installed")
def test_preview_returns_a_png_from_drawio(run):
    async def go(s):
        await s.call_tool("create_diagram", {"spec": SPEC, "output_path": "t.drawio.svg"})
        return await s.call_tool("preview_diagram", {"path": "t.drawio.svg"})
    r = run(go, with_drawio=True)
    assert not r.is_error and r.content[0].type == "image" and r.content[0].mime_type == "image/png"
