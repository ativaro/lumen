"""Real Qt/HTTPS against a local synthetic endpoint, not the Server auth/DB."""
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from PySide6.QtCore import Qt, QUrl, QPoint, QDateTime, QTimer, QThread, QFileSystemWatcher
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QDialog, QLineEdit, QComboBox
import shiboken6

from server_app_session import AppSession, Binding, SessionError
from server_app_window import ServerAppWindow, QWebEnginePage, QWebEngineScript
import lumen_connect

USER='73000000-0000-4000-8000-000000000001'
DEVICE='73000000-0000-4000-8000-000000000002'
FOLDER='73000000-0000-4000-8000-000000000003'
FILE='73000000-0000-4000-8000-000000000004'


class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(os.environ['LUMEN_HOST_TEST_ROOT']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
        cls.temp=tempfile.TemporaryDirectory(dir=root);cls.root=Path(cls.temp.name)
        cls.app=QApplication.instance() or QApplication([])
        cls.cert=cls.root/'ca.pem';cls.wrong_cert=cls.root/'unrelated-ca.pem';key=cls.root/'key.pem'
        for cert,target_key in ((cls.cert,key),(cls.wrong_cert,cls.root/'unrelated-key.pem')):
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=localhost',
                        '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-days','1',
                        '-out',str(cert),'-keyout',str(target_key)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.calls=[];cls.revoked=False;cls.challenge='';cls.hold_write=False
        cls.write_started=threading.Event();cls.release_write=threading.Event()
        cls.upload_started=threading.Event();cls.release_upload=threading.Event()
        cls.inventory_started=threading.Event();cls.release_inventory=threading.Event()
        cls.check_started=threading.Event();cls.release_check=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.handle_request()
            def do_POST(self):self.handle_request()
            def do_PUT(self):self.handle_request()
            def handle_request(self):
                cls.calls.append(dict(path=self.path,method=self.command,bearer=bool(self.headers.get('Authorization')),
                                      cookie=bool(self.headers.get('Cookie')),web='QtWebEngine' in self.headers.get('User-Agent','')))
                raw_body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                body=raw_body if self.command=='PUT' else json.loads(raw_body or b'{}')
                status=200;cookie=False
                if self.path=='/bridge/me':
                    data=dict(id=cls.native_user,device_id=cls.native_device,capabilities=cls.native_areas,
                              permissions_revision=cls.native_revision)
                elif self.path.startswith('/bridge/drive/'):
                    # Mock paired auth only; these routes are not proof of Server RLS.
                    if self.headers.get('Authorization')!='Bearer native-only-fixture' or self.headers.get('Cookie'):
                        status=403;data={}
                    elif self.path=='/bridge/drive/inventory':
                        if cls.hold_inventory:
                            cls.inventory_started.set();cls.release_inventory.wait(timeout=10)
                        data=dict(items=cls.drive_files,folders=[cls.folder],cursor='1',next=None)
                    elif self.path.startswith('/bridge/drive/changes?'):
                        data=dict(items=[],folders=[],cursor='1',more=False)
                    elif self.path.startswith('/bridge/drive/uploads/'):
                        parts=urlsplit(self.path).path.split('/');key=parts[4]
                        if self.command=='POST' and len(parts)==5:
                            cls.upload_requests.append(key);cls.upload_metadata.append(body)
                            if key not in cls.uploads:
                                cls.uploads[key]=dict(id=str(uuid4()),offset=0,size=body['size'],body=body,data=b'')
                            state=cls.uploads[key];data={k:state[k] for k in ('id','offset','size')}
                        else:
                            state=next(value for value in cls.uploads.values() if value['id']==key)
                            if self.command=='PUT':
                                if cls.hold_upload:
                                    cls.upload_started.set();cls.release_upload.wait(timeout=10)
                                state['data']+=body;state['offset']+=len(body);data=dict(offset=state['offset'])
                            elif parts[-1]=='finish':
                                meta=state['body']
                                data=dict(id=state['id'],family=FILE,version=1,revision=1,name=meta['name'],
                                    folder_id=meta['folder'],size=len(state['data']),sha256=hashlib.sha256(state['data']).hexdigest(),
                                    current=True,trashed=False,purpose='user')
                                if not cls.drive_files:cls.drive_files.append(data)
                            else:status=404;data={}
                    else:status=404;data={}
                elif self.path=='/bridge/apps/session-ticket':
                    cls.challenge=body['challenge'];data=dict(ticket='t'*43,expires=(datetime.now(timezone.utc)+timedelta(seconds=29)).isoformat())
                elif self.path=='/api/auth/desktop/exchange':
                    if (body['app']!=cls.app_kind or body['user_id']!=USER or body['device_id']!=DEVICE
                            or hashlib.sha256(body['verifier'].encode()).hexdigest()!=cls.challenge
                            or self.headers.get('Origin')!=cls.origin or self.headers.get('Authorization')):status=403
                    cookie=True;data=dict(user_id=USER,device_id=DEVICE,app=cls.app_kind,access='read',csrf='fixture',
                                          expires=(datetime.now(timezone.utc)+timedelta(seconds=899)).isoformat())
                elif self.path=='/api/me':
                    if cls.hold_check:
                        cls.check_started.set();cls.release_check.wait(timeout=10)
                    status=403 if cls.revoked or 'lumen_session='+'c'*43 not in self.headers.get('Cookie','') else 200
                    data=dict(user=dict(id=USER,device_id=DEVICE,desktop_app=cls.app_kind,device_kind='desktop',
                                        capabilities=['notes' if cls.app_kind=='notes' else 'translate'],admin=False,csrf='fixture'))
                elif self.path=='/api/note-drafts/tags':data=dict(body=body['body'],tags=[])
                elif self.path=='/api/translate':
                    if cls.hold_write:
                        cls.write_started.set();cls.release_write.wait(timeout=10)
                    status=403;data={'detail':'App jobs remain gated.'}
                elif self.path=='/api/ping':data={'cookie':'lumen_session='+'c'*43 in self.headers.get('Cookie','')}
                else:
                    data=('''<!doctype html><html><title>Notes fixture</title><section class="knowledge-editor">
                        <input class="title-input" value="Own fixture note"><div class="note-rich-text" contenteditable="true">Own fixture text</div>
                        </section><script>window.fixtureDirty=false;document.addEventListener('input',()=>window.fixtureDirty=true);
                        window.addEventListener('beforeunload',e=>{if(window.fixtureDirty)e.preventDefault()});</script></html>'''
                        if cls.app_kind=='notes' else '<!doctype html><html><title>Compose fixture</title><textarea id="translation-text"></textarea></html>')
                raw=data.encode() if isinstance(data,str) else json.dumps(data).encode()
                self.send_response(status);self.send_header('Content-Type','text/html' if isinstance(data,str) else 'application/json')
                self.send_header('Content-Length',str(len(raw)))
                if cookie:self.send_header('Set-Cookie','lumen_session='+'c'*43+'; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=Strict')
                self.end_headers();self.wfile.write(raw)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cls.cert,key)
        cls.server.socket=context.wrap_socket(cls.server.socket,server_side=True)
        cls.origin='https://127.0.0.1:'+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
        cls.app.processEvents();cls.temp.cleanup()

    def setUp(self):
        type(self).app_kind='compose';type(self).hold_check=False
        type(self).revoked=False;type(self).hold_write=False
        type(self).native_user=USER;type(self).native_areas=['translate'];type(self).native_revision=7
        type(self).native_device=DEVICE;type(self).hold_upload=False
        type(self).drive_files=[];type(self).uploads={};type(self).upload_requests=[];type(self).upload_metadata=[]
        type(self).folder=dict(id=FOLDER,name='Eigene Testkopien',parent_id=None,revision=1,trashed=False,can_write=True)
        self.upload_started.clear();self.release_upload.clear()
        type(self).hold_inventory=False;self.inventory_started.clear();self.release_inventory.clear()
        self.import_call_start=len(self.calls)
        self.write_started.clear();self.release_write.clear();self.windows=[]
        self.check_started.clear();self.release_check.clear()

    def tearDown(self):
        self.release_write.set();self.release_upload.set();self.release_inventory.set();self.release_check.set()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
            for window in self.windows:window.close()
            self.wait(lambda:all(w._disposed for w in self.windows))
            for w in self.windows:w.deleteLater()
            self.app.processEvents();QTest.qWait(100)

    def wait(self,predicate,timeout=15000):
        end=time.monotonic()+timeout/1000
        while not predicate():
            if time.monotonic()>end:
                self.fail('Own Qt fixture timed out: '+repr([(w.session.state,w._live,w._loaded,
                    w._worker is not None) for w in self.windows])+' calls='+repr(self.calls[-8:]))
            self.app.processEvents();QTest.qWait(20)

    def js(self,window,source,world=0):
        result=[];window.page.runJavaScript(source,world,lambda value:result.append(value))
        self.wait(lambda:bool(result));return result[0]

    def window(self,*,pilot=False,app='compose'):
        type(self).app_kind=app
        binding=Binding(self.origin,USER,DEVICE,app)
        session=AppSession(dict(server=self.origin,device_id=DEVICE,token='native-only-fixture',ca_file=str(self.cert)),binding)
        from server_app_window import _connection
        window=ServerAppWindow(session,self.root,pilot_connection=_connection()[1] if pilot else None)
        self.windows.append(window);window.show()
        self.wait(lambda:window._loaded or window.session.state not in ('disconnected','ready'))
        self.wait(lambda:window._loaded)
        return window

    def import_window(self,drive=True,*,pilot=False,app='compose'):
        type(self).native_areas=['notes' if app=='notes' else 'translate']+(['drive'] if drive else [])
        temp=tempfile.TemporaryDirectory(dir=self.root);self.addCleanup(temp.cleanup)
        self.import_root=Path(temp.name);(self.import_root/'config').mkdir()
        self.config=dict(server=self.origin,device_id=DEVICE,token='native-only-fixture',ca_file=str(self.cert))
        changed=patch.object(lumen_connect,'CONFIG',self.import_root/'config/connection.json')
        changed.start();self.addCleanup(changed.stop)
        lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
        env=patch.dict(os.environ,{'LUMEN_TOOLS_DATA':str(self.import_root/'tools')})
        env.start();self.addCleanup(env.stop)
        window=self.window(pilot=pilot,app=app);window.timer.stop();self.wait(lambda:window._worker is None)
        return window

    def note_input(self,window):
        self.js(window,"const field=document.querySelector('.note-rich-text');field.textContent='Own unsaved Notes text';"
                       "field.dispatchEvent(new Event('input',{bubbles:true}))")
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertIn('Own unsaved Notes text',window.session.draft(window._binding))

    def test_reference_selection_uses_current_app_hook_without_reloading_or_discarding(self):
        window=self.import_window(drive=False,pilot=True,app='notes');self.note_input(window)
        reference=dict(version=2,app='note',id=FILE,title='Own selected note',
                       locator=dict(server=self.origin,account=USER))
        self.js(window,"window.__lumenOpenReference=value=>{window.selectedReference=value;return false}")
        result=[];window.open_reference(reference,result.append);self.wait(lambda:bool(result))
        self.assertEqual(result,[False])
        self.assertEqual(self.js(window,'window.selectedReference.id'),FILE)
        self.assertEqual(self.js(window,"document.querySelector('.note-rich-text').textContent"),'Own unsaved Notes text')
        self.js(window,'window.__lumenOpenReference=()=>true')
        result=[];window.open_reference(reference,result.append);self.wait(lambda:bool(result))
        self.assertEqual(result,[True])
        with self.assertRaises(SessionError):
            window.open_reference(dict(reference,locator=dict(server=self.origin,account=FOLDER)),result.append)
        self.js(window,'delete window.__lumenOpenReference')
        result=[];window.open_reference(reference,result.append);self.wait(lambda:bool(result))
        self.assertEqual(result,[None])

    def test_reference_callback_is_rejected_after_native_connection_changes(self):
        window=self.import_window(drive=False,pilot=True,app='notes')
        reference=dict(version=2,app='note',id=FILE,title='Own selected note',
                       locator=dict(server=self.origin,account=USER))
        self.js(window,'window.__lumenOpenReference=()=>true')
        pending=[];result=[]
        with patch.object(window,'verify',side_effect=lambda **args:pending.append(args['ready'])):
            window.open_reference(reference,result.append)
        lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
        pending.pop()()
        self.assertEqual(result,[None])

    def test_reference_verification_failure_completes_once_without_selecting(self):
        window=self.import_window(drive=False,pilot=True,app='notes')
        reference=dict(version=2,app='note',id=FILE,title='Own selected note',
                       locator=dict(server=self.origin,account=USER))
        self.js(window,'window.__lumenOpenReference=()=>{window.selectedReference=true;return true}')
        result=[]
        with patch.object(window.session,'check',side_effect=OSError('Own synthetic disconnect')):
            window.open_reference(reference,result.append)
            self.wait(lambda:bool(result))
        self.assertEqual(result,[None]);self.assertFalse(self.js(window,'window.selectedReference === true'))

    def test_notes_expired_session_keeps_copy_only_for_same_binding_and_connection(self):
        window=self.import_window(drive=False,pilot=True,app='notes');self.note_input(window)
        window.session._deadline=window.session._clock()-1
        window.verify();self.wait(lambda:window.stack.currentWidget() is window.status_page and window._worker is None)
        self.wait(lambda:window.page.lifecycleState()==QWebEnginePage.LifecycleState.Frozen)
        self.assertTrue(window.copy.isVisible())
        self.assertTrue(window.copy.isEnabled())
        QApplication.clipboard().setText('Own recovery sentinel');window.copy.click()
        self.assertIn('Own unsaved Notes text',QApplication.clipboard().text())
        binding=window.session.binding
        window.session.binding=Binding(self.origin,FOLDER,DEVICE,'notes')
        QApplication.clipboard().setText('Own binding sentinel');window.copy_draft()
        self.assertEqual(QApplication.clipboard().text(),'Own binding sentinel')
        window.session.binding=binding
        lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
        QApplication.clipboard().setText('Own generation sentinel');window.copy_draft()
        self.assertEqual(QApplication.clipboard().text(),'Own generation sentinel')

    def test_notes_close_during_identity_worker_cancel_preserves_live_session_and_dom(self):
        window=self.import_window(drive=False,pilot=True,app='notes');self.note_input(window)
        window.timer.start();cookie=window.session._cookie;session_generation=window.session._generation
        type(self).hold_check=True;window.verify();self.wait(self.check_started.is_set)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as question:
            window.close()
            self.assertEqual(window.session._cookie,cookie)
            self.assertEqual(window.session._generation,session_generation)
            self.assertTrue(window._live);self.assertTrue(window.timer.isActive())
            self.release_check.set();self.wait(lambda:question.called and not window._closing)
        self.assertTrue(window.session.usable);self.assertTrue(window._live)
        self.wait(lambda:window.stack.currentWidget() is window.view)
        self.assertEqual(self.js(window,"document.querySelector('.note-rich-text').textContent"),'Own unsaved Notes text')

    def test_notes_tag_draft_post_can_resume_but_document_write_stays_uncertain(self):
        window=self.import_window(drive=False,pilot=True,app='notes');self.note_input(window)
        self.js(window,"fetch('/api/note-drafts/tags',{method:'POST',headers:{'Content-Type':'application/json'},"
                       "body:JSON.stringify({body:'Own draft',action:'list'})}).then(()=>window.tagsChecked=true)")
        self.wait(lambda:self.js(window,'window.tagsChecked') is True)
        self.assertFalse(window.session._write_seen)
        self.pause(window);self.assertFalse(window.session.uncertain);window.verify()
        self.wait(lambda:window._worker is None and window._live and window.stack.currentWidget() is window.view)
        self.assertEqual(self.js(window,"document.querySelector('.note-rich-text').textContent"),'Own unsaved Notes text')
        self.js(window,"fetch('/api/documents/"+FILE+"',{method:'PATCH',headers:{'Content-Type':'application/json'},"
                       "body:'{}'}).then(()=>window.documentWritten=true)")
        self.wait(lambda:self.js(window,'window.documentWritten') is True)
        self.assertTrue(window.session._write_seen)
        self.pause(window);self.assertTrue(window.session.uncertain);window.verify()
        self.wait(lambda:window._worker is None)
        self.assertFalse(window._live);self.assertFalse(window.session.usable)

    def theme_property(self, value):
        previous=self.app.property('lumenDesign')
        self.addCleanup(lambda:self.app.setProperty('lumenDesign',previous))
        if getattr(self.app,'theme_watcher',None) is None:
            self.app.theme_watcher=QFileSystemWatcher(self.app)
            self.addCleanup(lambda:setattr(self.app,'theme_watcher',None))
        self.app.setProperty('lumenDesign',value)
        # Unit sender trigger only; separate A/B acceptance uses real persisted changes.
        self.app.theme_watcher.fileChanged.emit(str(self.root/'unit-theme-source'))

    def test_theme_start_script_never_targets_foreign_or_closing_page(self):
        self.theme_property('glass');window=self.window();other=self.window()
        window.timer.stop();other.timer.stop()
        for field in ('page','profile','view','_closing'):
            with self.subTest(field=field):
                original=getattr(window,field)
                setattr(window,field,True if field=='_closing' else getattr(other,field))
                try:
                    with patch.object(window.page,'scripts',side_effect=AssertionError('No script registration on an unbound or closing page')):
                        window._theme_changed(str(self.root/'unit-theme-source'))
                finally:setattr(window,field,original)

    def test_theme_initial_public_ids_are_mainframe_document_creation_data(self):
        for theme in ('glass','graphite','atelier','midnight'):
            with self.subTest(theme=theme):
                self.theme_property(theme);window=self.window()
                self.assertEqual(self.js(window,'window.__lumenDesktopTheme'),theme)
                scripts=window.page.scripts().find('Lumen desktop theme')
                self.assertEqual(len(scripts),1);script=scripts[0]
                self.assertEqual(script.name(),'Lumen desktop theme')
                self.assertEqual(script.worldId(),QWebEngineScript.ScriptWorldId.MainWorld)
                self.assertEqual(script.injectionPoint(),QWebEngineScript.InjectionPoint.DocumentCreation)
                self.assertFalse(script.runsOnSubFrames())
                self.assertNotIn('document.',script.sourceCode())

    def test_theme_live_clear_and_invalid_values_never_persist_or_write(self):
        self.theme_property('glass');window=self.window();window.timer.stop()
        self.js(window,"window.themeEvents=0;addEventListener('lumen-desktop-theme',()=>window.themeEvents++)")
        before=len(self.calls)
        for value,expected in [('atelier','atelier'),('clear',None),('midnight','midnight'),
                               ('system',None),('graphite','graphite'),(['glass'],None),('<style>',None)]:
            with self.subTest(value=value):
                events=self.js(window,'window.themeEvents')
                self.theme_property(value)
                self.wait(lambda:self.js(window,'window.themeEvents')>events)
                self.assertEqual(self.js(window,'window.__lumenDesktopTheme ?? null'),expected or '')
                self.assertTrue(self.js(window,"localStorage.getItem('lumen-appearance')===null"))
        self.assertFalse(any(c['method']!='GET' for c in self.calls[before:]))
        self.assertFalse(any(c['path']=='/bridge/apps/session-ticket' for c in self.calls[before:]))

    def held_theme(self, window, pending):
        original=window.page.runJavaScript
        def run(source,*args):
            if '__lumenDesktopTheme' in source:pending.append(args[-1])
            else:original(source,*args)
        return patch.object(window.page,'runJavaScript',side_effect=run)

    def test_theme_all_three_reveal_callers_wait_for_latest_cosmetic_completion(self):
        from types import SimpleNamespace
        self.theme_property('glass')
        for caller in ('load','verify','cookie'):
            with self.subTest(caller=caller):
                window=self.window();window.timer.stop();pending=[]
                self.wait(lambda:window.stack.currentWidget() is window.view)
                window.stack.setCurrentWidget(window.status_page)
                with self.held_theme(window,pending):
                    if caller=='load':window._loaded_page(True)
                    elif caller=='verify':window._verified(SimpleNamespace(ok=True,deleteLater=lambda:None),window._generation)
                    else:window._cookie_added(window.profile,window._profile_cookie)
                    window.timer.stop();self.wait(lambda:len(pending)==1)
                    self.assertIs(window.stack.currentWidget(),window.status_page)
                    self.theme_property('atelier');self.wait(lambda:len(pending)==2)
                    pending[0](True);self.assertIs(window.stack.currentWidget(),window.status_page)
                    pending[1](True);self.assertIs(window.stack.currentWidget(),window.view)
                self.theme_property('glass');self.app.processEvents()

    def test_theme_late_completion_never_reveals_changed_context(self):
        self.theme_property('glass')
        for field in ('page','profile','view','binding','window_generation','session_generation','expired','blocked'):
            with self.subTest(field=field):
                window=self.window();window.timer.stop();pending=[]
                self.wait(lambda:window.stack.currentWidget() is window.view)
                window.stack.setCurrentWidget(window.status_page)
                with self.held_theme(window,pending):
                    window._loaded_page(True);self.wait(lambda:bool(pending))
                    original={}
                    if field in ('page','profile','view'):
                        original[field]=getattr(window,field);setattr(window,field,None)
                    elif field=='binding':original['_binding']=window._binding;window._binding=Binding(self.origin,USER,str(uuid4()),'compose')
                    elif field=='window_generation':window._generation+=1
                    elif field=='session_generation':window.session._generation+=1
                    elif field=='expired':window.session._deadline=0
                    else:window.block('offline')
                    try:pending[0](True);self.assertIs(window.stack.currentWidget(),window.status_page)
                    finally:
                        for key,value in original.items():setattr(window,key,value)

    def test_theme_close_cancel_applies_latest_without_reconnect_then_discard_cancels(self):
        self.theme_property('glass');window=self.window();window.timer.stop()
        self.js(window,"document.querySelector('textarea').value='Eigener Entwurf';document.querySelector('textarea').dispatchEvent(new Event('input',{bubbles:true}))")
        self.assertEqual(self.js(window,'window.__lumenComposeDraft',QWebEngineScript.ScriptWorldId.ApplicationWorld),'Eigener Entwurf')
        before=len(self.calls)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel) as asked:
            window.close();self.wait(lambda:asked.called and not window._closing)
        self.assertFalse(window._disposed)
        self.theme_property('midnight')
        self.wait(lambda:self.js(window,'window.__lumenDesktopTheme')=='midnight')
        self.assertEqual(window.session.draft(window.session.binding),'Eigener Entwurf')
        self.assertFalse(any(c['method']=='POST' for c in self.calls[before:]))
        pending=[]
        with self.held_theme(window,pending):
            window._loaded_page(True);self.wait(lambda:bool(pending))
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
                window.close();self.wait(lambda:window._disposed)
            pending[0](True);self.theme_property('atelier');self.app.processEvents()
            self.assertTrue(window._disposed)

    def test_text_pilot_atomic_aba_without_import_lease_blocks_old_reconnect(self):
        window=self.import_window(drive=False,pilot=True);self.assertIsNone(window._import_lease)
        before=len(self.calls)
        lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(dict(self.config,token='changed-fixture')))
        lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
        window.verify();self.wait(lambda:window._pilot_invalid)
        self.assertFalse(window._live);self.assertEqual(window.session.state,'identity')
        self.assertFalse(window.retry.isEnabled());self.assertFalse(window.session.has_cookie)
        window.verify(reconnect=True);QTest.qWait(40)
        self.assertFalse(any(c['path'] in ('/bridge/apps/session-ticket','/api/auth/desktop/exchange') for c in self.calls[before:]))
        self.assertTrue(window.copy.isHidden())
        with patch.object(QApplication,'clipboard',side_effect=AssertionError('No clipboard in pilot')):window.copy_draft()

    def test_text_pilot_config_change_during_close_finishes_profile_cleanup(self):
        window=self.import_window(drive=False,pilot=True);path=window.profile.persistentStoragePath()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
            window.close()
            lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(dict(self.config,token='changed-fixture')))
            self.wait(lambda:window._disposed)
        self.assertFalse(Path(path).exists())

    def test_text_bootstrap_worker_has_no_qt_and_only_translate_grant(self):
        from server_app_window import text_pilot_context
        from types import SimpleNamespace
        self.import_window(drive=False)
        profile=self.import_root/'bootstrap';(profile/'config/lumen-server').mkdir(parents=True,mode=0o700)
        config=profile/'config/lumen-server/connection.json'
        lumen_connect.save_private(config,json.dumps(self.config));results=[];errors=[]
        def boot():
            try:results.append(text_pilot_context(profile,SimpleNamespace(check=lambda:None)))
            except Exception as error:errors.append(type(error).__name__)
        with patch.object(lumen_connect,'CONFIG',config),patch('server_app_window.QUrl',side_effect=AssertionError('No Qt in worker')):
            thread=threading.Thread(target=boot);thread.start();thread.join(timeout=3)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.assertEqual(results[0][1],Binding(self.origin,USER,DEVICE,'compose'))
            type(self).native_areas=['translate','drive']
            with self.assertRaises(SessionError):text_pilot_context(profile,SimpleNamespace(check=lambda:None))

    def test_import_lease_worker_uses_no_gui_and_is_invalid_after_block(self):
        window=self.import_window();observed=[];errors=[]
        def coordinator(parent,lease,token):
            def check():
                try:
                    with patch.object(parent,'_cookie_valid',side_effect=AssertionError('Worker touched Qt proof')):
                        lease.check();observed.append('worker-ready')
                except Exception as error:errors.append(type(error).__name__)
            worker=threading.Thread(target=check);worker.start();worker.join(timeout=2)
            parent.block('offline')
            try:lease.check()
            except SessionError:observed.append('blocked')
        with patch('server_file_import_ui.start_import',side_effect=coordinator):
            window._lumen_file_import();self.wait(lambda:len(observed)>=2 or bool(errors) or window._import_error)
        self.assertEqual(observed,['worker-ready','blocked']);self.assertEqual(errors,[])

    def test_import_without_native_drive_grant_never_calls_coordinator(self):
        window=self.import_window(drive=False);called=[]
        with patch('server_file_import_ui.start_import',side_effect=lambda *a:called.append(a)):
            window._lumen_file_import();self.wait(lambda:window._import_error is not None)
        self.assertEqual(called,[]);self.assertIsNone(window._import_reference)

    def test_import_atomic_config_aba_invalidates_even_equal_end_scope(self):
        window=self.import_window();observed=[]
        def coordinator(parent,lease,token):
            original=lumen_connect.connection_scope(self.config)
            lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(dict(self.config,token='different-fixture')))
            lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
            observed.append(lumen_connect.connection_scope(lumen_connect.read_config())==original)
            try:lease.check()
            except SessionError:observed.append('denied')
            self.app.processEvents()
        with patch('server_file_import_ui.start_import',side_effect=coordinator):
            window._lumen_file_import();self.wait(lambda:bool(observed))
        self.assertEqual(observed,[True,'denied']);self.assertIsNone(window._import_reference)

    def import_dialogs(self,path,*,cancel_picker=False,before_review=lambda:None):
        errors=[];timer=QTimer();timer.setInterval(5);self.addCleanup(timer.stop)
        def answer():
            dialog=QApplication.activeModalWidget()
            if dialog is None or dialog.property('hostFixtureAnswered'):return
            try:
                if isinstance(dialog,QFileDialog):
                    dialog.setProperty('hostFixtureAnswered',True)
                    if cancel_picker:dialog.reject();return
                    dialog.setDirectory(str(path.parent))
                    def choose():
                        if not shiboken6.isValid(dialog):return
                        dialog.findChild(QLineEdit,'fileNameEdit').setText(str(path));dialog.accept()
                    QTimer.singleShot(50,choose)
                elif isinstance(dialog,QDialog) and dialog.windowTitle()=='Lumen Drive · Datei übernehmen':
                    dialog.setProperty('hostFixtureAnswered',True);before_review()
                    combo=dialog.findChild(QComboBox);combo.setCurrentIndex(combo.findData(FOLDER));dialog.accept()
                elif isinstance(dialog,QMessageBox) and dialog.windowTitle()=='Lumen Drive · Übernahme prüfen':
                    dialog.setProperty('hostFixtureAnswered',True);dialog.done(QMessageBox.StandardButton.Yes)
            except Exception as error:
                errors.append(type(error).__name__);dialog.reject()
        timer.timeout.connect(answer);timer.start();return errors

    def reference(self):
        return dict(app='files',kind='drive_file',id=FILE,title='Eigene Testkopie.txt',
                    locator=dict(server=self.origin,account=USER)),dict(id=FILE,version=1,revision=1)

    def test_import_real_coordinator_https_same_window_and_done_has_no_upload(self):
        from interop_data import Registry
        window=self.import_window();other=self.window();other.timer.stop();delivered=[];foreign=[]
        window.import_reference_ready.connect(lambda ref,resolved:delivered.append((ref,resolved,threading.get_ident())))
        other.import_reference_ready.connect(lambda *args:foreign.append(args))
        path=self.import_root/'Synthetisches Original.txt';content=b'Own native HTTPS import fixture\n';path.write_bytes(content)
        errors=self.import_dialogs(path);start=len(self.calls)
        window._lumen_file_import();self.wait(lambda:bool(delivered) or window._import_error)
        self.assertEqual(errors,[]);self.assertEqual(len(delivered),1);self.assertEqual(foreign,[])
        ref,resolved,thread_id=delivered[0]
        self.assertEqual(thread_id,threading.get_ident());self.assertEqual(ref['id'],FILE)
        self.assertEqual(set(ref),{'app','kind','id','title','locator'})
        self.assertEqual(set(resolved),{'id','version','revision'});self.assertEqual(resolved['version'],1)
        self.assertEqual(window._import_reference,dict(reference=ref,resolved=resolved))
        self.assertIsNone(other._import_reference);self.assertEqual(path.read_bytes(),content)
        self.assertEqual(next(iter(self.uploads.values()))['data'],content)
        self.assertEqual(set(self.upload_metadata[0]),{'name','size','sha256','folder','replaces','revision','mime'})
        calls=self.calls[start:]
        self.assertTrue(any(c['path']=='/api/me' and not c['bearer'] for c in calls))
        self.assertTrue(all(c['bearer'] and not c['cookie'] and not c['web'] for c in calls if '/bridge/drive/' in c['path']))
        html=self.js(window,'document.documentElement.outerHTML')
        self.assertNotIn('native-only-fixture',html);self.assertNotIn(str(path),html)
        self.assertEqual(self.js(window,'typeof qt'),'undefined')
        rows=Registry(self.import_root/'tools').history();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state'],'done')
        uploads=list(self.upload_requests)
        window._lumen_file_import(rows[0]['id']);self.wait(lambda:len(delivered)==2 or window._import_error)
        self.assertEqual(len(delivered),2);self.assertEqual(self.upload_requests,uploads)
        self.assertFalse(any(c['path']=='/api/translate' and c['method']=='POST' for c in self.calls[start:]))

    def test_import_native_picker_cancel_leaves_no_request_or_reference(self):
        from interop_data import Registry
        window=self.import_window();errors=self.import_dialogs(self.import_root/'unused',cancel_picker=True)
        window._lumen_file_import();self.wait(lambda:window._import_error is not None)
        self.assertEqual(errors,[]);self.assertEqual(Registry(self.import_root/'tools').history(),[])
        self.assertIsNone(window._import_reference);self.assertEqual(self.upload_requests,[])

    def test_import_close_waits_for_real_chunk_job_then_explicit_same_request_resume(self):
        from interop_data import Registry
        window=self.import_window();type(self).hold_upload=True;order=[];close_seen=[]
        page,profile=window.page,window.profile
        page.destroyed.connect(lambda *_:order.append('page'));profile.destroyed.connect(lambda *_:order.append('profile'))
        path=self.import_root/'Close fixture.txt';path.write_bytes(b'Own cancel chunk fixture')
        errors=self.import_dialogs(path);watch=QTimer();watch.setInterval(5);self.addCleanup(watch.stop)
        def close_during_chunk():
            if not self.upload_started.is_set() or close_seen:return
            jobs=[j for j in window.findChildren(QThread) if j.isRunning()]
            for job in jobs:job.finished.connect(lambda:order.append('job'))
            window.close()
            close_seen.append((len(jobs),window._disposed,shiboken6.isValid(page),shiboken6.isValid(profile)))
            self.release_upload.set()
        watch.timeout.connect(close_during_chunk);watch.start()
        window._lumen_file_import();self.wait(lambda:window._disposed);watch.stop()
        self.assertEqual(errors,[]);self.assertEqual(len(close_seen),1)
        count,disposed,page_alive,profile_alive=close_seen[0]
        self.assertGreaterEqual(count,1);self.assertEqual((disposed,page_alive,profile_alive),(False,True,True))
        self.assertLess(order.index('job'),order.index('page'));self.assertLess(order.index('page'),order.index('profile'))
        registry=Registry(self.import_root/'tools');rows=registry.history();self.assertEqual(len(rows),1)
        token=rows[0]['id'];self.assertEqual(rows[0]['state'],'pending');self.assertEqual(len(self.upload_requests),1)
        self.assertFalse(any(c['path'].endswith('/finish') for c in self.calls[self.import_call_start:]));self.assertIsNone(window._import_reference)
        resumed=self.window();resumed.timer.stop();delivered=[]
        resumed.import_reference_ready.connect(lambda *args:delivered.append(args))
        QTest.qWait(50);self.assertEqual(len(self.upload_requests),1)
        type(self).hold_upload=False;resumed._lumen_file_import(token)
        self.wait(lambda:bool(delivered) or resumed._import_error)
        self.assertEqual(len(delivered),1);self.assertEqual(registry.request(token)['state'],'done')
        self.assertEqual(len(set(self.upload_requests)),1);self.assertEqual(len(self.upload_requests),2)
        self.assertEqual(len(self.drive_files),1);self.assertFalse(any(c['method']=='DELETE' for c in self.calls[self.import_call_start:]))

    def test_import_progress_cancel_keeps_profile_and_same_pending_request(self):
        from interop_data import Registry
        window=self.import_window();type(self).hold_upload=True;cancelled=[];leases=[];signals=[];after=[]
        window.import_reference_ready.connect(lambda *args:signals.append(args))
        path=self.import_root/'Cancel fixture.txt';path.write_bytes(b'Own progress cancel fixture')
        errors=self.import_dialogs(path);watch=QTimer();watch.setInterval(5);self.addCleanup(watch.stop)
        def cancel():
            if not self.upload_started.is_set() or cancelled:return
            dialog=QApplication.activeModalWidget()
            if dialog is None:return
            leases.append(window._import_lease);dialog.reject();after.append(len(self.calls))
            # Root: Job cancellation gates in-flight work; lease expires in finally.
            cancelled.extend(j.cancelled.is_set() for j in window.findChildren(QThread)
                             if j.isRunning() and hasattr(j,'cancelled'))
            self.release_upload.set()
        watch.timeout.connect(cancel);watch.start()
        window._lumen_file_import();self.wait(lambda:window._import_error is not None);watch.stop()
        self.assertEqual(errors,[]);self.assertEqual(cancelled,[True]);self.assertFalse(window._disposed)
        self.assertEqual(signals,[])
        with self.assertRaises(SessionError):leases[0].check()
        QTest.qWait(50)
        self.assertEqual([c for c in self.calls[after[0]:] if c['path'].startswith('/bridge/')],[])
        self.assertTrue(shiboken6.isValid(window.profile));self.assertTrue(window._live)
        rows=Registry(self.import_root/'tools').history();self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['state'],'pending');self.assertEqual(len(set(self.upload_requests)),1)
        self.assertIsNone(window._import_reference);self.assertFalse(any(c['path'].endswith('/finish') for c in self.calls[self.import_call_start:]))

    def test_import_late_accept_requires_fresh_native_and_app_grants(self):
        cases=('account','device','revision','drive','compose','app_revoked','expired')
        for case in cases:
            with self.subTest(case=case):
                type(self).native_user=USER;type(self).native_device=DEVICE;type(self).native_revision=7;type(self).revoked=False
                window=self.import_window();signals=[];leases=[]
                window.import_reference_ready.connect(lambda *args:signals.append(args))
                def coordinator(parent,lease,token):
                    leases.append(lease);lease.accept_import(*self.reference())
                    if case=='account':type(self).native_user=str(uuid4())
                    elif case=='device':type(self).native_device=str(uuid4())
                    elif case=='revision':type(self).native_revision+=1
                    elif case=='drive':type(self).native_areas=['translate']
                    elif case=='compose':type(self).native_areas=['drive']
                    elif case=='app_revoked':type(self).revoked=True
                    elif case=='expired':parent.session._deadline=0
                with patch('server_file_import_ui.start_import',side_effect=coordinator):
                    window._lumen_file_import();self.wait(lambda:window._import_error is not None)
                self.assertEqual(len(leases),1);self.assertEqual(signals,[]);self.assertIsNone(window._import_reference)
                with self.assertRaises(SessionError):leases[0].check()

    def test_import_cancel_during_inventory_performs_no_later_io(self):
        window=self.import_window();type(self).hold_inventory=True;cancelled=[];after=[];signals=[];leases=[]
        window.import_reference_ready.connect(lambda *args:signals.append(args))
        watch=QTimer();watch.setInterval(5);self.addCleanup(watch.stop)
        def cancel():
            if not self.inventory_started.is_set() or cancelled:return
            dialog=QApplication.activeModalWidget()
            if dialog is None:return
            leases.append(window._import_lease);dialog.reject();cancelled.append(True);after.append(len(self.calls))
            self.release_inventory.set()
        watch.timeout.connect(cancel);watch.start()
        window._lumen_file_import();self.wait(lambda:window._import_error is not None);watch.stop()
        self.assertEqual(cancelled,[True]);self.assertEqual(signals,[]);self.assertEqual(self.upload_requests,[])
        with self.assertRaises(SessionError):leases[0].check()
        self.assertEqual([c['path'] for c in self.calls[after[0]:] if c['path'].startswith('/bridge/')],[])

    def test_import_actual_page_or_profile_change_and_worker_accept_are_denied(self):
        window=self.import_window();other=self.window();other.timer.stop();observed=[]
        def coordinator(parent,lease,token):
            foreign=QWebEnginePage(parent.profile,parent);page=parent.page;profile=parent.profile
            parent.view.setPage(foreign)
            try:
                try:lease.accept_import(*self.reference())
                except SessionError:observed.append('page')
            finally:parent.view.setPage(page);foreign.deleteLater()
            parent.profile=other.profile
            try:
                try:lease.accept_import(*self.reference())
                except SessionError:observed.append('profile')
            finally:parent.profile=profile
            def accept():
                try:lease.accept_import(*self.reference())
                except SessionError:observed.append('thread')
            thread=threading.Thread(target=accept);thread.start();thread.join(timeout=2)
        with patch('server_file_import_ui.start_import',side_effect=coordinator):
            window._lumen_file_import();self.wait(lambda:len(observed)==3 or window._import_error)
        self.assertEqual(observed,['page','profile','thread']);self.assertIsNone(window._import_reference)

    def test_import_watch_rearms_after_atomic_aba_and_old_callback_cannot_cancel_new_lease(self):
        window=self.import_window();leases=[];observed=[]
        def coordinator(parent,lease,token):
            leases.append(lease)
            if len(leases)==1:
                lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(dict(self.config,token='changed-fixture')))
                self.wait(lambda:parent._import_lease is None)
                lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
                QTest.qWait(40)
            else:
                sibling=lumen_connect.CONFIG.parent/'unrelated';sibling.write_text('Own fixture')
                QTest.qWait(30);lease.check()
                parent._fresh_import(leases[0],lambda:observed.append('old callback ran'))
                lease.check();observed.append('new lease valid')
        with patch('server_file_import_ui.start_import',side_effect=coordinator):
            window._lumen_file_import();self.wait(lambda:bool(leases) and not window._import_running)
            window._lumen_file_import();self.wait(lambda:len(leases)==2 and not window._import_running)
        self.assertEqual(observed,['new lease valid'])
        self.assertIn(str(lumen_connect.CONFIG),window._connection_watcher.files())
        self.assertIsNone(window._import_reference)
        for lease in leases:
            with self.assertRaises(SessionError):lease.check()

    def test_import_cookie_removal_and_reconnect_never_revive_old_lease(self):
        window=self.import_window();old=[];signals=[]
        window.import_reference_ready.connect(lambda *args:signals.append(args))
        def coordinator(parent,lease,token):
            old.append(lease);parent.profile.cookieStore().deleteAllCookies()
            self.wait(lambda:parent._import_lease is None)
        with patch('server_file_import_ui.start_import',side_effect=coordinator):
            window._lumen_file_import();self.wait(lambda:bool(old) and not window._import_running)
        window.verify();self.wait(lambda:window._worker is None)
        with self.assertRaises(SessionError):old[0].accept_import(*self.reference())
        self.assertEqual(signals,[]);self.assertIsNone(window._import_reference)

    def test_native_https_cookie_boundary_and_no_global_bridge(self):
        window=self.window()
        self.assertEqual(self.js(window,'document.cookie'),'')
        self.assertEqual(self.js(window,'typeof qt'),'undefined')
        self.assertNotIn('native-only-fixture',self.js(window,'document.documentElement.outerHTML'))
        self.js(window,"fetch('/api/me').then(r=>r.json()).then(v=>window.fixtureMe=v.user.desktop_app)")
        self.wait(lambda:self.js(window,'window.fixtureMe')=='compose')
        self.assertTrue(any(c['web'] and c['path']=='/api/me' and c['cookie'] and not c['bearer'] for c in self.calls))
        self.assertTrue(all(not c['bearer'] for c in self.calls if c['path'].startswith('/api/')))

    def test_profile_isolation_navigation_and_permissions(self):
        first=self.window();second=self.window()
        self.assertIsNot(first.profile,second.profile)
        self.assertNotEqual(first.profile.persistentStoragePath(),second.profile.persistentStoragePath())
        self.assertEqual(first.profile.persistentCookiesPolicy().name,'NoPersistentCookies')
        first.profile.cookieStore().deleteAllCookies();QTest.qWait(100)
        self.js(second,"fetch('/api/ping').then(r=>r.json()).then(v=>window.fixtureCookie=v.cookie)")
        self.wait(lambda:self.js(second,'window.fixtureCookie') is True)
        for url in ['https://other.test/','file:///etc/passwd',self.origin+'/?app=vault&presentation=desktop',
                    self.origin+'/?app=translate&presentation=desktop&ticket=fixture','javascript:alert(1)']:
            self.assertFalse(first.page.acceptNavigationRequest(QUrl(url),0,True))
        self.assertFalse(first.page.acceptNavigationRequest(QUrl(first.session.url),0,False))
        self.assertIsNone(first.page.createWindow(0));self.assertEqual(first.page.chooseFiles(0,[],[]),[])
        other_origin=self.origin.replace('127.0.0.1','localhost')
        self.js(second,"fetch("+json.dumps(other_origin+'/api/foreign-resource')+
                ").then(()=>window.foreignRequest='allowed').catch(()=>window.foreignRequest='blocked')")
        self.wait(lambda:self.js(second,'window.foreignRequest')=='blocked')
        self.assertFalse(any(c['path']=='/api/foreign-resource' for c in self.calls))

    def test_profile_is_offrecord_with_memory_only_storage_policies(self):
        window=self.window();profile=window.profile
        self.assertTrue(profile.isOffTheRecord(),'A named temporary directory is not an off-the-record profile')
        self.assertEqual(profile.storageName(),'')
        self.assertEqual(profile.persistentCookiesPolicy().name,'NoPersistentCookies')
        self.assertEqual(profile.httpCacheType().name,'MemoryHttpCache')
        self.assertEqual(profile.persistentPermissionsPolicy().name,'StoreInMemory')
        self.assertEqual(len(profile.additionalTrustedCertificates()),1)

    def test_local_storage_and_probe_cookie_stay_in_their_own_profile(self):
        first=self.window();second=self.window();marker='synthetic-otr-storage-probe'
        self.js(first,"localStorage.setItem('lumen-storage-probe',"+json.dumps(marker)+
                ");document.cookie='lumen_probe="+marker+"; Max-Age=3600; Path=/; Secure; SameSite=Strict'")
        self.assertEqual(self.js(first,"localStorage.getItem('lumen-storage-probe')"),marker)
        self.assertIn('lumen_probe='+marker,self.js(first,'document.cookie'))
        self.assertTrue(self.js(second,"localStorage.getItem('lumen-storage-probe')===null"))
        self.assertNotIn('lumen_probe=',self.js(second,'document.cookie'))

    def test_isolated_draft_survives_react_unmount_revoke_and_never_auto_replays(self):
        window=self.window()
        self.js(window,"document.querySelector('textarea').value='Nicht gesendet';document.querySelector('textarea').dispatchEvent(new Event('input',{bubbles:true}))")
        self.assertEqual(self.js(window,'typeof window.__lumenComposeDraft'),'undefined')
        self.js(window,"document.querySelector('textarea').remove()")
        type(self).revoked=True;window.verify()
        self.wait(lambda:window.stack.currentWidget() is window.status_page)
        self.wait(lambda:window.session.draft(window.session.binding)=='Nicht gesendet')
        self.assertFalse(window.session.usable)
        self.assertFalse(any(c['path']=='/api/translate' for c in self.calls))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
            window.close();self.app.processEvents();self.assertFalse(window._disposed)

    def test_empty_remount_preserves_draft_and_user_can_clear(self):
        self.app.setQuitOnLastWindowClosed(False)
        window=self.window();draft='Nicht gesendeter Entwurf'
        window.timer.stop();window.activateWindow();QTest.qWait(500)
        window.view.setFocus()
        self.js(window,"document.querySelector('textarea').focus()")
        QTest.mouseClick(window.view.focusProxy(),Qt.LeftButton,Qt.NoModifier,QPoint(25,20))
        QTest.qWait(100)
        QTest.keyClicks(window.view.focusProxy(),draft)
        QTest.qWait(100)
        self.assertEqual(self.js(window,"document.querySelector('textarea').value"),draft)
        self.wait(lambda:self.js(window,"document.querySelector('textarea').value")==draft)
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window.session.binding),draft)
        self.js(window,"document.querySelector('textarea').remove();const field=document.createElement('textarea');"
                       "field.id='translation-text';document.body.append(field)")
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window.session.binding),draft,
                         'An empty DOM remount must not erase the bound unsent draft')
        self.js(window,"const other=document.createElement('input');document.body.append(other);"
                       "other.value='Anderes Feld';other.dispatchEvent(new Event('input',{bubbles:true}))")
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window.session.binding),draft)
        window.view.setFocus()
        self.js(window,"document.querySelector('textarea').focus();document.addEventListener('input',e=>{"
                       "if(e.target.id==='translation-text' && e.target.value==='')window.fixtureUserClear=e.isTrusted})")
        QTest.mouseClick(window.view.focusProxy(),Qt.LeftButton,Qt.NoModifier,QPoint(25,20))
        QTest.qWait(100)
        QTest.keyClicks(window.view.focusProxy(),'Bewusst leeren')
        self.wait(lambda:self.js(window,"document.querySelector('textarea').value")=='Bewusst leeren')
        QTest.keyClick(window.view.focusProxy(),Qt.Key_A,Qt.ControlModifier)
        QTest.keyClick(window.view.focusProxy(),Qt.Key_Backspace)
        self.wait(lambda:self.js(window,"document.querySelector('textarea').value")=='')
        self.assertTrue(self.js(window,'window.fixtureUserClear'))
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window.session.binding),'')

    def pause(self,window):
        window.block('offline')
        self.wait(lambda:window.page.lifecycleState()==QWebEnginePage.LifecycleState.Frozen)

    def test_same_cookie_resumes_after_fresh_identity_check_without_new_ticket(self):
        window=self.window()
        self.js(window,"document.querySelector('textarea').value='Reconnect-Entwurf';"
                       "document.querySelector('textarea').dispatchEvent(new Event('input',{bubbles:true}))")
        self.js(window,"fetch('/api/ping').then(r=>r.json()).then(v=>window.cookieBefore=v.cookie)")
        self.wait(lambda:self.js(window,'window.cookieBefore') is True)
        tickets=sum(c['path']=='/bridge/apps/session-ticket' for c in self.calls)
        self.pause(window);window.verify()
        self.wait(lambda:window._worker is None and window._live
                  and window.stack.currentWidget() is window.view,timeout=3000)
        self.js(window,"fetch('/api/ping').then(r=>r.json()).then(v=>window.cookieAfter=v.cookie)")
        self.wait(lambda:self.js(window,'window.cookieAfter') is True)
        self.js(window,"document.querySelector('textarea').remove();const field=document.createElement('textarea');"
                       "field.id='translation-text';document.body.append(field)")
        captured=[];window._capture(lambda:captured.append(True));self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window.session.binding),'Reconnect-Entwurf')
        self.assertEqual(sum(c['path']=='/bridge/apps/session-ticket' for c in self.calls),tickets)

    def test_removed_or_expired_profile_cookie_is_not_reinserted_on_resume(self):
        for expired in (False,True):
            with self.subTest(expired=expired):
                window=self.window();removed=[]
                cookie=QNetworkCookie.parseCookies(window.session.web_cookie())[0]
                window.profile.cookieStore().cookieRemoved.connect(lambda c:removed.append(bytes(c.name())))
                self.pause(window)
                if expired:
                    cookie.setExpirationDate(QDateTime.currentDateTimeUtc().addSecs(-30))
                    window.profile.cookieStore().setCookie(cookie,QUrl(self.origin))
                else:window.profile.cookieStore().deleteAllCookies()
                self.wait(lambda:b'lumen_session' in removed)
                window.verify();self.wait(lambda:window._worker is None)
                self.assertFalse(window._live)
                self.assertIs(window.stack.currentWidget(),window.status_page)

    def test_changed_profile_cookie_while_paused_cannot_resume(self):
        window=self.window();cookie=QNetworkCookie.parseCookies(window.session.web_cookie())[0]
        changed=[];window.profile.cookieStore().cookieAdded.connect(lambda c:changed.append(bytes(c.value())))
        self.pause(window);cookie.setValue(b'd'*43)
        window.profile.cookieStore().setCookie(cookie,QUrl(self.origin))
        self.wait(lambda:b'd'*43 in changed)
        window.verify();self.wait(lambda:window._worker is None)
        self.assertFalse(window._live)
        self.assertEqual(window.session.state,'identity');self.assertFalse(window.retry.isEnabled())
        self.assertIs(window.stack.currentWidget(),window.status_page)

    def test_revoked_session_cannot_resume_with_its_old_profile_cookie(self):
        window=self.window();self.pause(window);type(self).revoked=True
        window.verify();self.wait(lambda:window._worker is None)
        self.assertFalse(window._live);self.assertEqual(window.session.state,'revoked')

    def test_different_profile_cannot_supply_resume_cookie_proof(self):
        window=self.window();other=self.window();original=window.profile
        self.pause(window);window.profile=other.profile
        try:
            window.verify();self.wait(lambda:window._worker is None)
            self.assertFalse(window._live)
        finally:window.profile=original

    def test_started_write_without_acknowledgement_stays_locked_without_replay(self):
        window=self.window();type(self).hold_write=True
        self.js(window,"fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},"
                       "body:JSON.stringify({text:'Nicht doppelt senden'})}).catch(()=>{})")
        self.wait(lambda:self.write_started.is_set())
        self.pause(window);window.verify();self.wait(lambda:window._worker is None)
        self.assertTrue(window.session.uncertain);self.assertFalse(window._live)
        self.assertEqual(sum(c['path']=='/api/translate' and c['method']=='POST' for c in self.calls),1)

    def test_tls_callback_rejects_and_uncertain_write_keeps_host_locked(self):
        window=self.window()
        class Error:
            rejected=False
            def rejectCertificate(self):self.rejected=True
        error=Error();window._certificate(error)
        self.assertTrue(error.rejected);self.assertFalse(window._live)
        self.assertIs(window.stack.currentWidget(),window.status_page)
        window.session.observe_write();window.block('offline')
        self.assertTrue(window.session.uncertain)
        window.verify();self.wait(lambda:window._worker is None)
        self.assertFalse(window._live)

    def test_real_web_tls_error_keeps_content_blocked(self):
        session=AppSession(dict(server=self.origin,device_id=DEVICE,token='native-only-fixture',
                               ca_file=str(self.wrong_cert)),Binding(self.origin,USER,DEVICE,'compose'))
        window=ServerAppWindow(session,self.root);self.windows.append(window)
        # Separate fixture trust: native HTTPS valid, WebEngine trusts an unrelated CA.
        session._config['ca_file']=str(self.cert);window.show()
        self.wait(lambda:session.state=='tls')
        self.assertFalse(window._live);self.assertFalse(window._loaded)
        self.assertIs(window.stack.currentWidget(),window.status_page)

    def test_expiry_does_not_renew_or_show_a_late_load(self):
        window=self.window();window.timer.stop()
        tickets=sum(c['path']=='/bridge/apps/session-ticket' for c in self.calls)
        window.session._deadline=0;window.verify()
        self.wait(lambda:window._worker is None and not window._live)
        self.assertEqual(sum(c['path']=='/bridge/apps/session-ticket' for c in self.calls),tickets)
        window._loaded_page(True)
        self.assertIs(window.stack.currentWidget(),window.status_page)
        window.verify(reconnect=True);self.assertFalse(window.retry.isEnabled())
        self.assertEqual(sum(c['path']=='/bridge/apps/session-ticket' for c in self.calls),tickets)

    def test_close_destroys_page_before_profile_and_removes_temporary_storage(self):
        window=self.window();storage=Path(window.profile.persistentStoragePath())
        destroyed=[]
        window.page.destroyed.connect(lambda:destroyed.append('page'))
        window.profile.destroyed.connect(lambda:destroyed.append('profile'))
        window.close();self.wait(lambda:not storage.exists())
        self.assertTrue(window._disposed);self.assertEqual(destroyed,['page','profile'])


if __name__=='__main__':unittest.main()
