# Third-party notices and acquisition licenses

The Apache-2.0 license in this repository applies to its original releasable material. The software named below is independently developed and separately acquired. Its code, model weights, tokenizers, binaries, and installed environments are not included in the source release. Those projects retain their copyright, attribution, and license terms. Installation preserves upstream license and notice files; this inventory does not replace them or relicense them.

The evaluator uses the documented inference recipes for these two models. The model authors and their training work are separate from this evaluation.

| Model | Pinned revision | Publisher-declared license |
|---|---|---|
| [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5/tree/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a) | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` | MIT |
| [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41) | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 |

The following inventory describes the pinned Windows CPython 3.13 runtime closure. License descriptions are taken from the publisher's exact-version metadata or tagged license; generic BSD descriptions are retained where metadata does not specify a variant. Dependencies may contain separately licensed bundled components. PyTorch, NumPy, and setuptools in particular include additional attribution files within their distributions.

| Package/version | License information | Primary source |
|---|---|---|
| APSW 3.53.4.0 | any-OSI; retain upstream origin and alteration notices | [license](https://rogerbinns.github.io/apsw/copyright.html) |
| sqlite-vec 0.1.9 | MIT or Apache-2.0 | [MIT](https://raw.githubusercontent.com/asg017/sqlite-vec/v0.1.9/LICENSE-MIT), [Apache](https://raw.githubusercontent.com/asg017/sqlite-vec/v0.1.9/LICENSE-APACHE) |
| Torch 2.9.1+cpu | BSD-style terms and bundled notices | [tagged license](https://raw.githubusercontent.com/pytorch/pytorch/v2.9.1/LICENSE) |
| Transformers 4.57.1 | Apache-2.0 | [metadata](https://pypi.org/pypi/transformers/4.57.1/json) |
| tokenizers 0.22.1 | Apache-2.0 | [tagged license](https://raw.githubusercontent.com/huggingface/tokenizers/v0.22.1/LICENSE) |
| safetensors 0.6.2 | Apache-2.0 | [metadata](https://pypi.org/pypi/safetensors/0.6.2/json) |
| huggingface-hub 0.36.0 | Apache-2.0 | [metadata](https://pypi.org/pypi/huggingface-hub/0.36.0/json) |
| hf-xet 1.2.0 | Apache-2.0 | [metadata](https://pypi.org/pypi/hf-xet/1.2.0/json) |
| NumPy 2.3.4 | BSD and bundled-component notices | [metadata](https://pypi.org/pypi/numpy/2.3.4/json) |
| filelock 3.19.1 | Unlicense | [metadata](https://pypi.org/pypi/filelock/3.19.1/json) |
| fsspec 2025.9.0 | BSD-3-Clause | [metadata](https://pypi.org/pypi/fsspec/2025.9.0/json) |
| packaging 25.0 | Apache-2.0 or BSD | [metadata](https://pypi.org/pypi/packaging/25.0/json) |
| PyYAML 6.0.3 | MIT | [metadata](https://pypi.org/pypi/pyyaml/6.0.3/json) |
| regex 2025.9.18 | Apache-2.0 AND CNRI-Python | [metadata](https://pypi.org/pypi/regex/2025.9.18/json) |
| requests 2.32.5 | Apache-2.0 | [metadata](https://pypi.org/pypi/requests/2.32.5/json) |
| tqdm 4.67.1 | MPL-2.0 AND MIT, per-file terms | [tagged license](https://raw.githubusercontent.com/tqdm/tqdm/v4.67.1/LICENCE) |
| typing-extensions 4.15.0 | PSF-2.0 | [metadata](https://pypi.org/pypi/typing-extensions/4.15.0/json) |
| Jinja2 3.1.6 | BSD | [metadata](https://pypi.org/pypi/jinja2/3.1.6/json) |
| MarkupSafe 3.0.3 | BSD-3-Clause | [metadata](https://pypi.org/pypi/markupsafe/3.0.3/json) |
| NetworkX 3.5 | BSD | [metadata](https://pypi.org/pypi/networkx/3.5/json) |
| SymPy 1.14.0 | BSD | [metadata](https://pypi.org/pypi/sympy/1.14.0/json) |
| mpmath 1.3.0 | BSD | [metadata](https://pypi.org/pypi/mpmath/1.3.0/json) |
| charset-normalizer 3.4.4 | MIT | [metadata](https://pypi.org/pypi/charset-normalizer/3.4.4/json) |
| idna 3.11 | BSD-3-Clause | [metadata](https://pypi.org/pypi/idna/3.11/json) |
| urllib3 2.5.0 | MIT | [metadata](https://pypi.org/pypi/urllib3/2.5.0/json) |
| certifi 2025.10.5 | MPL-2.0 | [metadata](https://pypi.org/pypi/certifi/2025.10.5/json) |
| colorama 0.4.6 | BSD | [metadata](https://pypi.org/pypi/colorama/0.4.6/json) |
| setuptools 80.9.0 | MIT and vendored-component notices | [metadata](https://pypi.org/pypi/setuptools/80.9.0/json) |
| psutil 7.1.0 | BSD-3-Clause | [metadata](https://pypi.org/pypi/psutil/7.1.0/json) |

SQLite itself is [in the public domain](https://sqlite.org/copyright.html). The optional sqlite-vec dependency is retained for acquisition identity and extension experiments; the measured semantic retrieval path uses NumPy cosine scanning.

The optional report-building environment is separate from the inference lock:
ReportLab 4.4.9 uses its BSD license (Copyright 2000-2025, ReportLab Inc.;
[publisher metadata](https://pypi.org/pypi/reportlab/4.4.9/json));
Pillow 12.3.0 declares MIT-CMU
([metadata](https://pypi.org/pypi/pillow/12.3.0/json)); and
charset-normalizer 3.5.1 declares MIT
([metadata](https://pypi.org/pypi/charset-normalizer/3.5.1/json)); and
pypdf 6.10.0 declares BSD-3-Clause
([metadata](https://pypi.org/pypi/pypdf/6.10.0/json)). These packages
are acquired separately. The report uses standard PDF fonts; no external font
binary is included. Generated figures plot this release's own measurements.

The model licenses do not establish ownership of every upstream training example or guarantee suitability for every later use. This release does not redistribute model training corpora. A distributor who later bundles environments, model files, fonts, or third-party source must inspect and retain the licenses and notices for those exact redistributed files.
