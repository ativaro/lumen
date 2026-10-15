import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QPushButton
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
                             view.itemDelegate().caption_rect(rect).center())
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

    def test_properties_in_file_and_background_context_menus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'notes.txt'; path.write_text('notes')
            window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat)); window.show()
            try:
                self.wait(lambda: window.fs.index(str(path)).isValid())
                index = window.proxy.mapFromSource(window.fs.index(str(path)))
                for point, expected in ((window.view.visualRect(index).center(), str(path)), (QPoint(-1, -1), tmp)):
                    actions = []
                    timer = QTimer(); timer.setInterval(20)
                    def inspect():
                        menu = QApplication.activePopupWidget()
                        if isinstance(menu, QMenu):
                            actions.extend(menu.actions()); menu.close()
                    timer.timeout.connect(inspect); timer.start()
                    with patch.object(window, 'show_properties') as properties:
                        window.context_menu(point)
                        timer.stop()
                        self.assertNotIn('Einstellungen …', [a.text() for a in actions])
                        next(a for a in actions if a.text().startswith('Eigenschaften …')).trigger()
                        properties.assert_called_once_with([expected])
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)

    def test_shared_settings_saves_files_without_changing_assistant_preferences(self):
        from settings_dialog import SettingsDialog
        with tempfile.TemporaryDirectory() as tmp:
            window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat)); window.show()
            assistant = QSettings('Lumen', 'Assistant')
            before = {key: assistant.value(key) for key in assistant.allKeys()}
            observed = {}
            def inspect():
                dialog = QApplication.activeModalWidget()
                try:
                    observed['type'] = isinstance(dialog, SettingsDialog)
                    observed['title'] = dialog.windowTitle()
                    observed['pages'] = [page['title'] for page in dialog.page_info]
                    observed['navigation'] = hasattr(dialog, 'navigation')
                    observed['buttons'] = [button.text() for button in dialog.findChildren(QPushButton)]
                    dialog.hidden.setChecked(True)
                    dialog.save_files()
                except Exception as error:
                    observed['error'] = str(error)
                finally:
                    if dialog: dialog.reject()
            try:
                QTimer.singleShot(30, inspect)
                with patch.object(SettingsDialog, 'reload') as reload:
                    window.show_settings()
                    QTest.qWait(40); reload.assert_called_once()
                self.assertNotIn('error', observed)
                self.assertTrue(observed['type'])
                self.assertEqual(observed['title'], 'Einstellungen — Lumen')
                self.assertIn('Lumen Files', observed['pages'])
                self.assertTrue(observed['navigation'])
                self.assertTrue(window.settings.value('hidden', False, type=bool))
                self.assertTrue(window.hidden)
                self.assertEqual({key: assistant.value(key) for key in assistant.allKeys()}, before)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)

    def test_properties_loads_file_and_blocks_unmounted_cloud(self):
        from file_properties import Properties
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'notes #1 $(keep).txt'; path.write_text('keep content')
            window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
            observed = {}
            timer = QTimer(); timer.setInterval(20)
            def inspect():
                dialog = QApplication.activeModalWidget()
                if isinstance(dialog, Properties) and dialog.fact:
                    observed['paths'] = dialog.paths
                    observed['name'] = dialog.name.text()
                    dialog.reject()
            timer.timeout.connect(inspect); timer.start()
            try:
                QTimer.singleShot(5000, lambda: QApplication.activeModalWidget().reject() if QApplication.activeModalWidget() else None)
                window.show_properties(path)
                self.assertEqual(observed, dict(paths=[str(path)], name=path.name))
                with patch.object(window.cloud, 'contains', return_value=True), patch.object(window.cloud, 'mounted', return_value=False), patch.object(window, 'error') as error, patch('file_properties.show') as show:
                    window.show_properties(path)
                    error.assert_called_once(); show.assert_not_called()
                self.assertEqual(path.read_text(), 'keep content')
            finally:
                timer.stop(); window.close(); window.deleteLater(); QTest.qWait(50)


if __name__ == '__main__': unittest.main()
