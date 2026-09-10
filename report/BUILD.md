# Build the technical report

The editable source is [manuscript.md](manuscript.md). Numerical tables and the
vector chart are generated directly from the three retained raw result bundles.
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
`figures/quality.svg` and `build-receipt.json`. The build record binds raw inputs,
manuscript, input manifest, builder, rendering versions and generated output
hashes. The PDF uses deterministic rendering, removes CreationDate and ModDate
fields, and retains the author metadata. Relative artifact links work in the
HTML; the PDF maps them to the repository's corresponding file paths.

The Markdown parser supports headings, paragraphs, simple bullets, tables,
fenced code, links and explicit `<!-- pagebreak -->` markers. Only the measured
quality chart is embedded. Review every rendered PDF page after manuscript or
layout changes: automated text extraction alone cannot establish visual quality.
Building the report uses the retained observations and local rendering packages.
