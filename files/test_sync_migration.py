"""Saved sync identities and pending work never become a new global selector."""
from copy import deepcopy
import unittest
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
        before = deepcopy(root['entries'])
        saved = []
        with patch.object(drive, 'request') as request:
            with self.assertRaises(ValueError):drive.reconcile({}, root, lambda:saved.append(True), lambda *_:None)
            request.assert_not_called()
        self.assertFalse(root['enabled'])
        self.assertTrue(saved)
        self.assertEqual(root['entries']['pending']['pending']['staged'], 'outgoing')
        self.assertEqual(root['entries'], before)

    def test_folder_binding_freezes_only_existing_upload_metadata(self):
        old = str(uuid4())
        root = dict(workspace=old, folder=str(uuid4()), entries={'old':dict(pending=dict(request_id='known'))})
        migration.migrate_drive_binding(root)
        self.assertEqual(migration.drive_path('/inventory', root), '/inventory')
        self.assertEqual(root['entries']['old']['pending']['legacy_upload_target'], old)
        self.assertFalse(migration.pending_drive_uploads(dict(root,entries={'new':dict(pending=dict(request_id='new'))})))
        with self.assertRaises(ValueError):migration.require_current_upload(old)
        migration.require_current_upload(None)

    def test_folder_binding_pending_legacy_upload_stops_without_rebinding(self):
        for migrated in (False, True):
            pending = dict(request_id=str(uuid4()), staged='outgoing', legacy_upload_target=str(uuid4()))
            root = dict(workspace=pending['legacy_upload_target'], folder=str(uuid4()), enabled=True,
                        account_sync_migrated=migrated, entries={'old':dict(pending=pending)})
            before = deepcopy(root)
            with patch.object(drive, 'request') as network,patch.object(drive.local,'directory') as local:
                with self.assertRaisesRegex(ValueError,'Vorschau'):drive.reconcile({},root,lambda:None,lambda *_:None)
            network.assert_not_called();local.assert_not_called()
            self.assertFalse(root['enabled']);before['enabled']=False
            self.assertEqual(root,before)

    def test_removed_notes_migration_cannot_recreate_an_old_scope_or_request(self):
        for name in ('note_target','note_scope_parts','pending_notes','note_request','asset_target','asset_path'):
            self.assertFalse(hasattr(migration,name),name)

    def test_concrete_binding_without_old_uploads_never_labels_future_requests_as_legacy(self):
        root=dict(workspace=str(uuid4()),folder=str(uuid4()),enabled=True,entries={})
        with patch.object(drive.local,'directory',side_effect=RuntimeError('file-boundary')),patch.object(drive,'request') as network:
            with self.assertRaisesRegex(RuntimeError,'file-boundary'):drive.reconcile({},root,lambda:None,lambda *_:None)
        network.assert_not_called()
        self.assertTrue(root['account_sync_migrated'])
        root['entries']['new']=dict(pending=dict(request_id=str(uuid4()),staged='new-outgoing'))
        self.assertFalse(migration.pending_drive_uploads(root))

    def test_migration_controller_never_replays_an_upload_through_normal_transport(self):
        import drive_binding_migration as binding
        pending = dict(request_id=str(uuid4()),staged='outgoing',legacy_upload_target=str(uuid4()))
        root = dict(entries={'old':dict(pending=pending)})
        proposal = dict(preview=dict(uploads=[dict(request_id=pending['request_id'],state='uploading')]))
        before=deepcopy((root,proposal))
        with patch.object(drive,'locked'),patch.object(binding,'load',return_value=({}, {}, root)), \
             patch.object(binding,'check_preview') as check,patch.object(binding.transport,'upload') as upload, \
             patch.object(drive,'request') as network,patch.object(drive,'save') as save:
            with self.assertRaisesRegex(ValueError,'bestätigte Fortsetzung'):binding.finish_uploads('old',proposal)
            check.assert_called_once_with(root,proposal)
            upload.assert_not_called();network.assert_not_called();save.assert_not_called()
        self.assertEqual((root,proposal),before)



if __name__=='__main__':unittest.main()
