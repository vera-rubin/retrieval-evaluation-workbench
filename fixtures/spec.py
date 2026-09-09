"""Authoring helpers; no searchable text is generated from relevance labels."""


def R(key, title, body, kind="fact", status="current", epistemic="supported", revision="r2", **metadata):
    return dict(key=key, title=title, body=body, kind=kind, status=status,
                epistemic=epistemic, revision=revision, **metadata)


def Q(key, category, text, relevance, rationale, **rules):
    return dict(key=key, category=category, text=text, relevance=relevance, rationale=rationale, rules=rules)


def C(family, project, owner, task, records, queries):
    return dict(family=family, project=project, owner=owner, task=task, records=records, queries=queries)
