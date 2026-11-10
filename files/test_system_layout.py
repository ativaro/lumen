"""Real Qt layout checks, run with the existing disposable HOME/XDG harness."""
import unittest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import create_app
from desktop_design import AppHeader, PAGE_MARGIN
from updater_app import UpdaterPage


class SystemLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app('graphite')

    def tearDown(self):
        for w in self.app.topLevelWidgets():
            w.close()
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_updater_uses_shared_title_and_keeps_check_action_visible(self):
        w = UpdaterPage()
        w.resize(850, 640)
        w.show()
        QTest.qWait(40)
        header = w.findChild(AppHeader)
        self.assertIsNotNone(header)
        self.assertEqual(header.title.font().pixelSize(), 26)
        self.assertEqual(header.title.font().weight(), 500)
        self.assertEqual(w.layout().contentsMargins().left(), PAGE_MARGIN)
        self.assertEqual(w.layout().contentsMargins().right(), PAGE_MARGIN)
        self.assertGreaterEqual(w.check_button.width(), w.check_button.sizeHint().width())

if __name__ == '__main__':
    unittest.main()
