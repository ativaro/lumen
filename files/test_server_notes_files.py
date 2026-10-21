"""Normal local-file Notes action: real Qt review and durable existing copy adapters."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID,uuid4

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QComboBox,QDialog,QLineEdit,QMessageBox,QWidget
from interop_data import Registry
from interop_sources import from_paths
from server_app_session import AppSession,Binding
from server_notes_handoffs import Requests
import server_notes_files as files
import test_server_file_import as fixture


class LocalNotesTest(unittest.TestCase):
    def wire(self,*args,**kwargs):
        self.assertNotEqual(threading.get_ident(),self.gui_thread)
        return fixture.FileImportTest.wire(self,*args,**kwargs)

    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.gui_thread=threading.get_ident();fixture.FileImportTest.setUp(self)
        self.config['device_id']=self.device;self.revision=7;self.capabilities=['notes','drive']
        self.folder_row['parent_id']=None
        self.env=patch.dict(os.environ,LUMEN_TOOLS_DATA=str(self.base/'tools'));self.env.start();self.addCleanup(self.env.stop)
        self.path=self.base/'Selected.md';self.original=b'# Original\n\ntest\n\n\n\ntest1\n';self.path.write_bytes(self.original)
        payload=from_paths([str(self.path)]);payload['source_url']=self.registry.register(payload['source'])
        self.parent=self.registry.enqueue('wissen','wissen.import',payload)
        self.binding=Binding(self.config['server'],self.account,self.device,'notes')
        self.session=AppSession(self.config,self.binding);self.session._cookie=b'x'*43
        self.session._deadline=self.session._clock()+600;self.session.state='ready';self.session.access='read_write'
        self.window=QWidget();self.window.session=self.session;self.window._binding=self.binding
        self.window._pilot_connection=('own',);self.window._generation=0;self.window._disposed=False;self.window._closing=False
        self.window._import_running=False;self.window._import_close=False;self.window._pilot_current=lambda:True
        self.window.block=lambda reason:None;self.addCleanup(self.window.deleteLater)
        self.notes={};self.operations={};self.posts=[];self.downloads=0;self.session.request=self.note_wire
        self.note_uncertain=False;self.download_source_changed=False
        self.review_count=0;self.cancel_drive_index=0;self.cancel_note=False;self.retry_notes=True
        self.requests=Requests(self.window)
        self.timer=QTimer();self.timer.setInterval(5);self.timer.timeout.connect(self.answer);self.timer.start();self.addCleanup(self.timer.stop)
        for active in (patch('server_notes_app.context',side_effect=lambda job:(dict(self.config),self.binding,('own',),self.revision)),
            patch.object(AppSession,'check',return_value=True),patch.object(AppSession,'connect',side_effect=AssertionError('Existing window session only')),
            patch('drive_references.materialized',side_effect=self.materialized)):
            active.start();self.addCleanup(active.stop)

    def profile(self,config,path,body=None,**kwargs):
        self.assertNotEqual(threading.get_ident(),self.gui_thread)
        self.assertEqual(path,'/bridge/me')
        return dict(id=self.account,device_id=self.device,permissions_revision=self.revision,capabilities=list(self.capabilities))

    def note_wire(self,path,body=None,**kwargs):
        self.assertNotEqual(threading.get_ident(),self.gui_thread)
        if path=='/api/note-collections':return []
        if body is not None:
            self.posts.append(json.loads(json.dumps(body)))
            token=UUID(body['operation_id']).hex
            self.assertTrue(self.registry.request(token)['choice']['note_capture']['attempted'])
            if body['operation_id'] in self.operations:
                row=self.notes[self.operations[body['operation_id']]];self.assertEqual(row['body'],body['body'])
            else:
                row=dict(body,id=str(uuid4()),revision=1,deleted=False,can_write=True)
                self.notes[row['id']]=row;self.operations[body['operation_id']]=row['id']
            if self.note_uncertain:self.note_uncertain=False;raise TimeoutError('Lost note response')
            return dict(row)
        return dict(self.notes[path.rsplit('/',1)[-1]])

    @contextmanager
    def materialized(self,refs,job):
        self.downloads+=1;paths=[]
        for ref in refs:
            row=self.cache['files'][ref['id']]
            value=next(value for value in self.sessions.values() if value.get('row',{}).get('id')==row['id'])
            path=self.base/('download-'+row['id']+'.txt');path.write_bytes(value['data']);paths.append(str(path))
        if self.download_source_changed:self.path.write_text('Original changed after its confirmed copy')
        yield paths
        for path in paths:Path(path).unlink()

    def answer(self):
        dialog=QApplication.activeModalWidget()
        if not isinstance(dialog,QDialog) or dialog.property('fixtureAnswered'):return
        if dialog.windowTitle()=='Lumen Drive · Datei übernehmen':
            dialog.setProperty('fixtureAnswered',True);self.review_count+=1
            if self.cancel_drive_index==self.review_count:dialog.reject();return
            destination=dialog.findChild(QComboBox);destination.setCurrentIndex(destination.findData(self.folder));dialog.accept()
        elif dialog.windowTitle().startswith('Als Notiz speichern'):
            dialog.setProperty('fixtureAnswered',True)
            if self.cancel_note:dialog.reject();return
            dialog.findChild(QLineEdit).setText('From selected files');dialog.accept()
        elif isinstance(dialog,QMessageBox) and dialog.windowTitle()=='Lumen Drive · Übernahme prüfen':
            dialog.setProperty('fixtureAnswered',True);dialog.done(QMessageBox.Yes)
        elif isinstance(dialog,QMessageBox) and dialog.windowTitle()=='Lumen Notes':
            dialog.setProperty('fixtureAnswered',True);dialog.button(QMessageBox.Yes if self.retry_notes else QMessageBox.Cancel).click()

    def receive(self):return self.requests.receive(self.parent)

    def plan(self):return self.registry.request(self.parent)['choice']['note_files']

    def test_local_file_copy_review_then_editable_private_note_and_stable_return(self):
        result=self.receive();self.assertEqual(result['app'],'note');self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.posts),1)
        note=self.notes[result['id']]
        self.assertIn(self.original.decode(),note['body']);self.assertIn('/?app=files&file=',note['body'])
        self.assertFalse(note['ai_allowed']);self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(self.registry.request(self.parent)['state'],'done')
        self.assertEqual(self.registry.resolve(self.registry.request(self.parent)['result']),result)
        self.assertNotIn(self.config['token'],json.dumps(self.plan()))
        self.assertEqual(self.window._import_running,False)

    def test_drive_cancel_preserves_source_and_reuses_child_ids_without_upload(self):
        self.cancel_drive_index=1;self.assertIsNone(self.receive());plan=self.plan()
        self.assertEqual(self.calls,[]);self.assertEqual(self.posts,[]);self.assertEqual(self.path.read_bytes(),self.original)
        self.cancel_drive_index=0;result=self.receive()
        self.assertEqual(self.plan()['children'],plan['children']);self.assertEqual(self.plan()['note_token'],plan['note_token']);self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.notes),1)
        self.assertEqual(result['app'],'note')

    def test_note_cancel_keeps_confirmed_copy_and_resumes_without_second_upload_or_download(self):
        self.cancel_note=True;self.assertIsNone(self.receive());self.assertEqual(len(self.sessions),1);self.assertEqual(self.posts,[])
        self.assertEqual(self.registry.request(self.parent)['state'],'pending');downloads=self.downloads
        self.cancel_note=False;self.receive()
        self.assertEqual(len(self.sessions),1);self.assertEqual(self.downloads,downloads);self.assertEqual(len(self.notes),1)
        self.assertEqual(sum(method=='PUT' for _,method,_ in self.calls),1)

    def test_upload_timeout_resumes_same_operation_without_duplicate_copy(self):
        self.lost_finish=True
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(len(self.sessions),1);self.assertEqual(self.posts,[])
        self.receive();self.assertEqual(len(self.sessions),1);self.assertEqual(len(self.notes),1)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_note_timeout_requires_confirmation_and_same_note_operation(self):
        self.note_uncertain=True
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(len(self.notes),1);self.assertEqual(len(self.sessions),1)
        self.retry_notes=False;self.assertIsNone(self.receive());self.assertEqual(len(self.posts),1)
        self.retry_notes=True;result=self.receive()
        self.assertEqual(result['id'],next(iter(self.notes)));self.assertEqual(len(self.notes),1);self.assertEqual(len(self.sessions),1)
        self.assertEqual(self.posts[0],self.posts[1])

    def test_permissions_do_not_expand_automatically_and_source_stays_intact(self):
        self.capabilities=['notes']
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(self.calls,[]);self.assertEqual(self.posts,[]);self.assertEqual(self.registry.request(self.parent)['choice'],{})
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_pairing_change_during_upload_never_creates_note_or_replays(self):
        self.after_chunk=lambda:self.config.update(token='new-pair-token')
        with self.assertRaises(ValueError):self.receive()
        before=len(self.calls)
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(len(self.calls),before);self.assertEqual(self.posts,[]);self.assertEqual(self.path.read_bytes(),self.original)

    def test_close_fence_during_upload_stops_followups_and_keeps_source(self):
        def close():self.window._import_close=True;self.window._generation+=1
        self.after_chunk=close
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(self.posts,[]);self.assertEqual(self.path.read_bytes(),self.original)
        self.assertFalse(self.window._import_running)

    def test_completed_parent_reopens_without_source_file_or_new_copies(self):
        result=self.receive();self.path.unlink();uploads=len(self.calls);posts=len(self.posts)
        self.assertEqual(self.receive(),result);self.assertEqual(len(self.calls),uploads);self.assertEqual(len(self.posts),posts)

    def test_text_is_from_confirmed_copy_even_if_original_changes_after_upload(self):
        self.download_source_changed=True;result=self.receive()
        self.assertIn(self.original.decode(),self.notes[result['id']]['body'])
        self.assertNotIn('Original changed after',self.notes[result['id']]['body'])
        self.assertEqual(self.path.read_text(),'Original changed after its confirmed copy')

    def test_multiple_files_keep_finished_child_when_later_copy_is_cancelled(self):
        second=self.base/'Second.pdf';second.write_bytes(b'Own synthetic PDF fixture')
        payload=from_paths([str(self.path),str(second)]);payload['source_url']=self.registry.register(payload['source'])
        self.parent=self.registry.enqueue('wissen','wissen.import',payload)
        self.cancel_drive_index=2;self.assertIsNone(self.receive());plan=self.plan()
        self.assertEqual(len(self.sessions),1);self.assertEqual(self.posts,[])
        self.cancel_drive_index=0;result=self.receive()
        self.assertEqual(self.plan()['children'],plan['children']);self.assertEqual(self.plan()['note_token'],plan['note_token']);self.assertEqual(len(self.sessions),2);self.assertEqual(len(self.notes),1)
        self.assertEqual(self.notes[result['id']]['body'].count('/?app=files&file='),2)
        self.assertEqual(self.path.read_bytes(),self.original);self.assertEqual(second.read_bytes(),b'Own synthetic PDF fixture')

    def test_directory_is_refused_without_copy_or_note(self):
        folder=self.base/'Directory';folder.mkdir();payload=from_paths([str(folder)]);payload['source_url']=self.registry.register(payload['source'])
        self.parent=self.registry.enqueue('wissen','wissen.import',payload)
        with self.assertRaises(ValueError):self.receive()
        self.assertEqual(self.calls,[]);self.assertEqual(self.posts,[]);self.assertTrue(folder.is_dir())

    def test_parent_receipt_failure_does_not_duplicate_note_or_copy_on_resume(self):
        complete=files.complete
        with patch.object(files,'complete',side_effect=OSError('Receipt interrupted')):
            with self.assertRaises(ValueError):self.receive()
        self.assertEqual(len(self.notes),1);self.assertEqual(self.registry.request(self.parent)['state'],'pending')
        self.receive();self.assertEqual(len(self.notes),1);self.assertEqual(len(self.sessions),1)

if __name__=='__main__':unittest.main()
