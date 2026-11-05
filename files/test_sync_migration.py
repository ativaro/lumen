"""Saved sync identities and pending work never become a new global selector."""
from copy import deepcopy
import unittest
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def resume_fixture(self, path, payload=b'original'):
        digest=hashlib.sha256(payload).hexdigest()
        pending=dict(request_id=str(uuid4()),staged='outgoing',hash=digest,legacy_upload_target=str(uuid4()))
        root=dict(path=str(path),identity=[path.stat().st_dev,path.stat().st_ino],entries={'old':dict(pending=pending)})
        key=str(uuid4());body=dict(name='original.txt',size=len(payload),sha256=digest,workspace=pending['legacy_upload_target'])
        item=dict(request_id=pending['request_id'],body=body)
        proposal=dict(plan=dict(uploads=[item]),preview=dict(fingerprint='a'*64,
            uploads=[dict(id=key,request_id=pending['request_id'],state='uploading')]))
        (path/'outgoing').write_bytes(payload)
        return root,proposal,item,key,digest

    def test_migration_controller_uses_only_explicit_approval_and_existing_transfer(self):
        import drive_binding_migration as binding
        with TemporaryDirectory() as tmp:
            path=Path(tmp);root,proposal,item,key,digest=self.resume_fixture(path)
            before=deepcopy((root,proposal))
            with patch.object(drive,'locked'),patch.object(binding,'load',return_value=({}, {}, root)), \
                 patch.object(binding,'check_preview') as check,patch.object(binding,'pending',return_value=[item]), \
                 patch.object(binding.transport,'upload') as upload,patch.object(drive,'save') as save, \
                 patch.object(drive,'request',return_value=dict(upload=dict(id=key,offset=2,size=8))) as approve, \
                 patch.object(binding.transport,'request',side_effect=[dict(id=key,offset=8),dict(id=key,sha256=digest)]) as wire:
                self.assertTrue(binding.finish_uploads('old',proposal))
                check.assert_called_once_with(root,proposal)
                approve.assert_called_once_with({},'/migrations/uploads/'+key+'/resume',
                    dict(plan=proposal['plan'],fingerprint='a'*64))
                self.assertEqual(wire.call_args_list[0].args,({},'/uploads/'+key+'?offset=2',b'iginal','PUT','application/octet-stream'))
                self.assertEqual(wire.call_args_list[1].args,({},'/uploads/'+key+'/finish'))
                upload.assert_not_called();save.assert_not_called()
            self.assertEqual((root,proposal),before)
            self.assertEqual((path/'outgoing').read_bytes(),b'original')

    def test_explicit_resume_rejection_never_falls_back_to_normal_upload(self):
        import drive_binding_migration as binding
        with TemporaryDirectory() as tmp:
            root,proposal,item,key,digest=self.resume_fixture(Path(tmp))
            with patch.object(drive,'locked'),patch.object(binding,'load',return_value=({}, {}, root)), \
                 patch.object(binding,'check_preview'),patch.object(binding,'pending',return_value=[item]), \
                 patch.object(drive,'request',side_effect=ValueError('stale approval')), \
                 patch.object(binding.transport,'request') as wire,patch.object(binding.transport,'upload') as upload:
                with self.assertRaisesRegex(ValueError,'stale approval'):binding.finish_uploads('old',proposal)
                wire.assert_not_called();upload.assert_not_called()

    def test_explicit_resume_rechecks_original_bytes_before_any_chunk(self):
        import drive_binding_migration as binding
        with TemporaryDirectory() as tmp:
            path=Path(tmp);root,proposal,item,key,digest=self.resume_fixture(path)
            (path/'outgoing').write_bytes(b'changed!')
            with patch.object(drive,'locked'),patch.object(binding,'load',return_value=({}, {}, root)), \
                 patch.object(binding,'check_preview'),patch.object(binding,'pending',return_value=[item]), \
                 patch.object(drive,'request',return_value=dict(upload=dict(id=key,offset=2,size=8))), \
                 patch.object(binding.transport,'request') as wire:
                with self.assertRaisesRegex(ValueError,'Originalübertragung'):binding.finish_uploads('old',proposal)
                wire.assert_not_called()
            self.assertEqual((path/'outgoing').read_bytes(),b'changed!')

    def test_confirmed_migration_releases_only_reviewed_pending_target(self):
        import drive_binding_migration as binding
        old,request,folder=[str(uuid4()) for _ in range(3)]
        intent=dict(request_id=request,hash='a'*64,path='original.txt',staged='original-stage',folder=None,
                    previous=None,legacy_upload_target=old)
        root=dict(workspace=old,entries={'old':dict(pending=intent,legacy_upload_target=old)},
                  cache=dict(files={},folders={}),migration=dict(id=str(uuid4())))
        state=dict(scope='same-user-origin-device',roots=[root])
        result=dict(files=[],folders=[],folder=dict(id=folder),uploads=[dict(request_id=request,state='not_started',
            next_body=dict(folder=folder,sha256='a'*64,name='original.txt'))])
        with patch.object(binding,'check_preview'),patch.object(binding.lumen_connect,'read_config',return_value={}), \
             patch.object(drive,'scope',return_value=state['scope']),patch.object(binding,'durable_save') as save:
            current=binding.finalize(state,root,result)
            save.assert_called_once_with(state)
        kept=current['entries']['old']['pending']
        self.assertEqual((kept['request_id'],kept['hash'],kept['staged']),(request,'a'*64,'original-stage'))
        self.assertEqual(kept['folder'],folder)
        self.assertNotIn('workspace',current)
        self.assertFalse(migration.pending_drive_uploads(current))
        self.assertIn('workspace',root)  # The separate original/journal is not rewritten.

    def test_unconfirmed_legacy_next_body_cannot_clear_the_pending_stop(self):
        import drive_binding_migration as binding
        old,request,folder=[str(uuid4()) for _ in range(3)]
        root=dict(workspace=old,entries={'old':dict(pending=dict(request_id=request,hash='a'*64,path='original.txt',
            staged='original-stage',folder=None,previous=None,legacy_upload_target=old))},
            cache=dict(files={},folders={}),migration=dict(id=str(uuid4())))
        state=dict(scope='same',roots=[root]);before=deepcopy(state)
        result=dict(files=[],folders=[],folder=dict(id=folder),uploads=[dict(request_id=request,state='not_started',
            next_body=dict(folder=folder,sha256='a'*64,name='original.txt',workspace=old))])
        with patch.object(binding,'check_preview'),patch.object(binding.lumen_connect,'read_config',return_value={}), \
             patch.object(drive,'scope',return_value='same'),patch.object(binding,'durable_save') as save:
            with self.assertRaisesRegex(ValueError,'eindeutige'):binding.finalize(state,root,result)
            save.assert_not_called()
        self.assertEqual(state,before)



if __name__=='__main__':unittest.main()
