import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageOps

from image_edit import file_stamp, save_image


class ImageEditTest(unittest.TestCase):
    def test_rotation_mirror_backup_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pattern.png'
            image = Image.new('RGB', (3, 2))
            image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)])
            image.save(path)
            original = path.read_bytes()
            backup = save_image(path, ['right', 'mirror'], file_stamp(path.stat()))
            self.assertEqual(Path(backup).read_bytes(), original)
            expected = image.transpose(Image.Transpose.ROTATE_270).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            with Image.open(path) as result:
                self.assertEqual(result.size, (2, 3))
                self.assertEqual(result.tobytes(), expected.tobytes())
            stale = file_stamp(path.stat())
            Image.new('RGB', (9, 8), 'green').save(path)
            changed = path.read_bytes()
            with self.assertRaises(ValueError):
                save_image(path, ['left'], stale)
            self.assertEqual(path.read_bytes(), changed)

    def test_exif_orientation_and_metadata_survive_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'camera.jpg'
            exif = Image.Exif()
            exif[274] = 6
            exif[315] = 'Test photographer'
            Image.new('RGB', (12, 8), 'red').save(path, exif=exif)
            save_image(path, ['right'], file_stamp(path.stat()))
            with Image.open(path) as result:
                self.assertEqual(result.size, (12, 8))
                self.assertIn(result.getexif().get(274), (None, 1))
                self.assertEqual(result.getexif().get(315), 'Test photographer')

    def test_animated_images_and_symlinks_are_not_flattened_or_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'animation.webp'
            Image.new('RGB', (5, 5), 'red').save(path, save_all=True,
                append_images=[Image.new('RGB', (5, 5), 'blue')], duration=100, loop=0)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_image(path, ['right'], file_stamp(path.stat()))
            self.assertEqual(path.read_bytes(), before)
            target = root / 'photo.png'
            Image.new('RGB', (3, 2), 'green').save(target)
            link = root / 'link.png'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                save_image(link, ['right'], file_stamp(link.stat()))
            self.assertTrue(link.is_symlink())


class GalleryTest(unittest.TestCase):
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

    def test_camera_sized_jpeg_decodes_with_worker_memory_limit(self):
        import json
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'camera.JPG'; output = Path(tmp) / 'preview.png'
            Image.new('RGB', (4032, 3024), 'green').save(source)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('preview.py')),
                                     '--data', str(source), str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['kind'], 'image', data)
            self.assertEqual((data['width'], data['height']), (4032, 3024))
            with Image.open(output) as preview:
                self.assertEqual(preview.size, (1600, 1200))

    def test_browse_prefetch_edit_save_and_trash(self):
        from gallery import Gallery
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QMessageBox
        from unittest.mock import patch
        from core import FileWorker
        with tempfile.TemporaryDirectory() as tmp:
            paths = [str(Path(tmp) / f'{i}.png') for i in range(3)]
            for i, path in enumerate(paths):
                Image.new('RGB', (60 + i, 40), 'green').save(path)
            gallery = Gallery(paths, paths[0])
            gallery.show()
            self.wait_until(lambda: gallery.data is not None and paths[1] in gallery.loader.cache)
            self.assertFalse(gallery.editor.isVisible())
            self.assertEqual(gallery.filmstrip.currentRow(), 0)
            QTest.keyClick(gallery, Qt.Key_Right)
            self.assertEqual(gallery.path, paths[1])
            self.assertIsNotNone(gallery.data)  # Cached neighbor appears in this event.
            QTest.mouseClick(gallery.canvas.viewport(), Qt.BackButton)
            self.assertEqual(gallery.path, paths[0])
            QTest.mouseClick(gallery.canvas.viewport(), Qt.ForwardButton)
            self.assertEqual(gallery.path, paths[1])
            QTest.keyClick(gallery.canvas.viewport(), Qt.Key_Back)
            self.assertEqual(gallery.path, paths[0])
            QTest.keyClick(gallery.canvas.viewport(), Qt.Key_Forward)
            self.assertEqual(gallery.path, paths[1])
            QTest.keyClick(gallery, Qt.Key_R)
            self.assertEqual(gallery.operations, ['right'])
            self.assertTrue(gallery.editor.isVisible())
            self.assertEqual(gallery.canvas.item.pixmap().width(), 40)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
                item = gallery.filmstrip.item(2)
                QTest.mouseClick(gallery.filmstrip.viewport(), Qt.LeftButton,
                                 pos=gallery.filmstrip.visualItemRect(item).center())
            self.assertEqual(gallery.path, paths[1])
            self.assertEqual(gallery.filmstrip.currentRow(), 1)
            gallery.save()
            self.wait_until(lambda: not gallery.busy and gallery.data is not None)
            with Image.open(paths[1]) as result:
                self.assertEqual(result.size, (40, 61))
            self.assertEqual(len(list((Path(tmp) / '.lumen-originals').iterdir())), 1)
            # A failed trash request keeps both the file and the current image.
            class FailedTrash(FileWorker):
                def run(self):
                    self.completed.emit([], ['Kein Papierkorb auf diesem Laufwerk'])
            with patch('gallery.FileWorker', FailedTrash), patch.object(QMessageBox, 'exec_', return_value=QMessageBox.Yes), patch.object(QMessageBox, 'warning') as warning:
                gallery.trash()
                self.wait_until(lambda: not gallery.busy)
                warning.assert_called_once()
            self.assertTrue(Path(paths[1]).exists())
            self.assertEqual(gallery.path, paths[1])
            # GIO trash itself has an isolated end-to-end test in test_lumen.
            # Here a worker moves into our test bin to exercise the gallery lifecycle.
            class TestTrash(FileWorker):
                def run(self):
                    Path(self.sources[0]).rename(Path(tmp) / 'test-bin.png')
                    self.completed.emit(self.sources, [])
            with patch('gallery.FileWorker', TestTrash), patch.object(QMessageBox, 'exec_', return_value=QMessageBox.Yes):
                gallery.trash()
            self.wait_until(lambda: not gallery.busy)
            self.assertFalse(Path(paths[1]).exists())
            self.assertEqual(gallery.path, paths[2])
            gallery.reject()
            self.assertFalse(gallery.isVisible())

    def test_filmstrip_scrolls_to_unloaded_images_and_bounds_thumbnail_work(self):
        from gallery import Gallery
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            paths = [str(Path(tmp) / f'{i}.png') for i in range(80)]
            for path in paths:
                Image.new('RGB', (60, 40), 'green').save(path)
            palette = self.app.palette()
            gallery = Gallery(paths, paths[0]); gallery.resize(900, 560); gallery.show()
            try:
                strip = gallery.filmstrip
                self.wait_until(lambda: gallery.data is not None and paths[0] in strip.loader.cache)
                self.assertLess(len(strip.visible_rows), 15)
                self.assertEqual(self.app.palette(), palette)
                gallery.jump(79)
                self.wait_until(lambda: paths[79] in strip.loader.cache)
                self.assertIn(79, strip.visible_rows)
                self.assertGreater(strip.horizontalScrollBar().value(), 0)
                self.assertTrue(strip.item(0).icon().isNull())
                previous = strip.item(78)
                QTest.mouseClick(strip.viewport(), Qt.LeftButton, pos=strip.visualItemRect(previous).center())
                self.assertEqual(gallery.index, 78)
                self.assertLess(len(strip.loader.cache), 30)
            finally:
                gallery.reject(); gallery.deleteLater()

    def test_photo_inspector_routes_actions_and_replaces_cached_preview(self):
        from preview import Preview
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photos = [root / 'red.png', root / 'blue.png']
            for path, color in zip(photos, ['red', 'blue']):
                Image.new('RGB', (120, 80), color).save(path)
            preview = Preview(); preview.resize(350, 650)
            requests = []
            preview.openImage.connect(lambda path, edit: requests.append((path, edit)))
            preview.show()
            try:
                for path, color in zip(photos, ['#ff0000', '#0000ff']):
                    preview.show_path(path, 'smb://nas/photos')
                    self.wait_until(lambda: preview.proc is None and preview.edit_button.isEnabled())
                    self.assertEqual(preview.pixmap.toImage().pixelColor(10, 10).name(), color)
                    self.assertEqual(preview.location.text(), 'NAS · nas')
                    self.assertIn('120 × 80', preview.detail.text())
                    self.assertLess(preview.stack.y(), preview.title.y())
                QTest.mouseClick(preview.open_button, Qt.LeftButton)
                QTest.mouseClick(preview.edit_button, Qt.LeftButton)
                self.assertEqual(requests, [(str(photos[1]), False), (str(photos[1]), True)])
                preview.show_path(root)
                self.wait_until(lambda: preview.proc is None)
                self.assertFalse(preview.edit_button.isVisible())
                self.assertIn('Standard-App', preview.open_button.text())
                self.assertGreater(preview.stack.y(), preview.title.y())
            finally:
                preview.cancel(); preview.close(); preview.deleteLater()


if __name__ == '__main__':
    unittest.main()
