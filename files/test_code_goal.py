import json
import unittest
from code_goal import parse, proposal


class GoalTest(unittest.TestCase):
    def test_language_independent_bounded_recommendation(self):
        goal = "請檢查我的文件"
        self.assertIn(goal, proposal(goal))
        value = dict(
            kind="tool",
            title="Prüfen",
            prompt=goal,
            reason="Wiederverwenden",
            checks=["Fehlende Felder nennen"],
        )
        self.assertEqual(parse(json.dumps(value)), value)
        for change in (
            {"kind": "shell"},
            {"checks": []},
            {"title": "x" * 161},
            {"grant": "all"},
            {"prompt": None},
            {"checks": [{}]},
        ):
            with self.assertRaises(ValueError):
                parse(json.dumps({**value, **change}))
        for text in ("", "x" * 8001, "\0", None):
            with self.assertRaises(ValueError):
                proposal(text)

    def test_repair_does_not_copy_source_paths_or_run_secrets(self):
        from code_repair import request

        plan = {
            "nodes": [
                dict(
                    kind="read_file", title="Quelle", config="/private/passwords.json"
                ),
                dict(kind="ai", title="Prüfen", config="Fehlende Angaben finden"),
                dict(kind="save_file", title="Speichern", config="/private/output"),
            ]
        }
        text = request(plan, 1)
        self.assertIn("Schritt 2", text)
        self.assertIn("Fehlende Angaben finden", text)
        self.assertNotIn("/private", text)
        self.assertNotIn("passwords.json", text)

    def test_code_origin_opens_the_entry_without_running_it(self):
        import tempfile
        from unittest.mock import patch
        from interop_data import Registry
        from interop_open import open_url

        with tempfile.TemporaryDirectory() as root:
            url = Registry(root).register(
                dict(app="code", id="entry-one", kind="record", title="Vergleich")
            )
            with patch("interop_open.launch") as launch:
                open_url(url, root)
                launch.assert_called_once_with("code", ["--entry", "entry-one"], root)
