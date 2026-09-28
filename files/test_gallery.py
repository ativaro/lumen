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
        cls.app = create_app()

    def wait_until(self, condition, seconds=15):
        import time
        from PyQt5.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition(), 'UI operation timed out')

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
            QTest.keyClick(gallery, Qt.Key_Right)
            self.assertEqual(gallery.path, paths[1])
            self.assertIsNotNone(gallery.data)  # Cached neighbor appears in this event.
            QTest.keyClick(gallery, Qt.Key_R)
            self.assertEqual(gallery.operations, ['right'])
            self.assertEqual(gallery.canvas.item.pixmap().width(), 40)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
                gallery.step(1)
            self.assertEqual(gallery.path, paths[1])
            gallery.save()
            self.wait_until(lambda: not gallery.busy and gallery.data is not None)
            with Image.open(paths[1]) as result:
                self.assertEqual(result.size, (40, 61))
            self.assertEqual(len(list((Path(tmp) / '.lumen-originals').iterdir())), 1)
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


if __name__ == '__main__':
    unittest.main()
