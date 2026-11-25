"""Actual private Qt profiles and HTTPS; project applications never get a Lumen cookie."""
import json
import base64
import hashlib
import os
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from test_server_app_window import PrivateHostFixture, FILE, USER, FOLDER


class NativeProjectHostTest(PrivateHostFixture):
    def git_review(self, action):
        from lumen_i18n import tr
        seen, errors = [], []
        timer = QTimer(); self.addCleanup(timer.stop)
        def inspect():
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, QMessageBox) or dialog.windowTitle() != tr('Lumen Code · Git-Zugriff prüfen'): return
            timer.stop(); seen.append(dialog)
            try:
                self.assertEqual(dialog.textFormat(), Qt.PlainText)
                self.assertIs(dialog.defaultButton(), dialog.button(QMessageBox.Cancel))
                action(dialog)
            except BaseException as error:
                errors.append(error); dialog.reject()
        timer.timeout.connect(inspect); timer.start(5)
        return seen, errors

    @staticmethod
    def approve_git(dialog):
        next(button for button in dialog.buttons() if dialog.buttonRole(button) == QMessageBox.AcceptRole).click()

    def test_git_cancel_default_escape_and_close_never_clone_or_upload(self):
        window = self.import_window(drive=False, pilot=True, app='code')
        evidence = os.environ.get('LUMEN_CAPTURE_EVIDENCE')
        self.wait(lambda:self.js(window, 'document.readyState') == 'complete')
        QTest.qWait(150)
        if evidence: self.assertTrue(window.grab().save(str(Path(evidence)/'git-window.png')))
        for action in (lambda d:d.button(QMessageBox.Cancel).click(), lambda d:d.defaultButton().click(),
                       lambda d:QTest.keyClick(d, Qt.Key_Escape), lambda d:d.close()):
            seen, errors = self.git_review(action)
            with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder') as upload:
                window._code_host.cloneGit(FILE, 'https://git.example.invalid/team/private.git')
            self.assertFalse(errors); self.assertTrue(seen)
            clone.assert_not_called(); upload.assert_not_called()
            self.assertFalse(window._code_host.transfers)

    def test_git_bridge_approval_binds_literal_remote_and_destination(self):
        from appearance import apply_design
        window = self.import_window(drive=False, pilot=True, app='code')
        remotes = ('https://git.example.invalid/team/private.git', 'git@git.example.invalid:team/private.git',
                   'https://git.example.invalid/<b>private</b>.git', 'ssh://git@git.example.invalid/ü\u202eteam.git')
        for theme, remote in zip(('graphite', 'glass', 'atelier', 'midnight'), remotes):
            apply_design(self.app, theme)
            def accept(dialog):
                for value in (json.dumps(remote, ensure_ascii=True), self.origin, USER, FILE): self.assertIn(value, dialog.text())
                self.assertEqual(dialog.button(QMessageBox.Cancel).text(), 'Abbrechen')
                for button in dialog.buttons():
                    self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
                evidence = os.environ.get('LUMEN_CAPTURE_EVIDENCE')
                if evidence: self.assertTrue(dialog.grab().save(str(Path(evidence)/('git-review-'+theme+'.png'))))
                self.approve_git(dialog)
            seen, errors = self.git_review(accept)
            self.js(window, "window.gitStates=[];window.addEventListener('lumen-code-host',e=>gitStates.push(e.detail.status),{once:false})")
            with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder', return_value={}) as upload:
                self.js(window, 'window.lumenCodeHost.cloneGit('+json.dumps(FILE)+','+json.dumps(remote)+')')
                self.wait(lambda:self.js(window, "gitStates.includes('imported')"))
            self.assertFalse(errors); self.assertTrue(seen)
            clone.assert_called_once(); upload.assert_called_once()
            self.assertEqual(clone.call_args.args[0], remote)
            self.assertEqual(upload.call_args.args[:3], (self.config, FILE, 1))

    def test_git_consent_explains_credentials_and_full_transfer_in_english(self):
        from appearance import apply_design
        apply_design(self.app, 'graphite')
        window = self.import_window(drive=False, pilot=True, app='code')
        def cancel(dialog):
            self.assertEqual(dialog.windowTitle(), 'Lumen Code · Review Git access')
            self.assertIn('Clone and transfer this Git repository?', dialog.text())
            self.assertIn('existing Git credentials and SSH agent', dialog.informativeText())
            self.assertIn('entire cloned project folder', dialog.informativeText())
            self.assertEqual(dialog.defaultButton().text(), 'Cancel')
            self.assertIn('Clone and transfer', [b.text() for b in dialog.buttons()])
            evidence = os.environ.get('LUMEN_CAPTURE_EVIDENCE')
            if evidence: self.assertTrue(dialog.grab().save(str(Path(evidence)/'git-review-en.png')))
            dialog.defaultButton().click()
        with patch('lumen_i18n.language', return_value='en'):
            seen, errors = self.git_review(cancel)
            with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder') as upload:
                window._code_host.cloneGit(FILE, 'https://git.example.invalid/team/private.git')
        self.assertFalse(errors); self.assertTrue(seen)
        clone.assert_not_called(); upload.assert_not_called()

    def test_git_approval_does_not_survive_identity_or_generation_changes(self):
        import lumen_connect
        for mode in ('binding', 'session-binding', 'window', 'session', 'connection'):
            window = self.import_window(drive=False, pilot=True, app='code')
            def change(dialog):
                if mode == 'binding': window._binding = replace(window._binding, account=FOLDER)
                elif mode == 'session-binding': window.session.binding = replace(window.session.binding, account=FOLDER)
                elif mode == 'window': window._generation += 1
                elif mode == 'session': window.session._generation += 1
                else: lumen_connect.save_private(lumen_connect.CONFIG, json.dumps(self.config))
                self.approve_git(dialog)
            seen, errors = self.git_review(change)
            with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder') as upload:
                window._code_host.cloneGit(FILE, 'https://git.example.invalid/team/private.git')
            self.assertFalse(errors); self.assertTrue(seen)
            clone.assert_not_called(); upload.assert_not_called()

    def test_git_reentrant_requests_cannot_replace_approval_or_release_its_guard(self):
        window = self.import_window(drive=False, pilot=True, app='code'); host = window._code_host
        remote = 'https://git.example.invalid/team/approved.git'
        def reenter(dialog):
            for identity in (FILE, FOLDER):
                host.cloneGit(identity, 'https://git.example.invalid/other/private.git')
                self.assertEqual(host.transfers, {FILE})
            self.approve_git(dialog)
        seen, errors = self.git_review(reenter)
        with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder', return_value={}):
            host.cloneGit(FILE, remote)
        self.assertFalse(errors); self.assertTrue(seen)
        clone.assert_called_once(); self.assertEqual(clone.call_args.args[0], remote)
        self.assertFalse(host.transfers)

    def test_git_rechecks_context_after_runtime_info_before_clone_and_upload(self):
        import lumen_connect
        original = lumen_connect.request
        for revoked_after in (1, 2):
            window = self.import_window(drive=False, pilot=True, app='code'); infos = []
            def changed(config, path, *args, **kwargs):
                value = original(config, path, *args, **kwargs)
                if path.endswith('/runtime/info'):
                    infos.append(path)
                    if len(infos) == revoked_after: window._generation += 1
                return value
            seen, errors = self.git_review(self.approve_git)
            with patch('server_code_host.clone_git') as clone, patch('server_code_host.import_folder') as upload, patch.object(lumen_connect, 'request', side_effect=changed):
                window._code_host.cloneGit(FILE, 'https://git.example.invalid/team/private.git')
            self.assertFalse(errors); self.assertTrue(seen)
            self.assertEqual(clone.call_count, revoked_after - 1); upload.assert_not_called()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        original = cls.server.RequestHandlerClass
        class Handler(original):
            protocol_version='HTTP/1.1'
            def handle_request(self):
                prefix = '/bridge/code-library/' + FILE
                code='/api/code-library/'+FILE+'/runtime/'
                if self.path.startswith(code+'patch?') or self.path==code+'jobs/'+('a'*32)+'/log':
                    data=(b'Complete retained Code output\n'*70000)
                    self.send_response(200);self.send_header('Content-Type','application/octet-stream')
                    self.send_header('Content-Disposition','attachment; filename="code-output.txt"')
                    self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
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
                        if route=='/ws-http10':self.protocol_version='HTTP/1.0'
                        self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept)
                        if route=='/ws-protocol':self.send_header('Sec-WebSocket-Protocol','lumen-chat')
                        self._headers_buffer.append(b'\r\n')
                        packet=b''.join(self._headers_buffer)+b'\x81\x05ready';self._headers_buffer=[]
                        self.wfile.write(packet);self.wfile.flush();self.close_connection=True
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
        for route in ('/','/ws-http10'):
            self.js(probe,"window.socketMessages=[];window.socket=new WebSocket(location.origin.replace('http','ws')+"+json.dumps(route)+");socket.onmessage=e=>{socketMessages.push(e.data);if(e.data==='ready')socket.send('browser-echo')}")
            self.wait(lambda:self.js(probe,"window.socketMessages.includes('browser-echo')"))
            self.assertEqual(self.js(probe,'window.socket.protocol'),'')
            self.js(probe,'window.socket.close()')
        self.assertEqual(self.websocket_protocols,[None,None])
        dialog.close()

    def test_code_patch_and_job_log_use_the_native_reviewed_download(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        from PySide6.QtWidgets import QFileDialog
        paths=['patch?tree='+('a'*40)+'&head='+('b'*40),'jobs/'+('a'*32)+'/log']
        for i,path in enumerate(paths):
            target=self.import_root/('reviewed-code-'+str(i)+'.txt')
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
                self.js(window,"(()=>{const a=document.createElement('a');a.download='code-output.txt';a.href="+json.dumps(self.origin+'/api/code-library/'+FILE+'/runtime/'+path)+";a.click()})()")
                self.wait(lambda:target.exists() and target.stat().st_size==len(b'Complete retained Code output\n')*70000)
                self.assertEqual(target.read_bytes(),b'Complete retained Code output\n'*70000)

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
