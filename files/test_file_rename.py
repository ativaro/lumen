import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu
from app import Window, create_app


class RenameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        deadline = time.monotonic()+5
        while not condition() and time.monotonic()<deadline: QTest.qWait(20)
        self.assertTrue(condition())

    def test_slow_click_renames_inline_and_double_click_still_opens(self):
        for mode in ('list', 'grid'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp)/'original.txt'; source.write_text('keep content')
                window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
                window.show(); window.set_view_mode(mode)
                try:
                    self.wait(lambda: window.fs.index(str(source)).isValid())
                    view = window.file_stack.currentWidget()
                    QTest.qWait(120)
                    index = window.proxy.mapFromSource(window.fs.index(str(source)))
                    view.scrollTo(index)
                    rect = view.visualRect(index)
                    point = (QPoint(rect.x()+65, rect.center().y()) if mode == 'list' else
                             view.itemDelegate().caption_rect(rect.adjusted(10, 8, -10, -8)).center())
                    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=point)
                    QTest.qWait(QApplication.doubleClickInterval()+50)
                    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=point)
                    self.wait(lambda: any(e.isVisible() for e in view.findChildren(QLineEdit)))
                    QTest.qWait(30)
                    editor = next(e for e in view.findChildren(QLineEdit) if e.isVisible())
                    self.assertEqual(editor.selectedText(), 'original')
                    editor.setText('renamed.txt'); QTest.keyClick(editor, Qt.Key_Return)
                    target = Path(tmp)/'renamed.txt'
                    self.wait(lambda: target.exists() and window.file_job is None)
                    self.assertEqual(target.read_text(), 'keep content'); self.assertFalse(source.exists())
                    view.clearSelection(); QTest.qWait(40)
                    index = window.proxy.mapFromSource(window.fs.index(str(target)))
                    with patch.object(window, 'open_path') as opened:
                        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
                        QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
                        QTest.qWait(QApplication.doubleClickInterval()+50)
                        opened.assert_called_once_with(str(target))
                        self.assertFalse(any(e.isVisible() for e in view.findChildren(QLineEdit)))
                finally:
                    window.close(); window.deleteLater(); QTest.qWait(50)

    def test_settings_in_file_and_background_context_menus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'notes.txt'; path.write_text('notes')
            window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat)); window.show()
            try:
                self.wait(lambda: window.fs.index(str(path)).isValid())
                index = window.proxy.mapFromSource(window.fs.index(str(path)))
                for point in (window.view.visualRect(index).center(), QPoint(-1, -1)):
                    window.view.clearSelection()
                    actions = []
                    timer = QTimer(); timer.setInterval(20)
                    def inspect():
                        menu = QApplication.activePopupWidget()
                        if isinstance(menu, QMenu):
                            actions.extend(menu.actions()); menu.close()
                    timer.timeout.connect(inspect); timer.start()
                    with patch.object(window, 'show_settings') as settings:
                        window.context_menu(point)
                        timer.stop()
                        next(a for a in actions if a.text() == 'Einstellungen …').trigger()
                        settings.assert_called_once_with()
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)


if __name__ == '__main__': unittest.main()
