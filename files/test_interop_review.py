"""Regression cases found during independent review of the shared handoff layer."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt, QCoreApplication, QEvent, QMimeData, QPointF, QUrl
from PyQt5.QtGui import QDropEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from interop_data import Registry
import interop_ui


class ReviewRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'LUMEN_DATA': str(self.root/'state'), 'LUMEN_TOOLS_DATA': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.registry = Registry(self.root)
        self.windows = []
        self.errors = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for window in self.windows:
            if window.job:
                window.job.cancelled.set()
                window.job.wait(5000)
                QCoreApplication.processEvents()
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def window(self, cls):
        window = cls(self.root)
        window.error = self.errors.append
        self.windows.append(window)
        return window

    def test_reused_old_filename_cannot_retarget_moved_object(self):
        old, new = str(self.root/'old.md'), str(self.root/'new.md')
        url = self.registry.register(dict(app='files', kind='file', id=old, path=old, title='Original'))
        self.registry.relocate(old, new)
        moved = self.registry.register(dict(app='files', kind='file', id=new, path=new, title='Moved'))
        reused = self.registry.register(dict(app='files', kind='file', id=old, path=old, title='Different file'))
        self.assertEqual(moved, url)
        self.assertNotEqual(reused, url)
        self.assertEqual(self.registry.resolve(url)['path'], new)

    def test_claim_is_released_when_worker_cannot_start(self):
        from tools_workbench import Workbench
        window = self.window(Workbench)
        token = self.registry.enqueue('workbench', 'workbench.add', dict(title='New', text='Text'))
        choice = dict(id='', title='New', mode='copy', token=token, due='')
        with patch.object(interop_ui, 'review', return_value=choice), patch.object(window, 'work', side_effect=ValueError('save failed')):
            control = interop_ui.controller(window)
            control.enqueue(dict(handoff=token))
            control.process()
        self.assertEqual(self.registry.request(token)['state'], 'pending')

    def test_claim_is_released_after_gui_finish_failure(self):
        from tools_workbench import Workbench
        window = self.window(Workbench)
        key = window.library.create('Existing', notes='Original notes', questions=[], resources=[])
        window.focus_record(key)
        source = dict(app='wissen', kind='note', id='source.md', title='Source')
        token = self.registry.enqueue('workbench', 'workbench.add', dict(title='New', text='Incoming content', source=source, source_url=self.registry.register(source)))
        choice = dict(id=key, title='Existing', mode='copy', token=token, due='')
        with patch.object(interop_ui, 'review', return_value=choice), patch.object(Registry, 'finish', side_effect=ValueError('registry failure')):
            interop_ui.controller(window).deliver(dict(handoff=token))
            for _ in range(200):
                QTest.qWait(10)
                if not window.job: break
        self.assertIsNone(window.job)
        self.assertEqual(self.registry.request(token)['state'], 'pending')
        self.assertTrue(self.errors)
        self.assertIn('registry failure', self.errors)
        self.assertIn('Incoming content', window.notes.toPlainText())
        window.save()
        self.assertIn('Incoming content', window.library.get(key)['notes'])

    def test_draft_reference_opens_when_another_account_is_selected(self):
        from tools_inbox import Inbox
        import inbox_data
        from interop_open import focus
        window = self.window(Inbox)
        first = window.library.create('First', kind='imap')
        second = window.library.create('Second', kind='imap')
        key = inbox_data.save_draft(window.library, second, dict(subject='Second account draft', body='Text'))
        window.focus_record(first)
        focus(window, dict(app='inbox', kind='draft', id=key, title='Draft', locator=dict(account=second)))
        self.assertEqual(window.drafts.currentItem().data(0, Qt.UserRole)['id'], key)

    def test_missing_dropped_file_is_reported_without_uncaught_qt_callback(self):
        from tools_workbench import Workbench
        window = self.window(Workbench)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.root/'removed-before-drop.pdf'))])
        event = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        uncaught = []
        with patch('sys.excepthook', side_effect=lambda *value: uncaught.append(value)):
            interop_ui.controller(window).eventFilter(window, event)
            QTest.qWait(20)
        self.assertEqual(uncaught, [])
        self.assertTrue(self.errors)


if __name__ == '__main__':
    unittest.main()
