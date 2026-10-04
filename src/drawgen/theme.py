"""The visual theme: component kinds, zone tints and edge styles.

Colour encodes the TYPE of a component, never its meaning on its own; the label
carries the meaning. That is what lets one palette serve every diagram, and it
is why callers (and Claude) pick a kind rather than a hex value.
"""
from __future__ import annotations

FONT = "Helvetica"

# Three sizes only: title, node, edge/annotation.
TITLE_SIZE = 20
NODE_SIZE = 12
EDGE_SIZE = 10

# fill, stroke, font colour, shape. Muted, print-safe, readable in light and dark viewers.
KINDS: dict[str, dict] = {
    "actor":     {"fill": "#E8EEF9", "stroke": "#3B5BA9", "font": "#1F2A44", "shape": "actor", "label": "Person / role"},
    "external":  {"fill": "#F3F4F6", "stroke": "#6B7280", "font": "#1F2937", "shape": "box", "dashed": True, "label": "External system"},
    "service":   {"fill": "#E6F4EA", "stroke": "#2E7D4F", "font": "#14361F", "shape": "box", "label": "Service"},
    "ai":        {"fill": "#F3E8FD", "stroke": "#7B3FBF", "font": "#2E1252", "shape": "box", "label": "AI component"},
    "worker":    {"fill": "#FFF4E0", "stroke": "#C27C0E", "font": "#4A2F05", "shape": "box", "label": "Background worker"},
    "datastore": {"fill": "#E3F2FD", "stroke": "#1E6FB8", "font": "#0B2A47", "shape": "cylinder", "label": "Data store"},
    "queue":     {"fill": "#FDECEC", "stroke": "#B23A3A", "font": "#4A1414", "shape": "queue", "label": "Queue / stream"},
    "ui":        {"fill": "#E0F7F6", "stroke": "#0F8A84", "font": "#073B38", "shape": "box", "label": "User interface"},
    "gov":       {"fill": "#FFF8E1", "stroke": "#8D6E00", "font": "#3D3000", "shape": "box", "label": "Government source"},
    "security":  {"fill": "#FDF2F8", "stroke": "#A23B72", "font": "#4A1030", "shape": "box", "label": "Security control"},
    "decision":  {"fill": "#FFFFFF", "stroke": "#374151", "font": "#111827", "shape": "rhombus", "label": "Decision"},
    "step":      {"fill": "#FFFFFF", "stroke": "#374151", "font": "#111827", "shape": "box", "label": "Process step"},
    "terminal":  {"fill": "#1F2937", "stroke": "#1F2937", "font": "#FFFFFF", "shape": "pill", "label": "Start / end"},
    "note":      {"fill": "#FFFBEB", "stroke": "#D4B106", "font": "#3D3000", "shape": "note", "label": "Note"},
}

ZONE_COLOURS: dict[str, tuple[str, str]] = {
    "blue":   ("#F5F8FE", "#9DB4E3"),
    "green":  ("#F4FAF6", "#9CCBAE"),
    "purple": ("#FAF5FE", "#C9A8EC"),
    "amber":  ("#FFFBF2", "#E6C27A"),
    "grey":   ("#F9FAFB", "#C4C9D1"),
    "red":    ("#FEF7F7", "#E5A3A3"),
    "teal":   ("#F2FBFA", "#8FD1CC"),
}

EDGE_STYLES: dict[str, dict] = {
    "sync":  {"stroke": "#374151", "dashed": False, "width": 1.5, "label": "Synchronous call"},
    "async": {"stroke": "#B23A3A", "dashed": True, "width": 1.5, "label": "Async / event"},
    "data":  {"stroke": "#1E6FB8", "dashed": False, "width": 1.5, "label": "Data flow"},
    "ai":    {"stroke": "#7B3FBF", "dashed": False, "width": 1.5, "label": "Model call"},
    "weak":  {"stroke": "#9CA3AF", "dashed": True, "width": 1.0, "label": "Optional / manual"},
}

# Default node sizes. Wide enough for a two-word label plus a sub-line at 12px.
NODE_W, NODE_H = 170, 64


def describe() -> dict:
    """The theme as plain data, for `drawgen kinds` and the MCP `list_kinds` tool."""
    return {
        "kinds": {k: {"label": v["label"], "shape": v["shape"], "fill": v["fill"], "stroke": v["stroke"]}
                  for k, v in KINDS.items()},
        "zone_colours": list(ZONE_COLOURS),
        "edge_styles": {k: v["label"] for k, v in EDGE_STYLES.items()},
        "default_node_size": [NODE_W, NODE_H],
    }
