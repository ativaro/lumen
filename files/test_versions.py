import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from lumen_store import Store
from lumen_versions import Versions
from lumen_offline import digest


class VersionsTest(unittest.TestCase):
    def test_external_changes_delete_guarded_restore_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state'); versions = Versions(store)
            root = Path(tmp) / 'documents'; root.mkdir(); file = root / 'notes.txt'; file.write_text('first')
            versions.configure([str(root)], copies=2); versions.capture(root)
            first = versions.history(file)[0]
            file.write_text('from external app'); versions.capture(root)
            with self.assertRaises(ValueError): versions.restore(first['id'], first['hash'])
            self.assertEqual(file.read_text(), 'from external app')
            versions.restore(first['id'], digest(file)); self.assertEqual(file.read_text(), 'first')
            file.unlink(); versions.capture(root); self.assertIsNone(versions.history(file)[0]['hash'])
            versions.restore(first['id'], None); self.assertEqual(file.read_text(), 'first')
            versions.prune(); self.assertEqual(len(versions.history(file)), 2)
            self.assertTrue(all((versions.objects / r['hash']).exists() for r in versions.history(file) if r['hash']))
            with self.assertRaises(ValueError): versions.configure([str(root), str(root)])

    def test_daemon_survives_ui_and_native_comparison_restores(self):
        from PySide6.QtWidgets import QApplication
        from versions_ui import VersionsDialog
        from lumen_versions import start
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            versions = Versions(); root = Path(tmp) / 'docs'; root.mkdir(); path = root / 'text.txt'; path.write_text('before')
            versions.configure([str(root)], interval=10); process = start(versions.store)
            try:
                deadline = time.monotonic() + 8
                while not versions.history(path) and time.monotonic() < deadline: time.sleep(.05)
                self.assertEqual(len(versions.history(path)), 1)
                path.write_text('external change')
                dialog = VersionsDialog(path=str(path)); dialog.list.setCurrentRow(0)
                deadline = time.monotonic() + 8
                while dialog.proc and time.monotonic() < deadline: app.processEvents(); time.sleep(.01)
                self.assertIn('external change', dialog.diff.toPlainText()); self.assertTrue(dialog.restore_button.isEnabled())
                dialog.restore_button.click()
                deadline = time.monotonic() + 8
                while dialog.proc and time.monotonic() < deadline: app.processEvents(); time.sleep(.01)
                self.assertEqual(path.read_text(), 'before'); dialog.reject(); app.processEvents()
            finally: process.terminate(); process.wait(timeout=5)
