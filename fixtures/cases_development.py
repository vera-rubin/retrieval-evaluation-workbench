"""Invented development stories, authored before any engine output was viewed."""
from spec import C, Q, R

CASES = [
    C("canvas_exports", "Canvas", "Iris", "image-export", [
        R("dimensions", "Export edge limit", "Canvas clamps either raster export edge to 8192 pixels. The limit applies after scaling; a wide but short image can still exceed it. The encoder returns EXPORT_EDGE_LIMIT before allocating the destination buffer."),
        R("symbol", "Where export dimensions are checked", "The function checkRasterBounds in src/export/raster_bounds.ts checks the scaled width and height. It runs before encodePng and emits EXPORT_EDGE_LIMIT with the offending edge.", kind="code-reference"),
        R("old", "Previous export ceiling", "The first Canvas exporter allowed an edge of 4096 pixels. Large poster requests were rejected even when they fit the newer memory budget.", status="superseded", revision="r1"),
        R("decision", "Poster export capacity decision", "The team selected the 8192-pixel ceiling after budgeting a single RGBA destination surface. The change replaces the earlier 4096-pixel restriction; it does not promise unlimited poster dimensions.", kind="decision", supersedes=["old"]),
        R("preference", "Iris prefers visible export sizing", "For the image-export task, Iris wants the final pixel dimensions shown beside the scale control. A silent downscale is unacceptable because print layouts depend on the requested dimensions.", kind="preference", level=2),
        R("preview", "Preview edge policy", "Canvas preview thumbnails stop at 1024 pixels on the long edge. This restriction belongs to the preview task and does not define downloadable export size.", task="preview"),
        R("other", "Canvas export service at the museum", "The museum's unrelated Canvas kiosk exports postcards with a 2048-pixel edge. Its TIFF writer uses a separate color profile.", project="Museum", owner="Noel"),
        R("observation", "Portrait export measurement", "A synthetic portrait at 3000 by 7000 pixels passed the bounds check at scale one; scale two was rejected. This observation confirms scale is applied before checking each edge.", kind="observation", epistemic="verified"),
        R("guess", "Possible transparent pixel optimization", "Iris suspects fully transparent margins could be trimmed to permit larger apparent canvases. No implementation or memory measurements support that idea.", kind="hypothesis", epistemic="claimed"),
        R("deleted", "Removed print-shop payload", None, status="deleted", epistemic="claimed", provenance=[]),
    ], [
        Q("identifier", "identifiers", "What raises EXPORT_EDGE_LIMIT?", {"dimensions": 3, "symbol": 3, "observation": 1}, "The policy and exact code reference directly identify the condition; the measurement illustrates it. The preview rule answers a different task."),
        Q("paraphrase", "paraphrases", "Can I export a huge poster if just one side is too long?", {"dimensions": 3, "symbol": 2, "decision": 2, "observation": 1}, "The per-edge rule directly answers; the helper corroborates scaled-edge checking, the capacity decision explains why, and the portrait example illustrates the behavior."),
        Q("preference", "preferences", "How should Iris be shown the export resolution?", {"preference": 3}, "Only the image-export preference states the UI requirement; scale measurements are not a preference."),
        Q("historical", "historical-revisions", "What edge ceiling did the first Canvas exporter use?", {"old": 3}, "This is explicitly an r1 historical question; the replacement policy is excluded by revision and status.", statuses=["superseded"], revisions=["r1"]),
        Q("multi", "multi-record", "Which limit and code location explain the poster export change?", {"dimensions": 2, "symbol": 3, "decision": 3}, "The code location and rationale are separately necessary; the concise limit statement is useful corroboration."),
        Q("absent", "deleted-payload", "What address was in the removed print-shop payload?", {}, "The only print-shop record is a tombstone with no body. No retained record supplies an address.", statuses=["current", "deleted"]),
        Q("observed", "observations", "What happened when the synthetic portrait export was tried at scale two?", {"observation":3}, "Only the recorded trial establishes what happened in that exercise; general policy is not evidence that a trial ran.", epistemics=["verified"]),
        Q("museum", "project-scope", "What postcard edge limit applies to the museum's Canvas kiosk?", {"other":3}, "The same-name kiosk is in Museum, not the Canvas product workspace; explicit project and owner rules select its policy.", projects=["Museum"], owners=["Noel"], tasks=["image-export"]),
    ]),
]
