import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from drive_ui import Drive
from drive_migration_ui import Migration
from lumen_i18n import tr


class BindingUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, dialog):
        end = time.monotonic() + 3
        while dialog.job and time.monotonic() < end:
            QTest.qWait(10)
        self.assertIsNone(dialog.job)

    def test_migration_reason_survives_paused_refresh_and_selection(self):
        root = dict(
            id="old",
            path="/synthetic/Drive",
            folder=None,
            enabled=False,
            status="other",
            entries={"q": dict(request_id="pending")},
        )
        with patch("drive_ui.sync.read", return_value={"roots": [root]}):
            window = Drive()
            window.work = lambda *a: None
            try:
                window.refresh_roots()
                self.assertIn(tr("Umstellung erforderlich"), window.roots.currentText())
                self.assertIn("/synthetic/Drive", window.migration_status.text())
                self.assertIn("1", window.migration_status.text())
                self.assertFalse(window.migration_button.isHidden())
                root["migration"] = {"id": "receipt"}
                window.refresh_roots()
                self.assertEqual(window.migration_button.text(), tr("Umstellung fortsetzen …"))
                root["folder"] = "converted"
                window.refresh_roots()
                self.assertTrue(window.migration_button.isHidden())
            finally:
                self.app.processEvents()
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_explicit_preview_upload_resolution_and_confirmation(self):
        root = dict(id="old", path="/synthetic/Drive", entries={}, folder=None)
        with patch("drive_ui.sync.read", return_value={"roots": [root]}):
            parent = Drive()
            parent.work = lambda *a: None
            parent.cache = {"folders": {}}
            dialog = Migration(parent, root)
            proposal = dict(
                plan={
                    "folder": "target",
                    "uploads": [{"request_id": "request", "body": {"name": "queued.txt"}}],
                },
                preview=dict(
                    folder={"id": "target", "name": "Converted"},
                    files=[{"id": "original-id", "name": "original.txt"}],
                    folders=[],
                    uploads=[{"request_id": "request", "state": "uploading"}],
                    ready=False,
                ),
            )
            try:
                with (
                    patch("drive_migration_ui.migration.preview", return_value=proposal) as preview,
                    patch("drive_migration_ui.migration.apply") as apply,
                ):
                    self.assertFalse(dialog.commit.isEnabled())
                    apply.assert_not_called()
                    preview.assert_not_called()
                    dialog.preview()
                    self.wait(dialog)
                    self.assertFalse(dialog.commit.isEnabled())
                    self.assertFalse(dialog.finish.isHidden())
                    self.assertNotIn("original-id", dialog.details.toPlainText())
                    self.assertIn("queued.txt", dialog.details.toPlainText())
                    dialog.technical.setChecked(True)
                    self.assertIn("original-id", dialog.details.toPlainText())
                    self.assertIn("request", dialog.details.toPlainText())
                    self.assertIn("original.txt", dialog.details.toPlainText())
                    proposal["preview"]["ready"] = True
                    proposal["preview"]["uploads"][0]["state"] = "completed"
                    dialog.preview()
                    self.wait(dialog)
                    self.assertTrue(dialog.commit.isEnabled())
                    apply.assert_not_called()
                    dialog.name.setText("Other")
                    self.assertFalse(dialog.commit.isEnabled())
                    self.assertIsNone(dialog.proposal)
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()
                parent.close()
                parent.deleteLater()
                self.app.processEvents()

    def test_mixed_adopt_names_unmodified_and_moving_originals_separately(self):
        root = dict(id="old", path="/synthetic/Drive", entries={}, folder=None)
        with patch("drive_ui.sync.read", return_value={"roots": [root]}):
            parent = Drive()
            parent.work = lambda *a: None
            parent.cache = {"folders": {}}
            dialog = Migration(parent, root)
            try:
                proposal = dict(
                    plan={"uploads": []},
                    preview=dict(
                        folder={"id": "target", "name": "Converted"},
                        adopt=True,
                        files=[
                            {"id": "kept", "name": "original.txt", "folder_id": "target"},
                            {"id": "moved", "name": "queued.txt", "folder_id": None},
                        ],
                        folders=[],
                        uploads=[],
                        ready=True,
                        moving={"files": ["moved"], "folders": []},
                    ),
                )
                dialog.present(proposal)
                text = dialog.details.toPlainText()
                self.assertIn(tr("Bleibt unverändert im Zielordner:"), text)
                self.assertIn(tr("Wird in den gewählten Zielordner verschoben:"), text)
                self.assertNotIn(
                    tr("Bestehende Zuordnung übernehmen, ohne Serverdateien zu verschieben."), text
                )
                self.assertLess(
                    text.index("original.txt"), text.index(tr("Wird in den gewählten Zielordner verschoben:"))
                )
                self.assertGreater(
                    text.index("queued.txt"), text.index(tr("Wird in den gewählten Zielordner verschoben:"))
                )
                self.assertTrue(dialog.commit.isEnabled())
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()
                parent.close()
                parent.deleteLater()
                self.app.processEvents()

    def test_unknown_apply_exposes_resume_and_cancel(self):
        root = dict(id="old", path="/synthetic/Drive", entries={}, folder=None)
        with patch("drive_ui.sync.read", return_value={"roots": [root]}):
            parent = Drive()
            parent.work = lambda *a: None
            parent.cache = {"folders": {}}
            dialog = Migration(parent, root)
            dialog.proposal = {"preview": {"ready": True}, "plan": {"folder": "target"}}

            def interrupted(*_):
                root["migration"] = {
                    "id": "receipt",
                    "plan": {"folder": "target", "files": [], "uploads": []},
                }
                raise OSError("Lost reply")

            try:
                with patch("drive_migration_ui.migration.apply", side_effect=interrupted):
                    dialog.apply()
                    self.wait(dialog)
                self.assertIn("Lost reply", dialog.status.text())
                self.assertTrue(dialog.commit.isEnabled())
                self.assertFalse(dialog.abort.isHidden())
                self.assertFalse(dialog.inspect.isEnabled())
                self.assertFalse(dialog.mode.isEnabled())
                resumed = Migration(parent, root)
                self.assertIn(tr("Bestätigter Zielordner"), resumed.details.toPlainText())
                self.assertTrue(resumed.commit.isEnabled())
                resumed.close()
                resumed.deleteLater()
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()
                parent.close()
                parent.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
