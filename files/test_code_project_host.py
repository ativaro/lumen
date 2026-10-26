"""Actual private Qt profiles and HTTPS; project applications never get a Lumen cookie."""
import json
import base64
import hashlib
from unittest.mock import patch
from types import SimpleNamespace
from test_server_app_window import PrivateHostFixture, FILE


class NativeProjectHostTest(PrivateHostFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        original = cls.server.RequestHandlerClass
        class Handler(original):
            protocol_version='HTTP/1.1'
            def handle_request(self):
                prefix = '/bridge/code-library/' + FILE
                if self.path == prefix + '/runtime/info':
                    data = json.dumps(dict(id=FILE, revision=1, title='Actual preview fixture')).encode()
                    mime = 'application/json'
                elif self.path == prefix + '/runtime/launch':
                    data = b'{"ready":true}'; mime = 'application/json'
                elif self.path.startswith(prefix + '/preview/'):
                    cls.application_requests.append(dict(path=self.path, cookie=self.headers.get('Cookie'),
                        app_cookie=self.headers.get('X-Lumen-App-Cookie'), bearer=self.headers.get('Authorization')))
                    route = self.path[len(prefix + '/preview'):]
                    if self.headers.get('Upgrade','').lower()=='websocket':
                        cls.websocket_protocols.append(self.headers.get('Sec-WebSocket-Protocol'))
                        accept=base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                        self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept)
                        if route=='/ws-protocol':self.send_header('Sec-WebSocket-Protocol','lumen-chat')
                        self.end_headers();self.wfile.write(b'\x81\x05ready');self.wfile.flush();self.close_connection=True
                        self.connection.settimeout(5)
                        try:
                            header=self.rfile.read(2)
                            if len(header)<2 or header[0]&15!=1:return
                            size=header[1]&127;mask=self.rfile.read(4);payload=self.rfile.read(size)
                            payload=bytes(v^mask[i%4] for i,v in enumerate(payload))
                            self.wfile.write(bytes([129,len(payload)])+payload);self.wfile.flush()
                        except (OSError,IndexError):pass
                        return
                    if route == '/api/me':
                        data = b'{"application":true}'; mime = 'application/json'
                    else:
                        data = b'''<!doctype html><script>
                        localStorage.setItem('project-state',localStorage.getItem('project-state')||'retained');
                        document.cookie='project_cookie=own; Path=/';
                        fetch('/api/me').then(r=>r.json()).then(v=>window.application=v.application);
                        </script><h1>Whole application</h1>'''
                        mime = 'text/html'
                else: return super().handle_request()
                self.send_response(200); self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        cls.server.RequestHandlerClass = Handler

    def test_preview_websocket_without_application_subprotocol(self):
        type(self).application_requests=[];type(self).websocket_protocols=[]
        window=self.import_window(drive=False,pilot=True,app='code');window._code_host.openPreview(FILE)
        dialog=window._code_host.previews[FILE];page=dialog._code_preview[3];probe=SimpleNamespace(page=page)
        self.wait(lambda:self.js(probe,'window.application===true'))
        self.js(probe,"window.socketMessages=[];window.socket=new WebSocket(location.origin.replace('http','ws'));socket.onmessage=e=>{socketMessages.push(e.data);if(e.data==='ready')socket.send('browser-echo')}")
        self.wait(lambda:self.js(probe,"window.socketMessages.includes('browser-echo')"))
        self.assertEqual(self.js(probe,'window.socket.protocol'),'')
        self.assertEqual(self.websocket_protocols,[None])
        dialog.close()

    def test_preview_websocket_keeps_application_protocol_negotiation(self):
        type(self).application_requests=[];type(self).websocket_protocols=[]
        window=self.import_window(drive=False,pilot=True,app='code');window._code_host.openPreview(FILE)
        dialog=window._code_host.previews[FILE];probe=SimpleNamespace(page=dialog._code_preview[3])
        self.wait(lambda:self.js(probe,'window.application===true'))
        for route,accepted in (('/ws-protocol',True),('/ws-reject',False)):
            with self.subTest(route=route):
                self.js(probe,"window.socketMessages=[];window.socket=new WebSocket(location.origin.replace('http','ws')+"+json.dumps(route)+",'lumen-chat');socket.onmessage=e=>{socketMessages.push(e.data);if(e.data==='ready')socket.send('browser-echo')}")
                if accepted:
                    self.wait(lambda:self.js(probe,"window.socketMessages.includes('browser-echo')"))
                    self.assertEqual(self.js(probe,'window.socket.protocol'),'lumen-chat')
                    self.js(probe,'window.socket.close()')
                else:
                    self.wait(lambda:self.js(probe,'window.socket.readyState===WebSocket.CLOSED'))
                    self.assertEqual(self.js(probe,'window.socketMessages.length'),0)
        self.assertEqual(self.websocket_protocols,['lumen-chat','lumen-chat'])
        dialog.close()

    def test_preview_has_own_origin_cookies_storage_and_no_native_channel(self):
        type(self).application_requests = []
        window = self.import_window(drive=False, pilot=True, app='code')
        self.assertTrue(self.js(window, 'typeof window.lumenCodeHost==="object"'))
        self.js(window, "window.applicationOffers=[];window.addEventListener('lumen-code-host',e=>{if(e.detail.status==='result_offer')window.applicationOffers.push(e.detail.offer)})")
        window._code_host.openPreview(FILE)
        self.assertIn(FILE, window._code_host.previews)
        dialog = window._code_host.previews[FILE]
        from PySide6.QtWebEngineWidgets import QWebEngineView
        view = dialog.findChild(QWebEngineView)
        probe = SimpleNamespace(page=view.page())
        try:
            self.wait(lambda: self.js(probe, 'window.application===true'))
        except AssertionError:
            self.fail(repr(dict(url=view.url().toString(), body=self.js(probe, 'document.body?.innerText'), calls=self.application_requests)))
        self.assertEqual(self.js(probe, 'typeof window.lumenCodeHost'), 'undefined')
        self.wait(lambda: self.js(probe, 'typeof window.lumen?.proposeNote==="function"'))
        self.js(probe, "window.lumen.proposeNote({title:'Reviewed application result',body:'Complete application text'})")
        self.wait(lambda: self.js(window, 'window.applicationOffers.length===1'))
        self.assertEqual(self.js(window, 'window.applicationOffers[0].body'), 'Complete application text')
        from PySide6.QtWidgets import QFileDialog
        export = self.import_root / 'application-result.txt'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(export), '')):
            self.js(probe, "(()=>{const a=document.createElement('a');a.download='result.txt';a.href=URL.createObjectURL(new Blob(['Actual application export']));a.click()})()")
            self.wait(lambda: export.exists() and export.read_text() == 'Actual application export')
        self.assertEqual(self.js(probe, 'localStorage.getItem("project-state")'), 'retained')
        self.assertNotIn('lumen_session', self.js(probe, 'document.cookie'))
        self.assertTrue(self.application_requests)
        self.assertTrue(all(row['cookie'] is None for row in self.application_requests))
        self.assertTrue(all(row['bearer'] == 'Bearer native-only-fixture' for row in self.application_requests))
        self.assertTrue(any('project_cookie=own' in (row['app_cookie'] or '') for row in self.application_requests))
        origin = view.url().toString().split('/', 3)[:3]
        self.js(probe, 'localStorage.setItem("project-state","edited")')
        dialog.close(); self.wait(lambda: FILE not in window._code_host.previews)
        self.app.processEvents()
        window._code_host.openPreview(FILE)
        dialog = window._code_host.previews[FILE]; view = dialog.findChild(QWebEngineView)
        probe = SimpleNamespace(page=view.page())
        self.wait(lambda: self.js(probe, 'window.application===true'))
        self.assertEqual(view.url().toString().split('/', 3)[:3], origin)
        self.assertEqual(self.js(probe, 'localStorage.getItem("project-state")'), 'edited')
        from PySide6.QtCore import QUrl
        view.setUrl(QUrl('about:blank'));self.wait(lambda:view.url().toString()=='about:blank')
        dialog._code_preview[6].offer('note','Outside the application','Must not cross the bridge')
        self.assertEqual(self.js(window,'window.applicationOffers.length'),1)
        dialog.close()
