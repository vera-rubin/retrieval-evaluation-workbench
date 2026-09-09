"""Independent tiny fixtures for adapter contracts, not held-out evaluations."""
import hashlib
from pathlib import Path
import re
import tempfile
import unittest

from hippo_eval.contracts import DEFAULT_CONFIG
from hippo_eval.retrieval import (HybridEngine, RetrievalInputError, RetrievalMissing,
                                  create_engine, tokenizer_chunks)


def record(rid, text, owner="a"):
    return {"id": rid, "title": "", "body": text,
            "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "owner": owner, "provenance": [{"source_id": "fixture", "availability": "retained"}]}


class SimpleOffsetTokenizer:
    """Test double solely for offset algorithm; never produces model scores."""
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, add_special_tokens=True, **kwargs):
        spans = [(match.start(), match.end()) for match in re.finditer(r"\S+", text)]
        return {"input_ids": list(range(len(spans) + (2 if add_special_tokens else 0))),
                "offset_mapping": spans}


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("lexical")
        self.records = [record("first", "cobalt scheduler resumes exact receipt\r\nUnicode café 🧠\x00tail"),
                        record("hidden", "cobalt cobalt cobalt", "b"),
                        record("third", "amber retention policy")]
        self.engine.build(self.records, DEFAULT_CONFIG)

    def tearDown(self):
        self.engine.close()

    def test_lexical_eligibility_and_exact_fetch(self):
        ranked = self.engine.search({"text": "cobalt"}, {"first", "third"}, 10)
        self.assertEqual([item["record_id"] for item in ranked], ["first"])
        fetched = self.engine.fetch("first")
        self.assertEqual(fetched, self.records[0])
        fetched["body"] = "changed"
        fetched["provenance"].clear()
        self.assertEqual(self.engine.fetch("first"), self.records[0])

    def test_safe_fts_query_and_empty(self):
        self.assertEqual(self.engine.search({"text": '" NOT : ( ) *'}, set(), 10), [])
        self.assertEqual(self.engine.search({"text": "!!!"}, {"first"}, 10), [])
        self.assertEqual(self.engine.search({"text": 'cobalt" OR ('}, {"first"}, 10)[0]["record_id"], "first")

    def test_unknown_eligible_id_rejected(self):
        with self.assertRaises(RetrievalInputError):
            self.engine.search({"text": "cobalt"}, {"missing"}, 10)

    def test_indexed_text_has_no_record_id_or_metadata(self):
        self.assertEqual(self.engine.search({"text": "first hidden third fixture"}, {"first", "hidden", "third"}, 10), [])

    def test_changed_original_does_not_mutate_index_or_fetch(self):
        self.records[0]["body"] = "replaced"
        self.assertIn("cobalt", self.engine.fetch("first")["body"])

    def test_duplicate_ids_and_digest_mismatch_fail(self):
        other = create_engine("lexical")
        try:
            with self.assertRaises(RetrievalInputError):
                other.build([self.records[0], self.records[0]], DEFAULT_CONFIG)
            bad = dict(self.records[0], body_sha256="invalid")
            with self.assertRaises(RetrievalInputError):
                other.build([bad], DEFAULT_CONFIG)
        finally:
            other.close()

    def test_tokenizer_offsets_cover_full_unicode_source(self):
        text = "  café 🧠 one two\r\nthree four five six seven eight nine  "
        chunks = tokenizer_chunks(text, SimpleOffsetTokenizer(), 6, 1, "r", "body")
        self.assertGreater(len(chunks), 1)
        covered = set()
        for chunk in chunks:
            self.assertEqual(text[chunk["char_start"]:chunk["char_end"]], chunk["text"])
            self.assertEqual(text.encode()[chunk["byte_start"]:chunk["byte_end"]], chunk["text"].encode())
            self.assertLessEqual(chunk["token_count"], 6)
            covered.update(range(chunk["char_start"], chunk["char_end"]))
        self.assertEqual(covered, set(range(len(text))))
        self.assertEqual(chunks[-1]["char_end"], len(text))

    def test_no_silent_lexical_term_truncation(self):
        with self.assertRaises(RetrievalInputError):
            self.engine.search({"text": " ".join("term" + str(n) for n in range(257))}, {"first"}, 10)

    def test_missing_model_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            semantic = create_engine("bge", Path(temporary))
            with self.assertRaisesRegex(RetrievalMissing, "MODEL_NOT_STAGED"):
                semantic.build(self.records, DEFAULT_CONFIG)
            semantic.close()

    def test_rrf_is_record_rank_fusion_not_raw_score_addition(self):
        class Stub:
            def __init__(self, result): self.result = result
            def search(self, query, eligible_ids, k): return self.result[:k]
        engine = HybridEngine("bge", None)
        engine.config = dict(DEFAULT_CONFIG, lexical_weight=2.0, semantic_weight=1.0)
        engine.lexical = Stub([{"record_id": "a", "score": 0.00001}, {"record_id": "b", "score": 0.000009}])
        engine.semantic = Stub([{"record_id": "b", "score": 0.99}, {"record_id": "a", "score": 0.1}])
        ranked = engine.search({"text": "x"}, {"a", "b"}, 10)
        self.assertEqual([item["record_id"] for item in ranked], ["a", "b"])
        self.assertAlmostEqual(ranked[0]["score"], 2 / 61 + 1 / 62)


if __name__ == "__main__":
    unittest.main()
