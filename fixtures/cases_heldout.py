"""Invented held-out stories; no development family appears in this file."""
from spec import C, Q, R

CASES = [
    C("orchard_irrigation", "Orchard", "Mara", "watering", [
        R("quota", "Dawn watering quota", "Orchard allocates nine liters to each young pear tree at dawn. Mature apple rows use a separate schedule; the pear quota should not be copied to them."),
        R("valve", "Pear valve lookup", "resolvePearValve in control/rows/pear_valves.py maps a row label to its physical valve channel. Missing labels produce PEAR_ROW_UNKNOWN; the function does not infer a neighboring channel.", kind="code-reference"),
        R("weather", "Rainfall pause decision", "The watering controller skips the dawn pear cycle when the previous six hours recorded at least four millimeters of rain. It resumes at the next eligible dawn, without making up the skipped volume.", kind="decision"),
        R("old", "Early pear quota", "The pilot applied twelve liters per young pear tree. The trial notes predate the soil retention survey.", status="superseded", revision="r1"),
        R("change", "Soil retention adjustment", "The soil survey found puddling around young pears. The accepted adjustment reduced their dawn allocation from twelve to nine liters; other fruit rows were unaffected.", kind="decision", supersedes=["old"]),
        R("display", "Mara wants amounts before confirmation", "Mara asks the watering control to display liters per tree before opening a valve. She prefers a written amount to a slider percentage because volunteers rotate between rows.", kind="preference", level=2),
        R("harvest", "Pear crate label color", "The Orchard harvest task uses blue labels for pear crates and orange labels for apples. Label colors carry no watering instruction.", task="harvest"),
        R("other", "Orchard community garden", "At the unrelated Hill Garden project, a bed nicknamed Orchard receives three liters each evening. Mara's orchard controls cannot address this garden's tap.", project="Hill Garden", owner="Evan"),
        R("trial", "Rain gauge pause observation", "A simulated rainfall total of 4.2 millimeters suppressed the dawn pear cycle. At 3.8 millimeters the scheduled cycle remained enabled.", kind="observation", epistemic="verified"),
        R("lost", "Unretained frost forecast", "A copied note predicts frost on the east pear row at dawn, but its forecast attachment was not retained. The note does not establish a verified frost threshold.", epistemic="claimed", provenance="missing"),
    ], [
        Q("identifier", "code-references", "Where does PEAR_ROW_UNKNOWN originate?", {"valve": 3}, "The valve lookup alone connects the identifier with a specific symbol and source path."),
        Q("paraphrase", "paraphrases", "If it rained enough overnight, do young pears get extra water later?", {"weather": 3, "trial": 1}, "The decision explicitly denies catch-up watering; the boundary observation corroborates rainfall gating only."),
        Q("scope", "task-scope", "What should volunteers see before Mara opens the watering valve?", {"display": 3}, "The preference concerns the watering confirmation. Harvest crate colors and a different garden's tap are out of scope."),
        Q("historical", "supersession", "How did the pear allocation change after the soil survey?", {"old": 2, "change": 3, "quota": 2}, "The decision states the transition; the old and current facts corroborate both endpoints.", statuses=["current", "superseded"]),
        Q("multi", "multi-record", "State the young pear quota and the overnight rain rule together.", {"quota": 3, "weather": 3, "change": 1, "trial": 1}, "Quota and rain gating are distinct necessary facts. The soil decision supports the quota but adds no rain condition; the rainfall trial illustrates the gating rule without supplying the quota."),
        Q("unsupported", "missing-evidence", "What verified frost threshold should halt dawn watering?", {}, "The frost note is claimed and its attachment is missing; the retained rain evidence does not answer a frost question.", epistemics=["verified"], require_evidence=True),
        Q("garden", "project-scope", "How much water does Hill Garden's bed nicknamed Orchard receive in the evening?", {"other":3}, "This names the separate Hill Garden project and its owner; pear-tree policy from Orchard is excluded.", projects=["Hill Garden"], owners=["Evan"], tasks=["watering"]),
    ]),
]
