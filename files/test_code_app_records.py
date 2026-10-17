import tempfile
import unittest
from lumen_store import Store
from code_library import Collection
from code_app_checks import cases


class RecordsTest(unittest.TestCase):
    def test_bounded_history_and_restore_as_separate_draft(self):
        from code_app_edit import Drafts

        with tempfile.TemporaryDirectory() as root:
            collection = Collection(Store(root))
            item = collection.create("app", "App", value={"html": "Original"})
            for n in range(12):
                item = collection.update(
                    item["id"], item["revision"], definition={"html": f"Fassung {n}"}
                )
            self.assertEqual(
                [r["revision"] for r in collection.records.versions(item["id"])],
                list(range(12, 2, -1)),
            )
            value = collection.records.version(item["id"], 12)
            self.assertEqual(value["html"], "Fassung 10")
            drafts = Drafts(collection)
            draft = drafts.open(item["id"])
            draft["value"] = value
            draft = drafts.write(draft)
            self.assertEqual(
                collection.get(item["id"])["definition"]["html"], "Fassung 11"
            )
            self.assertEqual(drafts.commit(draft)["definition"]["html"], "Fassung 10")

    def test_explicit_examples_and_stale_editor_fence(self):
        with tempfile.TemporaryDirectory() as root:
            collection = Collection(Store(root))
            item = collection.create("app", "App")
            example = dict(
                id="one",
                name="Test",
                expect="84",
                fields=[
                    dict(
                        id="amount",
                        name="",
                        type="number",
                        index=0,
                        value="42",
                        checked=False,
                        selected=None,
                    )
                ],
            )
            saved = collection.records.save_tests(item["id"], 0, [example])
            self.assertEqual(saved, collection.records.tests(item["id"]))
            with self.assertRaisesRegex(ValueError, "inzwischen"):
                collection.records.save_tests(item["id"], 0, [])
            for field_type in ("password", "hidden", "file", "script"):
                with self.assertRaises(ValueError):
                    cases(
                        [
                            {
                                **example,
                                "fields": [
                                    {**example["fields"][0], "type": field_type}
                                ],
                            }
                        ]
                    )
            self.assertEqual(
                collection.records.save_tests(item["id"], 1, [])["cases"], []
            )
