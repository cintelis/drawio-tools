"""Build the Claude Desktop release assets into dist/:

    drawgen-<version>.mcpb   the extension: double-click to install in Claude Desktop
    drawio-skill.zip         the skill, to upload under Settings -> Capabilities -> Skills

    uv run python mcpb/build.py

The bundle holds the source, pyproject.toml and uv.lock, not the dependencies:
Claude Desktop installs those with uv, so one bundle serves every platform. The
manifest's version and tool list come from the package, so they cannot drift.
Packing uses the MCPB CLI through npx, so Node must be installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "mcpb"
DIST = ROOT / "dist"
STAGE = DIST / "mcpb"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"


def _summary(doc: str | None) -> str:
    """A docstring's first paragraph, on one line."""
    para = (doc or "").strip().split("\n\n")[0]
    return " ".join(line.strip() for line in para.splitlines())


def manifest(version: str) -> dict:
    from drawgen.mcp_server import server

    data = json.loads((HERE / "manifest.in.json").read_text(encoding="utf-8"))
    data["version"] = version
    data["tools"] = [{"name": t.name, "description": _summary(t.description)}
                     for t in anyio.run(server.list_tools)]
    return data


def stage(version: str) -> None:
    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    shutil.copytree(ROOT / "src", STAGE / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("pyproject.toml", "uv.lock", "README.md"):  # README: pyproject names it
        shutil.copy2(ROOT / name, STAGE / name)
    shutil.copy2(HERE / "server.py", STAGE / "server.py")
    (STAGE / ".mcpbignore").write_text(".venv/\n__pycache__/\n*.pyc\n", encoding="utf-8")
    (STAGE / "manifest.json").write_text(json.dumps(manifest(version), indent=2) + "\n", encoding="utf-8")


def mcpb(*args: str) -> None:
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found: install Node.js to pack the extension")
    subprocess.run([npx, "--yes", MCPB_CLI, *args], check=True)


def main() -> None:
    import drawgen

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if drawgen.__version__ != version:
        sys.exit(f"drawgen.__version__ is {drawgen.__version__} but pyproject.toml says {version}")

    stage(version)
    out = DIST / f"drawgen-{version}.mcpb"
    mcpb("validate", str(STAGE / "manifest.json"))
    mcpb("pack", str(STAGE), str(out))

    skill = shutil.make_archive(str(DIST / "drawio-skill"), "zip", root_dir=ROOT / "skills", base_dir="drawio")
    print(f"built {out.relative_to(ROOT)} and {Path(skill).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
