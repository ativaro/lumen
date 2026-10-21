"""Saved sync identities and pending work never become a new global selector."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import drive_sync as drive
import sync_migration as migration


class MigrationTest(unittest.TestCase):
    def test_resource_urls_keep_ids_but_not_a_global_area(self):
        old, folder, family = [str(uuid4()) for _ in range(3)]
        self.assertEqual(drive.parse_address('lumen-drive://' + old + '/' + folder), ('folder', folder))
        self.assertEqual(drive.parse_address('lumen-drive://' + old + '/file/' + family + '/sample'), ('file', family))
        self.assertEqual(drive.parse_address('lumen-drive://' + old), ('root', None))
        self.assertEqual(drive.parse_address(drive.location(folder)), ('folder', folder))
        self.assertNotIn(old, drive.location(folder))
        for bad in ['https://x', 'lumen-drive:///folder/not-a-uuid', drive.location(folder)+'?workspace='+old]:
            with self.assertRaises(ValueError):drive.parse_address(bad)

    def test_account_inventory_limit_includes_folders_on_last_page(self):
        page=dict(items=[], folders=[dict(id=str(i)) for i in range(100001)], cursor='known', next=None)
        with patch.object(drive, 'request', return_value=page), patch.object(drive, 'refresh') as refresh:
            with self.assertRaises(ValueError):drive.inventory({})
            refresh.assert_not_called()

    def test_whole_area_stops_before_network_and_keeps_pending_bytes(self):
        old = str(uuid4())
        root = dict(workspace=old, folder=None, enabled=True,
                    entries={'pending':dict(pending=dict(request_id=str(uuid4()), staged='outgoing'))})
        saved = []
        with patch.object(drive, 'request') as request:
            with self.assertRaises(ValueError):drive.reconcile({}, root, lambda:saved.append(True), lambda *_:None)
            request.assert_not_called()
        self.assertFalse(root['enabled'])
        self.assertTrue(saved)
        self.assertEqual(root['entries']['pending']['pending']['staged'], 'outgoing')
        self.assertEqual(root['entries']['pending']['pending']['legacy_upload_target'], old)

    def test_folder_binding_freezes_only_existing_upload_metadata(self):
        old = str(uuid4())
        root = dict(workspace=old, folder=str(uuid4()), entries={'old':dict(pending=dict(request_id='known'))})
        migration.migrate_drive_binding(root)
        self.assertEqual(migration.drive_path('/inventory', root), '/inventory')
        self.assertEqual(migration.drive_upload_target(root, root['entries']['old']['pending']), old)
        self.assertIsNone(migration.drive_upload_target(root, dict(request_id='new')))
        self.assertEqual(migration.drive_upload_fields({'name':'new'},None), {'name':'new'})

    def test_only_unsent_legacy_notes_keep_old_target(self):
        from lumen_store import Store
        from wissen_data import Notebook, digest
        with tempfile.TemporaryDirectory() as tmp:
            book=Notebook(Store(Path(tmp)/'state'),Path(tmp)/'notes',create=True)
            old=str(uuid4())
            key='knowledge/sync-workspace/'+digest((str(book.root)+'\0'+str(book.identity)).encode())
            book.store.set_setting(key,old)
            book.create('Unsent','Preserve')
            state={'notes':{}}
            scanned=migration.pending_notes(book,state,book.scan())
            identity=scanned['notes'][0]['note_id']
            self.assertEqual(state['legacy_note_targets'],{identity:old})
            self.assertEqual(book.scan()['notes'][0]['note_id'],identity)
            book.create('New','Personal')
            migration.pending_notes(book,state,book.scan())
            self.assertEqual(state['legacy_note_targets'],{identity:old})



if __name__=='__main__':unittest.main()
