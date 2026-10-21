import unittest
import tempfile
import hashlib
import os
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import drive_references as drive
from interop_data import validate_payload, validate_ref


class DriveReferencesTest(unittest.TestCase):
    def setUp(self):
        self.ref = dict(app='files', kind='drive_file', id=str(uuid4()), title='Original.txt',
                        locator=dict(server='https://staging.invalid', account=str(uuid4())))
        self.config = dict(server='https://staging.invalid', token='private-device-token')
        self.row = dict(id=str(uuid4()), family=self.ref['id'], name='Renamed.txt', trashed=False, revision=7, size=5, sha256=hashlib.sha256(b'hello').hexdigest())

    def test_inventory_cancel_at_each_response_prevents_another_http_step(self):
        from lumen_jobs import Job
        from tools_data import Cancelled
        for stage in ('before','page','last_page','changes'):
            with self.subTest(stage=stage):
                job=Job(lambda _:None);calls=[]
                if stage=='before':job.cancelled.set()
                def wire(config,path,body=None):
                    calls.append(path)
                    if path=='/inventory':
                        if stage in ('page','last_page'):job.cancelled.set()
                        return dict(items=[],folders=[],cursor='1',next='second' if stage=='page' else None)
                    job.cancelled.set()
                    return dict(items=[],folders=[],cursor='2',more=True)
                with patch.object(drive.sync,'request',side_effect=wire),self.assertRaises(Cancelled):
                    drive.sync.inventory(self.config,job=job)
                expected=[] if stage=='before' else ['/inventory']
                if stage=='changes':expected.append('/changes?cursor=1')
                self.assertEqual(calls,expected)

    def test_refresh_cancel_before_or_after_response_performs_no_next_io(self):
        from lumen_jobs import Job
        from tools_data import Cancelled
        for cancelled_before in (False,True):
            with self.subTest(cancelled_before=cancelled_before):
                job=Job(lambda _:None);calls=[]
                if cancelled_before:job.cancelled.set()
                def wire(config,path,body=None):
                    calls.append(path);job.cancelled.set()
                    return dict(items=[],folders=[],cursor='2',more=True)
                with patch.object(drive.sync,'request',side_effect=wire),self.assertRaises(Cancelled):
                    drive.sync.refresh(self.config,dict(files={},folders={},cursor='1'),job=job)
                self.assertEqual(calls,[] if cancelled_before else ['/changes?cursor=1'])

    def test_resolve_forwards_same_job_and_stops_after_cancelled_native_me(self):
        from lumen_jobs import Job
        from tools_data import Cancelled
        job=Job(lambda _:None);cache=dict(files={self.ref['id']:self.row},folders={})
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config), \
             patch.object(drive.lumen_connect,'request',return_value=dict(id=self.ref['locator']['account'])) as me, \
             patch.object(drive.sync,'inventory',return_value=cache) as inventory:
            self.assertEqual(drive.resolve([self.ref],job),(self.config,[self.row]))
            inventory.assert_called_once_with(self.config,job=job);inventory.reset_mock()
            def cancelled(*args):
                job.cancelled.set();return dict(id=self.ref['locator']['account'])
            me.side_effect=cancelled
            with self.assertRaises(Cancelled):drive.resolve([self.ref],job)
            inventory.assert_not_called()

    def test_reference_and_payload_keep_identity_without_local_path_or_credentials(self):
        self.assertEqual(validate_ref(self.ref), self.ref)
        payload = dict(title='Selection', source=self.ref, paths=[], references=[self.ref])
        self.assertEqual(validate_payload(payload), payload)
        for extra in ({'path':'/tmp/fake'}, {'token':'secret'}):
            with self.assertRaises(ValueError): validate_ref(dict(self.ref, **extra))
        for server in ('http://staging.invalid','https://user:secret@staging.invalid','https://staging.invalid/bridge/files','https://staging.invalid?token=secret'):
            with self.assertRaises(ValueError): validate_ref(dict(self.ref, locator=dict(self.ref['locator'],server=server)))

    def test_resolve_current_revision_and_allow_same_account_token_rotation(self):
        cache=dict(files={self.ref['id']:self.row}, folders={})
        with patch.object(drive.lumen_connect,'read_config',return_value=dict(self.config,token='rotated')), patch.object(drive.lumen_connect,'request',return_value=dict(id=self.ref['locator']['account'])), patch.object(drive.sync,'inventory',return_value=cache):
            config, rows=drive.resolve([self.ref])
            self.assertEqual(rows,[self.row]);self.assertEqual(config['token'],'rotated')

    def test_wrong_origin_user_revocation_and_account_change_fail_closed(self):
        cache=dict(files={self.ref['id']:self.row},folders={})
        with patch.object(drive.lumen_connect,'read_config',return_value=self.config) as config, patch.object(drive.lumen_connect,'request',return_value=dict(id=self.ref['locator']['account'])) as request, patch.object(drive.sync,'inventory',return_value=cache) as inventory:
            config.return_value=dict(self.config,server='https://other.invalid')
            with self.assertRaises(ValueError):drive.resolve([self.ref])

            request.assert_not_called()
            config.return_value=self.config;request.return_value=dict(id=str(uuid4()))
            with self.assertRaises(ValueError):drive.resolve([self.ref])
            inventory.assert_not_called()
            request.return_value=dict(id=self.ref['locator']['account']);inventory.return_value=dict(files={},folders={})
            with self.assertRaises(ValueError):drive.resolve([self.ref])
            inventory.return_value=cache;config.side_effect=[self.config,dict(self.config,token='different')]
            with self.assertRaises(ValueError):drive.resolve([self.ref])

    def test_project_and_note_preserve_every_original_without_downloading(self):
        from interop_data import Registry
        from interop_targets import apply
        from lumen_store import Store
        from tools_data import Library
        from tools_ui import Job
        import wissen_data
        folder=dict(self.ref,kind='drive_folder',id=str(uuid4()),title='Folder')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'tools';store=Store(Path(tmp)/'state');wissen_data.activate(store)
            refs=[self.ref,folder];registry=Registry(root)
            payload=dict(title='Selection',paths=[],references=refs,source=self.ref,source_url=registry.register(self.ref))
            job=Job(lambda _:None)
            with patch.object(drive,'resolve',return_value=(self.config,[])), patch('drive_transport.download',side_effect=AssertionError('No downloads for links')):
                project=apply('workbench.add',payload,dict(title='Project',mode='link',token='project'),job,root,store)
                resources=Library('workbench',root).get(project['id'])['resources']
                self.assertEqual([registry.resolve(r['target']) for r in resources],refs)
                note=apply('wissen.import',payload,dict(title='Note',mode='link',token='note'),job,root,store)
                text=wissen_data.Notebook(store).read(note['id'])['text']
                for ref in refs:self.assertIn(registry.register(ref),text)

    def test_bounded_copy_cleanup_on_success_cancel_and_changed_version(self):
        from tools_data import Cancelled
        job=SimpleNamespace(check=lambda:None)
        def download(config,root,row,progress):
            Path(root['path'],'stage').write_bytes(b'hello');progress(5,5);return 'stage'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,XDG_CACHE_HOME=tmp), patch.object(drive,'resolve',return_value=(self.config,[self.row])) as resolve, patch('drive_transport.download',side_effect=download) as fetch:
            with drive.materialized([self.ref],job) as paths:
                self.assertEqual(Path(paths[0]).read_bytes(),b'hello')
            self.assertFalse(Path(paths[0]).exists())
            job.check=lambda:(_ for _ in ()).throw(Cancelled())
            with self.assertRaises(Cancelled), drive.materialized([self.ref],job):pass
            self.assertFalse(list(Path(tmp).glob('lumen-drive-handoffs/copy-*')))
            job.check=lambda:None
            def interrupted(config,root,row,progress):
                Path(root['path'],'partial').write_bytes(b'he')
                job.check=lambda:(_ for _ in ()).throw(Cancelled())
                progress(2,5)
            fetch.side_effect=interrupted
            with self.assertRaises(Cancelled),drive.materialized([self.ref],job):pass
            self.assertFalse(list(Path(tmp).glob('lumen-drive-handoffs/copy-*')))
            job.check=lambda:None;fetch.side_effect=download
            resolve.side_effect=[(self.config,[self.row]),(self.config,[dict(self.row,revision=8)])]
            with self.assertRaises(ValueError),drive.materialized([self.ref],job):pass
            self.assertFalse(list(Path(tmp).glob('lumen-drive-handoffs/copy-*')))
            resolve.side_effect=None;resolve.return_value=(self.config,[dict(self.row,size=drive.MAX_COPY+1)])
            fetch.reset_mock()
            with self.assertRaises(ValueError),drive.materialized([self.ref],job):pass
            fetch.assert_not_called()

    def test_reader_and_translate_copy_only_on_apply_keep_origin_and_replay(self):
        from interop_data import Registry
        from interop_targets import apply,available
        from tools_data import Library
        from tools_ui import Job
        def download(config,root,row,progress):
            Path(root['path'],'stage').write_bytes(b'hello');return 'stage'
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,XDG_CACHE_HOME=tmp+'/cache'),patch.object(drive,'resolve',return_value=(self.config,[self.row])),patch('drive_transport.download',side_effect=download) as fetch,patch('reader_data.worker',return_value=dict(pages=1)):
            root=Path(tmp)/'tools';registry=Registry(root);url=registry.register(self.ref)
            payload=dict(title='Original',source=self.ref,source_url=url,paths=[],references=[self.ref])
            self.assertIn('reader.import',available(payload));fetch.assert_not_called()
            job=Job(lambda _:None)
            for action in ('reader.import','translate.import'):
                choice=dict(title='Copy',mode='copy',token=action)
                result=apply(action,payload,choice,job,root)
                calls=fetch.call_count
                self.assertEqual(result,apply(action,payload,choice,job,root));self.assertEqual(fetch.call_count,calls)
                library=Library(result['app'],root);record=library.get(result['id'])
                self.assertIn(url,record['interop_sources'])
                self.assertNotIn('original_path',record)
                if action=='reader.import':self.assertEqual(library.asset(record['asset']).read_bytes(),b'hello')
                else:self.assertEqual(record['source'],'hello')
            self.assertFalse(list(Path(tmp+'/cache/lumen-drive-handoffs').glob('copy-*')))



if __name__ == '__main__':unittest.main()
