---
name: drawio
description: Create and edit draw.io diagrams as editable .drawio.svg files, alone or inside markdown documents that render on GitHub and in GuardStein. Use for architecture, data-flow, sequence, ER and process diagrams, or whenever the user asks for a diagram, a figure in a document, or a change to an existing .drawio / .drawio.svg.
---

# draw.io diagrams with drawgen

Use the drawgen MCP tools. They write `NAME.drawio.svg`: an SVG that GitHub shows as a
picture, with the diagram embedded so draw.io, its VS Code extension and GuardStein open
it for editing. Never hand-write mxGraph XML for a new diagram; write a spec.

## Workflow

1. `spec_reference` once per session: spec format, kinds, zone colours, edge styles, and
   whether draw.io Desktop is installed.
2. Write the spec (below).
3. Write it:
   - a figure for a document: `create_markdown_document` (new file, `{{diagram:NAME}}`
     placeholders) or `add_diagram_to_markdown` (existing file, `after_heading`);
   - a standalone file: `create_diagram` with `output_path: NAME.drawio.svg`.
4. Read the `check` report in the result. Fix EVERY error and warning, then write again:
   - `overlap` / `out-of-page`: move or resize; leave 40px between shapes.
   - `edge-through-shape`: set `exit`/`entry`, or add `points` that route around.
   - `label-overflow`: widen the box (w) or shorten the label; move detail into `sub`.
   - `dangling-edge`: an edge names an id that does not exist.
5. If `preview_diagram` works (draw.io installed), look at the image before finishing.
   Check that the story reads left to right or top to bottom and nothing is cramped.

To change an existing diagram: `read_diagram` on the `.drawio.svg` (or on the `.md` to
list its diagrams), edit the XML, `update_diagram`. For a diagram you made from a spec,
regenerating from the edited spec is cleaner; use `add_diagram_to_markdown` with
`replace_link` to swap the figure in its document.

## Into a GuardStein note

When the guardstein MCP server is connected (`guardstein_*` tools) and the user wants
the diagram in a note:

1. Write it locally with `create_diagram`, `output_path: <name>.drawio.svg`, and fix the
   check report as above.
2. `guardstein_add_diagram` with that path and an `alt` caption:
   - existing note: `note_id` (from `guardstein_list_notes`), plus `after_heading` to
     place it under a section;
   - edited diagram: `replace_link` with the `assets/...` link already in the note
     (`guardstein_read_note` shows it);
   - otherwise it creates a new note (`title`, `folder`).
It reads the note, inserts the link and writes it back with the version it read, so a
concurrent edit is never overwritten. Don't paste the link in with
`guardstein_update_note` yourself unless you are also changing text.

To edit a diagram that is already in a note: `guardstein_read_asset` returns the SVG
text; the draw.io XML is the root `content` attribute. Save it as a local .drawio, edit
or rebuild, write a new .drawio.svg, then `guardstein_add_diagram` with `replace_link`.
Vault workspaces refuse API writes by design; say so rather than retrying.

## Spec rules

- Pick a `kind` for every component; colour comes from the theme and means type only.
  The label carries the meaning. Never put colours in a spec.
  actor, external, service, ai, worker, datastore, queue, ui, gov, security, decision,
  step, terminal, note.
- Label every edge with what crosses it (`HTTPS`, `order.created`, `SQL`). Edge `style`:
  sync (default), async, data, ai, weak.
- Group with `zones` (a tinted, titled container). A node inside a zone uses
  `zone: <id>` and absolute page coordinates inside the zone's rectangle; leave 40px
  under the zone title.
- Layout: give `x`/`y` for anything that matters; `layout: auto` places nodes without
  coordinates left to right by dependency, which suits pipelines and simple flows.
  Default node size is 170 x 64; widen to 200-240 for two-word labels with a `sub`.
- Grid: align on multiples of 10, keep a consistent gap (40-80px), one flow direction.
- `legend: true` adds a legend of the kinds and edge styles used, beside the content.
- Leave out `width`/`height` and the page is sized to the content.
- One idea per diagram. Over about 15 nodes, split into pages (`pages: [...]`) or
  separate figures.

## Example

```yaml
title: Order flow
subtitle: From checkout to the warehouse
zones:
  - {id: aws, label: AWS ap-southeast-2, x: 260, y: 90, w: 700, h: 260, colour: amber}
nodes:
  - {id: shopper, label: Shopper, kind: actor, x: 40, y: 160}
  - {id: api, label: Orders API, kind: service, sub: Node 24 on ECS, zone: aws, x: 300, y: 160}
  - {id: db, label: Postgres, kind: datastore, zone: aws, x: 560, y: 140, w: 140, h: 90}
  - {id: q, label: Order events, kind: queue, zone: aws, x: 760, y: 160}
edges:
  - {from: shopper, to: api, label: POST /orders}
  - {from: api, to: db, label: insert, style: data}
  - {from: api, to: q, label: order.created, style: async, exit: bottom, entry: bottom,
     points: [[385, 290], [845, 290]]}
legend: true
```

## Rendering

Without draw.io Desktop the SVG is drawn by a built-in renderer: approximate, still
editable, redrawn exactly the next time anyone saves it in draw.io. `drawio_status` says
which is in use. `install_drawio` fetches draw.io (pinned, checksum-verified, about
150-180 MB); ask the user first.
