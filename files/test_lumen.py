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

    def test_tabs_sort_and_preview_width_survive_reopening(self):
        from app import Window
        from PyQt5.QtCore import QSettings, Qt
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / 'first', root / 'second'
            first.mkdir(); second.mkdir()
            settings = QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
            window = Window(str(first), settings)
            window.show()
            window.new_tab(str(second))
            window.view.sortByColumn(1, Qt.DescendingOrder)
            window.splitter.setSizes([700, 340])
            QTest.qWait(50)
            sizes = window.splitter.sizes()
            window.close()
            window.deleteLater()
            restored = Window(settings=settings)
            restored.show(); QTest.qWait(50)
            try:
                self.assertEqual([t['history'][t['position']] for t in restored.tabs_data], [str(first), str(second)])
                self.assertEqual(restored.current_path, str(second))
                self.assertEqual(restored.view.header().sortIndicatorSection(), 1)
                self.assertEqual(restored.view.header().sortIndicatorOrder(), Qt.DescendingOrder)
                self.assertLess(abs(restored.splitter.sizes()[1] - sizes[1]), 5)
            finally:
                restored.close(); restored.deleteLater()
            # A requested folder takes precedence over the saved workspace.
            explicit = Window(str(first), settings)
            self.assertEqual(explicit.tabs.count(), 1)
            explicit.close(); explicit.deleteLater()
            second.rmdir()
            settings.setValue('session/tabs', [str(second), str(first), 'smb://server/share', 'smb://u:secret@server/share'])
            settings.setValue('session/activeTab', 1)
            from unittest.mock import patch
            with patch('network.Network.mount') as mount:
                recovered = Window(settings=settings)
                self.assertEqual(recovered.tabs.count(), 2)
                self.assertEqual(recovered.current_path, str(first))
                mount.assert_not_called()
                recovered.close(); recovered.deleteLater()
            QTest.qWait(50)

    def test_grid_thumbnails_selection_search_and_settings(self):
        from app import Window
        from PyQt5.QtCore import QSettings, Qt
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QApplication
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / 'photo.png'
            Image.new('RGB', (900, 600), 'red').save(photo)
            broken = root / 'broken.png'
            broken.write_bytes(b'not an image')
            nested = root / 'nested'
            nested.mkdir()
            Image.new('RGB', (200, 300), 'blue').save(nested / 'other.png')
            settings = QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
            window = Window(tmp, settings)
            window.show()
            try:
                QTest.qWait(50)
                QTest.keyClick(window, Qt.Key_2, Qt.ControlModifier)
                self.assertIs(window.file_stack.currentWidget(), window.grid)
                self.wait_until(lambda: str(photo) in window.grid.loader.cache and str(broken) in window.grid.failed)
                pixmap = window.grid.loader.cache[str(photo)][0]
                self.assertEqual((pixmap.width(), pixmap.height()), (256, 170))
                index = window.proxy.mapFromSource(window.fs.index(str(photo)))
                QTest.mouseClick(window.grid.viewport(), Qt.LeftButton, pos=window.grid.visualRect(index).center())
                self.assertEqual(window.selected_paths(), [str(photo)])
                QTest.keyClick(window.grid, Qt.Key_C, Qt.ControlModifier)
                self.assertEqual(QApplication.clipboard().mimeData().urls()[0].toLocalFile(), str(photo))
                window.set_view_mode('list')
                self.assertEqual(window.selected_paths(), [str(photo)])
                window.set_view_mode('grid')
                window.thumbnail_size.setValue(192)
                Image.new('RGB', (900, 600), 'green').save(photo)
                self.wait_until(lambda: str(photo) in window.grid.loader.cache and
                    window.grid.loader.cache[str(photo)][0].toImage().pixelColor(10, 10).green() == 128)
                window.search.setText('other')
                self.wait_until(lambda: window.proxy.sourceModel() is window.results and not window.search_jobs)
                self.wait_until(lambda: str(nested / 'other.png') in window.grid.loader.cache)
                self.assertEqual(window.grid.model().rowCount(window.grid.rootIndex()), 1)
                window.navigate(nested)
                self.wait_until(lambda: str(nested / 'other.png') in window.grid.loader.cache)
                self.assertEqual(window.grid.rootIndex(), window.view.rootIndex())
            finally:
                window.close(); window.deleteLater()
            restored = Window(settings=settings)
            self.assertIs(restored.file_stack.currentWidget(), restored.grid)
            self.assertEqual(restored.thumbnail_size.value(), 192)
            restored.close(); restored.deleteLater()
            QTest.qWait(50)

    def test_compact_breadcrumb_keeps_current_folder_visible(self):
        from app import Window
        from PyQt5.QtCore import QPoint, QSettings, Qt
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat))
            window.show(); window.resize(1000, 640)
            try:
                path = str(Path.home() / 'a-long-project-folder' / 'another-long-folder' / 'current-folder-name')
                window.build_crumbs(path); QTest.qWait(50)
                last = window.crumb_layout.itemAt(window.crumb_layout.count() - 2).widget()
                viewport = window.crumbs.viewport()
                self.assertEqual(last.toolTip(), path)
                self.assertGreaterEqual(last.mapTo(viewport, QPoint()).x(), 0)
                self.assertLessEqual(last.mapTo(viewport, last.rect().topRight()).x(), viewport.width())
                self.assertLessEqual(window.crumbs.height(), 40)
                QTest.keyClick(window, Qt.Key_L, Qt.ControlModifier)
                self.assertIs(window.path_stack.currentWidget(), window.path_edit)
                from unittest.mock import patch
                with patch('assistant_backend.OpenCodeBackend.refresh_sessions'):
                    window.ask_lumen('open', [])
                    QTest.qWait(50)
                    self.assertGreaterEqual(window.centralWidget().width(), 1000)
                    window.assistant_dock.hide(); QTest.qWait(50)
                    self.assertEqual(window.minimumWidth(), 1000)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)

    def test_grid_renders_folder_icon_before_clearing_native_decoration(self):
        from app import Window
        from PyQt5.QtCore import QSettings, QRect, Qt
        from PyQt5.QtGui import QImage, QPainter
        from PyQt5.QtWidgets import QStyle, QStyleOptionViewItem
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / 'Documents'; folder.mkdir()
            document = root / 'Notes.txt'; document.write_text('Example')
            window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat))
            window.show(); window.set_view_mode('grid')
            try:
                self.wait_until(lambda: window.fs.index(str(folder)).isValid())
                index = window.proxy.mapFromSource(window.fs.index(str(folder)))
                image = QImage(224, 210, QImage.Format_ARGB32); image.fill(Qt.transparent)
                option = QStyleOptionViewItem(); option.initFrom(window.grid)
                option.rect = QRect(0, 0, 224, 210); option.state = QStyle.State_Enabled
                painter = QPainter(image)
                window.grid.itemDelegate().paint(painter, option, index); painter.end()
                # A native folder has colored pixels inside the icon area; a blank
                # tile or the selection border cannot satisfy this check.
                colored = sum(image.pixelColor(x, y).saturation() > 90
                              and image.pixelColor(x, y).alpha() > 128
                              for x in range(40, 184) for y in range(30, 130))
                self.assertGreater(colored, 100)
                index = window.proxy.mapFromSource(window.fs.index(str(document)))
                self.assertTrue(index.isValid())
                image.fill(Qt.transparent)
                painter = QPainter(image)
                window.grid.itemDelegate().paint(painter, option, index); painter.end()
                self.assertGreater(sum(image.pixelColor(x, y).alpha() > 128
                                       for x in range(60, 164) for y in range(45, 125)), 50)

            finally:
                window.close(); window.deleteLater(); QTest.qWait(100)

    def test_folder_badges_follow_configured_locations_in_list_grid_and_libraries(self):
        from app import Window
        from folder_icons import folder_icons
        from PyQt5.QtCore import QSettings, QStandardPaths, Qt, QModelIndex
        from PyQt5.QtTest import QTest
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document, picture, ordinary = (root / name for name in ('Meine Texte', 'Meine Fotos', 'Documents'))
            for path in (document, picture, ordinary): path.mkdir()
            link = root / 'Verknüpfung'; link.symlink_to(document, target_is_directory=True)
            locations = {QStandardPaths.DocumentsLocation: str(document), QStandardPaths.PicturesLocation: str(picture)}
            with patch.object(QStandardPaths, 'writableLocation', side_effect=lambda kind: locations.get(kind, '')):
                icons = folder_icons()
            window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat))
            window.proxy.folder_icons = icons
            window.show()
            try:
                self.wait_until(lambda: window.fs.index(str(link)).isValid())
                def image(path):
                    index = window.proxy.mapFromSource(window.fs.index(str(path)))
                    return index.data(Qt.DecorationRole).pixmap(120, 104).toImage()
                self.assertNotEqual(image(document), image(picture))
                self.assertNotEqual(image(document), image(ordinary))
                self.assertEqual(image(ordinary), icons[''].pixmap(120, 104).toImage())
                self.assertEqual(image(link), window.fs.index(str(link)).data(Qt.DecorationRole).pixmap(120, 104).toImage())
                expected = image(document)
                window.spaces.add_entry(
                    {'path': str(document), 'name': document.name, 'directory': True,
                     'size': 0, 'modified': document.stat().st_mtime},
                    {'label': 'Local test', 'location': tmp}, tmp, 100)
                window.proxy.setSourceModel(window.results)
                window.set_file_root(QModelIndex()); window.set_view_mode('grid')
                self.assertEqual(window.proxy.index(0, 0).data(Qt.DecorationRole).pixmap(120, 104).toImage(), expected)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(100)

    def test_system_colors_and_font_follow_light_and_dark_kde_settings(self):
        from app import Window, apply_system_appearance
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
        from PyQt5.QtGui import QIcon, QPalette
        palette, font, theme, style = self.app.palette(), self.app.font(), QIcon.themeName(), self.app.styleSheet()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'kdeglobals'
                window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat))
                window.show()
                self.addCleanup(window.deleteLater)
                self.addCleanup(window.close)
                for background, foreground in [('16,25,37', '248,250,252'), ('255,255,255', '32,35,40')]:
                    path.write_text('[General]\nfont=Noto Sans,9,-1,5,400,0\n'
                        f'[Colors:Window]\nBackgroundNormal={background}\nForegroundNormal={foreground}\n'
                        f'[Colors:View]\nBackgroundNormal={background}\nForegroundNormal={foreground}\n')
                    apply_system_appearance(self.app, path)
                    QTest.qWait(20)
                    self.assertEqual(self.app.palette().color(QPalette.Base).getRgb()[:3], tuple(map(int, background.split(','))))
                    self.assertEqual(self.app.palette().color(QPalette.Text).getRgb()[:3], tuple(map(int, foreground.split(','))))
                    self.assertEqual(self.app.font().family(), 'Noto Sans')
                    self.assertEqual(self.app.font().pointSizeF(), 9)
                    self.assertEqual(window.view.palette().color(QPalette.Base).getRgb()[:3], tuple(map(int, background.split(','))))
        finally:
            self.app.setStyleSheet('')
            self.app.setPalette(palette)
            self.app.setFont(font)
            QIcon.setThemeName(theme)
            self.app.setStyleSheet(style)

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
                self.assertIs(window.view.window(), window)
                for receiver in (window.view, window.view.viewport(), window.places.viewport(), window.preview.text.viewport(), window.search, window.tabs):
                    QTest.mouseClick(receiver, Qt.BackButton)
                    self.assertEqual(window.current_path, str(first))
                    QTest.mouseClick(receiver, Qt.ForwardButton)
                    self.assertEqual(window.current_path, str(second))
                    QTest.keyClick(receiver, Qt.Key_Back)
                    self.assertEqual(window.current_path, str(first))
                    QTest.keyClick(receiver, Qt.Key_Forward)
                    self.assertEqual(window.current_path, str(second))
                dialog = QDialog(window)
                dialog.setModal(True)
                dialog.show()
                QTest.qWait(20)
                QTest.mouseClick(dialog, Qt.BackButton)
                QTest.mouseClick(window.search, Qt.BackButton)
                QTest.keyClick(dialog, Qt.Key_Back)
                QTest.keyClick(window.search, Qt.Key_Back)
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
