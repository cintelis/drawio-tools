# drawio-tools

Generate, check and export draw.io diagrams from Claude Desktop and Claude Code, as
**editable `.drawio.svg`** files: SVGs that GitHub renders as pictures, with the diagram
embedded so draw.io, its VS Code extension and GuardStein open them for editing. Markdown
documents link them with relative paths, so a document reads the same on GitHub, in a
clone and in GuardStein:

```
docs/architecture.md                        ![Order flow](assets/3f9c21ab-order-flow.drawio.svg)
docs/assets/3f9c21ab-order-flow.drawio.svg   picture + embedded diagram
```

The 8 hex characters are a hash of the diagram, so a changed diagram gets a new file
name and nobody sees a stale cached picture.

| Piece | For |
|---|---|
| `drawgen-mcp`, an MCP server | Claude Desktop and Claude Code. The main interface |
| `skills/drawio/SKILL.md` | How Claude should design diagrams and use the tools |
| `drawgen` CLI | Scripts, CI, the Claude Code hook |
| `drawgen` Python library | Diagrams as code (see `examples/`) |
| Claude Code plugin (`.claude-plugin/`) | Server + skill + a hook that checks every `.drawio` Claude writes |

## How it works

1. Claude writes a **spec** (YAML or JSON): components by `kind` (service, datastore,
   queue, ai, actor…), zones, labelled edges. Colour comes from the theme and only ever
   means type; the label carries the meaning. `spec_reference` returns the format.
2. drawgen builds the mxGraph XML, refusing duplicate ids, edges to nothing and unknown
   kinds with messages that say which entry is wrong and what would be accepted.
3. The **checker** reports overlaps, off-page shapes, broken edges, edges that run
   through other shapes, and labels that will not fit. Claude fixes them and rebuilds.
4. The diagram is **rendered** to `.drawio.svg` with the diagram embedded:
   - by **draw.io Desktop** when available: exact;
   - otherwise by a **built-in renderer** (standard library only): approximate, still
     editable, and redrawn exactly the next time anyone saves it in draw.io.

## Install

Releases are on the [releases page](https://github.com/cintelis/drawio-tools/releases).
The repository is private, so every route needs a GitHub account with access to it.
Exact rendering and previews also need draw.io Desktop: the `install_drawio` tool fetches
it (about 170 MB, it asks first), or see [Shipping draw.io](#shipping-drawio).

### Claude Code: the plugin

The plugin brings the MCP server, the skill and the check-on-write hook together. It
needs [uv](https://docs.astral.sh/uv/) on your PATH.

```bash
claude plugin marketplace add cintelis/drawio-tools
claude plugin install drawio-tools@drawio-tools
```

Claude Code clones the repository with your own git credentials and never prompts. If
`gh auth login` works for you, run `gh auth setup-git` once so git can use it. Without a
GitHub SSH key, also set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`.

**Updates:** run `claude plugin update drawio-tools@drawio-tools`, or turn on auto-update
under **Marketplaces** in `/plugin`.

**For everyone in a repository**, commit this as `.claude/settings.json` (or merge it
into the one you have). Teammates who trust the folder get the plugin with no commands:

```json
{
  "extraKnownMarketplaces": {
    "drawio-tools": {
      "source": { "source": "github", "repo": "cintelis/drawio-tools" }
    }
  },
  "enabledPlugins": {
    "drawio-tools@drawio-tools": true
  }
}
```

**For a whole organisation**, an admin puts the same keys in managed settings (Team and
Enterprise: claude.ai **Organization settings > Claude Code > Managed settings**) and
adds `"autoUpdate": true` beside `source`, so new releases arrive without anyone
updating.

Just the MCP server, without the skill or hook:
`claude mcp add drawgen -- uvx --from git+https://github.com/cintelis/drawio-tools@v0.2.0 drawgen-mcp`.
In Claude Code, relative paths resolve against the project directory.

### Claude Desktop: the extension

1. From the latest release, download `drawgen-X.Y.Z.mcpb` and `drawio-skill.zip`.
2. Double-click the `.mcpb` (or drag it onto Settings → Extensions) and choose where
   diagrams go. Claude Desktop installs Python and the dependencies itself.
3. Upload `drawio-skill.zip` under Settings → Capabilities → Skills. On Team and
   Enterprise plans, an admin can add the skill for everyone instead.

To update, install the new release's `.mcpb` over the old one.

**Without the extension**, add the server to `claude_desktop_config.json` (Settings →
Developer → Edit Config) and restart Claude. Use the full path to `uvx`, because Desktop
does not inherit your shell's PATH. `DRAWGEN_WORKDIR` is where relative paths land:

```json
{
  "mcpServers": {
    "drawgen": {
      "command": "C:\Users\YOU\.local\bin\uvx.exe",
      "args": ["--from", "git+https://github.com/cintelis/drawio-tools@v0.2.0", "drawgen-mcp"],
      "env": { "DRAWGEN_WORKDIR": "C:\Users\YOU\Documents\Diagrams" }
    }
  }
}
```

### CI and servers: the Docker image

Each release publishes `ghcr.io/cintelis/drawgen:X.Y.Z` (plus `X.Y` and `latest`), with
draw.io Desktop and a virtual display included, so rendering is exact:

```bash
docker run --rm -v "$PWD:/work" -w /work ghcr.io/cintelis/drawgen:0.2.0 drawgen check docs/*.md
```

The image is private like the repository: `docker login ghcr.io` first, using a token
with `read:packages`.

### Development

```bash
git clone https://github.com/cintelis/drawio-tools C:\code\drawio-tools
cd C:\code\drawio-tools
uv sync
uv run drawgen install-drawio   # optional: exact rendering + previews
uv run pytest -q
claude --plugin-dir .           # try the plugin from your checkout
```

## MCP tools

| Tool | Does |
|---|---|
| `spec_reference` | Spec format, kinds, zone colours, edge styles, renderer in use |
| `create_diagram` | Spec → `NAME.drawio.svg` (or `.drawio`, plus png/pdf), with a check report |
| `create_markdown_document` | Markdown with `{{diagram:NAME}}` placeholders → `.md` + `assets/*.drawio.svg` |
| `add_diagram_to_markdown` | Insert under a heading, append, or `replace_link` an existing figure |
| `check_diagram` | Check any `.drawio` / `.drawio.svg` |
| `read_diagram` | XML of a diagram, or the diagrams a `.md` links |
| `update_diagram` | Write edited XML back and re-render in place |
| `export_diagram` | `.drawio` → svg / png / pdf |
| `preview_diagram` | PNG so Claude can see the result (needs draw.io) |
| `drawio_status`, `install_drawio` | Which renderer; fetch draw.io (asks the user first) |

## CLI

```bash
drawgen build spec.yaml -o docs/assets/flow.drawio.svg [--format png] [--strict]
drawgen doc README.md.tmpl -d flow=flow.yaml -d erd=erd.yaml -o README.md
drawgen check docs/*.md docs/assets/*.drawio.svg [--json] [--strict]
drawgen export big.drawio -f svg,png [--no-embed]
drawgen extract figure.drawio.svg -o figure.drawio
drawgen kinds | drawio-status | install-drawio
```

`check` exits 1 on errors (and on warnings with `--strict`), so it can gate CI.

## Shipping draw.io

draw.io Desktop (Apache-2.0) is the only exact renderer, and it is a 150-180 MB Electron
app per platform, so it is **not** bundled. `drawgen install-drawio` downloads the
vendor's portable build for the current OS, **pinned** (`install.VERSION`) and
**verified** against the SHA-256 the release publishes, into a per-user cache
(`%LOCALAPPDATA%\drawgen`, `~/Library/Caches/drawgen`, `~/.cache/drawgen`;
`DRAWGEN_CACHE` overrides). drawgen finds it there automatically, after `DRAWIO_BIN`,
PATH and the usual install locations. To bump: take the asset names and digests from
`gh api repos/jgraph/drawio-desktop/releases/tags/v<version>` into `ASSETS`.

For CI and servers, the `Dockerfile` bakes draw.io and xvfb into an image whose default
command is the MCP server; each release publishes it to GHCR. The CI workflow has an
`exact-render` job doing the same on a plain runner.

## The checker's limits

Two checks are estimates, stated so a warning is read correctly. draw.io routes
orthogonal edges itself at draw time, so `edge-through-shape` approximates the route the
way draw.io's router chooses sides; and there are no font metrics, so `label-overflow`
estimates width from character counts, calibrated against draw.io 31 renders of
Helvetica. Both lean towards reporting. A checker cannot judge whether a diagram tells
its story clearly: that is what `preview_diagram` is for.

## Releasing

1. Set the new version in `pyproject.toml`, `src/drawgen/__init__.py` and
   `.claude-plugin/plugin.json`, then run `uv lock`. `tests/test_release.py` fails if
   they disagree. Claude Code only updates the plugin when `plugin.json` changes, so
   pushed commits without a version bump never reach users.
2. Add a `## X.Y.Z` section to `CHANGELOG.md`. It becomes the release notes.
3. Update the `@vX.Y.Z` pins in this README, merge to `main`, then tag and push:
   `git tag vX.Y.Z && git push origin vX.Y.Z`.

The release workflow checks that the tag matches `pyproject.toml` and runs the tests.
It then publishes the GitHub release (`.mcpb`, skill zip, wheel, sdist) and the GHCR
image. To build the Desktop assets locally, run `uv run python mcpb/build.py` (needs
Node). They land in `dist/`.

## Layout

```
src/drawgen/
  theme.py        kinds, zone colours, edge styles
  diagram.py      Diagram / Document: themed and raw APIs, id guard
  spec.py         YAML/JSON spec -> Document, auto layout
  check.py        the checker
  svg_render.py   built-in mxGraph -> SVG renderer
  export.py       draw.io CLI, editable SVG naming and extraction
  install.py      pinned draw.io download
  markdown.py     markdown documents with editable diagrams
  cli.py          drawgen
  mcp_server.py   drawgen-mcp
skills/drawio/SKILL.md
mcpb/             Claude Desktop extension: manifest template, launcher, build.py
.claude-plugin/, .mcp.json, hooks/hooks.json     Claude Code plugin
examples/clearline/   themed API, 9 diagrams
examples/bluefield/   raw API with its own palette, 8 pages in one file
```
