import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QMainWindow, QLineEdit
from PySide6.QtTest import QTest
from reader_workspace import ReadingWorkspace


class ReadingWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.window = QMainWindow(); self.files = QLineEdit('retained folder and selection')
        self.delete = self.window.menuBar().addMenu('Files').addAction('Delete')
        self.window.setCentralWidget(self.files)
        self.workspace = ReadingWorkspace(self.window, self.root/'tools')
        self.window.show()

    def tearDown(self):
        self.workspace.reader.close(); self.window.close(); self.window.deleteLater()
        self.app.processEvents(); self.tmp.cleanup()

    def wait(self):
        end = time.monotonic()+15
        while time.monotonic()<end:
            QTest.qWait(25)
            if not self.workspace.reader.job and self.workspace.reader.data: return
        self.fail(self.workspace.reader.status.text())

    def test_real_document_return_and_reopen_keep_copy_position_and_original(self):
        path = self.root/'article.html'; path.write_text('<h1>Example</h1><p>Readable synthetic content.</p>')
        before = path.read_bytes(); self.workspace.open_file(path); self.wait()
        self.assertFalse(self.delete.isEnabled())
        reader = self.workspace.reader; key = reader.current
        self.assertIn('Readable', reader.data['text'])
        reader.note_id = ''; reader.save()
        self.workspace.back(); self.assertIs(self.workspace.currentWidget(), self.files)
        self.assertTrue(self.delete.isEnabled())
        self.assertEqual(self.files.text(), 'retained folder and selection')
        self.workspace.open_file(path); self.wait()
        self.assertEqual(reader.current, key); self.assertEqual(len(reader.library.all()), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_back_and_close_during_job_do_not_destroy_worker(self):
        self.workspace.setCurrentIndex(1); reader = self.workspace.reader; reader.job = Mock()
        try:
            self.workspace.back(); self.assertEqual(self.workspace.currentIndex(), 1)
            self.assertFalse(self.workspace.can_close()); reader.job.cancelled.set.assert_called_once()
        finally: reader.job = None

    def test_missing_source_does_not_leave_files(self):
        with self.assertRaises(FileNotFoundError): self.workspace.open_file(self.root/'missing.pdf')
        self.assertEqual(self.workspace.currentIndex(), 0)

    def test_context_action_uses_same_files_window(self):
        from interop_ui import files_menu
        from PySide6.QtWidgets import QMenu
        path=self.root/'book.txt'; path.write_text('Synthetic')
        window=Mock(); menu=QMenu()
        with patch('interop_ui.root_for', return_value=self.root/'tools'), patch('interop_ui.launch') as launch:
            files_menu(window,menu,[str(path)])
            action=next(a for a in menu.actions() if 'Reader' in a.text()); action.trigger()
            window.open_reader.assert_called_once_with(str(path)); launch.assert_not_called()

    def test_library_and_full_translation_return_keep_draft_and_features(self):
        self.workspace.open_library()
        self.assertFalse(self.workspace.reader.sidebar.isHidden())
        self.assertFalse(self.delete.isEnabled())
        self.workspace.back()
        self.workspace.open_translation()
        translate = self.workspace.translation
        self.assertFalse(translate.sidebar.isHidden())
        self.assertEqual(translate.tabs.count(), 2)
        translate.input.setPlainText('Synthetic translation draft')
        identity = translate.current
        self.workspace.back()
        self.assertTrue(self.delete.isEnabled())
        self.assertEqual(self.files.text(), 'retained folder and selection')
        self.workspace.open_translation()
        self.assertIs(self.workspace.translation, translate)
        self.assertEqual(translate.current, identity)
        self.assertEqual(translate.input.toPlainText(), 'Synthetic translation draft')
        translate.job = Mock()
        try:
            self.workspace.back()
            self.assertEqual(self.workspace.currentIndex(), 2)
            self.assertFalse(self.workspace.can_close())
        finally:
            translate.job = None
        self.assertTrue(self.workspace.can_close())
