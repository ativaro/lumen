import tempfile
import unittest
from pathlib import Path

from file_spaces import Catalog, scan_source
from lumen_store import Store


class CatalogTest(unittest.TestCase):
    def test_room_shelves_are_separate_and_reopening_preserves_concurrent_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Catalog(Store(Path(tmp) / 'state')), Catalog(Store(Path(tmp) / 'state'))
            first.add_shelf([tmp + '/global.txt'])
            first.use_room_shelf('a', [tmp + '/a.txt'])
            second.use_room_shelf('b', [tmp + '/b.txt'])
            self.assertEqual(first.shelf(), [tmp + '/a.txt'])
            self.assertEqual(second.shelf(), [tmp + '/b.txt'])
            second.use_room_shelf('a')
            second.add_shelf([tmp + '/new.txt']); second.remove_shelf([tmp + '/a.txt'])
            first.use_room_shelf('a', [tmp + '/a.txt'])
            self.assertEqual(first.shelf(), [tmp + '/new.txt'])
            first.use_room_shelf()
            self.assertEqual(first.shelf(), [tmp + '/global.txt'])

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

    def test_deleted_rooms_conflict_and_local_control_characters_are_valid(self):
        from file_spaces import canonical
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Store(Path(tmp) / 'state'))
            room = catalog.save_room(None, 'Test', {})
            newer = catalog.save_room(room, 'Newer', {'draft': 'keep'})
            with self.assertRaises(ValueError): catalog.remove('room', room['id'], room)
            self.assertEqual(catalog.rooms(), [newer])
            catalog.remove('room', room['id'])
            with self.assertRaises(ValueError): catalog.save_room(room, 'Test', {})
            self.assertEqual(canonical(tmp + '/note\n2026.txt'), tmp + '/note\n2026.txt')

    def test_sources_references_and_rooms_survive_restart_without_copying_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state')
            catalog = Catalog(store)
            local = Path(tmp) / 'local'; local.mkdir()
            source = local / 'same.txt'; source.write_text('original')
            library = catalog.save_library(None, 'Projekt', [
                {'label': 'PC', 'location': str(local)},
                {'label': 'NAS', 'location': 'smb://server/docs'}])
            catalog.add_shelf([str(source), str(source), 'smb://server/docs/same.txt'])
            room = catalog.save_room(None, 'Arbeit', {'tabs': [str(local)], 'shelf': catalog.shelf()})
            again = Catalog(store)
            self.assertEqual(len(again.shelf()), 2)
            self.assertEqual(again.library(library['id'])['sources'][1]['label'], 'NAS')
            self.assertEqual(again.rooms()[0]['id'], room['id'])
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

    def test_unified_sources_shelf_rooms_and_stale_navigation(self):
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
                room = catalog.save_room(None, 'Projekt', window.spaces.capture())
                catalog.add_shelf([str(a / 'collected-in-another-window.txt')])
                window.navigate(str(b)); window.spaces.open_room(room)
                self.wait(lambda: window.spaces.pending == 0)
                self.assertEqual(window.current_location, SHELF)
                self.assertEqual(window.tabs.count(), 2)
                self.assertNotIn(str(a / 'collected-in-another-window.txt'), catalog.shelf())
                self.assertIn(str(a / 'collected-in-another-window.txt'), Catalog(catalog.store).shelf())
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

    def test_room_preserves_draft_remote_context_and_never_submits(self):
        from app import Window
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Catalog(Store(Path(tmp) / 'state'))
            window = Window(tmp, QSettings(tmp + '/files.ini', QSettings.IniFormat), catalog)
            with patch('assistant_backend.OpenCodeBackend.refresh_sessions'), patch('assistant_backend.OpenCodeBackend.send') as send:
                window.ask_lumen('open', [])
                chat = window.assistant
                chat.composer.setPlainText('Ungesendeter Entwurf')
                chat.paths = ['smb://nas/Other/keep.txt']
                room = catalog.save_room(None, 'Entwurf', window.spaces.capture())
                chat.composer.clear()
                errors = []; window.error = lambda *args: errors.append(args)
                chat.backend.busy = True; window.spaces.open_room(room)
                self.assertTrue(errors)
                self.assertIsNone(window.spaces.active_room)
                self.assertEqual(chat.composer.toPlainText(), '')
                chat.backend.busy = False; window.spaces.open_room(room)
                self.assertEqual(chat.composer.toPlainText(), 'Ungesendeter Entwurf')
                self.assertEqual(chat.paths, ['smb://nas/Other/keep.txt'])
                chat.composer.setPlainText('Geänderter Entwurf')
                window.spaces.open_room(room)
                self.assertEqual(chat.composer.toPlainText(), 'Geänderter Entwurf')
                catalog.save_room(room, 'Anderes Fenster', room['state'])
                with patch('file_spaces_ui.QInputDialog.getText', return_value=('Meine Kopie', True)):
                    window.spaces.new_room()
                self.assertNotEqual(window.spaces.active_room['id'], room['id'])
                self.assertEqual(window.spaces.active_room['state']['chat']['draft'], 'Geänderter Entwurf')
                send.assert_not_called()
                window.close(); window.deleteLater(); QTest.qWait(30)
