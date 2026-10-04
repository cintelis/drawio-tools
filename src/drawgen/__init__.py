"""drawgen: generate, check and export draw.io diagrams, as editable .drawio.svg."""
from .check import Issue, Report, check_file, check_xml
from .diagram import Diagram, DiagramError, Document
from .export import ExportError, find_drawio, render, render_all
from .markdown import add_diagram, diagrams_in, write_document
from .spec import SpecError, build

__all__ = [
    "Diagram", "Document", "DiagramError", "build", "SpecError", "check_file", "check_xml",
    "Issue", "Report", "render", "render_all", "find_drawio", "ExportError",
    "write_document", "add_diagram", "diagrams_in",
]
__version__ = "0.1.0"
