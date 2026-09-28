import tempfile
import threading
import unittest
from pathlib import Path

from core import copy_entry, move_entry, search_paths, valid_name


class FilesTest(unittest.TestCase):
    def test_search_nested_hidden_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'nested').mkdir()
            (root / 'nested' / 'Sommer FOTO.jpg').write_bytes(b'photo')
            (root / '.Foto.txt').write_text('hidden')
            (root / 'nested' / 'loop').symlink_to(root, target_is_directory=True)
            hits = list(search_paths(root, 'foto', False, threading.Event()))
            self.assertEqual(hits, [root / 'nested' / 'Sommer FOTO.jpg'])
            self.assertEqual(len(list(search_paths(root, 'foto', True, threading.Event()))), 2)
            stop = threading.Event()
            stop.set()
            self.assertEqual(list(search_paths(root, '', True, stop)), [])

    def test_copy_move_refuse_overwrite_and_recursive_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, target = root / 'source', root / 'target'
            src.mkdir()
            target.mkdir()
            (src / 'hello.txt').write_text('original')
            (src / 'link').symlink_to('hello.txt')
            copied = copy_entry(src, target)
            self.assertEqual((copied / 'hello.txt').read_text(), 'original')
            self.assertTrue((copied / 'link').is_symlink())
            with self.assertRaises(Exception):
                copy_entry(src, target)
            with self.assertRaises(ValueError):
                copy_entry(src, src)
            other = root / 'other.txt'
            other.write_text('keep')
            with self.assertRaises(Exception):
                move_entry(src / 'hello.txt', other)
            self.assertEqual(other.read_text(), 'keep')
            self.assertEqual((src / 'hello.txt').read_text(), 'original')
            move_entry(other, root / 'renamed.txt')
            self.assertFalse(other.exists())
            self.assertEqual((root / 'renamed.txt').read_text(), 'keep')

    def test_names_cannot_escape_directory(self):
        for name in ['', '.', '..', '../outside', '/tmp/out', 'bad\x00name']:
            with self.assertRaises(ValueError):
                valid_name(name)
        self.assertEqual(valid_name(' Sommer 2026.txt '), ' Sommer 2026.txt ')


class NativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait_until(self, condition, seconds=15):
        import time
        from PyQt5.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition(), 'UI operation timed out')

    def test_mouse_history_over_child_widgets_and_dialog_isolation(self):
        from app import Window
        from PyQt5.QtCore import QSettings, Qt
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QDialog
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / 'first', root / 'first' / 'second'
            second.mkdir(parents=True)
            window = Window(tmp, QSettings(str(root / 'settings.ini'), QSettings.IniFormat))
            window.show()
            try:
                window.navigate(first)
                window.navigate(second)
                QTest.qWait(50)
                for receiver in (window.view.viewport(), window.places.viewport(), window.preview.text.viewport(), window.search, window.tabs):
                    QTest.mouseClick(receiver, Qt.BackButton)
                    self.assertEqual(window.current_path, str(first))
                    QTest.mouseClick(receiver, Qt.ForwardButton)
                    self.assertEqual(window.current_path, str(second))
                dialog = QDialog(window)
                dialog.setModal(True)
                dialog.show()
                QTest.qWait(20)
                QTest.mouseClick(dialog, Qt.BackButton)
                QTest.mouseClick(window.search, Qt.BackButton)
                self.assertEqual(window.current_path, str(second))
                dialog.close()
            finally:
                window.close()
                window.deleteLater()
                QTest.qWait(100)

    def test_places_fit_in_compact_window_and_long_names_elide(self):
        from app import Window
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
        from PyQt5.QtGui import QIcon
        with tempfile.TemporaryDirectory() as tmp:
            window = Window(tmp, QSettings(str(Path(tmp) / 'settings.ini'), QSettings.IniFormat))
            window.show()
            try:
                window.places.clear()
                window.places.addItems(['Persönlicher Ordner', 'Schreibtisch', 'Downloads', 'Dokumente',
                    'Bilder', 'Videos', 'Musik', 'Dateisystem', 'NAS', 'Ein sehr langer gemerkter Projektordner'])
                for i in range(window.places.count()):
                    window.places.item(i).setIcon(QIcon.fromTheme('folder'))
                for size in ((1380, 860), (1024, 700), (1000, 640)):
                    window.resize(*size)
                    QTest.qWait(50)
                    self.assertEqual(window.places.verticalScrollBar().maximum(), 0, size)
                    self.assertFalse(window.places.horizontalScrollBar().isVisible())
                    self.assertTrue(window.places.viewport().rect().contains(window.places.visualItemRect(window.places.item(9))), size)
            finally:
                window.close()
                window.deleteLater()
                QTest.qWait(100)

    def test_navigation_search_previews_and_file_actions(self):
        import os
        import subprocess
        from app import Window
        from PyQt5.QtCore import QItemSelectionModel, QPoint, QSettings, Qt
        from PyQt5.QtGui import QImage, QColor, QPainter, QPdfWriter
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / 'nested'
            nested.mkdir()
            text = nested / 'Summer Notes.txt'
            text.write_text('This is plain text. <script>never rendered</script>')
            (root / '.hidden.txt').write_text('hidden')
            (root / 'large.txt').write_text('a' * 200000)
            (root / 'binary.bin').write_bytes(b'\x00\x01\xff')
            (root / 'invalid.png').write_bytes(b'broken image')
            os.mkfifo(root / 'pipe')
            image = QImage(640, 480, QImage.Format_RGB32)
            image.fill(QColor('#81cdbd'))
            image.save(str(root / 'image.png'))
            (root / 'vector.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="green"/><text x="10" y="40">Lumen</text></svg>')
            pdf = QPdfWriter(str(root / 'report.pdf'))
            painter = QPainter(pdf)
            painter.drawText(200, 200, 'Lumen preview test')
            pdf.newPage()
            painter.drawText(200, 200, 'Page two')
            painter.end()
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=blue:s=320x240:d=0.3', '-y', str(root / 'clip.mp4')], check=True)
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.2', '-y', str(root / 'sound.wav')], check=True)
            settings = QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
            window = Window(tmp, settings)
            window.show()
            self.wait_until(lambda: window.proxy.rowCount(window.view.rootIndex()) >= 10)
            self.assertLess(window.tabs.mapTo(window, QPoint()).y(), window.search.mapTo(window, QPoint()).y())
            self.assertNotIn('/mnt/games', [window.places.item(i).data(Qt.UserRole) for i in range(window.places.count())])
            from unittest.mock import patch
            with patch('app.Gallery') as gallery:
                gallery.return_value.path = str(root / 'vector.svg')
                window.open_path(str(root / 'image.png'))
                gallery.assert_called_once()
                self.assertEqual(set(gallery.call_args.args[0]), {str(root / name) for name in ['image.png', 'invalid.png', 'vector.svg']})
                self.assertEqual(window.selected_paths(), [str(root / 'vector.svg')])
            window.new_tab(str(nested))
            self.assertEqual(window.current_path, str(nested))
            window.navigate(root)
            window.history(-1)
            self.assertEqual(window.current_path, str(nested))
            window.close_tab(1)
            self.assertEqual(window.current_path, tmp)
            self.assertEqual(window.tabs.count(), 1)
            window.search.setText('summer notes')
            self.wait_until(lambda: window.results.rowCount() == 1 and window.search_job is None)
            self.assertEqual(window.results.item(0).data(Qt.UserRole), str(text))
            window.search.setText('image')
            QTest.qWait(270)
            window.search.setText('report')
            self.wait_until(lambda: window.search_job is None and window.results.rowCount() == 1
                            and window.results.item(0).text() == 'report.pdf')
            window.search.setText('does not exist')
            self.wait_until(lambda: window.search_job is None and window.results.rowCount() == 0)
            window.search.clear()
            self.wait_until(lambda: window.proxy.sourceModel() is window.fs)
            window.toggle_hidden()
            self.wait_until(lambda: window.proxy.mapFromSource(window.fs.index(str(root / '.hidden.txt'))).isValid())
            window.set_kind('image')
            self.assertFalse(window.proxy.mapFromSource(window.fs.index(str(root / 'report.pdf'))).isValid())
            window.set_kind('all')
            for name in ['image.png', 'vector.svg', 'report.pdf', 'clip.mp4', 'sound.wav']:
                with self.subTest(preview=name):
                    window.preview.show_path(root / name)
                    self.wait_until(lambda: window.preview.proc is None)
                    self.assertIs(window.preview.stack.currentWidget(), window.preview.image,
                                  window.preview.message.text())
                    self.assertFalse(window.preview.pixmap.isNull())
                    if name.endswith('pdf'):
                        self.assertEqual(window.preview.pages, 2)
                        window.preview.change_page(1)
                        self.wait_until(lambda: window.preview.proc is None)
                        self.assertEqual(window.preview.page, 2)
                        self.assertFalse(window.preview.next.isEnabled())
            window.preview.show_path(root / 'large.txt')
            self.wait_until(lambda: window.preview.proc is None)
            self.assertEqual(len(window.preview.text.toPlainText()), 128 * 1024)
            self.assertIn('128 KB', window.preview.note.text())
            for name in ['binary.bin', 'invalid.png', 'pipe']:
                window.preview.show_path(root / name)
                self.wait_until(lambda: window.preview.proc is None)
                self.assertIs(window.preview.stack.currentWidget(), window.preview.message)
            window.preview.show_path(root / 'report.pdf')
            window.preview.show_path(text)
            self.wait_until(lambda: window.preview.proc is None)
            self.assertEqual(window.preview.text.toPlainText(), text.read_text())
            window.run_operation('copy', [str(text)], tmp)
            self.wait_until(lambda: window.file_job is None)
            self.assertEqual((root / text.name).read_text(), text.read_text())
            window.run_operation('rename', [str(root / text.name)], str(root / 'Renamed.txt'))
            self.wait_until(lambda: window.file_job is None)
            self.assertEqual((root / 'Renamed.txt').read_text(), text.read_text())
            index = window.proxy.mapFromSource(window.fs.index(str(root / 'Renamed.txt')))
            window.view.setCurrentIndex(index)
            window.view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            window.copy(True)
            window.navigate(nested)
            window.paste()
            self.wait_until(lambda: window.file_job is None)
            self.assertTrue((nested / 'Renamed.txt').exists())
            self.assertFalse((root / 'Renamed.txt').exists())
            # A single-selection action is driven through the actual keyboard shortcut.
            window.navigate(root)
            window.view.setFocus()
            QTest.keyClick(window.view, Qt.Key_F, Qt.ControlModifier)
            self.assertTrue(window.search.hasFocus())
            window.close()
            self.assertFalse(window.isVisible())

    def test_trash_uses_freedesktop_recovery_metadata(self):
        import os
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'trash-test.txt'
            source.write_text('recover me')
            script = ('from gi.repository import Gio; import sys; '
                      'Gio.File.new_for_path(sys.argv[1]).trash(None)')
            env = {**os.environ, 'HOME': tmp, 'XDG_DATA_HOME': str(root / 'data')}
            subprocess.run(['/usr/bin/python3', '-c', script, str(source)], env=env, check=True)
            self.assertFalse(source.exists())
            trashed = list((root / 'data/Trash/files').glob('trash-test*'))
            self.assertEqual(len(trashed), 1)
            self.assertEqual(trashed[0].read_text(), 'recover me')
            self.assertEqual(len(list((root / 'data/Trash/info').glob('*.trashinfo'))), 1)


if __name__ == '__main__':
    unittest.main()
