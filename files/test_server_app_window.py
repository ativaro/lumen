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

from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
import shiboken6

from server_app_session import AppSession, Binding, SessionError
from server_app_window import ServerAppWindow, QWebEnginePage, QWebEngineScript

USER='73000000-0000-4000-8000-000000000001'
DEVICE='73000000-0000-4000-8000-000000000002'


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
        cls.calls=[];cls.revoked=False;cls.challenge=''
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.handle_request()
            def do_POST(self):self.handle_request()
            def handle_request(self):
                cls.calls.append(dict(path=self.path,method=self.command,bearer=bool(self.headers.get('Authorization')),
                                      cookie=bool(self.headers.get('Cookie')),web='QtWebEngine' in self.headers.get('User-Agent','')))
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
                status=200;cookie=False
                if self.path=='/bridge/me':
                    data=dict(id=USER,device_id=DEVICE,capabilities=['translate'])
                elif self.path=='/bridge/apps/session-ticket':
                    cls.challenge=body['challenge'];data=dict(ticket='t'*43,expires=(datetime.now(timezone.utc)+timedelta(seconds=29)).isoformat())
                elif self.path=='/api/auth/desktop/exchange':
                    if (body['app']!='compose' or body['user_id']!=USER or body['device_id']!=DEVICE
                            or hashlib.sha256(body['verifier'].encode()).hexdigest()!=cls.challenge
                            or self.headers.get('Origin')!=cls.origin or self.headers.get('Authorization')):status=403
                    cookie=True;data=dict(user_id=USER,device_id=DEVICE,app='compose',access='read',csrf='fixture',
                                          expires=(datetime.now(timezone.utc)+timedelta(seconds=899)).isoformat())
                elif self.path=='/api/me':
                    status=403 if cls.revoked or 'lumen_session='+'c'*43 not in self.headers.get('Cookie','') else 200
                    data=dict(user=dict(id=USER,device_id=DEVICE,desktop_app='compose',device_kind='desktop',
                                        capabilities=['translate'],admin=False,csrf='fixture'))
                elif self.path=='/api/translate':status=403;data={'detail':'App jobs remain gated.'}
                elif self.path=='/api/ping':data={'cookie':bool(self.headers.get('Cookie'))}
                else:
                    data='<!doctype html><html><title>Compose fixture</title><textarea id="translation-text"></textarea></html>'
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
        type(self).revoked=False;self.windows=[]

    def tearDown(self):
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

    def window(self):
        binding=Binding(self.origin,USER,DEVICE,'compose')
        session=AppSession(dict(server=self.origin,device_id=DEVICE,token='native-only-fixture',ca_file=str(self.cert)),binding)
        window=ServerAppWindow(session,self.root);self.windows.append(window);window.show()
        self.wait(lambda:window._loaded or window.session.state not in ('disconnected','ready'))
        self.wait(lambda:window._loaded)
        return window

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
