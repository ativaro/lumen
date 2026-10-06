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
                        properties.assert_called_once_with(expected)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)

    def test_files_settings_dialog_saves_and_updates_only_file_preferences(self):
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
                    QTest.qWait(40); reload.assert_not_called()
                self.assertNotIn('error', observed)
                self.assertTrue(observed['type'])
                self.assertEqual(observed['title'], 'Lumen Files · Einstellungen')
                self.assertEqual(observed['pages'], ['Lumen Files'])
                self.assertFalse(observed['navigation'])
                self.assertNotIn('Systemzustand neu laden', observed['buttons'])
                self.assertIn('Google-Drive-Einstellungen …', observed['buttons'])
                self.assertTrue(window.settings.value('hidden', False, type=bool))
                self.assertTrue(window.hidden)
                self.assertEqual({key: assistant.value(key) for key in assistant.allKeys()}, before)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)

    def test_properties_launch_native_dialog_with_safe_urls_and_report_missing_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'notes #1 $(keep).txt'; path.write_text('keep content')
            window = Window(tmp, QSettings(tmp+'/prefs.ini', QSettings.IniFormat)); window.show()
            process = Mock(); process.startDetached.return_value = (True, 123)
            try:
                with patch('shutil.which', return_value='/usr/bin/kioclient'), patch('lumen_i18n.worker_process', return_value=process):
                    window.show_properties(path)
                    process.setProgram.assert_called_once_with('/usr/bin/kioclient')
                    args = process.setArguments.call_args.args[0]
                    self.assertEqual(args[-2], 'openProperties')
                    self.assertEqual(QUrl(args[-1]).toLocalFile(), str(path))
                    self.assertIn('Lumen Files · Eigenschaften', args)
                    process.startDetached.assert_called_once_with()
                    with patch.object(window.network, 'remote', return_value='sftp://server/folder/notes%20%231.txt'):
                        window.show_properties(path)
                    self.assertEqual(process.setArguments.call_args.args[0][-1], 'sftp://server/folder/notes%20%231.txt')
                    process.startDetached.return_value = (False, 0)
                    with patch.object(window, 'error') as error:
                        window.show_properties(path)
                        error.assert_called_once_with('Die Dateieigenschaften konnten nicht geöffnet werden.')
                with patch('shutil.which', return_value=None), patch.object(window, 'error') as error:
                    window.show_properties(path)
                    self.assertIn('kde-cli-tools', error.call_args.args[0])
                self.wait(lambda: window.fs.index(str(path)).isValid()); QTest.qWait(100)
                window.view.setCurrentIndex(window.proxy.mapFromSource(window.fs.index(str(path))))
                window.view.setFocus()
                with patch('shutil.which', return_value='/usr/bin/kioclient'), patch('lumen_i18n.worker_process', return_value=process):
                    process.reset_mock(); process.startDetached.return_value = (True, 123)
                    QTest.keyClick(window.view, Qt.Key_Return, Qt.AltModifier)
                    process.startDetached.assert_called_once_with()
                self.assertEqual(path.read_text(), 'keep content')
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)


if __name__ == '__main__': unittest.main()
