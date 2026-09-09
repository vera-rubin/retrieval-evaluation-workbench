"""Independent malformed-fixture tests; no model output is used as an oracle."""
from copy import deepcopy
import unittest

from hippo_eval.contracts import body_digest
from hippo_eval.fixtures import validate_fixtures


def fixture_pair():
    record = {"id": "rec-first", "family": "first", "project": "p", "task": "t", "owner": "o",
              "level": 1, "kind": "decision", "status": "current", "epistemic": "supported",
              "revision": "v2", "title": "Cache expiry decision", "body": "Expire entries after an hour.",
              "body_sha256": body_digest("Expire entries after an hour."),
              "provenance": [{"source_id": "minutes", "revision": "v2", "availability": "retained"}],
              "supersedes": []}
    query = {"id": "ask-first", "split": "development", "family": "first", "category": "decision",
             "text": "When do entries expire?", "relevance": {"rec-first": 3},
             "rationale": "The decision directly states the expiry interval.", "answerable": True,
             "rules": {"projects": ["p"], "owners": ["o"], "tasks": ["t"], "statuses": ["current"],
                       "epistemics": ["supported"], "revisions": None, "require_evidence": True}}
    return ({"schema": "hippo-corpus/v1", "version": "test", "authorship": {"synthetic": True}, "records": [record]},
            {"schema": "hippo-queries/v1", "version": "test", "authorship": {"synthetic": True}, "queries": [query]})


class FixtureAuditTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.queries = fixture_pair()

    def audit(self):
        return validate_fixtures(self.corpus, self.queries)

    def assert_error(self, fragment):
        result = self.audit()
        self.assertFalse(result["valid"])
        self.assertTrue(any(fragment in error for error in result["errors"]), result)

    def test_valid_pair(self):
        result = self.audit()
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["summary"]["query_count"], 1)
        self.assertEqual(result["summary"]["eligible_pools"]["answerable_at_most_10"], 1)

    def test_shared_level_requires_verified_epistemic(self):
        self.corpus["records"][0]["level"] = 3
        self.assert_error("level 3 shared memory requires verified")

    def test_verified_shared_record_is_valid(self):
        self.corpus["records"][0].update(level=3, epistemic="verified", owner="Hive")
        self.queries["queries"][0]["rules"].update(owners=["Hive"], epistemics=["verified"])
        self.assertTrue(self.audit()["valid"])

    def test_malformed_envelope_does_not_crash(self):
        for bad in (None, [], 5, "text", {}, {"records": [False]}):
            self.assertFalse(validate_fixtures(bad, None)["valid"])

    def test_broken_relevance_reference(self):
        self.queries["queries"][0]["relevance"] = {"unknown": 3}
        self.assert_error("broken relevant record reference")

    def test_hash_checks_exact_unicode_bytes(self):
        self.corpus["records"][0]["body"] = "Café — expiry"
        self.assert_error("body_sha256")

    def test_ineligible_label_rejected_for_each_rule(self):
        for rule in ("projects", "owners", "tasks", "statuses", "epistemics", "revisions"):
            corpus, queries = fixture_pair()
            queries["queries"][0]["rules"][rule] = []
            result = validate_fixtures(corpus, queries)
            self.assertTrue(any("ineligible" in error for error in result["errors"]), rule)

    def test_missing_evidence_cannot_receive_relevance(self):
        self.corpus["records"][0]["provenance"][0]["availability"] = "missing"
        self.assert_error("ineligible")

    def test_missing_evidence_allowed_when_explicitly_requested(self):
        self.corpus["records"][0]["provenance"][0]["availability"] = "missing"
        self.queries["queries"][0]["rules"]["require_evidence"] = False
        self.assertTrue(self.audit()["valid"])

    def test_deleted_payload_cannot_be_relevant(self):
        record = self.corpus["records"][0]
        record.update(status="deleted", body=None, body_sha256=None)
        self.queries["queries"][0]["rules"]["statuses"] = ["deleted"]
        self.assert_error("ineligible")

    def test_answerable_matches_labels(self):
        self.queries["queries"][0]["answerable"] = False
        self.assert_error("answerable")

    def test_boolean_is_not_relevance_grade(self):
        self.queries["queries"][0]["relevance"]["rec-first"] = True
        self.assert_error("grade")

    def test_duplicate_ids(self):
        self.corpus["records"].append(deepcopy(self.corpus["records"][0]))
        self.assert_error("duplicate record ID")

    def test_contradictory_labels_same_text_rules(self):
        duplicate = deepcopy(self.queries["queries"][0])
        duplicate.update(id="different", relevance={}, answerable=False)
        self.queries["queries"].append(duplicate)
        self.assert_error("contradictory labels")

    def test_duplicate_query_same_labels(self):
        duplicate = deepcopy(self.queries["queries"][0])
        duplicate["id"] = "different"
        self.queries["queries"].append(duplicate)
        self.assert_error("duplicate query text and rules")

    def test_family_split_leakage(self):
        duplicate = deepcopy(self.queries["queries"][0])
        duplicate.update(id="held", split="heldout", text="State the current cache lifetime.")
        self.queries["queries"].append(duplicate)
        self.assert_error("split leakage")

    def test_cross_family_relevance(self):
        self.queries["queries"][0]["family"] = "other"
        self.assert_error("crosses family boundary")

    def test_oracle_id_in_body(self):
        record = self.corpus["records"][0]
        record["body"] += " See rec-first for the answer."
        record["body_sha256"] = body_digest(record["body"])
        self.assert_error("oracle record ID embedded")

    def test_oracle_id_in_query_text(self):
        self.queries["queries"][0]["text"] = "What does rec-first say?"
        self.assert_error("oracle record ID embedded in query text")

    def test_broken_supersedes_reference(self):
        self.corpus["records"][0]["supersedes"] = ["missing"]
        self.assert_error("broken supersedes")

    def test_supersession_cycle(self):
        first = self.corpus["records"][0]
        first.update(status="superseded", supersedes=["rec-second"])
        second = deepcopy(first)
        second.update(id="rec-second", supersedes=["rec-first"])
        self.corpus["records"].append(second)
        self.assert_error("supersession cycle")

    def test_conflicting_source_availability(self):
        second = deepcopy(self.corpus["records"][0])
        second["id"] = "rec-second"
        second["provenance"][0]["availability"] = "missing"
        self.corpus["records"].append(second)
        self.assert_error("contradictory availability")

    def test_invalid_rule_types_do_not_crash(self):
        for value in (False, {}, "current", [None], [["current"]]):
            _, queries = fixture_pair()
            queries["queries"][0]["rules"]["statuses"] = value
            self.assertFalse(validate_fixtures(self.corpus, queries)["valid"])

    def test_exact_record_text_crossing_splits(self):
        other = deepcopy(self.corpus["records"][0])
        other.update(id="rec-other", family="second")
        self.corpus["records"].append(other)
        query = deepcopy(self.queries["queries"][0])
        query.update(id="ask-other", family="second", split="heldout", text="How long is the cache valid?", relevance={"rec-other": 3})
        self.queries["queries"].append(query)
        self.assert_error("identical searchable text crosses splits")


if __name__ == "__main__":
    unittest.main()
