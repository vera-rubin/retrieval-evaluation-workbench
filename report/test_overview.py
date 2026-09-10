"""Report-only figure checks; run with the optional report environment."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from report import build_report, overview


class OverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stats = overview.dataset_statistics(ROOT)

    def test_counts_include_filtering_and_separate_query_denominators(self):
        self.assertEqual((self.stats["corpus_records"], self.stats["indexed_records"]), (300, 291))
        self.assertEqual([self.stats[key] for key in ("eligible_min", "eligible_median", "eligible_max")], [1, 36, 43])
        for split in self.stats["splits"].values():
            self.assertEqual(split, {"queries": 94, "answerable": 79, "empty_relevance": 15})

    def test_changed_indexable_count_is_rejected(self):
        corpus = json.loads((ROOT / "fixtures/corpus.json").read_text(encoding="utf-8"))
        queries = json.loads((ROOT / "fixtures/queries.json").read_text(encoding="utf-8"))
        changed = deepcopy(corpus)
        next(row for row in changed["records"] if row["body"] is not None)["body"] = None
        with patch("report.overview.json.loads", side_effect=[changed, queries]):
            with self.assertRaisesRegex(ValueError, "counts differ"):
                overview.dataset_statistics(ROOT)

    def test_changed_query_filter_is_rejected(self):
        corpus = json.loads((ROOT / "fixtures/corpus.json").read_text(encoding="utf-8"))
        queries = json.loads((ROOT / "fixtures/queries.json").read_text(encoding="utf-8"))
        queries["queries"][0]["rules"]["projects"] = []
        with patch("report.overview.json.loads", side_effect=[corpus, queries]):
            with self.assertRaisesRegex(ValueError, "counts differ"):
                overview.dataset_statistics(ROOT)

    def test_svg_accessibility_and_five_method_selections(self):
        tree = ET.fromstring(overview.svg(self.stats))
        ns = {"s": "http://www.w3.org/2000/svg"}
        text = [node.text for node in tree.findall("s:text", ns)]
        for name in ("FTS5 BM25", "BGE-small", "MiniLM", "FTS5 + BGE", "FTS5 + MiniLM"):
            self.assertEqual(text.count(name), 1)
        self.assertEqual(text.count("up to 10"), 5)
        self.assertEqual(text.count("Full available component rankings"), 2)
        self.assertIn("Relevance labels enter only here", text)
        self.assertIn("Procedure schematic", tree.find("s:desc", ns).text)
        self.assertEqual(tree.attrib["role"], "img")

    def test_point_sizes_bounds_and_text_overlap(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        boxes = []
        for item in overview.elements(self.stats):
            if item[0] != "text":
                continue
            _, x, y, value, size, _, bold = item
            width = stringWidth(value, "Helvetica-Bold" if bold else "Helvetica", size)
            self.assertGreaterEqual(size, 9)
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + width, overview.WIDTH)
            self.assertGreaterEqual(y - size, 0)
            self.assertLessEqual(y + .2 * size, overview.HEIGHT)
            box = (x, y-size, x+width, y+.2*size, value)
            for other in boxes:
                intersects = (min(box[2], other[2]) > max(box[0], other[0]) and
                              min(box[3], other[3]) > max(box[1], other[1]))
                self.assertFalse(intersects, (value, other[4]))
            boxes.append(box)

    def test_vector_preview_and_deterministic_bytes(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as directory:
            first, second = [Path(directory) / name for name in ("first.pdf", "second.pdf")]
            overview.preview_pdf(self.stats, first)
            overview.preview_pdf(self.stats, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            pdf = PdfReader(first)
            self.assertEqual(len(pdf.pages), 1)
            self.assertEqual(tuple(map(float, pdf.pages[0].mediabox[2:])), (overview.WIDTH, overview.HEIGHT))
            self.assertEqual(pdf.pages[0].extract_text().count("up to 10"), 5)
            self.assertFalse(pdf.pages[0].get("/Resources", {}).get("/XObject"))
            self.assertEqual(pdf.metadata["/Author"], "Nathan Chandrasekar")

    def test_pdf_and_svg_use_the_same_text_and_font_sizes(self):
        from reportlab.graphics.shapes import String
        drawing = overview.drawing(self.stats)
        actual = [(node.text, node.fontSize) for node in drawing.contents if isinstance(node, String)]
        ns = {"s": "http://www.w3.org/2000/svg"}
        tree = ET.fromstring(overview.svg(self.stats))
        expected = [(node.text, float(node.attrib["font-size"])) for node in tree.findall("s:text", ns)]
        self.assertEqual(actual, expected)

    def test_unsupported_figure_is_still_rejected(self):
        text = "![Unexpected image](figures/unknown.svg)"
        with self.assertRaisesRegex(ValueError, "two verified figures"):
            build_report.html_document(text)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unverified report figure"):
                build_report.build_pdf(text, Path(directory)/"report.pdf", None, self.stats)

    def test_report_has_two_ordered_figures_and_single_captions(self):
        markdown = (ROOT / "report/report.md").read_text(encoding="utf-8")
        figures = [value for kind, value in build_report.blocks(markdown) if kind == "figure"]
        self.assertEqual([value[1] for value in figures], ["figures/overview.svg", "figures/quality.svg"])
        self.assertTrue(figures[0][0].startswith("Figure 1."))
        self.assertTrue(figures[1][0].startswith("Figure 2."))
        rendered = build_report.html_document(markdown)
        self.assertEqual(rendered.count("<figure>"), 2)
        self.assertEqual(rendered.count("<figcaption>Figure 1."), 1)
        self.assertEqual(rendered.count("<figcaption>Figure 2."), 1)
        self.assertIn("fifteen empty-relevance queries", figures[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
