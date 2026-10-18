"""Repeated Notes scan failures must not stack modal event loops."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QEvent, QSettings, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox
from tools_data import Library
from tools_ui import ToolWindow
from tools_wissen import Wissen


class ScanWindow(QMainWindow):
    safe = ToolWindow.safe
    error = ToolWindow.error
    scanned = Wissen.scanned
    refresh = Wissen.refresh
    in_collection = Wissen.in_collection
    update_collections = lambda self: None
    connections = lambda self: None


class NotesScanErrorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def boxes(self):
        return [w for w in self.app.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible()]

    def dismiss(self):
        for box in reversed(self.boxes()): box.done(QMessageBox.Ok)

    def test_unavailable_library_keeps_one_dialog_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            w = ScanWindow(); w.setWindowTitle('Lumen Notes')
            w.status = QLabel(); w.entries = QListWidget(); w.search = QLineEdit()
            w.settings = QSettings(str(root/'settings.ini'), QSettings.IniFormat)
            w.notes = {}; w.doc = None; w.area = 'user'; w.book = None; w.view_sort = ''; w.dirty = False
            w.library = Library('wissen', root/'tools'); w.current = w.library.create('Synthetic scan profile')
            original = hashlib.sha256(w.library.db.read_bytes()).hexdigest()
            old = w.library.root; retained = old.with_name('retained-profile'); old.rename(retained)
            scan = dict(notes=[], unchanged=[], folders=[], errors=0, limited=False)
            returned = []; peak = []; before_dismiss = []
            def invoke():
                peak.append(len(self.boxes()))
                w.safe(w.scanned, scan)
                returned.append(True); peak.append(len(self.boxes()))
            try:
                for i in range(6): QTimer.singleShot(20+30*i, invoke)
                # This also releases the old implementation, keeping the failing test finite.
                QTimer.singleShot(220, lambda: before_dismiss.append(len(returned)))
                QTimer.singleShot(240, self.dismiss)
                QTest.qWait(350)
                self.assertEqual(len(returned), 6)
                self.assertEqual(before_dismiss, [6])
                self.assertEqual(max(peak), 1)
                retained.rename(old); w.safe(w.scanned, scan)
                self.assertEqual(self.boxes(), [])
                self.assertEqual(hashlib.sha256(w.library.db.read_bytes()).hexdigest(), original)
                w.error('Synthetic retry'); QTest.qWait(10)
                self.assertEqual(len(self.boxes()), 1)
                w.error('Latest synthetic error')
                self.assertEqual(len(self.boxes()), 1)
                self.assertEqual(self.boxes()[0].text(), 'Latest synthetic error')
                self.dismiss(); QTest.qWait(10)
                w.error('Retry after dismissal'); QTest.qWait(10)
                self.assertEqual(len(self.boxes()), 1)
            finally:
                self.dismiss()
                if retained.exists(): retained.rename(old)
                w.close(); w.deleteLater(); self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_parent_close_and_delete_clear_error_reference(self):
        from PySide6.QtCore import Qt
        from shiboken6 import isValid
        w = ScanWindow(); w.status = QLabel(); w.setAttribute(Qt.WA_DeleteOnClose)
        w.show(); w.error('Synthetic parent close')
        dialog = w._error_dialog
        self.assertTrue(isValid(dialog))
        w.close(); self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(w))
        self.assertFalse(isValid(dialog))
        self.assertIsNone(w._error_dialog)

    def test_old_dialog_deletion_does_not_clear_new_error(self):
        w = ScanWindow(); w.status = QLabel()
        try:
            w.error('Old error'); old = w._error_dialog
            old.done(QMessageBox.Ok)
            w.error('New error'); new = w._error_dialog
            self.app.sendPostedEvents(None, QEvent.DeferredDelete)
            self.assertIs(w._error_dialog, new)
            self.assertTrue(new.isVisible())
        finally:
            self.dismiss(); w.close(); w.deleteLater()
            self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_real_tool_window_close_clears_its_child_dialog(self):
        from PySide6.QtCore import Qt
        from shiboken6 import isValid
        with tempfile.TemporaryDirectory() as directory:
            w = ToolWindow('wissen', 'Lumen Notes', 'Synthetic error lifecycle', '', root=Path(directory)/'tools')
            w.setAttribute(Qt.WA_DeleteOnClose); w.show()
            w.error('Synthetic ToolWindow close')
            dialog = w._error_dialog
            self.assertEqual(dialog.textFormat(), Qt.PlainText)
            self.assertEqual(dialog.windowModality(), Qt.WindowModal)
            w.close(); self.app.sendPostedEvents(None, QEvent.DeferredDelete)
            self.assertFalse(isValid(w)); self.assertFalse(isValid(dialog))
            self.assertIsNone(w._error_dialog)

    def test_hidden_parent_can_show_a_new_error_after_reopening(self):
        from shiboken6 import isValid
        with tempfile.TemporaryDirectory() as directory:
            w = ToolWindow('wissen', 'Lumen Notes', 'Synthetic reopen lifecycle', '', root=Path(directory)/'tools')
            try:
                w.show(); w.error('Error before close')
                self.assertTrue(w._error_dialog.isVisible())
                w.close(); QTest.qWait(10)
                self.assertFalse(w.isVisible())
                w.show(); w.error('Error after reopen')
                self.assertTrue(isValid(w._error_dialog))
                self.assertTrue(w._error_dialog.isVisible())
                self.assertEqual(w._error_dialog.text(), 'Error after reopen')
                w.hide(); w.show(); w.error('Error after parent hide')
                self.assertTrue(w._error_dialog.isVisible())
                w._error_dialog.hide(); w.error('Error after child hide')
                self.assertTrue(w._error_dialog.isVisible())
                self.assertEqual(w._error_dialog.text(), 'Error after child hide')
            finally:
                self.dismiss(); w.close(); w.deleteLater()
                self.app.sendPostedEvents(None, QEvent.DeferredDelete)
