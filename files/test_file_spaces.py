import tempfile
import unittest
from pathlib import Path

from file_spaces import Catalog, scan_source
from lumen_store import Store


class CatalogTest(unittest.TestCase):
    def test_organize_each_source_keeps_its_own_scope(self):
        from organize import snapshot, validate_moves
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for source in ('PC', 'NAS'):
                folder = Path(tmp) / source; folder.mkdir()
                path = folder / 'same.txt'; path.write_text(source); paths.append(str(path))
            items = snapshot(paths, None)
            for mode, target in [('rename', 'new.txt'), ('sort', 'Archive/same.txt')]:
                moves, errors = validate_moves(items, [{'id': i, 'target': target} for i in range(2)], None, mode)
                self.assertFalse(errors)
                self.assertEqual(len(moves), 2)
                self.assertTrue(all(Path(m['destination']).is_relative_to(Path(m['source']).parent) for m in moves))

    def test_deleted_libraries_conflict_and_local_control_characters_are_valid(self):
        from file_spaces import canonical
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Store(Path(tmp) / 'state'))
            library = catalog.save_library(None, 'Test', [])
            newer = catalog.save_library(library, 'Newer', [])
            with self.assertRaises(ValueError): catalog.remove('library', library['id'], library)
            self.assertEqual(catalog.library(library['id']), newer)
            catalog.remove('library', library['id'])
            with self.assertRaises(ValueError): catalog.save_library(library, 'Test', [])
            self.assertEqual(canonical(tmp + '/note\n2026.txt'), tmp + '/note\n2026.txt')

    def test_sources_and_references_survive_restart_without_copying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state')
            catalog = Catalog(store)
            local = Path(tmp) / 'local'; local.mkdir()
            source = local / 'same.txt'; source.write_text('original')
            library = catalog.save_library(None, 'Projekt', [
                {'label': 'PC', 'location': str(local)},
                {'label': 'NAS', 'location': 'smb://server/docs'}])
            catalog.add_shelf([str(source), str(source), 'smb://server/docs/same.txt'])
            again = Catalog(store)
            self.assertEqual(len(again.shelf()), 2)
            self.assertEqual(again.library(library['id'])['sources'][1]['label'], 'NAS')
            again.remove_shelf([str(source)])
            self.assertEqual(source.read_text(), 'original')
            with self.assertRaises(ValueError):
                catalog.save_library(None, 'Bad', [{'label': 'NAS', 'location': 'smb://u:secret@server/docs'}])

    def test_listing_preserves_same_names_hidden_files_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('a', 'b'):
                (root / name).mkdir(); (root / name / 'same.txt').write_text(name)
            (root / 'a' / '.hidden').write_text('hidden')
            rows = list(scan_source(str(root / 'a'), '', False, 100))
            self.assertEqual([row['name'] for row in rows if 'path' in row], ['same.txt'])
            hits = list(scan_source(tmp, 'same', False, 100))
            self.assertEqual(len([row for row in hits if 'path' in row]), 2)
            self.assertTrue(any('error' in row for row in scan_source(str(root / 'missing'), '', False, 100)))


class NativeSpacesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        import time
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 10
        while not condition() and time.monotonic() < deadline: QTest.qWait(20)
        self.assertTrue(condition())

    def test_unified_sources_shelf_and_stale_navigation(self):
        from app import Window
        from file_spaces import LIBRARY, SHELF
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtTest import QTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalog = Catalog(Store(root / 'state'))
            a, b = root / 'PC', root / 'NAS'; a.mkdir(); b.mkdir()
            for folder in (a, b): (folder / 'same.txt').write_text(folder.name)
            library = catalog.save_library(None, 'Gemeinsam', [
                {'label': 'PC', 'location': str(a)}, {'label': 'NAS', 'location': str(b)},
                {'label': 'Offline', 'location': str(root / 'missing')}])
            window = Window(str(a), QSettings(tmp + '/files.ini', QSettings.IniFormat), catalog)
            window.show()
            try:
                window.navigate(LIBRARY + library['id'])
                self.wait(lambda: window.spaces.pending == 0)
                self.assertEqual(window.results.rowCount(), 2)
                self.assertEqual({window.results.item(i, 4).text() for i in range(2)}, {'PC', 'NAS'})
                self.assertEqual(len(window.spaces.errors), 1)
                window.spaces.collect([str(a / 'same.txt'), str(b / 'same.txt')])
                window.new_tab(SHELF)
                self.wait(lambda: window.spaces.pending == 0)
                self.assertEqual(window.results.rowCount(), 2)
                self.assertEqual(window.current_location, SHELF)
                self.assertEqual(window.tabs.count(), 2)
                window.spaces.remove_shelf([str(a / 'same.txt')])
                self.wait(lambda: window.spaces.pending == 0)
                self.assertEqual(window.results.rowCount(), 1)
                self.assertTrue((a / 'same.txt').exists())
                window.navigate(LIBRARY + library['id']); window.navigate(str(a))
                QTest.qWait(200)
                self.assertIs(window.proxy.sourceModel(), window.fs)
                self.assertEqual(window.current_path, str(a))
            finally:
                window.close(); window.deleteLater(); QTest.qWait(30)
