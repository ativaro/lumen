import json
import unittest


class GoalTest(unittest.TestCase):


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
