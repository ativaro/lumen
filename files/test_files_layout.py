"""Files layout regressions; run only with a disposable HOME/XDG profile."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings, QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QFrame, QTreeWidgetItem, QStyle, QStyleOptionButton

from app import Window, create_app
from desktop_design import AppHeader, PAGE_MARGIN, NAV_WIDTH
from drive_ui import Drive
from file_spaces import Catalog
from lumen_i18n import tr
from lumen_store import Store


class FilesLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_app('graphite')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.windows = []

    def tearDown(self):
        for w in reversed(self.windows):
            w.close()
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def show(self, w, width, height):
        self.windows.append(w)
        w.resize(width, height)
        w.show()
        QTest.qWait(60)
        return w

    def test_compact_files_keeps_filter_and_transfer_names_visible(self):
        w = self.show(Window(str(self.root), QSettings(str(self.root/'files.ini'), QSettings.IniFormat),
                             Catalog(Store(self.root/'catalog'))), 1000, 640)
        for b in w.filter_buttons.values():
            self.assertGreaterEqual(b.width(), b.sizeHint().width(), b.text())
        transfers = next(b for b in w.findChildren(QPushButton) if b.text() == tr('Übertragungen'))
        self.assertGreaterEqual(transfers.width(), transfers.sizeHint().width())
        self.assertGreater(transfers.y(), w.filter_buttons['all'].y())
        self.assertEqual(w.findChild(QFrame, 'sidebar').width(), NAV_WIDTH)
        self.assertEqual(w.findChild(QFrame, 'footer').layout().contentsMargins().left(), PAGE_MARGIN)

    def test_long_footer_message_keeps_compact_window_and_actions(self):
        w = self.show(Window(str(self.root), QSettings(str(self.root/'files.ini'), QSettings.IniFormat),
                             Catalog(Store(self.root/'catalog'))), 1000, 640)
        w.activity.setText('Lumen Drive: ' + 'Die ausgewählte Datei ist vorübergehend nicht erreichbar. ' * 3)
        self.app.processEvents()
        self.assertEqual(w.width(), 1000)
        self.assertTrue(w.activity.wordWrap())
        self.assertGreater(w.activity.height(), w.activity.fontMetrics().height())

    def test_opening_pdf_keeps_the_same_window_surface_and_file_selection(self):
        from test_pdf_fixtures import Writer
        document = self.root / 'sample.pdf'
        writer = Writer()
        writer.add_page(120, 120)
        writer.save(document)
        window = self.show(Window(str(self.root), QSettings(str(self.root/'files.ini'), QSettings.IniFormat),
                                  Catalog(Store(self.root/'catalog'))), 1000, 640)
        surface = window.centralWidget()
        files = surface.currentWidget()
        for _ in range(100):
            index = window.proxy.mapFromSource(window.fs.index(str(document)))
            if index.isValid():
                break
            QTest.qWait(20)
        self.assertTrue(index.isValid())
        window.view.setCurrentIndex(index)
        window.open_path(str(document))
        self.assertIs(window.centralWidget(), surface)
        self.assertFalse(files.isVisible())
        reader = surface.reader
        for _ in range(250):
            if reader.data and not reader.job:
                break
            QTest.qWait(20)
        self.assertTrue(reader.data, reader.status.text())
        self.assertFalse(reader.canvas.pixmap.isNull())
        surface.back()
        self.assertTrue(files.isVisible())
        self.assertEqual(window.view.currentIndex(), index)

    def test_drive_secondary_actions_remain_reachable_without_wide_minimum(self):
        with patch.object(Drive, 'reload'), patch.object(Drive, 'refresh_roots'), patch.object(Drive, 'conflicts') as conflicts, patch.object(Drive, 'remove') as remove:
            w = self.show(Drive(), 760, 680)
            w.timer.stop()
            self.assertEqual(w.width(), 760)
            item = QTreeWidgetItem(['Raumplan.pdf', 'application/pdf', '1.8 MB'])
            w.list.addTopLevelItem(item)
            self.app.processEvents()
            self.assertEqual(w.list.font().pixelSize(), 14)
            self.assertGreaterEqual(w.list.visualItemRect(item).height(), 38)
            offline = next(b for b in w.findChildren(QPushButton) if b.text() == tr('Offline verfügbar …'))
            option = QStyleOptionButton()
            offline.initStyleOption(option)
            content = offline.style().subElementRect(QStyle.SE_PushButtonContents, option, offline)
            needed = offline.fontMetrics().horizontalAdvance(offline.text())
            if not offline.icon().isNull():
                needed += offline.iconSize().width() + 4
            self.assertGreaterEqual(content.width(), needed)
            more = next(b for b in w.findChildren(QPushButton) if b.menu())
            actions = more.menu().actions()
            self.assertEqual([a.text() for a in actions], [tr('Konflikte lösen'), tr('Verbindung entfernen')])
            for action in actions:
                more.menu().popup(more.mapToGlobal(QPoint(0, more.height())))
                more.menu().setActiveAction(action)
                QTest.keyClick(more.menu(), Qt.Key_Return)
            conflicts.assert_called_once()
            remove.assert_called_once()
            for b in w.findChildren(QPushButton):
                if b.isVisible():
                    self.assertGreaterEqual(b.width(), b.sizeHint().width(), b.text())

if __name__ == '__main__':
    unittest.main()
