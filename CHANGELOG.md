# Changelog

Each release is a git tag `vX.Y.Z`. The section for a version becomes its GitHub
release notes, so write it for the people installing it.

## 0.2.0

- Claude Desktop extension: `drawgen-X.Y.Z.mcpb` on each GitHub release installs with a
  double-click and asks for the diagrams folder. No clone, no JSON editing.
- `drawio-skill.zip` on each release, ready to upload to Claude Desktop.
- Docker image published to `ghcr.io/cintelis/drawgen` on each release.
- Team setup: a `.claude/settings.json` snippet that offers the plugin to everyone who
  opens a repository.
- The MCP server reports the package version; a test keeps every version in step.

## 0.1.0

- drawgen library, CLI, MCP server, skill and Claude Code plugin.
- Skill: diagrams into GuardStein notes through the guardstein MCP server.
