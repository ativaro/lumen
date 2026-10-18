"""Real Qt layout checks, run with the existing disposable HOME/XDG harness."""
import copy
import tempfile
from pathlib import Path
import unittest
from PySide6.QtCore import QSize, QCoreApplication, QEvent, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QDialogButtonBox, QPushButton
from app import create_app
from desktop_design import AppHeader, PAGE_MARGIN
from lumen_store import Store
from lumen_i18n import tr
from lumen_workplace import ModeDialog
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

    def test_long_audio_labels_preserve_compact_geometry_selection_and_full_text(self):
        description = 'Kopfhörer am Schreibtisch – digitale Audioausgabe für konzentriertes Arbeiten'
        mode = {'id': 'synthetic', 'name': 'Konzentriert arbeiten', 'audio': 'output-b',
                'volume': -1, 'quiet': 60, 'layout': 'tile', 'connections': []}
        original = copy.deepcopy(mode)
        with tempfile.TemporaryDirectory() as root:
            w = ModeDialog(Store(Path(root)), mode, [
                {'name': 'output-a', 'description': description},
                {'name': 'output-b', 'description': description + ' · USB-Audiointerface'}], None)
            w.resize(580, 530)
            w.show()
            QTest.qWait(40)
            self.assertEqual(w.size(), QSize(580, 530))
            self.assertEqual(w.layout().contentsMargins().left(), PAGE_MARGIN)
            self.assertEqual(w.findChild(AppHeader).title.font().pixelSize(), 26)
            self.assertEqual(w.audio.count(), 3)
            self.assertEqual(w.audio.currentData(), 'output-b')
            self.assertEqual(w.audio.toolTip(), description + ' · USB-Audiointerface')
            self.assertEqual(w.audio.itemData(2, Qt.ToolTipRole), description + ' · USB-Audiointerface')
            w.audio.setCurrentIndex(1)
            self.assertEqual(w.audio.currentData(), 'output-a')
            self.assertEqual(w.audio.toolTip(), description)
            scroll = w.findChild(QScrollArea)
            scroll.ensureWidgetVisible(w.connections)
            self.app.processEvents()
            self.assertTrue(w.findChild(QDialogButtonBox).isVisible())
            add = next(b for b in w.findChildren(QPushButton) if b.text() == tr('Netzwerk hinzufügen …'))
            scroll.ensureWidgetVisible(add)
            self.app.processEvents()
            self.assertTrue(scroll.viewport().rect().contains(add.mapTo(scroll.viewport(), QPoint(0, 0))))
            w.reject()
            self.assertEqual(mode, original)


if __name__ == '__main__':
    unittest.main()
