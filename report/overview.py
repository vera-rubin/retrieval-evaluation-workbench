"""Editable vector schematic of the recorded comparison; no retrieval execution."""
from __future__ import annotations

import html
import json
from pathlib import Path
import statistics

from hippo_eval.contracts import eligible

WIDTH, HEIGHT = 515, 386
NAVY, TEAL, GRAY = "#18364B", "#007F83", "#526373"
RULE = "#DBE4EA"


def dataset_statistics(root: Path) -> dict:
    """Derive the schematic's counts from the unchanged evaluation dataset."""
    corpus = json.loads((root / "fixtures/corpus.json").read_text(encoding="utf-8"))
    queries = json.loads((root / "fixtures/queries.json").read_text(encoding="utf-8"))
    records, questions = corpus["records"], queries["queries"]
    pools = [sum(eligible(record, query) for record in records) for query in questions]
    splits = {split: {"queries": len(selected),
                      "answerable": sum(query["answerable"] for query in selected),
                      "empty_relevance": sum(not query["relevance"] for query in selected)}
              for split in ("development", "heldout")
              for selected in [[query for query in questions if query["split"] == split]]}
    actual = {"corpus_records": len(records),
              "indexed_records": sum(record["body"] is not None for record in records),
              "query_count": len(questions),
              "eligible_min": min(pools), "eligible_median": statistics.median(pools),
              "eligible_max": max(pools), "splits": splits}
    expected = {"corpus_records": 300, "indexed_records": 291, "query_count": 188,
                "eligible_min": 1, "eligible_median": 36, "eligible_max": 43,
                "splits": {split: {"queries": 94, "answerable": 79, "empty_relevance": 15}
                           for split in ("development", "heldout")}}
    if actual != expected:
        raise ValueError("Overview counts differ from the report's established dataset")
    return actual


def elements(stats: dict) -> list[tuple]:
    """One point-based layout shared by SVG, embedded PDF and preview PDF."""
    items = []

    def text(x, y, value, size=9.5, color=NAVY, bold=False):
        items.append(("text", x, y, value, size, color, bold))

    def line(x1, y1, x2, y2, color=RULE):
        items.append(("line", x1, y1, x2, y2, color))

    text(12, 16, "SHARED DATA / INDEX CONSTRUCTION", color=TEAL, bold=True)
    text(12, 39, f"{stats['corpus_records']} corpus records", 14, bold=True)
    line(178, 35, 210, 35, TEAL)
    line(205, 31, 210, 35, TEAL)
    line(205, 39, 210, 35, TEAL)
    text(225, 39, f"{stats['indexed_records']} indexed records", 14, bold=True)
    text(12, 58, "Titles and bodies; the same searchable records for all five configurations.")
    items.append(("rect", 0, 73, WIDTH, 43, "#EFF7F7"))
    text(12, 90, "FOR EACH QUERY", 9.5, TEAL, True)
    text(144, 90, "Same query and filtering rules", 10.5, bold=True)
    text(144, 106, f"{stats['eligible_min']}-{stats['eligible_max']} eligible records; median {stats['eligible_median']:g}", 10, TEAL)
    text(12, 135, "CONFIGURATION", 9.3, GRAY, True)
    text(144, 135, "RANK WITHIN THE ELIGIBLE SET", 9.3, GRAY, True)
    text(445, 135, "SELECT", 9.3, GRAY, True)
    methods = (
        ("FTS5 BM25", "Term matching / BM25", "Eligible term matches"),
        ("BGE-small", "Passage cosine similarity", "Best passage score per record"),
        ("MiniLM", "Passage cosine similarity", "Best passage score per record"),
        ("FTS5 + BGE", "Full available component rankings", "Reciprocal-rank fusion"),
        ("FTS5 + MiniLM", "Full available component rankings", "Reciprocal-rank fusion"),
    )
    for index, (label, first, second) in enumerate(methods):
        y = 144 + 34 * index
        text(12, y + 17, label, 10.8, bold=True)
        text(144, y + 12, first, 10)
        text(144, y + 25, second, 9.3, GRAY)
        text(445, y + 12, "up to 10", 10, bold=True)
        text(445, y + 25, "records", 9.3, GRAY)
        line(12, y + 32, WIDTH - 12, y + 32)
    text(12, 334, "AFTER EACH METHOD'S SELECTION", 9.3, TEAL, True)
    text(12, 352, "Fetch and check preservation", 10.7, bold=True)
    text(12, 369, "Complete records: bytes, provenance, fields", 9.3)
    line(259, 345, 259, 375)
    text(276, 352, "Evaluate relevance and rank", 10.7, bold=True)
    text(276, 369, "Relevance labels enter only here", 9.3)
    return items


def svg(stats: dict) -> str:
    output = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}pt" height="{HEIGHT}pt" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="overview-title overview-desc">',
              '<title id="overview-title">One dataset, five retrieval comparisons</title>',
              '<desc id="overview-desc">Procedure schematic. Index construction uses the common searchable corpus. Query-specific filtering restricts ranking. The five configurations select up to ten records; hybrids fuse full available component rankings before selection. Complete-record preservation and relevance evaluation are distinct checks. Layout does not represent timing or concurrent execution.</desc>',
              '<rect width="100%" height="100%" fill="white"/>']
    for kind, *args in elements(stats):
        if kind == "text":
            x, y, value, size, color, bold = args
            output.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{"bold" if bold else "normal"}" fill="{color}">{html.escape(value)}</text>')
        elif kind == "rect":
            x, y, width, height, color = args
            output.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}"/>')
        else:
            x1, y1, x2, y2, color = args
            output.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="0.7"/>')
    return "\n".join(output + ["</svg>"]) + "\n"


def drawing(stats: dict, width=WIDTH):
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor
    result = Drawing(WIDTH, HEIGHT)
    result.add(Rect(0, 0, WIDTH, HEIGHT, fillColor=HexColor("#FFFFFF"), strokeColor=None))
    for kind, *args in elements(stats):
        if kind == "text":
            x, y, value, size, color, bold = args
            result.add(String(x, HEIGHT-y, value, fontName="Helvetica-Bold" if bold else "Helvetica",
                              fontSize=size, fillColor=HexColor(color)))
        elif kind == "rect":
            x, y, box_width, height, color = args
            result.add(Rect(x, HEIGHT-y-height, box_width, height, fillColor=HexColor(color), strokeColor=None))
        else:
            x1, y1, x2, y2, color = args
            result.add(Line(x1, HEIGHT-y1, x2, HEIGHT-y2, strokeColor=HexColor(color), strokeWidth=.7))
    scale = width / WIDTH
    result.scale(scale, scale)
    result.width *= scale
    result.height *= scale
    return result


def preview_pdf(stats: dict, path: Path):
    """Vector intermediate for a PNG preview of exactly the same schematic."""
    from reportlab.graphics import renderPDF
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(str(path), pagesize=(WIDTH, HEIGHT), invariant=1)
    canvas.setTitle("One dataset, five retrieval comparisons")
    canvas.setAuthor("Nathan Chandrasekar")
    renderPDF.draw(drawing(stats), canvas, 0, 0)
    canvas.save()
