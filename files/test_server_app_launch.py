"""Missing device rights stay actionable through the real background-job dialog."""
import threading
import sys
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
import server_notes_app as launch
from server_app_session import SessionError


class LaunchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.enterContext(patch('lumen_i18n.language', return_value='de'))
        self.config = dict(server='https://synthetic.invalid', device_id=str(uuid4()), token='NEVER_IN_BROWSER')
        self.me = dict(id=str(uuid4()), device_id=self.config['device_id'], capabilities=['notes'], permissions_revision=2)
        self.stamp = ('synthetic-private-config',)
        self.enterContext(patch.object(launch, '_connection', side_effect=lambda: (dict(self.config), self.stamp)))
        self.enterContext(patch.object(launch.lumen_connect, 'request', side_effect=lambda *a, **k: dict(self.me)))
        self.job = SimpleNamespace(check=lambda: None)

    def test_missing_code_and_audio_rights_are_permissions_not_identity(self):
        for kind, capability in (('code', 'code'), ('audio', 'media')):
            with self.subTest(kind=kind), self.assertRaises(SessionError) as caught:
                launch.context(self.job, kind)
            self.assertEqual(caught.exception.kind, 'permission')
            self.assertNotIn(capability, self.me['capabilities'])

    def test_invalid_identity_is_not_presented_as_missing_right(self):
        self.me['device_id'] = str(uuid4())
        with self.assertRaises(SessionError) as caught:
            launch.context(self.job, 'code')
        self.assertEqual(caught.exception.kind, 'identity')

    def test_granted_code_and_audio_open_their_own_binding(self):
        self.me['capabilities'] = ['notes', 'code', 'media']
        for kind in ('code', 'audio'):
            with self.subTest(kind=kind):
                checked = launch.context(self.job, kind)
                self.assertEqual(checked[1].app, kind)
                self.assertEqual(checked[3], 2)

    def timer(self, function):
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(function)
        timer.start()
        self.addCleanup(timer.stop)
        return timer

    def test_real_worker_permission_dialog_browser_and_explicit_retry(self):
        opened = []
        owner_thread = threading.get_ident()
        requests = []
        def profile(*args, **kwargs):
            requests.append(threading.get_ident())
            return dict(self.me)
        self.enterContext(patch.object(launch.lumen_connect, 'request', side_effect=profile))
        from PySide6.QtGui import QDesktopServices
        self.enterContext(patch.object(QDesktopServices, 'openUrl', side_effect=lambda url: opened.append(url.toString()) or True))
        self.enterContext(patch('lumen_connect_gui.ConnectionDialog', side_effect=AssertionError('No re-pair wizard')))
        def answer():
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, QMessageBox):
                return
            self.assertEqual(dialog.textFormat(), Qt.PlainText)
            self.assertIn('Lumen Code', dialog.text())
            self.assertIn('Serverdaten', dialog.text())
            self.assertNotIn(self.config['token'], dialog.text())
            if not opened:
                next(b for b in dialog.buttons() if b.text() == 'Gerätefreigabe öffnen').click()
            else:
                # This stands for the owner enabling the scope in the server UI.
                self.me['capabilities'] = ['notes', 'code']
                next(b for b in dialog.buttons() if b.text() == 'Erneut prüfen').click()
        timer = self.timer(answer)
        checked = launch.verify_context('code')
        timer.stop()
        self.assertEqual(checked[1].app, 'code')
        self.assertEqual(opened, [self.config['server'] + '/?app=devices&device=' + self.config['device_id']])
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(thread != owner_thread for thread in requests))

    def test_close_keeps_rights_unchanged(self):
        def answer():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                next(b for b in dialog.buttons() if b.text() == 'Schließen').click()
        timer = self.timer(answer)
        self.assertIsNone(launch.verify_context('audio'))
        timer.stop()
        self.assertEqual(self.me['capabilities'], ['notes'])

    def test_retired_rooms_cli_fails_before_app_or_network_start(self):
        import tools_app
        with patch.object(sys,'argv',['tools_app.py','workbench','--section','rooms']), \
             patch('lumen_paths.require_test_profile'),patch.object(tools_app,'pilot_profile',return_value=None), \
             patch.object(tools_app,'create_app',side_effect=AssertionError('No app start')):
            with self.assertRaises(SystemExit) as caught:tools_app.main()
        self.assertEqual(caught.exception.code,2)

    def test_new_reference_receiver_does_not_reuse_old_window_ipc_or_drafts(self):
        from server_app_session import Binding
        binding=Binding(self.config['server'],self.me['id'],self.config['device_id'],'notes')
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(launch.QStandardPaths,'writableLocation',return_value=temporary):
            root=Path(temporary)
            old=root/('lumen-notes-'+hashlib.sha256(json.dumps([binding.origin,binding.account,binding.device,self.stamp]).encode()).hexdigest()[:24])
            old.mkdir(mode=0o700);draft=old/'own-draft';draft.write_text('Unsaved original')
            target=launch.runtime_root(binding,self.stamp)
            self.assertNotEqual(target,old)
            self.assertEqual(target,launch.runtime_root(binding,self.stamp))
            self.assertEqual(draft.read_text(),'Unsaved original')

    def test_cancel_does_not_reopen_recovery(self):
        with patch('interop_dialogs.run_job', return_value=None), patch.object(launch, 'recover') as recover:
            self.assertIsNone(launch.verify_context('code'))
            recover.assert_not_called()

    def test_code_preview_receiver_does_not_forward_to_the_old_link_only_host(self):
        from server_app_session import Binding
        for app in ('code','notes'):
            with self.subTest(app=app), tempfile.TemporaryDirectory() as temporary, \
                 patch.object(launch.QStandardPaths,'writableLocation',return_value=temporary):
                binding=Binding(self.config['server'],self.me['id'],self.config['device_id'],app)
                old=Path(temporary)/('lumen-'+app+'-'+hashlib.sha256(json.dumps([binding.origin,binding.account,binding.device,self.stamp,'app-links-1']).encode()).hexdigest()[:24])
                old.mkdir(mode=0o700);draft=old/'own-draft';draft.write_text('Keep old live draft')
                target=launch.runtime_root(binding,self.stamp)
                if app=='code':self.assertNotEqual(target,old)
                else:self.assertEqual(target,old)
                self.assertEqual(draft.read_text(),'Keep old live draft')

    def test_normal_launch_without_right_never_creates_host(self):
        def answer():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                next(b for b in dialog.buttons() if b.text() == 'Schließen').click()
        timer = self.timer(answer)
        with patch.object(launch, 'ServerAppWindow') as host, patch.object(launch, 'runtime_root') as runtime:
            self.assertEqual(launch.run(self.app, kind='code'), 1)
            host.assert_not_called()
            runtime.assert_not_called()
        timer.stop()

    def test_code_reference_entry_uses_same_recovery(self):
        import code_app
        with patch.object(code_app, 'create_app', return_value=self.app), patch.object(launch, 'verify_context', return_value=None) as verify:
            self.assertEqual(code_app.main(['--entry', str(uuid4())]), 1)
            verify.assert_called_once_with('code')

    def test_recovery_link_rejects_invalid_origin_and_device(self):
        from PySide6.QtGui import QDesktopServices
        for key, value in (('server', 'https://foreign.invalid/?token=secret'), ('device_id', '../secret')):
            with self.subTest(key=key):
                config = dict(self.config, **{key: value})
                with patch.object(launch, '_connection', return_value=(config, self.stamp)), patch.object(QDesktopServices, 'openUrl') as opened:
                    with self.assertRaises((SessionError, ValueError)):
                        launch.open_device_permissions()
                    opened.assert_not_called()

    def test_changed_pairing_never_opens_stale_device_link(self):
        from PySide6.QtGui import QDesktopServices
        with patch.object(launch, '_connection', side_effect=[(self.config, self.stamp), (self.config, ('changed',))]), patch.object(QDesktopServices, 'openUrl') as opened:
            with self.assertRaises(SessionError):
                launch.open_device_permissions()
            opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
