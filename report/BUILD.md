# Build the technical report

The editable source is [manuscript.md](manuscript.md). Numerical tables and the
quality chart are generated directly from the three retained raw result bundles.
The builder recomputes their analyses and requires all five methods, complete
query counts, successful execution, compatible identities and recorded resource
measurements.

The report environment is optional and separate from retrieval dependencies:

```powershell
py -3.13 -m venv .report-venv
.\.report-venv\Scripts\python.exe -m pip install -r report\requirements.txt
.\.report-venv\Scripts\python.exe -I report\build_report.py --check-only
.\.report-venv\Scripts\python.exe -I report\build_report.py
```

The four pinned rendering-package versions were used for the included report.
Their installation does not alter the retrieval dependency lock or environment.
The source package does not bundle third-party binaries or fonts. Built-in PDF
fonts and generated vector graphics avoid external font or image downloads.

Default raw inputs are `results/release-development/run.json.gz`,
`results/release-heldout/run.json.gz` and
`results/release-heldout-repeat/run.json.gz`. The [input manifest](inputs.json)
binds the manuscript to the exact SHA-256 identities and order of these three
raw bundles. Alternate `--runs` paths are
accepted only when their bytes are identical, and paths must remain under the
repository. For new measurements, update both `inputs.json` and the manuscript
so the abstract and interpretation describe those data, even when the runs are
compatible. Use the generic workbench report command for another dataset.
Use a new `--out` directory to preserve an earlier render. The report requires
the established 94-query splits, including the descriptive subset of 54 answerable
held-out queries with more than ten eligible candidates. Changed counts are rejected.

Outputs are `report.md`, responsive static `report.html`, `report.pdf`,
`figures/quality.svg`, `figures/overview.svg` and `build-receipt.json`. The build record binds raw inputs,
manuscript, input manifest, builder, rendering versions and generated output
hashes. The PDF uses deterministic rendering, removes CreationDate and ModDate
fields, and retains the author metadata. Relative artifact links work in the
HTML; the PDF maps them to the repository's corresponding file paths.

The Markdown parser supports headings, paragraphs, simple bullets, tables,
fenced code, links and explicit `<!-- pagebreak -->` markers. The two supported
figures are the procedure schematic and measured quality chart. Review every rendered PDF page after manuscript or
layout changes: automated text extraction alone cannot establish visual quality.
Building the report uses the retained observations and local rendering packages.

## Procedure schematic

[overview.py](overview.py) is the editable vector source for Figure 1. It uses
one point-based layout for the SVG and the embedded PDF, with labels of at least
9.3 pt at the report's full text width. Dataset counts come from the committed
corpus and queries using the evaluator's filtering function. The builder rejects
counts that differ from the reported dataset and records the two input hashes,
schematic-source hash and derived counts in `build-receipt.json`. Figure 2 retains
the measured quality chart. Neither figure requires model inference.

Run the additional rendering checks in the report environment:

```powershell
.\.report-venv\Scripts\python.exe -B -I report\test_overview.py
```

For a phone preview of the same figure, `overview.preview_pdf` exports its vector
drawing to a separate PDF. Render that file with an available Poppler installation,
for example `pdftoppm -r 300 -singlefile -png overview.pdf overview`.
Poppler is optional preview tooling; the report build needs only the four pinned
Python packages. Record the preview renderer version and resulting PNG hash with
the review assets. Keep temporary renders outside the source distribution.
