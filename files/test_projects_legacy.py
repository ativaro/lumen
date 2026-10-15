import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from file_spaces import Catalog
from lumen_store import Store
from projects_legacy import migrate
from tools_data import Library


class LegacyProjectsTest(unittest.TestCase):
    def test_idempotent_reference_migration_keeps_originals_and_user_edits(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root)/'state'); library = Library('workbench', Path(root)/'tools')
            original = Path(root)/'original.txt'; original.write_text('never copied')
            room = dict(id='legacy-room', name='Existing collection', note='Keep note',
                sources=[dict(label='Original', location=str(original))], urls=['https://example.org'],
                pins=[dict(kind='task', id='a'*32, title='Saved task')],
                state=dict(tabs=[str(original), 'smb://offline.invalid/share'], shelf=[str(original)],
                    tasks=['a'*32, 'b'*32], chat=dict(directory=root+'/', session='ses_example', draft='Do not send')))
            catalog = Catalog(store); catalog.put('room', room)
            catalog.use_room_shelf(room['id'], [])
            catalog.add_shelf([str(Path(root)/'latest-shelf.txt')])
            with patch('tools_data.Library.import_file', side_effect=AssertionError('No file copy')):
                first = migrate(library, store); self.assertEqual(len(first), 1)
                record = library.get(first[0]); self.assertEqual(record['notes'], 'Keep note\n\nÜbernommener Gesprächsentwurf (nicht gesendet):\nDo not send')
                self.assertEqual([r['target'] for r in record['resources']].count(str(original)), 1)
                self.assertIn('smb://offline.invalid/share', [r['target'] for r in record['resources']])
                self.assertEqual(len(record['references']), 3)
                self.assertEqual(next(r['chat']['directory'] for r in record['references'] if r['kind']=='chat'),root)
                self.assertIn(str(Path(root)/'latest-shelf.txt'), [r['target'] for r in record['resources']])
                self.assertEqual(record['legacy_room'], room); self.assertEqual(catalog.rooms(), [room])
                library.update(first[0], title='Edited', notes='User edit')
                self.assertEqual(migrate(library, store), [])
                self.assertEqual(library.get(first[0])['notes'], 'User edit')
                library.archive(first[0]); self.assertEqual(migrate(library, store), [])
                self.assertTrue(library.get(first[0])['_archived'])
                self.assertEqual(original.read_text(), 'never copied')
                self.assertFalse(list(library.assets.iterdir()))

    def test_automatic_previous_window_is_not_a_project(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'state'); library=Library('workbench',Path(root)/'tools')
            Catalog(store).put('room',dict(id='previous',name='Previous',state={}))
            self.assertEqual(migrate(library,store),[])
            self.assertEqual(len(Catalog(store).rooms()),1)
