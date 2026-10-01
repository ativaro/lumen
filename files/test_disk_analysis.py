import os
import tempfile
import time
import unittest
from pathlib import Path


class DiskAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait_until(self, condition, seconds=15):
        from PyQt5.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Disk scan timed out')

    def test_sizes_sparse_hardlinks_symlinks_and_lazy_tree(self):
        from disk_analysis import DiskAnalysis
        from PyQt5.QtCore import Qt
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'nested'
            folder.mkdir()
            (folder / 'data\nwith\ttab').write_bytes(b'a' * 8192)
            os.link(folder / 'data\nwith\ttab', folder / 'hardlink')
            (folder / 'loop').symlink_to(root, target_is_directory=True)
            with (root / 'sparse').open('wb') as stream:
                stream.truncate(8 * 1024**2)
            dialog = DiskAnalysis(tmp)
            dialog.show()
            self.wait_until(lambda: dialog.proc is None and dialog.root_item.data(0, Qt.UserRole + 1))
            expected = sum(path.lstat().st_blocks * 512 for path in [root, folder, folder / 'data\nwith\ttab', folder / 'loop', root / 'sparse'])
            self.assertEqual(dialog.root_item.data(1, Qt.UserRole), expected)
            child = next(dialog.root_item.child(i) for i in range(dialog.root_item.childCount())
                         if dialog.root_item.child(i).data(0, Qt.UserRole) == str(folder))
            child.setExpanded(True)
            self.wait_until(lambda: child.data(0, Qt.UserRole + 1))
            self.assertEqual(child.childCount(), 2)  # One hardlink counted, symlink not followed.
            dialog.apparent.setChecked(True)
            self.wait_until(lambda: dialog.proc is None and dialog.root_item.data(0, Qt.UserRole + 1))
            self.assertGreaterEqual(dialog.root_item.data(1, Qt.UserRole), 8 * 1024**2)
            self.assertEqual(dialog.root_item.child(0).text(0), 'sparse')
            dialog.scan(dialog.root_item)
            dialog.stop()
            self.assertIsNone(dialog.proc)
            self.assertIn('abgebrochen', dialog.status.text())
            dialog.close()

    def test_inaccessible_folder_is_reported_and_retry_recovers(self):
        if os.geteuid() == 0:
            self.skipTest('Root kann Testordner trotz fehlender Rechte lesen.')
        from disk_analysis import DiskAnalysis
        from PyQt5.QtCore import Qt
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / 'blocked'
            blocked.mkdir()
            (blocked / 'private').write_text('test data')
            blocked.chmod(0)
            try:
                dialog = DiskAnalysis(tmp)
                values = []
                dialog.sizesReady.connect(values.append)
                dialog.apparent.setChecked(True)
                self.wait_until(lambda: dialog.proc is None)
                self.assertIn('Unvollständig', dialog.status.text())
                self.assertEqual(values, [])
                self.assertTrue(dialog.errors)
                self.assertFalse(dialog.root_item.data(0, Qt.UserRole + 1))
                blocked.chmod(0o700)
                dialog.restart()
                self.wait_until(lambda: dialog.proc is None)
                self.assertTrue(dialog.root_item.data(0, Qt.UserRole + 1))
                self.assertEqual(values[-1][str(blocked)], len('test data'))
                dialog.close()
            finally:
                blocked.chmod(0o700)

    def test_folder_sizes_fill_list_and_library_without_automatic_scan(self):
        from unittest.mock import patch
        from PyQt5.QtCore import QSettings, Qt, QTimer
        from PyQt5.QtTest import QTest
        from app import Window
        from disk_analysis import DiskAnalysis
        from file_spaces import Catalog, LIBRARY
        from lumen_store import Store
        from core import size_text
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / 'Daten'; folder.mkdir()
            (folder / 'nested').mkdir()
            (folder / 'empty').mkdir()
            (folder / 'nested' / 'file').write_bytes(b'x' * 8192)
            (root / 'file.txt').write_bytes(b'x' * 2048)
            catalog = Catalog(Store(root / 'state'))
            window = Window(tmp, QSettings(str(root / 'settings.ini'), QSettings.IniFormat), catalog)
            window.show()
            def cell(path):
                return window.proxy.mapFromSource(window.fs.index(str(path), 1))
            try:
                self.wait_until(lambda: cell(folder).isValid())
                self.assertEqual(cell(folder).data(), 'Berechnen')
                self.assertIn('Klick', cell(folder).data(Qt.ToolTipRole))
                self.assertTrue(cell(root / 'file.txt').data())
                self.assertFalse(window.findChildren(DiskAnalysis))
                def close_when_ready():
                    dialog = window.findChild(DiskAnalysis)
                    if dialog and dialog.proc is None:
                        self.assertTrue(dialog.apparent.isChecked())
                        dialog.accept()
                    else: QTimer.singleShot(20, close_when_ready)
                QTimer.singleShot(20, close_when_ready)
                QTest.mouseClick(window.view.viewport(), Qt.LeftButton, pos=window.view.visualRect(cell(folder)).center())
                expected = (folder / 'nested' / 'file').stat().st_size
                self.assertEqual(cell(folder).data(), size_text(expected))
                self.assertEqual(window.proxy.folder_sizes[str(folder)], expected)
                self.assertEqual(window.proxy.folder_sizes[str(folder / 'empty')], 0)
                window.refresh()
                self.assertEqual(cell(folder).data(), 'Berechnen')
                library = catalog.save_library(None, 'Test', [{'label': 'PC', 'location': tmp}])
                window.navigate(LIBRARY + library['id'])
                self.wait_until(lambda: window.spaces.pending == 0)
                index = next(window.proxy.index(i, 1) for i in range(window.proxy.rowCount())
                             if window.proxy.index(i, 0).data() == 'Daten')
                self.assertEqual(index.data(), 'Berechnen')
                with patch.object(window, 'open_analysis') as analysis:
                    window.size_clicked(index)
                    analysis.assert_called_once_with(str(folder), apparent=True)
            finally:
                window.close(); window.deleteLater(); QTest.qWait(50)


if __name__ == '__main__':
    unittest.main()
