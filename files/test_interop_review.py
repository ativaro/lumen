"""Regression cases found during independent review of the shared handoff layer."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QCoreApplication, QEvent, QMimeData, QPointF, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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






if __name__ == '__main__':
    unittest.main()
