"""Release metadata: every place that states the version agrees, and the Desktop
extension's manifest is complete. Claude Code only updates a plugin when
plugin.json's version changes, so a missed bump means users never get the release."""
import importlib.util
import json
import tomllib
from pathlib import Path

import drawgen
from drawgen.mcp_server import server

ROOT = Path(__file__).resolve().parent.parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_versions_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert drawgen.__version__ == VERSION, "src/drawgen/__init__.py"
    assert plugin["version"] == VERSION, ".claude-plugin/plugin.json"
    assert server.version == VERSION, "mcp_server"
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert all("version" not in p for p in marketplace["plugins"]), "version belongs in plugin.json only"


def test_mcpb_manifest_lists_every_tool():
    spec = importlib.util.spec_from_file_location("mcpb_build", ROOT / "mcpb" / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    m = build.manifest(VERSION)
    assert m["version"] == VERSION
    assert {t["name"] for t in m["tools"]} >= {"create_diagram", "check_diagram", "preview_diagram"}
    assert all(t["description"] and "\n" not in t["description"] for t in m["tools"])
    assert m["server"]["mcp_config"]["env"]["DRAWGEN_WORKDIR"] == "${user_config.workdir}"
