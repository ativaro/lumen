import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox
from app import Window, create_app
import lumen_transfers as transfers


class TransferPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app()

    def test_many_sources_stay_compact_resizable_and_scrollable(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LUMEN_DATA": tmp + "/state"}):
            window = Window(tmp, QSettings(tmp + "/settings.ini", QSettings.IniFormat))
            window.resize(1200, 1100)
            window.show()
            minimum_before = window.minimumSizeHint().height()
            try:
                panel = window.transfer_panel
                sources = [f"/network/photos/2024/02/image-{n:04}.jpg" for n in range(121)]
                with patch.object(transfers, "start"):
                    ticket = panel.enqueue("drive-upload", sources, "lumen-drive:///", drive={"scope": "test", "folder": None})
                transfers.update(panel.store, ticket["id"], status="failed", errors=["Test: Verbindung unterbrochen"])
                panel.refresh()
                QTest.qWait(100)
                self.assertLess(panel.height(), 400)
                self.assertLess(window.minimumSizeHint().height(), minimum_before + 350)
                self.assertTrue(panel.detail.toPlainText().startswith("Test: Verbindung unterbrochen"))
                self.assertIn(sources[-1], panel.detail.toPlainText())
                bar = panel.detail.verticalScrollBar()
                self.assertGreater(bar.maximum(), 0)
                bar.setValue(bar.maximum())
                scroll = bar.value()
                panel.refresh()
                self.assertEqual(bar.value(), scroll)
                window.resizeDocks([panel], [420], Qt.Vertical)
                QTest.qWait(30)
                expanded = panel.height()
                window.resizeDocks([panel], [260], Qt.Vertical)
                QTest.qWait(30)
                self.assertLess(panel.height(), expanded)
                self.assertTrue(panel.resume.isVisible())
                self.assertTrue(panel.resume.isEnabled())
                if os.getenv("LUMEN_BULK_TRANSFER_SCREENSHOT"):
                    bar.setValue(0)
                    window.grab().save(os.environ["LUMEN_BULK_TRANSFER_SCREENSHOT"])
            finally:
                window.close()
                window.deleteLater()
                QTest.qWait(20)

    def test_toggle_pause_resume_cancel_and_background_copy(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"LUMEN_DATA": tmp + "/state"}),
        ):
            source = Path(tmp, "source")
            source.mkdir()
            file = source / "Testdatei.bin"
            file.write_bytes(b"a" * 1024**2)
            target = Path(tmp, "destination")
            target.mkdir()
            window = Window(
                str(target), QSettings(tmp + "/settings.ini", QSettings.IniFormat)
            )
            window.show()
            window.error = lambda *args: self.fail(str(args))
            try:
                panel = window.transfer_panel
                self.assertFalse(panel.isVisible())
                toggle = next(
                    b
                    for b in window.findChildren(QPushButton)
                    if b.text() == "Übertragungen"
                )
                QTest.mouseClick(toggle, Qt.LeftButton)
                self.assertTrue(panel.isVisible())
                QTest.mouseClick(toggle, Qt.LeftButton)
                self.assertFalse(panel.isVisible())
                with patch.object(transfers, "start"):
                    window.run_operation("copy", [str(file)], str(target))
                    self.assertTrue(panel.isVisible())
                    value = panel.selected()
                    self.assertTrue(panel.pause.isEnabled())
                    QTest.mouseClick(panel.pause, Qt.LeftButton)
                    self.assertTrue(
                        panel.store.setting(transfers.PREFIX + value["id"])["cancel"]
                    )
                    transfers.update(
                        panel.store,
                        value["id"],
                        status="paused",
                        bytes=512 * 1024,
                        total=1024**2,
                    )
                    panel.refresh()
                    self.assertTrue(panel.resume.isEnabled())
                    if os.getenv("LUMEN_TRANSFER_SCREENSHOT"):
                        QTest.qWait(100)
                        window.grab().save(os.environ["LUMEN_TRANSFER_SCREENSHOT"])
                    QTest.mouseClick(panel.resume, Qt.LeftButton)
                    self.assertFalse(
                        panel.store.setting(transfers.PREFIX + value["id"])["cancel"]
                    )
                    with patch.object(
                        QMessageBox, "question", return_value=QMessageBox.Yes
                    ):
                        QTest.mouseClick(panel.cancel, Qt.LeftButton)
                transfers.supervise(panel.store, value["id"])
                self.assertEqual(
                    panel.store.setting(transfers.PREFIX + value["id"])["status"],
                    "cancelled",
                )
                window.run_operation("copy", [str(file)], str(target))
                self.assertIsNone(window.file_job)
                self.assertTrue(
                    window.close()
                )  # Independent worker survives closing Files.
                deadline = time.monotonic() + 10
                while not (target / file.name).exists() and time.monotonic() < deadline:
                    QTest.qWait(50)
                self.assertEqual((target / file.name).read_bytes(), file.read_bytes())
            finally:
                window.close()
                window.deleteLater()
                QTest.qWait(20)


if __name__ == "__main__":
    unittest.main()
