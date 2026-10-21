"""Native Code entry/chooser/review against synthetic private Qt + HTTPS profiles."""
import json
from pathlib import Path
import socket
from unittest.mock import patch

from PySide6.QtCore import QThread, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QLineEdit, QMessageBox, QPlainTextEdit
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEnginePermission

from test_server_app_window import PrivateHostFixture, USER, DEVICE, FILE, FOLDER
from server_app_session import SessionError
import lumen_connect
import server_audio_permissions as permissions
import server_code_capture

TASK='73000000-0000-4000-8000-000000000005'


class CodeHostTest(PrivateHostFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        original=cls.server.RequestHandlerClass
        class Handler(original):
            def handle_request(self):
                if self.path=='/api/me' and cls.wrong_account:
                    raw=json.dumps(dict(user=dict(id=FOLDER,device_id=DEVICE,desktop_app='code',
                        device_kind='desktop',capabilities=['code'],admin=False,csrf='fixture'))).encode()
                    self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                    return
                if self.path!='/api/code-library':return super().handle_request()
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                cls.code_posts.append(dict(body=body,cookie=self.headers.get('Cookie'),
                    csrf=self.headers.get('X-Lumen-CSRF'),origin=self.headers.get('Origin'),
                    bearer=self.headers.get('Authorization')))
                if cls.drop_code_response:
                    self.close_connection=True
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                raw=json.dumps(dict(id=FILE,title=body['title'])).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        cls.server.RequestHandlerClass=Handler

    def setUp(self):
        super().setUp();type(self).code_posts=[];type(self).wrong_account=False;type(self).drop_code_response=False

    def review(self,action):
        """Operate the real native review dialog; HTTP and the worker stay real."""
        result=[]
        def choose():
            dialog=QApplication.activeModalWidget()
            if not isinstance(dialog,QDialog) or dialog.windowTitle()!='Lumen Code · Als Werkzeug speichern':
                QTimer.singleShot(10,choose);return
            try:action(dialog)
            except BaseException as error:result.append(error);dialog.reject()
        QTimer.singleShot(0,choose)
        return result

    def task(self):
        return patch.object(server_code_capture,'Store',return_value=type('OwnStore',(),{
            'task':lambda self,key:dict(title='Eigene Aufgabe',prompt='Eigener synthetischer Auftrag')})())

    @staticmethod
    def accept(dialog):
        text=dialog.findChild(QPlainTextEdit)
        assert text.isReadOnly() and text.toPlainText()=='Eigener synthetischer Auftrag'
        dialog.findChild(QLineEdit).setText('Eigenes Werkzeug')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()

    def test_code_save_review_posts_once_with_same_cookie_without_worker_qt(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        def gui_only():
            self.assertEqual(QThread.currentThread(),self.app.thread())
            return original_cookie()
        original_cookie=window._cookie_valid
        errors=self.review(self.accept)
        with self.task(),patch.object(window,'_cookie_valid',side_effect=gui_only):
            saved=server_code_capture.capture(window,TASK)
        self.assertFalse(errors)
        self.assertEqual(saved,dict(version=2,app='code',id=FILE,title='Eigenes Werkzeug',
            locator=dict(server=self.origin,account=USER)))
        self.assertEqual(len(self.code_posts),1)
        call=self.code_posts[0]
        self.assertEqual(call['cookie'],'lumen_session='+'c'*43)
        self.assertEqual((call['csrf'],call['origin'],call['bearer']),('fixture',self.origin,None))
        self.assertEqual(call['body']['definition'],dict(prompt='Eigener synthetischer Auftrag'))
        self.assertEqual(call['body']['title'],'Eigenes Werkzeug')
        self.assertTrue(window.session.usable)

    def test_code_save_modal_cancel_and_identity_changes_never_post(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        errors=self.review(lambda dialog:dialog.reject())
        with self.task():self.assertIsNone(server_code_capture.capture(window,TASK))
        self.assertFalse(errors);self.assertFalse(self.code_posts)
        def changed(dialog):
            lumen_connect.save_private(lumen_connect.CONFIG,json.dumps(self.config))
            self.accept(dialog)
        errors=self.review(changed)
        with self.task(),self.assertRaises(SessionError):server_code_capture.capture(window,TASK)
        self.assertFalse(errors);self.assertFalse(self.code_posts)

    def test_code_save_cookie_account_or_revision_revoke_never_posts(self):
        for mode in ('account','revision'):
            with self.subTest(mode=mode):
                type(self).wrong_account=False;type(self).revoked=False
                window=self.import_window(drive=False,pilot=True,app='code')
                def changed(dialog):
                    if mode=='account':type(self).wrong_account=True
                    else:
                        type(self).native_revision+=1;type(self).revoked=True
                    self.accept(dialog)
                errors=self.review(changed)
                with self.task(),self.assertRaises(ValueError):server_code_capture.capture(window,TASK)
                self.assertFalse(errors);self.assertFalse(self.code_posts)
                self.assertFalse(window.session.usable)

    def test_code_save_lost_response_does_not_replay(self):
        window=self.import_window(drive=False,pilot=True,app='code');type(self).drop_code_response=True
        errors=self.review(self.accept)
        with self.task(),self.assertRaises(ValueError):server_code_capture.capture(window,TASK)
        self.assertFalse(errors);self.assertEqual(len(self.code_posts),1)
        self.assertTrue(window.session.uncertain);self.assertFalse(window.session.usable)
        with self.task(),self.assertRaises(SessionError):server_code_capture.capture(window,TASK)
        self.assertEqual(len(self.code_posts),1)

    def test_code_multiple_chooser_is_explicit_and_rejects_modal_generation_or_account_change(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        first=self.import_root/'one.py';second=self.import_root/'two.txt'
        first.write_text('print("Eigen")\n');second.write_text('Eigener Text\n')
        mode=QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
        original_cookie=window._cookie_valid
        def gui_only():
            self.assertEqual(QThread.currentThread(),self.app.thread());return original_cookie()
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(first),str(second)],'')) as picker, \
                patch.object(window,'_cookie_valid',side_effect=gui_only):
            self.assertEqual(permissions.choose(window,mode),[str(first),str(second)])
        picker.assert_called_once()
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([],'')):
            self.assertEqual(permissions.choose(window,mode),[])
        def changed(*args):window._generation+=1;return [str(first)],''
        with patch.object(QFileDialog,'getOpenFileNames',side_effect=changed):
            self.assertEqual(permissions.choose(window,mode),[])
        def changed_account(*args):type(self).wrong_account=True;return [str(first)],''
        with patch.object(QFileDialog,'getOpenFileNames',side_effect=changed_account):
            self.assertEqual(permissions.choose(window,mode),[])
        self.assertFalse(window.session.usable)

    def test_code_chooser_limits_and_secret_files_fail_closed(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        mode=QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
        samples=[('.env.production',b'own=synthetic'),('bad.txt',b'bad\xff'),('nul.txt',b'own\0text'),
            ('large.txt',b'a'*(512*1024+1)),('secret.key',b'own synthetic key')]
        with patch.object(QMessageBox,'warning') as warning:
            for name,data in samples:
                with self.subTest(name=name):
                    target=self.import_root/name;target.write_bytes(data)
                    with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(target)],'')):
                        self.assertEqual(permissions.choose(window,mode),[])
            self.assertEqual(warning.call_count,len(samples))
        target=self.import_root/'own.txt';target.write_text('own')
        with patch.object(QMessageBox,'warning'),patch.object(QFileDialog,'getOpenFileNames',return_value=([str(target)]*257,'')):
            self.assertEqual(permissions.choose(window,mode),[])
        class Permission:
            def isValid(self):return True
            def permissionType(self):return QWebEnginePermission.PermissionType.MediaAudioCapture
            def origin(self):return QUrl(window._binding.origin)
            def grant(self):raise AssertionError('Code cannot grant microphone')
            def deny(self):self.denied=True
        request=Permission()
        with patch.object(QMessageBox,'question',side_effect=AssertionError('No Code microphone prompt')):
            permissions.permission(window,request)
        self.assertTrue(request.denied)

    def test_code_chooser_rechecks_actual_bytes_after_size_check(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        target=self.import_root/'changed.txt';target.write_text('small')
        old_info=target.stat();target.write_bytes(b'x'*(512*1024+1))
        real_lstat=Path.lstat
        def previous_info(path):return old_info if path==target else real_lstat(path)
        with patch.object(Path,'lstat',previous_info),patch.object(QMessageBox,'warning'), \
                patch.object(QFileDialog,'getOpenFileNames',return_value=([str(target)],'')):
            self.assertEqual(permissions.choose(window,QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple),[])

    def test_code_save_task_activation_opens_created_tool_without_reloading(self):
        from server_notes_handoffs import Requests
        window=self.import_window(drive=False,pilot=True,app='code')
        self.js(window,'window.__lumenOpenReference=value=>{window.selectedReference=value;return true}')
        requests=Requests(window);errors=self.review(self.accept)
        with self.task():
            requests.activate(dict(save_task=TASK))
            self.wait(lambda:not requests.pending)
        requests.timer.stop();self.assertFalse(errors);self.assertEqual(len(self.code_posts),1)
        self.assertEqual(self.js(window,'window.selectedReference.id'),FILE)
        self.assertEqual(self.js(window,'window.selectedReference.app'),'code')
        self.assertEqual(window.view.url().toString(),window._binding.url)
        self.assertTrue(window.session.usable)

    def test_code_entry_ref_and_save_task_share_current_private_host(self):
        import code_app
        import server_notes_app
        from interop_data import Registry
        from server_notes_handoffs import Requests
        window=self.import_window(drive=False,pilot=True,app='code')
        self.js(window,'window.__lumenOpenReference=value=>{window.selectedReference=value;return true}')
        activations=[]
        def opened(application,activation,**keywords):
            self.assertIs(application,self.app);self.assertEqual(keywords,dict(kind='code'))
            activations.append(activation);return 9
        with patch.object(code_app,'create_app',return_value=self.app),patch.object(server_notes_app,'run',side_effect=opened):
            self.assertEqual(code_app.main(['--entry',FILE]),9)
            reference=Registry().resolve(activations[-1]['reference'])
            self.assertEqual(reference['locator'],dict(server=self.origin,account=USER))
            self.assertEqual(reference['id'],FILE)
            requests=Requests(window);requests.activate(activations[-1]);self.wait(lambda:not requests.pending);requests.timer.stop()
            self.assertEqual(self.js(window,'window.selectedReference.id'),FILE)
            self.assertEqual(code_app.main(['--ref',activations[-1]['reference']]),9)
            self.assertEqual(activations[-1],activations[-2])
            self.assertEqual(code_app.main(['--save-task',TASK]),9)
            self.assertEqual(activations[-1],dict(save_task=TASK))
            with self.assertRaises(ValueError):code_app.main(['--entry','../../foreign'])
        foreign=dict(reference,locator=dict(server=self.origin,account=FOLDER))
        with self.assertRaises(ValueError):requests.activate(dict(reference=Registry().register(foreign)))
        self.assertFalse(requests.pending)

    def test_code_chooser_rejects_symlink_and_actual_total_over_eight_mib(self):
        window=self.import_window(drive=False,pilot=True,app='code')
        target=self.import_root/'source.txt';target.write_text('own')
        linked=self.import_root/'link.txt';linked.symlink_to(target)
        mode=QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
        with patch.object(QMessageBox,'warning'),patch.object(QFileDialog,'getOpenFileNames',return_value=([str(linked)],'')):
            self.assertEqual(permissions.choose(window,mode),[])
        paths=[]
        for number in range(17):
            value=self.import_root/f'bounded-{number}.txt';value.write_bytes(b'x'*(512*1024));paths.append(str(value))
        with patch.object(QFileDialog,'getOpenFileNames',return_value=(paths[:16],'')):
            self.assertEqual(permissions.choose(window,mode),paths[:16])
        with patch.object(QMessageBox,'warning'),patch.object(QFileDialog,'getOpenFileNames',return_value=(paths,'')):
            self.assertEqual(permissions.choose(window,mode),[])

    def test_code_dom_multiple_file_input_uses_private_native_chooser(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        window=self.import_window(drive=False,pilot=True,app='code')
        first=self.import_root/'main.py';second=self.import_root/'README.md'
        first.write_text('print("Eigen")\n');second.write_text('# Eigener Text\n')
        self.js(window,"const picker=document.createElement('input');picker.type='file';picker.multiple=true;"
            "picker.id='own-code-picker';picker.style='position:fixed;left:10px;top:10px;width:300px;height:50px;z-index:100';"
            "picker.onchange=async()=>window.picked=await Promise.all(Array.from(picker.files,f=>f.text()));document.body.append(picker)")
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(first),str(second)],'')) as picker:
            self.wait(lambda:window.stack.currentWidget() is window.view)
            window.view.setFocus();self.app.processEvents()
            QTest.mouseClick(window.view.focusProxy() or window.view,Qt.MouseButton.LeftButton,pos=QPoint(40,30))
            self.wait(lambda:self.js(window,'Array.isArray(window.picked)'))
        picker.assert_called_once()
        self.assertEqual(json.loads(self.js(window,'JSON.stringify(window.picked)')),['print("Eigen")\n','# Eigener Text\n'])
        self.assertTrue(window.session.usable)
