import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lumen_store import Store
from wissen_data import Notebook
import wissen_sync as sync


class NotesSyncTest(unittest.TestCase):
    def test_memory_and_containing_folder_cannot_be_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state');cfg=dict(server='https://test.invalid',token='test')
            for root in (store.directory/'lumen-memory',store.directory,Path(tmp)):
                book=Notebook(store,root,create=True)
                with self.assertRaises(ValueError):sync.settings(book,cfg)

    def test_two_devices_offline_conflicts_replay_delete_and_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            books=[Notebook(Store(Path(tmp)/('state'+str(i))),Path(tmp)/('notes'+str(i)),create=True) for i in range(2)]
            a,b=books;remote={};lost=[True];allowed=[True]
            cfg=dict(server='https://synthetic.invalid',token='synthetic')
            def request(config,path,body=None):
                if path=='/bridge/me':return dict(name='Synthetic user',capabilities=['notes'] if allowed[0] else [])
                if not allowed[0]:raise ValueError('Access denied')
                if path=='/bridge/notes':return dict(items=[dict(r) for r in remote.values()],next=None)
                identity=path.rsplit('/',1)[-1]
                if body is None:return dict(remote[identity])
                row=remote.get(identity);title,text=('','') if body['deleted'] else (body['title'],body['body'])
                if row and (row['title'],row['body'],row['deleted'])==(title,text,body['deleted']):return dict(applied=True,note=dict(row))
                if row and row['revision']!=body['revision']:return dict(applied=False,note=dict(row))
                row=dict(id=identity,title=title,body=text,deleted=body['deleted'],revision=row['revision']+1 if row else 1)
                remote[identity]=row
                if lost[0]:lost[0]=False;raise OSError('Lost response after commit')
                return dict(applied=True,note=dict(row))
            with patch('lumen_connect.read_config',return_value=cfg),patch('lumen_connect.request',side_effect=request):
                for book in books:
                    self.assertFalse(sync.enabled(book));sync.sync_config(book,sync.scope(book,cfg),True)
                first=a.create('One','Original')
                with self.assertRaises(OSError):sync.sync(a)
                self.assertEqual(len(remote),1)
                sync.sync(a);self.assertEqual(len(remote),1)
                identity=a.read(first['path'])['note_id']
                self.assertEqual(remote[identity]['revision'],1)
                sync.sync(b);self.assertIn('Original',b.scan()['notes'][0]['text'])
                # Move keeps the document UUID and does not create another server note.
                os.rename(a.root/first['path'],a.root/'Moved.md');sync.sync(a)
                self.assertEqual(len(remote),1)
                current=a.read('Moved.md');a.write('Moved.md','# One\n\nOffline change',current['hash'])
                remote[identity].update(title='Web title',body='Web edit',revision=2)
                result=sync.sync(a);self.assertEqual(len(result['conflicts']),1)
                self.assertIn('Offline change',a.read(result['conflicts'][0])['text'])
                self.assertIn('Web edit',a.read('Moved.md')['text'])
                sync.sync(a);sync.sync(b);self.assertEqual(len(remote),2)
                self.assertEqual(len(b.scan()['notes']),2)
                # Remote deletion must preserve an independently edited local version.
                current=a.read('Moved.md');a.write('Moved.md','# One\n\nKeep after delete',current['hash'])
                remote[identity].update(title='',body='',deleted=True,revision=3)
                result=sync.sync(a)
                self.assertFalse((a.root/'Moved.md').exists())
                self.assertIn('Keep after delete',a.read(result['conflicts'][0])['text'])
                sync.sync(b)
                self.assertFalse(any(n['note_id']==identity for n in b.scan()['notes']))
                # Revocation preserves every local byte.
                before={str(p):p.read_bytes() for p in a.root.rglob('*.md')};allowed[0]=False
                with self.assertRaises(ValueError):sync.sync(a)
                self.assertEqual(before,{str(p):p.read_bytes() for p in a.root.rglob('*.md')})
                # Changing the paired identity requires fresh opt-in.
                cfg['token']='replacement';self.assertFalse(sync.enabled(a))

    def test_concurrent_local_write_and_symlink_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            book=Notebook(Store(Path(tmp)/'state'),Path(tmp)/'notes',create=True)
            cfg=dict(server='https://test.invalid',token='test');remote={};racing=[False]
            def request(config,path,body=None):
                if path=='/bridge/me':return dict(name='Test',capabilities=['notes'])
                if path=='/bridge/notes':return dict(items=list(remote.values()),next=None)
                identity=path.rsplit('/',1)[-1]
                if body:
                    remote[identity]=dict(id=identity,title=body['title'],body=body['body'],revision=1,deleted=False)
                    return dict(applied=True,note=remote[identity])
                if racing[0]:
                    note=book.scan()['notes'][0];book.write(note['path'],'# Concurrent\n\nDo not lose',note['hash']);racing[0]=False
                return dict(remote[identity])
            with patch('lumen_connect.read_config',return_value=cfg),patch('lumen_connect.request',side_effect=request):
                sync.sync_config(book,sync.scope(book,cfg),True);note=book.create('Test','before');sync.sync(book)
                identity=next(iter(remote));remote[identity].update(body='Remote new',revision=2);racing[0]=True
                with self.assertRaisesRegex(ValueError,'CONFLICT'):sync.sync(book)
                self.assertIn('Do not lose',book.read(note['path'])['text'])
                (book.root/note['path']).unlink();(book.root/note['path']).symlink_to('/etc/hostname')
                with self.assertRaises(OSError):sync.sync(book)
                self.assertFalse(remote[identity]['deleted'])


class SyncDialogTest(unittest.TestCase):
    def test_background_sync_keeps_editor_and_live_draft(self):
        import time
        from threading import Event
        from PySide6.QtWidgets import QApplication
        from tools_wissen import Wissen
        from wissen_sync_ui import synchronize
        app=QApplication.instance() or QApplication([]);release=Event()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools','XDG_CONFIG_HOME':tmp+'/config'}),patch.object(Wissen,'initialize'):
            window=Wissen(tmp+'/tools');window.book=Notebook(window.store,Path(tmp)/'notes',create=True)
            window.poll_timer.stop();window.sync_timer.stop();note=window.book.create('Test','Before');window.show_note(note)
            def remote(*args,**kwargs):
                release.wait(3);window.book.write(note['path'],'# Test\n\nServer change',note['hash'])
                return dict(scan=window.book.scan(),changed=1,conflicts=[])
            try:
                with patch('wissen_sync.enabled',return_value=True),patch('wissen_data.worker',side_effect=remote):
                    synchronize(window);self.assertIsNotNone(window.poller);self.assertTrue(window.editor.isEnabled())
                    window.editor.insertPlainText('Live draft ');window.dirty=True
                    draft=window.document_text();release.set();until=time.monotonic()+5
                    while window.poller and time.monotonic()<until:app.processEvents();time.sleep(.01)
                    self.assertIsNone(window.poller);self.assertTrue(window.conflict)
                    self.assertEqual(window.document_text(),draft)
            finally:
                release.set();window.closing=True;window.close();window.deleteLater();app.processEvents()

    def test_visible_scope_offline_disable_and_no_implicit_activation(self):
        from PySide6.QtWidgets import QApplication,QDialogButtonBox,QCheckBox
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from tools_wissen import Wissen
        from wissen_sync_ui import show_dialog,synchronize
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LUMEN_DATA':tmp+'/state','LUMEN_TOOLS_DATA':tmp+'/tools','XDG_CONFIG_HOME':tmp+'/config'}),patch.object(Wissen,'initialize'):
            window=Wissen(tmp+'/tools');window.book=Notebook(window.store,Path(tmp)/'notes',create=True)
            window.poll_timer.stop();window.sync_timer.stop()
            info=dict(server='https://sync.example',user='Synthetic',scope='scope',enabled=True,allowed=False,reachable=False)
            try:
                with patch.object(window,'action') as action,patch('wissen_sync.enabled',return_value=False):
                    synchronize(window);action.assert_not_called()
                    show_dialog(window,info);app.processEvents()
                    dialog=window.sync_dialog;checkbox=dialog.findChild(QCheckBox)
                    self.assertTrue(checkbox.isEnabled());checkbox.setChecked(False)
                    buttons=dialog.findChild(QDialogButtonBox)
                    QTest.mouseClick(buttons.button(QDialogButtonBox.Save),Qt.LeftButton)
                    action.assert_called_once()
                    self.assertEqual(action.call_args.args[0],'sync_config')
                    self.assertEqual(action.call_args.kwargs,dict(expected='scope',enabled=False))
                window.area='lumen'
                with patch.object(window,'action') as action:
                    synchronize(window);action.assert_not_called()
            finally:
                window.closing=True;window.close();window.deleteLater();app.processEvents()


if __name__=='__main__':unittest.main()

class BackgroundSyncTest(unittest.TestCase):
    def test_requires_optin_and_rejects_new_account_or_replaced_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state');book=Notebook(store,Path(tmp)/'notes',create=True)
            cfg=dict(server='https://test.invalid',token='synthetic')
            self.assertEqual(sync.background(store),dict(enabled=False))
            with patch('lumen_connect.read_config',return_value=cfg),patch('lumen_connect.request',return_value=dict(name='Test',capabilities=['notes'])),patch('wissen_sync.sync',return_value={'enabled':True}) as run:
                sync.sync_config(book,sync.scope(book,cfg),True)
                self.assertTrue(sync.background(store)['enabled']);self.assertEqual(run.call_count,1)
                cfg['token']='another-account'
                with self.assertRaises(ValueError):sync.background(store)
                self.assertEqual(run.call_count,1);cfg['token']='synthetic'
                book.root.rename(book.root.with_name('moved'));book.root.mkdir()
                with self.assertRaises(ValueError):sync.background(store)
                self.assertEqual(run.call_count,1)

class SharedFoldersAndAssetsTest(unittest.TestCase):
    def test_shared_scope_move_recovery_and_immutable_attachments(self):
        import hashlib
        from wissen_sync_assets import prepare,receive
        with tempfile.TemporaryDirectory() as tmp:
            book=Notebook(Store(Path(tmp)/'state'),Path(tmp)/'notes',create=True)
            cfg=dict(server='https://test.invalid',token='synthetic');area='00000000-0000-4000-8000-000000000001'
            def request(config,path,body=None):
                if path=='/bridge/me':return dict(name='Test',capabilities=['notes'])
                if path=='/bridge/note-workspaces':return [dict(id=area,title='Team',private=False,role='editor')]
                raise AssertionError(path)
            with patch('lumen_connect.read_config',return_value=cfg),patch('lumen_connect.request',side_effect=request):
                original=sync.scope(book,cfg)
                sync.sync_config(book,original,True,target_workspace=area)
                self.assertNotEqual(original,sync.scope(book,cfg))
                note=book.create('Title','Body');identity=note['note_id'] or '00000000-0000-4000-8000-000000000002'
                key,state=sync.settings(book,cfg)
                state['pending_move']=dict(id=identity,source=note['path'],target='Team/Nested/Moved.md',hash=note['hash'],text='# Moved\n\nBody',revision=2)
                book.store.set_setting(key,state)
                with patch.object(book,'remove',side_effect=OSError('Interrupted')):
                    with self.assertRaises(OSError):sync.finish_move(book,key,state)
                self.assertTrue((book.root/note['path']).exists())
                sync.finish_move(book,key,state)
                self.assertFalse((book.root/note['path']).exists())
                self.assertEqual(book.read('Team/Nested/Moved.md')['note_id'],identity)
                with self.assertRaises(ValueError):sync.sync_config(book,sync.scope(book,cfg),True,target_workspace='')
                (book.root/'attachments').mkdir();raw=b'synthetic attachment';(book.root/'attachments/a.bin').write_bytes(raw)
                note=book.create('Attached','[file](attachments/a.bin)')
                uploads=[];known=set()
                with patch('wissen_sync_assets.transfer',side_effect=lambda cfg,sha,area,content=None:uploads.append(sha)):
                    note,assets=prepare(book,note,cfg,area,known,lambda x:None)
                    prepare(book,note,cfg,area,known,lambda x:None)
                self.assertEqual(len(uploads),1)
                self.assertEqual(assets[0]['sha256'],hashlib.sha256(raw).hexdigest())
                receive(book,assets,cfg,area)
                # Enabling attachments after text-only sync retrieves canonical links.
                (book.root/assets[0]['path']).unlink()
                with patch('wissen_sync_assets.transfer',return_value=raw):
                    prepare(book,note,cfg,area,known,lambda x:None)
                self.assertEqual((book.root/assets[0]['path']).read_bytes(),raw)
                (book.root/assets[0]['path']).write_bytes(b'Keep local change')
                with self.assertRaises(ValueError):receive(book,assets,cfg,area)
