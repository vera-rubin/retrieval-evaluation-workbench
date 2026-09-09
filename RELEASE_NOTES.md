# Proposed v1.0.0

Release candidate prepared for author review. No release date or DOI has been
assigned, and no publication is implied by the proposed version.

The standalone source distribution includes five local retrieval methods,
versioned synthetic inputs, eligibility and full-record validation, strict
result and trace checking, regression comparisons, pinned acquisition,
reproduction commands, machine-readable observations, and a technical report.

Reliability coverage includes nonzero comparison exits on regression or
incompatibility while preserving reports; rejection of empty or wholly
unexecuted test discovery; dependency bootstrap for a selected artifact root
before CLI import and identity capture; and deterministic inference-lock
ownership, stale recovery, PID reuse, live-worker protection and zombie handling.

The export preserves retrieval text and labels, deliberately changes public
metadata and generic scenario examples, and measures new runs under the release
source identity. See [evidence scope](docs/PUBLIC_EVIDENCE.md) and the
[technical report](report/report.md). Windows CPython 3.13 x64 is the initial
tested platform. Model weights and third-party binaries are acquired separately.

The source distribution contains no release or deployment automation. Later
publication requires approval of the exact commit and release assets.
