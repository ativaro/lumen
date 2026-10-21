"""Synthetic Audio records: exact sources, current pairing, and reviewed Drive copies."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from interop_data import Registry
import lumen_connect
from server_app_session import AppSession,Binding
import server_audio_capture as audio


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()));self.registry=Registry(self.root/'tools')
        self.config=dict(server='https://fixture.invalid',device_id=str(uuid4()),token='private-synthetic')
        self.binding=Binding(self.config['server'],str(uuid4()),self.config['device_id'],'audio');self.revision=6
        self.job=SimpleNamespace(check=lambda:None);self.session=AppSession(self.config,self.binding)
        self.session._cookie=b'x'*43;self.session._deadline=self.session._clock()+600;self.session.state='ready';self.session.access='read_write';self.session.request=self.request
        self.source=dict(app='files',kind='file',id='/fixture/source.txt',title='Selected original',path='/fixture/source.txt')
        self.payload=dict(title='Selected text',text='test\n\n\n\ntest1',paths=[],source=self.source,source_url=self.registry.register(self.source))
        self.token=self.registry.enqueue('radio','radio.add',self.payload)
        self.choice=dict(id='',title='Übernommene Auswahl',token=self.token,mode='copy',due='')
        self.posts=[];self.records={};self.lost=False;self.after_post=lambda:None;self.areas=['media','tasks','drive']
        self.enterContext(patch.object(lumen_connect,'read_config',side_effect=lambda:dict(self.config)))
        self.enterContext(patch.object(lumen_connect,'request',side_effect=lambda *args,**kwargs:dict(id=self.binding.account,device_id=self.binding.device,permissions_revision=self.revision,capabilities=self.areas)))

    def request(self,path,body=None,**kwargs):
        if path.startswith('/api/media/records/'):
            return deepcopy(self.records[path.split('/')[-1]])
        self.assertEqual(path,'/api/media/records');self.posts.append(deepcopy(body))
        identity=body['id']
        if identity not in self.records:self.records[identity]=dict(body,revision=1,archived=False)
        self.after_post()
        if self.lost:self.lost=False;raise TimeoutError('Committed reply lost')
        return deepcopy(self.records[identity])

    def capture(self,**kwargs):return audio.capture(self.token,self.choice,self.session,self.revision,self.job,root=self.root/'tools',**kwargs)

    def test_text_record_preserves_blank_lines_and_has_durable_server_return_path(self):
        result=self.capture();self.assertEqual(result['app'],'media');self.assertEqual(result['version'],2)
        self.assertIn(self.payload['text'],self.posts[0]['text']);self.assertIn(self.payload['source_url'],self.posts[0]['text'])
        self.assertEqual(self.posts[0]['mode'],'radio');self.assertEqual(self.posts[0]['attachments'],[])
        self.assertEqual(self.capture(),result);self.assertEqual(len(self.posts),1)
        self.assertEqual(self.registry.request(self.token)['state'],'done')
        self.assertEqual(self.registry.related(self.registry.request(self.token)['result'])[0]['id'],self.source['id'])
        self.assertNotIn(self.config['token'],self.registry.library.db.read_bytes().decode(errors='ignore'))

    def test_agenda_uses_same_record_api_and_never_opens_local_library(self):
        import interop_targets
        self.token=self.registry.enqueue('meetings','meetings.agenda',self.payload);self.choice=dict(self.choice,token=self.token)
        with patch.object(interop_targets,'Library',side_effect=AssertionError('Retired local audio writer')):
            self.assertEqual(interop_targets.choices('meetings.agenda',session=self.session,permissions_revision=self.revision,job=self.job),[])
            result=interop_targets.apply('meetings.agenda',self.payload,self.choice,self.job,root=self.root/'tools',session=self.session,permissions_revision=self.revision)
        self.assertEqual(result['app'],'media');self.assertEqual(self.posts[0]['mode'],'meeting')

    def test_lost_reply_requires_explicit_identical_id_and_source_replay(self):
        self.lost=True
        with self.assertRaises(TimeoutError):self.capture()
        with self.assertRaisesRegex(ValueError,'unklar'):self.capture()
        self.assertEqual(len(self.posts),1);self.capture(retry=True)
        self.assertEqual(self.posts[0],self.posts[1]);self.assertEqual(len(self.records),1)

    def test_changed_pairing_after_commit_never_publishes_wrong_account_receipt(self):
        self.after_post=lambda:self.config.update(token='changed')
        with self.assertRaises(ValueError):self.capture()
        self.assertEqual(self.registry.request(self.token)['state'],'pending');self.assertEqual(len(self.records),1)

    def test_current_grants_and_audio_app_are_required_before_writing(self):
        self.areas=['media']
        with self.assertRaises(ValueError):self.capture()
        self.areas=['media','tasks'];self.session.binding=Binding(self.binding.origin,self.binding.account,self.binding.device,'projects')
        with self.assertRaises(ValueError):self.capture()
        self.assertEqual(self.posts,[])

    def test_existing_drive_files_are_version_pinned_and_foreign_refs_fail(self):
        ref=dict(app='files',kind='drive_file',id=str(uuid4()),title='source.pdf',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.payload=dict(self.payload,references=[ref]);self.token=self.registry.enqueue('radio','radio.add',self.payload);self.choice=dict(self.choice,token=self.token)
        row=dict(id=str(uuid4()),version=3,name='source.pdf')
        with patch('drive_references.resolve',return_value=(self.config,[row])):
            self.lost=True
            with self.assertRaises(TimeoutError):self.capture()
        with patch('drive_references.resolve',return_value=(self.config,[dict(row,version=4)])):
            with self.assertRaisesRegex(ValueError,'geändert'):self.capture(retry=True)
        self.assertEqual(len(self.posts),1)
        foreign=dict(ref,locator=dict(ref['locator'],account=str(uuid4())))
        self.payload=dict(self.payload,references=[foreign]);self.token=self.registry.enqueue('radio','radio.add',self.payload);self.choice=dict(self.choice,token=self.token)
        with self.assertRaises(ValueError):self.capture()

    def test_recording_needs_confirmed_copy_and_keeps_local_original_bytes(self):
        from interop_sources import from_paths
        path=self.root/'original.wav';path.write_bytes(b'Own synthetic audio');before=path.read_bytes()
        self.payload=from_paths([str(path)]);self.payload['source_url']=self.registry.register(self.payload['source'])
        self.token=self.registry.enqueue('meetings','meetings.import',self.payload);self.choice=dict(self.choice,token=self.token)
        with self.assertRaisesRegex(ValueError,'Drive'):self.capture()
        with patch('server_file_import.apply',side_effect=AssertionError('No automatic upload')):
            plan=audio.begin_files(self.token,self.session,self.revision,self.job,root=self.root/'tools')
        with self.assertRaisesRegex(ValueError,'Dateikopie'):self.capture()
        child=plan['children'][0]['token'];ref=dict(app='files',kind='drive_file',id=str(uuid4()),title=path.name,locator=dict(server=self.binding.origin,account=self.binding.account))
        with self.registry.library.connect() as db:db.execute("UPDATE handoffs SET state='done',result=? WHERE id=?",(self.registry.register(ref),child))
        row=dict(id=str(uuid4()),version=2,name=path.name)
        with patch('server_file_import.apply',return_value=dict(reference=ref)),patch('drive_references.resolve',return_value=(self.config,[row])):
            self.capture()
        self.assertEqual(self.posts[0]['recording'],row['id']);self.assertEqual(self.posts[0]['attachments'],[])
        self.assertEqual(path.read_bytes(),before)

    def test_retired_local_audio_writes_and_local_synthesis_fail_closed(self):
        import interop_targets,interop_workflows
        with patch.object(interop_targets,'Library',side_effect=AssertionError('No old writer')),patch('tools_data.synthesize',side_effect=AssertionError('No local voice')):
            for action in audio.ACTIONS:
                with self.assertRaises(ValueError):interop_targets.choices(action)
                payload=self.payload
                if action=='meetings.import':payload=dict(payload,paths=['/fixture/audio.wav'])
                with self.assertRaises(ValueError):interop_targets.apply(action,payload,self.choice,self.job,root=self.root/'tools')
            self.assertFalse(hasattr(interop_workflows,'spoken_status'))

    def test_selected_server_note_uses_current_metadata_and_reference_grant(self):
        note=dict(version=2,app='note',id=str(uuid4()),title='Selected note',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.payload=dict(self.payload,source=note,source_url=self.registry.register(note));self.token=self.registry.enqueue('radio','radio.add',self.payload);self.choice=dict(self.choice,token=self.token)
        metadata=dict(id=note['id'],kind='note',revision=3,mode='reference',supported=True,readable=True)
        original=self.request
        with patch.object(self.session,'request',side_effect=lambda path,*args,**kwargs:metadata if path.startswith('/api/media/sources/') else original(path,*args,**kwargs)):
            self.capture()
        self.assertEqual(self.posts[0]['attachments'],[dict(id=note['id'],kind='note',revision=3,mode='reference')])

    def test_denied_note_never_becomes_an_unqualified_text_copy(self):
        note=dict(version=2,app='note',id=str(uuid4()),title='Selected note',locator=dict(server=self.binding.origin,account=self.binding.account))
        self.payload=dict(self.payload,source=note,source_url=self.registry.register(note));self.token=self.registry.enqueue('radio','radio.add',self.payload);self.choice=dict(self.choice,token=self.token)
        metadata=dict(id=note['id'],kind='note',revision=3,mode='reference',supported=True,readable=False)
        with patch.object(self.session,'request',return_value=metadata):
            with self.assertRaisesRegex(ValueError,'freigegeben'):self.capture()
        self.assertEqual(self.posts,[]);self.assertEqual(self.records,{})


class HostSignalTest(unittest.TestCase):
    def test_recording_uses_real_host_drive_review_https_and_signal_before_record_capture(self):
        # Existing bounded Qt/HTTPS fixture; auth is synthetic, Host/importer are real.
        import os,wave
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication,QDialog
        from test_server_app_window import WindowTest
        WindowTest.setUpClass();self.addCleanup(WindowTest.tearDownClass)
        host=WindowTest('test_import_real_coordinator_https_same_window_and_done_has_no_upload')
        host.setUp();self.addCleanup(host.doCleanups);self.addCleanup(host.tearDown)
        from appearance import apply_design
        apply_design(host.app,'graphite')
        window=host.import_window(app='audio');window.session.access='read_write';WindowTest.native_areas=['media','tasks','drive']
        path=host.import_root/'Own recording.wav'
        with wave.open(str(path),'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0\0'*800)
        original=path.read_bytes();registry=Registry();from interop_sources import from_paths
        payload=from_paths([str(path)]);payload['source_url']=registry.register(payload['source']);token=registry.enqueue('meetings','meetings.import',payload)
        host.import_dialogs(path);timer=QTimer();timer.setInterval(5);self.addCleanup(timer.stop)
        def answer_audio():
            dialog=QApplication.activeModalWidget()
            if isinstance(dialog,QDialog) and dialog.windowTitle()=='Aufnahme in Lumen Audio Studio · Meeting öffnen':
                evidence=os.environ.get('LUMEN_CAPTURE_EVIDENCE')
                if evidence:dialog.grab().save(str(Path(evidence)/'audio-recording-review.png'))
                dialog.accept()
        timer.timeout.connect(answer_audio);timer.start();posts=[];records={};original_request=window.session.request
        def request(route,body=None,**kwargs):
            if route=='/api/media/records':
                posts.append(deepcopy(body));records[body['id']]=dict(body,archived=False,revision=1);return deepcopy(records[body['id']])
            if route.startswith('/api/media/records/'):return deepcopy(records[route.split('/')[-1]])
            return original_request(route,body,**kwargs)
        with patch.object(window.session,'request',side_effect=request):result=audio.receive(window,token)
        self.assertEqual(result['app'],'media');self.assertEqual(len(posts),1);self.assertEqual(len(host.upload_requests),1)
        self.assertEqual(posts[0]['recording'],next(iter(host.uploads.values()))['id'])
        self.assertEqual(next(iter(host.uploads.values()))['data'],original);self.assertEqual(path.read_bytes(),original)
        self.assertEqual(registry.request(token)['state'],'done');self.assertFalse(window._import_running)
        self.assertEqual(set(host.upload_metadata[0]),{'name','size','sha256','folder','replaces','revision','mime'})


class ReviewDesignTest(unittest.TestCase):
    def test_shared_review_uses_all_themes_and_fits_a_narrow_window(self):
        import os
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
        from appearance import apply_design
        from interop_ui import review
        app=QApplication.instance() or QApplication([])
        request=dict(id=uuid4().hex,action='radio.add',payload=dict(title='Ein längerer Titel für eine bestätigte Audioausgabe',text='Ein geprüfter Text\n\nmit erhaltenen Absätzen.',paths=[]))
        spec=dict(label='Lumen Audio Studio',heading='Lumen Audio Studio',modes=['copy'],save_label='In Audio Studio speichern',
            description='Einen neuen Audio-Studio-Eintrag auf dem verbundenen Server speichern. Originale bleiben unverändert.')
        for theme in ('glass','graphite','atelier','midnight'):
            apply_design(app,theme)
            for width in (620,380):
                observed=[];timer=QTimer();timer.setInterval(5)
                def answer():
                    dialog=QApplication.activeModalWidget()
                    if not isinstance(dialog,QDialog) or dialog.windowTitle()!='Lumen Audio Studio':return
                    dialog.resize(width,600);app.processEvents()
                    buttons=dialog.findChild(QDialogButtonBox)
                    observed.append((dialog.width(),all(b.fontMetrics().horizontalAdvance(b.text().replace('&',''))+12<=b.width() for b in buttons.buttons())))
                    evidence=os.environ.get('LUMEN_CAPTURE_EVIDENCE')
                    if evidence:dialog.grab().save(str(Path(evidence)/('audio-review-'+theme+'-'+str(width)+'.png')))
                    timer.stop();dialog.accept()
                timer.timeout.connect(answer);timer.start()
                try:result=review(None,request,spec=spec,rows=[])
                finally:timer.stop()
                self.assertEqual(result['title'],request['payload']['title']);self.assertEqual(observed,[(width,True)])
