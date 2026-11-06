"""Regression suite: no personal data, no live service required."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from xops_core.store import add_posts, connect, counts, export_approved, find_posts, initialize, review
from xops_core.validators import ValidationError, load_document, validate_document, weighted_length

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample.json"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite3"
        self.conn = connect(self.db)
        self.addCleanup(self.conn.close)
        initialize(self.conn)
        self.doc = load_document(SAMPLE)

    def import_sample(self):
        posts = validate_document(self.doc)
        result = add_posts(self.conn, posts)
        self.assertEqual(result, {"imported": 1, "duplicates": 0})

    def test_end_to_end_approve_and_export(self):
        self.import_sample()
        row = find_posts(self.conn)[0]
        self.assertEqual(row["status"], "pending")
        review(self.conn, row["id"], "approved")
        destination = Path(self.temp.name) / "approved.json"
        self.assertEqual(export_approved(self.conn, destination), 1)
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], "PUBLIC_POSTS_V1")
        self.assertEqual(len(payload["posts"]), 1)
        self.assertEqual(payload["posts"][0]["event_id"], "example.public-data-update.20261105")
        self.assertEqual(counts(self.conn)["exported"], 1)
        self.assertEqual(export_approved(self.conn, destination), 0)
        with self.assertRaises(ValidationError):
            review(self.conn, row["id"], "rejected")
        audit = self.conn.execute("SELECT action FROM audit ORDER BY id").fetchall()
        self.assertEqual([r["action"] for r in audit], ["imported", "reviewed", "exported"])

    def test_rejected_not_exported(self):
        self.import_sample()
        review(self.conn, 1, "rejected")
        output = Path(self.temp.name) / "empty.json"
        self.assertEqual(export_approved(self.conn, output), 0)
        self.assertFalse(output.exists())

    def test_review_state_change(self):
        self.import_sample()
        review(self.conn, 1, "rejected")
        review(self.conn, 1, "approved")
        self.assertEqual(counts(self.conn)["approved"], 1)

    def test_idempotent_reimport(self):
        self.import_sample()
        self.assertEqual(add_posts(self.conn, validate_document(self.doc)),
                         {"imported": 0, "duplicates": 1})

    def test_same_event_different_post_id_skip(self):
        self.import_sample()
        other = copy.deepcopy(self.doc)
        other["posts"][0]["post_id"] = "new.post.id"
        self.assertEqual(add_posts(self.conn, validate_document(other))["duplicates"], 1)

    def test_same_post_id_different_event_raises(self):
        self.import_sample()
        other = copy.deepcopy(self.doc)
        other["posts"][0]["event_id"] = "another.event"
        with self.assertRaisesRegex(ValidationError, "different event"):
            add_posts(self.conn, validate_document(other))
        self.assertEqual(sum(counts(self.conn).values()), 1)

    def test_different_account_same_event_is_accepted(self):
        self.import_sample()
        other = copy.deepcopy(self.doc)
        other["posts"][0].update(post_id="demo.en.20261105.01", account="en", lang="en")
        self.assertEqual(add_posts(self.conn, validate_document(other))["imported"], 1)
        self.assertEqual(counts(self.conn)["pending"], 2)

    def test_duplicate_event_in_one_batch_rejected(self):
        other = copy.deepcopy(self.doc)
        other["posts"].append(copy.deepcopy(other["posts"][0]))
        other["posts"][1]["post_id"] = "demo.zh.20261105.02"
        with self.assertRaisesRegex(ValidationError, "one post per event"):
            validate_document(other)

    def test_duplicate_post_in_one_batch_rejected(self):
        other = copy.deepcopy(self.doc)
        other["posts"].append(copy.deepcopy(other["posts"][0]))
        other["posts"][1]["event_id"] = "second.event"
        with self.assertRaisesRegex(ValidationError, "post_id appears"):
            validate_document(other)

    def test_atomic_import_on_collision(self):
        self.import_sample()
        other = copy.deepcopy(self.doc)
        base = other["posts"][0]
        base["event_id"] = "new.event"
        base["post_id"] = "new.post"
        colliding = copy.deepcopy(base)
        colliding["event_id"] = "another.event"
        colliding["post_id"] = "demo.zh.20261105.01"
        other["posts"].append(colliding)
        with self.assertRaises(ValidationError):
            add_posts(self.conn, validate_document(other))
        self.assertEqual(counts(self.conn)["pending"], 1)

    def test_unsupported_schema(self):
        doc = copy.deepcopy(self.doc)
        doc["version"] = "PUBLIC_POSTS_V2"
        with self.assertRaisesRegex(ValidationError, "PUBLIC_POSTS_V1"):
            validate_document(doc)

    def test_text_too_long(self):
        doc = copy.deepcopy(self.doc)
        doc["posts"][0]["text"] = "中" * 131
        with self.assertRaisesRegex(ValidationError, "260"):
            validate_document(doc)

    def test_untrusted_url_rejected(self):
        for url in ["http://example.com", "javascript:alert(1)", "https://user:pw@example.com", "https://bad url", "https://[::1"]:
            doc = copy.deepcopy(self.doc)
            doc["posts"][0]["source_url"] = url
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_document(doc)

    def test_missing_quote(self):
        doc = copy.deepcopy(self.doc)
        del doc["posts"][0]["source_quote"]
        with self.assertRaises(ValidationError):
            validate_document(doc)

    def test_nested_source_supported(self):
        doc = copy.deepcopy(self.doc)
        p = doc["posts"][0]
        p["source"] = {"name": p.pop("source_name"), "url": p.pop("source_url"),
                       "tier": p.pop("source_tier"), "quote": p.pop("source_quote")}
        self.assertEqual(validate_document(doc)[0]["source_tier"], "demo")

    def test_fenced_json_import(self):
        path = Path(self.temp.name) / "email.txt"
        path.write_text("Subject: Sample\n" + chr(96)*3 + "json\n" + json.dumps(self.doc, ensure_ascii=False) + "\n" + chr(96)*3 + "\n", encoding="utf-8")
        self.assertEqual(len(validate_document(load_document(path))), 1)

    def test_reject_more_than_one_json_block(self):
        path = Path(self.temp.name) / "email.txt"
        fence = chr(96)*3
        path.write_text(fence + "json\n{}\n" + fence + "\n" + fence + "json\n{}\n" + fence, encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_document(path)

    def test_empty_posts_allowed(self):
        self.assertEqual(validate_document({"version": "PUBLIC_POSTS_V1", "posts": []}), [])

    def test_keep_approved_mode(self):
        self.import_sample()
        review(self.conn, 1, "approved")
        output = Path(self.temp.name) / "approved.json"
        self.assertEqual(export_approved(self.conn, output, keep_approved=True), 1)
        self.assertEqual(counts(self.conn)["approved"], 1)

    def test_char_weight(self):
        self.assertEqual(weighted_length("Hello中文"), 9)

    def test_invalid_review_id(self):
        with self.assertRaises(ValidationError):
            review(self.conn, 999, "approved")


class ExtendedSchemaTests(unittest.TestCase):
    def test_public_translation_preserved(self):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        post = doc["posts"][0]
        post["text_zh"] = "测试中译文"
        post["alt_texts_zh"] = ["备选译文一", "备选译文二"]
        post["stage_now"] = "verification"
        post["evergreen"] = False
        validated = validate_document(doc)[0]
        self.assertEqual(validated["text_zh"], "测试中译文")
        self.assertEqual(validated["alt_texts_zh"], ["备选译文一", "备选译文二"])
        self.assertFalse(validated["evergreen"])

    def test_secret_unknown_fields_are_discarded(self):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        doc["posts"][0]["private_access_token"] = "DO_NOT_PUBLISH"
        self.assertNotIn("private_access_token", validate_document(doc)[0])


if __name__ == "__main__":
    unittest.main()
