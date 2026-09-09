# Supplied-trace examples

These are model-authored literal synthetic expectations and separate correct
and deliberately incorrect traces. They test exact JSON comparison, including
types, keys, values, array order, missing observations, and unexpected metadata.
They are not observed output from a persistence, identity, recovery, or
publication service. The public derivative contains 12 cases and 35 steps.

| Case | Observable distinction | Deliberate incorrect observation |
|---|---|---|
| S01 | Event identity, operation receipts, and content differ | Two records for one delivered event |
| S02 | Interrupted writes must not claim partial commit | A record appears before commit |
| S03 | Accepted candidate and verified status differ | Candidate status is verified |
| S04 | Correction history and disagreement remain visible | An unresolved conflict acquires a winner |
| S05 | Denied results disclose no metadata | A title appears in a denied response |
| S06 | Stale index and changed selection are explicit | A revoked hit is returned |
| S07 | Exact Unicode body and provenance are retained | UTF-8 byte count is wrong |
| S08 | Unavailable assistance is an explicit outcome | Paid fallback is reported |
| S09 | Replacement and unknown actions are reported honestly | An unknown action is replayed |
| S10 | Incomplete deletion/restore stays incomplete | Erasure completes with a pending copy |
| S11 | Review, proposal and publication are different states | An unreviewed draft is accepted |
| S12 | Status changes need not erase retained history | Retained body becomes null |

Each incorrect case changes one observable value. For S07, `Café\n猫` has six
Unicode code points and nine UTF-8 bytes. Unit tests independently check known
failing case IDs and paths; they do not accept a trace's own assertion that it
is correct. The example authoring and model-assisted review are not human
annotation or authenticated runtime validation. See
[evidence identities](../docs/PUBLIC_EVIDENCE.md) for derivative scope.
