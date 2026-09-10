# Installation and reproduction

The initial supported platform is **Windows x64 with CPython 3.13**. The release
validation used CPython 3.13.15. Linux and macOS have not been tested. The
staging lock selects Windows binaries, including CPU-only PyTorch; it performs
no source builds and does not install packages globally.

Run these PowerShell commands from the downloaded or cloned repository root.
Git is optional: a source archive records `git_head: null` and still hashes
the source files used by each run.

## Create an isolated environment and acquire dependencies

Install an appropriate Python interpreter through a trusted platform channel
if one is not already available. The following assumes the standard Python
launcher can select CPython 3.13:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -I staging\stage_cpu.py wheels
.\.venv\Scripts\python.exe -I staging\stage_cpu.py install
.\.venv\Scripts\python.exe -I staging\stage_cpu.py models
```

The `wheels` action retrieves the 29 pinned binary distributions from PyPI and
the official PyTorch CPU index. It compares the selected wheel hashes to
[the committed lock](../staging/requirements-cpu-win-cp313.lock), verifies the
dependency closure and declared startup files, and does not regenerate that
lock. `install` uses offline, hash-required pip installation into
`.artifacts/site`. It refuses to overwrite a populated dependency site.

The `models` action retrieves only an allowlisted set of files from the two
immutable model revisions, verifies their hashes or Git blob identities, and
writes local manifests. It does not invoke inference or custom model code.
Weights and third-party binaries are not included in the source release. The
network acquisition path requires no account or authentication.

The artifact staging ceiling is 3 GiB. Wheels, installed dependencies, model
files, test records and caches live below `.artifacts/`; the Python virtual
environment is separate. A failure produces a timestamped diagnostic record.
Inspect it before retrying an incomplete download or a populated install target.
Keep the pinned versions and integrity checks when reproducing these results.

To use another artifact directory, give the same path to all three staging
actions and to every command that performs retrieval or declares a protocol:

```powershell
.\.venv\Scripts\python.exe -I staging\stage_cpu.py wheels --artifacts .local-assets
.\.venv\Scripts\python.exe -I staging\stage_cpu.py install --artifacts .local-assets
.\.venv\Scripts\python.exe -I staging\stage_cpu.py models --artifacts .local-assets
.\.venv\Scripts\python.exe -I workbench.py prepare-reproduction --artifacts .local-assets --out .local-assets\protocol.json
```

Only the selected `site` is inserted into the import path. The supervised
worker runs with `-I -S`; staged `.pth` files are never executed.
The default test suite expects the default `.artifacts/site` for its small
custom-root regression probes. Use the default setup for release validation.

## Check the dataset, evaluator and scenarios

```powershell
.\.venv\Scripts\python.exe -I workbench.py validate --out .artifacts\checks\fixtures.json
.\.venv\Scripts\python.exe -I workbench.py smoke --out .artifacts\checks\tests.json
.\.venv\Scripts\python.exe -I workbench.py smoke --pattern test_review_fixes.py --out .artifacts\checks\reliability.json
.\.venv\Scripts\python.exe -I workbench.py smoke --pattern test_publication.py --out .artifacts\checks\standalone.json
.\.venv\Scripts\python.exe -I workbench.py check-traces scenarios\cases.json scenarios\correct.json --out .artifacts\checks\correct.json
.\.venv\Scripts\python.exe -I workbench.py check-traces scenarios\cases.json scenarios\incorrect.json --out .artifacts\checks\incorrect.json
```

All commands above should exit zero except the deliberate `incorrect.json`
check, which must exit one and reject every supplied incorrect case. Test
records distinguish no discovery, zero executed tests, failures and successful
execution. A typo in `--pattern` cannot silently run another selection.

## Reproduce the established five-method comparison

These commands reuse the selected 240-token / 32-overlap / lexical-weight-1 /
RRF-60 configuration and both existing query splits. The held-out queries are
already known, so this is a fixed-configuration reproduction.

```powershell
.\.venv\Scripts\python.exe -I workbench.py prepare-reproduction --out .artifacts\protocol.json
.\.venv\Scripts\python.exe -I workbench.py run --reproduction .artifacts\protocol.json --split development --out .artifacts\runs\development
.\.venv\Scripts\python.exe -I workbench.py run --reproduction .artifacts\protocol.json --split heldout --out .artifacts\runs\heldout
.\.venv\Scripts\python.exe -I workbench.py run --reproduction .artifacts\protocol.json --split heldout --out .artifacts\runs\heldout-repeat
.\.venv\Scripts\python.exe -I workbench.py compare .artifacts\runs\heldout\run.json.gz .artifacts\runs\heldout-repeat\run.json.gz --out .artifacts\checks\repeat-comparison.json --report-out .artifacts\checks\repeat-report
```

Run these sequentially. Each `run` defaults to lexical, BGE, MiniLM, lexical+BGE
and lexical+MiniLM. The evaluator permits one active inference process and at
most two compute threads and a 2 GiB RSS setting. The semantic path samples its
own RSS after model load and every encode batch, raising an error above the
limit. The supervisor polls the run's inference process every 100 ms and terminates it
on a sampled RSS excess or the default 900-second run bound. These abort checks
are not an OS hard allocation ceiling. Each method rebuilds its index; models
run on the CPU. Seed 17 is passed to `torch.manual_seed` at model load; eval mode
and `torch.inference_mode` do not establish cross-host determinism.

The protocol binds current source-file, dependency, dataset, configuration and
model identities. Editing any bound input invalidates the declaration; create
a new declaration and output directory after a deliberate change. Existing run
outputs and protocol files are not overwritten. A missing model is `NOT_RUN`
and has no retrieval score.

The comparison command preserves its JSON and requested HTML/Markdown report
before returning nonzero for incompatible inputs or a detected quality
regression. Differences in observed latency are reported but are not treated
as a quality regression. Changed dataset, dependency or model identities can
make runs incompatible; the comparison report records the reason.

For a lexical-only quick execution, use `run --methods lexical --split
development --out <new-directory>`. The models are not needed for this path,
but the pinned APSW and process-monitor packages must be installed.

## Results and extension

There are two reproduction targets. Rescoring the retained bundles and rebuilding
their report requires no model execution; see the [results ledger](../results/README.md).
The commands above re-execute retrieval with newly acquired local artifacts and
produce new runtime observations. Neither a retained-rank arithmetic check nor
a same-host repeat proves identical results or timings on a different host.
The [bundled implementation bounds](INTERFACES.md#bounds-of-the-bundled-implementations)
describe the lexical SQL/term caps and model-token limits relevant to new inputs.

Each completed run emits `run.json.gz`, `analysis.json`, `report.json`,
`report.md`, `report.html`, an execution plan and sampled resource measurements.
The compressed bundle contains the complete machine-readable observations.
Open the static `report.html` directly; no web server is used.
[Interfaces](INTERFACES.md) describes external adapters and supplied traces.

Inference locks identify the supervisor and worker by process creation time and
PID. A lock can be reclaimed when both recorded owners are proven absent.
Malformed, legacy or ambiguous locks produce an error and require inspection;
an active run's lock must remain in place.
