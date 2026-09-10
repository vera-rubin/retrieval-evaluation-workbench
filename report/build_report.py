"""Build the technical report from verified raw observations and Markdown source."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import html
import importlib.metadata
import io
import json
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.summarize_results import summarize
from hippo_eval.contracts import digest
from report import overview

TITLE = "Reproducible Retrieval Evaluation: A Workbench for Lexical, Semantic, and Hybrid Search"
SHORT_TITLE = "Reproducible Retrieval Evaluation"
AUTHOR = "Nathan Chandrasekar"
REPOSITORY = "https://github.com/vera-rubin/retrieval-evaluation-workbench"
ORDER = ("lexical", "bge", "minilm", "hybrid_bge", "hybrid_minilm")
LABELS = dict(zip(ORDER, ("FTS5 BM25", "BGE-small", "MiniLM", "FTS+BGE", "FTS+MiniLM")))
DEFAULT_RUNS = ("results/release-development/run.json.gz", "results/release-heldout/run.json.gz", "results/release-heldout-repeat/run.json.gz")
NAVY, TEAL, GRAY = "#18364B", "#007F83", "#526373"
WIDTH, HEIGHT = 720, 335


def verify_input_bindings(paths, manifest):
    """Do not attach fixed narrative claims to a different measurement run."""
    if manifest.get("schema") != "retrieval-evaluation-report-inputs/v1":
        raise ValueError("Unsupported report input manifest")
    entries = manifest.get("inputs")
    if not isinstance(entries, list) or len(entries) != 3 or len(paths) != 3:
        raise ValueError("Report narrative requires its three exact raw inputs")
    for path, entry in zip(paths, entries):
        if (not isinstance(entry, dict) or not isinstance(entry.get("file"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", entry.get("sha256", ""))):
            raise ValueError("Malformed report input binding")
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("Report input leaves the public repository")
        if sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Report narrative is bound to different raw bytes or input order; revise inputs.json and manuscript deliberately before using new measurements")


def method_map(run):
    methods = {m["name"]: m for m in run["analysis"]["methods"]}
    if set(methods) != set(ORDER):
        raise ValueError("Report requires exactly the five declared retrieval methods")
    for name, method in methods.items():
        summary = method.get("summary")
        if (method.get("status") != "EXECUTED" or not method.get("valid") or not summary
                or summary["error_queries"] or summary["unavailable_queries"]):
            raise ValueError(f"Report requires complete successful execution: {name}")
        if summary["query_count"] != 94 or summary["answerable_queries"] != 79 or summary["unanswerable_queries"] != 15:
            raise ValueError("Report counts differ from the established 94-query split")
    return methods


def markdown_table(headers, rows):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def fmt(value, places=4):
    if value is None:
        raise ValueError("A required report measurement is absent")
    return f"{value:.{places}f}"


def substitutions(runs):
    development, heldout, repeat = runs
    if [r["split"] for r in runs] != ["development", "heldout", "heldout"]:
        raise ValueError("Inputs must be development, heldout, heldout-repeat in that order")
    maps = [method_map(run) for run in runs]
    for run in runs[1:]:
        for key in ("fixture_digest", "source_digest", "dependency_digest", "metric_version"):
            if run["source_identity"][key] != runs[0]["source_identity"][key]:
                raise ValueError(f"Report runs have incompatible {key}")
        if run["configuration"] != development["configuration"]:
            raise ValueError("Report runs have incompatible configuration")
    for name in ORDER:
        if any(mapping[name]["identity"] != maps[0][name]["identity"] for mapping in maps[1:]):
            raise ValueError(f"Report runs have incompatible method identity: {name}")
    def quality(mapping):
        return markdown_table(["Method", "Recall@10", "Precision@10", "MRR@10", "nDCG@10"],
                              [[LABELS[name], *[fmt(mapping[name]["summary"][field]) for field in
                                 ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k")]] for name in ORDER])
    latency_rows = []
    setup_rows = []
    pool_rows = []
    for name in ORDER:
        first, second = maps[1][name]["summary"], maps[2][name]["summary"]
        if first["latency"]["count"] != 94 or second["latency"]["count"] != 94:
            raise ValueError("Latency sample count differs from observed query count")
        latency_rows.append([LABELS[name], *[fmt(source["latency"][key], 2)
                            for source in (first, second) for key in ("p50_ms", "p95_ms")]])
        measure = heldout["measurements"][name]
        setup_rows.append([LABELS[name], fmt(measure["load_ms"] / 1000, 3), fmt(measure["index_ms"] / 1000, 3)])
        selected = [q for q in maps[1][name]["queries"] if q["answerable"] and q["eligible_record_count"] > 10]
        if len(selected) != 54:
            raise ValueError("Expected 54 answerable heldout queries with more than ten eligible records")
        pool_rows.append([LABELS[name], len(selected),
                          fmt(statistics.fmean(q["metrics"]["recall_at_k"] for q in selected)),
                          fmt(statistics.fmean(q["metrics"]["ndcg_at_k"] for q in selected))])
    resource_rows = []
    for label, run in zip(("Development", "Heldout", "Heldout repeat"), runs):
        resource = run["resource"]
        if not resource or resource.get("failure") is not None or resource.get("child_exit_code") != 0:
            raise ValueError("Report requires a successful sampled resource receipt")
        resource_rows.append([label, fmt(resource["peak_rss_bytes"] / 1024**2, 1), resource["rss_samples"], fmt(resource["elapsed_ms"] / 1000, 1)])
    identity_rows = [[Path(run["raw_file"]).parent.name, run["raw_sha256"]] for run in runs]
    return {
        "QUALITY_TABLE": quality(maps[1]),
        "DEVELOPMENT_TABLE": quality(maps[0]),
        "LATENCY_TABLE": markdown_table(["Method", "First p50 ms", "First p95 ms", "Repeat p50 ms", "Repeat p95 ms"], latency_rows),
        "SETUP_TABLE": markdown_table(["Method", "Load seconds", "Index seconds"], setup_rows),
        "RESOURCE_TABLE": markdown_table(["Run", "Peak RSS MiB", "RSS samples", "Elapsed seconds"], resource_rows),
        "POOL_TABLE": markdown_table(["Method", "Queries", "Recall@10", "nDCG@10"], pool_rows),
        "QUALITY_FIGURE": "![Figure 2. Recall and nDCG on the 79 answerable held-out queries in the primary pass.](figures/quality.svg)",
        "MEASUREMENTS_ID": markdown_table(["Raw bundle directory", "SHA-256 of run.json.gz"], identity_rows),
    }


def chart_elements(heldout):
    mapping = method_map(heldout)
    elements = []
    left, plot_width, top = 145, 505, 60
    elements.append(("text", 12, 24, "Heldout retrieval quality (79 answerable queries)", 18, NAVY))
    for tick in (0, .25, .5, .75, 1):
        x = left + tick * plot_width
        elements.append(("line", x, top - 8, x, 309, "#DFE6EB"))
        elements.append(("text", x - 9, 326, fmt(tick, 2), 11, GRAY))
    for index, name in enumerate(ORDER):
        y = top + index * 49
        elements.append(("text", 12, y + 18, LABELS[name], 14, NAVY))
        summary = mapping[name]["summary"]
        for offset, field, color in ((0, "recall_at_k", TEAL), (20, "ndcg_at_k", NAVY)):
            value = summary[field]
            elements.append(("rect", left, y + offset, value * plot_width, 15, color))
            elements.append(("text", left + value * plot_width + 5, y + offset + 12, fmt(value, 3), 11, color))
    elements.append(("rect", 470, 12, 11, 11, TEAL))
    elements.append(("text", 487, 23, "Recall@10", 12, NAVY))
    elements.append(("rect", 580, 12, 11, 11, NAVY))
    elements.append(("text", 597, 23, "nDCG@10", 12, NAVY))
    return elements


def svg_chart(heldout):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
             '<title id="title">Recall and nDCG for five retrieval methods</title>',
             '<desc id="desc">Exact observed heldout macro averages over 79 answerable queries; zero-baseline bars without uncertainty intervals.</desc>',
             '<rect width="100%" height="100%" fill="white"/>']
    for item in chart_elements(heldout):
        kind, *args = item
        if kind == "text":
            x, y, text, size, color = args
            parts.append(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" fill="{color}">{html.escape(text)}</text>')
        elif kind == "rect":
            x, y, width, height, color = args
            parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}"/>')
        else:
            x1, y1, x2, y2, color = args
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"/>')
    return "\n".join(parts + ["</svg>"]) + "\n"


def pdf_chart(heldout, width):
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor
    drawing = Drawing(WIDTH, HEIGHT)
    for item in chart_elements(heldout):
        kind, *args = item
        if kind == "text":
            x, y, text, size, color = args
            drawing.add(String(x, HEIGHT-y, text, fontName="Helvetica", fontSize=size, fillColor=HexColor(color)))
        elif kind == "rect":
            x, y, bar_width, height, color = args
            drawing.add(Rect(x, HEIGHT-y-height, bar_width, height, fillColor=HexColor(color), strokeColor=None))
        else:
            x1, y1, x2, y2, color = args
            drawing.add(Line(x1, HEIGHT-y1, x2, HEIGHT-y2, strokeColor=HexColor(color)))
    scale = min(width / WIDTH, 220 / HEIGHT)
    drawing.scale(scale, scale)
    drawing.width *= scale
    drawing.height *= scale
    return drawing


def blocks(markdown):
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
        elif line == "<!-- pagebreak -->":
            yield "pagebreak", None
            index += 1
        elif line.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            if index == len(lines):
                raise ValueError("Unclosed Markdown code fence")
            yield "code", "\n".join(code)
            index += 1
        elif line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                values = [c.strip() for c in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", value) for value in values):
                    rows.append(values)
                index += 1
            if len({len(row) for row in rows}) != 1:
                raise ValueError("Inconsistent Markdown table column count")
            yield "table", rows
        elif re.match(r"^#{1,3} ", line):
            level = len(line.split(" ", 1)[0])
            yield "heading", (level, line[level+1:])
            index += 1
        elif line.startswith("!["):
            match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if not match:
                raise ValueError("Malformed figure reference")
            yield "figure", (match[1], match[2])
            index += 1
        elif line.startswith(("- ", "* ")):
            yield "bullet", line[2:]
            index += 1
        else:
            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip() and not re.match(r"^(#{1,3} |[-*] |\||```|!\[|<!-- pagebreak -->)", lines[index].strip()):
                paragraph.append(lines[index].strip())
                index += 1
            yield "paragraph", " ".join(paragraph)


def link_url(url, pdf=False):
    if urlparse(url).scheme:
        if urlparse(url).scheme not in ("http", "https", "mailto"):
            raise ValueError("Unsupported manuscript link scheme")
        return url
    if not pdf:
        return url
    if url.startswith("#"):
        return REPOSITORY + "/blob/main/report/report.md" + url
    target = (ROOT / "report" / url.split("#", 1)[0]).resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("Manuscript local link leaves the public repository")
    suffix = "#" + url.split("#", 1)[1] if "#" in url else ""
    return REPOSITORY + "/blob/main/" + quote(target.relative_to(ROOT).as_posix()) + suffix


def inline(text, pdf=False):
    text = text.replace("\u2011", "-").replace("\u2212", "-")
    tokens = re.split(r"(\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)", text)
    output = []
    for token in tokens:
        match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", token)
        if match:
            url = html.escape(link_url(match[2], pdf), quote=True)
            output.append(f'<a href="{url}" color="{TEAL}">{html.escape(match[1])}</a>')
        elif token.startswith("`") and token.endswith("`"):
            value = html.escape(token[1:-1])
            output.append(f'<font name="Courier" size="9">{value}</font>' if pdf else f'<code>{value}</code>')
        elif token.startswith("**") and token.endswith("**"):
            output.append('<b>' + html.escape(token[2:-2]) + '</b>')
        elif token.startswith("*") and token.endswith("*"):
            output.append('<i>' + html.escape(token[1:-1]) + '</i>')
        else:
            output.append(html.escape(token))
    return "".join(output)


CSS = """body{margin:0;background:#edf2f5;color:#18364b;font:17px/1.65 system-ui,Arial,sans-serif}main{max-width:850px;margin:auto;background:white;padding:36px 42px 60px}h1{font-size:2.05rem;line-height:1.2}h2{font-size:1.45rem;line-height:1.3;border-top:1px solid #dce5eb;padding-top:24px;margin-top:36px}h3{font-size:1.15rem}a{color:#007f83;text-underline-offset:3px}p{margin:0 0 16px}code{font-size:.84em;overflow-wrap:anywhere}pre{background:#f2f6f8;padding:15px;overflow:auto;font-size:13px;line-height:1.5}figure{margin:24px 0}figure img{width:100%;height:auto}figcaption{font-size:14px;color:#526373}.table-scroll{overflow:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.45}th,td{padding:9px 10px;border-bottom:1px solid #dce5eb;text-align:right;vertical-align:top}th{color:white;background:#18364b}th:first-child,td:first-child{text-align:left}tbody tr:nth-child(even){background:#f4f7f9}td{overflow-wrap:anywhere}.pagebreak{border:0;border-top:1px solid #dce5eb;margin:34px 0}footer{font-size:13px;color:#526373;margin-top:36px}@media(max-width:600px){main{padding:22px 18px}h1{font-size:1.8rem}body{font-size:16px}th,td{padding:7px}table{min-width:480px}}@media print{body{background:white}main{max-width:none;padding:0}.pagebreak{break-after:page;border:0}}"""


def html_document(markdown):
    output = []
    for kind, value in blocks(markdown):
        if kind == "heading":
            level, text = value
            anchor = re.sub(r"[^a-z0-9 -]", "", text.lower()).replace(" ", "-")
            output.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
        elif kind == "paragraph":
            output.append('<p>' + inline(value) + '</p>')
        elif kind == "bullet":
            output.append('<ul><li>' + inline(value) + '</li></ul>')
        elif kind == "code":
            output.append('<pre><code>' + html.escape(value) + '</code></pre>')
        elif kind == "table":
            head, *rows = value
            table = '<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + inline(x) + '</th>' for x in head) + '</tr></thead><tbody>'
            table += ''.join('<tr>' + ''.join('<td>' + inline(x) + '</td>' for x in row) + '</tr>' for row in rows)
            output.append(table + '</tbody></table></div>')
        elif kind == "figure":
            caption, path = value
            if path not in ("figures/quality.svg", "figures/overview.svg"):
                raise ValueError("The report builder supports only its two verified figures")
            output.append(f'<figure><img src="{path}" alt="{html.escape(caption, quote=True)}"><figcaption>{inline(caption)}</figcaption></figure>')
        else:
            output.append('<hr class="pagebreak">')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            f'<meta name="author" content="{AUTHOR}"><title>{html.escape(TITLE)}</title><style>{CSS}</style></head><body><main>' +
            '\n'.join(output) + '</main></body></html>\n')


def build_pdf(markdown, path, heldout, overview_stats):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
    from reportlab.lib.colors import HexColor
    width = A4[0] - 80
    styles = {
        'body': ParagraphStyle('Body', fontName='Helvetica', fontSize=10.7, leading=14.1, spaceAfter=7, textColor=HexColor(NAVY), splitLongWords=True),
        'h1': ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=25, leading=29, spaceBefore=5, spaceAfter=16, textColor=HexColor(NAVY), keepWithNext=True),
        'h2': ParagraphStyle('Heading', fontName='Helvetica-Bold', fontSize=15, leading=18, spaceBefore=10, spaceAfter=7, textColor=HexColor(NAVY), keepWithNext=True),
        'h3': ParagraphStyle('Subheading', fontName='Helvetica-Bold', fontSize=12, leading=15, spaceBefore=8, spaceAfter=6, textColor=HexColor(TEAL), keepWithNext=True),
        'cell': ParagraphStyle('Cell', fontName='Helvetica', fontSize=8.5, leading=11.5, textColor=HexColor(NAVY), splitLongWords=True),
        'tablehead': ParagraphStyle('TableHead', fontName='Helvetica-Bold', fontSize=8.5, leading=11.5, textColor=colors.white, splitLongWords=True),
        'caption': ParagraphStyle('Caption', fontName='Helvetica', fontSize=8.7, leading=12, spaceAfter=12, textColor=HexColor(GRAY)),
        'code': ParagraphStyle('Code', fontName='Courier', fontSize=8.0, leading=10.5, spaceAfter=10, textColor=HexColor(NAVY), splitLongWords=True),
    }
    story = []
    for kind, value in blocks(markdown):
        if kind == 'heading':
            level, text = value
            story.append(Paragraph(inline(text, True), styles['h' + str(level)]))
        elif kind == 'paragraph':
            story.append(Paragraph(inline(value, True), styles['body']))
        elif kind == 'bullet':
            style = ParagraphStyle('Bullet', parent=styles['body'], leftIndent=12, firstLineIndent=-9, spaceAfter=5)
            story.append(Paragraph('- ' + inline(value, True), style))
        elif kind == 'code':
            story.append(Paragraph('<br/>'.join(html.escape(line).replace(' ', '&nbsp;') for line in value.splitlines()), styles['code']))
        elif kind == 'pagebreak':
            story.append(PageBreak())
        elif kind == 'figure':
            caption, figure = value
            if figure == 'figures/quality.svg':
                graphic = pdf_chart(heldout, width)
            elif figure == 'figures/overview.svg':
                graphic = overview.drawing(overview_stats, width)
            else:
                raise ValueError('Unverified report figure')
            story.append(KeepTogether([graphic, Paragraph(inline(caption, True), styles['caption'])]))
        else:
            rows = [[Paragraph(inline(cell, True), styles['tablehead'] if index == 0 else styles['cell']) for cell in row]
                    for index, row in enumerate(value)]
            columns = len(rows[0])
            first = width * (.30 if columns >= 4 else .35)
            table = Table(rows, colWidths=[first] + [(width-first)/(columns-1)]*(columns-1), repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor(NAVY)),
                                       ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,HexColor('#F2F6F8')]),
                                       ('LINEBELOW',(0,0),(-1,-1),.35,HexColor('#DBE4EA')),
                                       ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),
                                       ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),3),
                                       ('BOTTOMPADDING',(0,0),(-1,-1),3)]))
            story.extend([table, Spacer(1,8)])
    def page_frame(canv, doc):
        canv.saveState()
        canv.setFont('Helvetica',8)
        canv.setFillColor(HexColor(GRAY))
        canv.drawString(46,A4[1]-28,SHORT_TITLE)
        canv.drawRightString(A4[0]-46,27,str(doc.page))
        canv.setStrokeColor(HexColor('#DBE4EA'))
        canv.line(46,A4[1]-34,A4[0]-46,A4[1]-34)
        canv.restoreState()
    def deterministic_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        return canvas.Canvas(*args, **kwargs)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=40,rightMargin=40,topMargin=46,bottomMargin=40,
                            title=TITLE, author=AUTHOR, subject='Software technical report with reproducible synthetic retrieval measurements',
                            creator='Reproducible Retrieval Evaluation report builder')
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame, canvasmaker=deterministic_canvas)
    # Invariant rendering must not suggest a fictitious publication date.
    # Public pypdf metadata setters preserve pages and links while clearing dates.
    from pypdf import PdfWriter
    writer = PdfWriter(clone_from=io.BytesIO(path.read_bytes()))
    writer.metadata = {key: value for key, value in dict(writer.metadata or {}).items()
                       if key not in ("/CreationDate", "/ModDate")}
    with path.open("wb") as output:
        writer.write(output)
    writer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manuscript', type=Path, default=ROOT/'report/manuscript.md')
    parser.add_argument('--runs', type=Path, nargs=3, default=[ROOT/p for p in DEFAULT_RUNS])
    parser.add_argument('--out', type=Path, default=ROOT/'report')
    parser.add_argument('--check-only', action='store_true', help='Validate inputs/substitutions without creating artifacts')
    args = parser.parse_args()
    manifest_path = ROOT / 'report/inputs.json'
    inputs_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    verify_input_bindings(args.runs, inputs_manifest)
    runs = [summarize(p.resolve()) for p in args.runs]
    values = substitutions(runs)
    overview_stats = overview.dataset_statistics(ROOT)
    source = args.manuscript.read_text(encoding='utf-8')
    requested = re.findall(r'\{\{([A-Z_]+)\}\}', source)
    if set(requested) - set(values):
        raise ValueError('Unknown manuscript substitutions: ' + ', '.join(sorted(set(requested)-set(values))))
    for name, value in values.items():
        source = source.replace('{{' + name + '}}', value)
    if '{{' in source or '}}' in source:
        raise ValueError('Unresolved manuscript placeholder')
    parsed = list(blocks(source))
    rendered_html = html_document(source)
    if args.check_only:
        print(json.dumps({'valid':True,'raw_runs':len(runs),'blocks':len(parsed),'explicit_pages':1+sum(kind=='pagebreak' for kind,_ in parsed),
                          'substitutions':requested,'source_digest':runs[0]['source_identity']['source_digest']},indent=2))
        return
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'figures').mkdir(exist_ok=True)
    (args.out/'figures/quality.svg').write_text(svg_chart(runs[1]),encoding='utf-8',newline='\n')
    (args.out/'figures/overview.svg').write_text(overview.svg(overview_stats),encoding='utf-8',newline='\n')
    (args.out/'report.md').write_text(source,encoding='utf-8',newline='\n')
    (args.out/'report.html').write_text(rendered_html,encoding='utf-8',newline='\n')
    build_pdf(source,args.out/'report.pdf',runs[1],overview_stats)
    outputs = ('report.md','report.html','report.pdf','figures/quality.svg','figures/overview.svg')
    receipt={'schema':'retrieval-evaluation-report-build/v1','raw_inputs':[{key:run[key] for key in ('raw_file','raw_sha256')} for run in runs],
             'manuscript_sha256':sha256(args.manuscript.read_bytes()).hexdigest(),
             'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
             'inputs_manifest_sha256':sha256(manifest_path.read_bytes()).hexdigest(),
             'overview':{'source_sha256':sha256(Path(overview.__file__).read_bytes()).hexdigest(),
                         'dataset_inputs':{name:sha256((ROOT/name).read_bytes()).hexdigest()
                                           for name in ('fixtures/corpus.json','fixtures/queries.json')},
                         'statistics':overview_stats,'kind':'logical_procedure_schematic'},
             'dependencies':{name:importlib.metadata.version(name) for name in ('reportlab','Pillow','charset-normalizer','pypdf')},
             'outputs':{name:sha256((args.out/name).read_bytes()).hexdigest() for name in outputs},
             'scope':'Observed synthetic retrieval results; known query splits; no retuning or inferential significance claims'}
    (args.out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'built':list(outputs),'raw_runs':len(runs),'deterministic_pdf_metadata':True,'pdf_date_fields':'omitted'},indent=2))


if __name__ == '__main__':
    main()
