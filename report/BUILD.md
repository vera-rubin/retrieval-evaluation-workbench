# Build the technical report

The editable source is [manuscript.md](manuscript.md). Numerical tables and the
vector chart are generated directly from the three retained raw result bundles.
The builder recomputes their analyses and requires all five methods, complete
query counts, successful execution, compatible identities and measured resource
receipts. It never trusts a manually edited table or cached summary as evidence.

The report environment is optional and separate from retrieval dependencies:

```powershell
py -3.13 -m venv .report-venv
.\.report-venv\Scripts\python.exe -m pip install -r report\requirements.txt
.\.report-venv\Scripts\python.exe -I report\build_report.py --check-only
.\.report-venv\Scripts\python.exe -I report\build_report.py
```

The four exact rendering-package versions were used for this candidate build.
Their installation does not alter the retrieval dependency lock or environment.
The source package does not bundle third-party binaries or fonts. Built-in PDF
fonts and generated vector graphics avoid external font or image downloads.

Default raw inputs are `results/release-development/run.json.gz`,
`results/release-heldout/run.json.gz` and
`results/release-heldout-repeat/run.json.gz`. The [input manifest](inputs.json) binds the manuscript to the exact SHA-256
identities and order of these three raw bundles. Alternate `--runs` paths are
accepted only when their bytes are identical, and paths must remain under the
repository. New measurements require a deliberate review and revision of both
`inputs.json` and the manuscript, even when the evaluator considers the runs
compatible; its fixed abstract and interpretation must not silently describe
different data. Use the generic workbench report command for an unrelated run.
Use a new `--out` directory to preserve an earlier render. The report is specific to the established 94-query splits, including
the diagnostic subset of 54 answerable heldout queries with more than ten
eligible candidates; it rejects changed counts rather than silently relabeling
another dataset.

Outputs are `report.md`, responsive static `report.html`, `report.pdf`,
`figures/quality.svg` and `build-receipt.json`. The receipt binds raw inputs,
manuscript, input manifest, builder, rendering versions and generated output
hashes. The PDF uses deterministic rendering, removes CreationDate and ModDate
fields, and retains the stated human author; it contains no local filesystem
path or invented publication date. Relative artifact links work in the HTML; the PDF maps them
to the intended repository's corresponding public file paths.

The Markdown parser supports headings, paragraphs, simple bullets, tables,
fenced code, links and explicit `<!-- pagebreak -->` markers. Only the measured
quality chart is embedded. Review every rendered PDF page after manuscript or
layout changes: automated text extraction alone cannot establish visual quality.
The builder performs no retrieval, hosted inference, network request or release
operation.
