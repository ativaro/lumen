"""Real private Qt pages; synthetic data only, no personal pairing or secrets."""
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWidgets import QFileDialog
from test_server_app_window import PrivateHostFixture
import server_audio_permissions


class VaultInboxHostTest(PrivateHostFixture):
    def test_each_app_opens_only_its_private_bound_page(self):
        for app in ('vault', 'inbox'):
            with self.subTest(app=app):
                window = self.import_window(drive=False, pilot=True, app=app)
                self.assertEqual(window.session.binding.app, app)
                self.assertTrue(window.session.usable)
                self.assertIn('?app='+app+'&presentation=desktop', window.page.url().toString())
                self.assertFalse(window._binding.navigation(self.origin+'/?app=code&presentation=desktop'))

    def test_vault_dirty_guard_never_copies_secret_fields(self):
        window = self.import_window(drive=False, pilot=True, app='vault')
        self.js(window, "document.body.innerHTML='<textarea>synthetic-private-secret</textarea>';window.addEventListener('beforeunload',e=>e.preventDefault());")
        captured=[]; window._capture(lambda:captured.append(True)); self.wait(lambda:bool(captured))
        self.assertEqual(window.session.draft(window._binding), 'unsaved')
        self.assertFalse(window._copy_allowed()); self.assertTrue(window.copy.isHidden())
        settings=window.page.settings()
        self.assertTrue(settings.testAttribute(QWebEngineSettings.JavascriptCanAccessClipboard))
        self.assertFalse(settings.testAttribute(QWebEngineSettings.JavascriptCanPaste))
        with patch.object(window,'_capture') as capture:
            window.block('revoked')
        capture.assert_not_called()
        self.wait(lambda:window.page.lifecycleState()==QWebEnginePage.LifecycleState.Discarded)
        self.assertEqual(window.session.draft(window._binding), '')

    def test_vault_keyfile_requires_fresh_session_and_bounded_regular_selection(self):
        window = self.import_window(drive=False, pilot=True, app='vault')
        key=self.import_root/'fixture.key'; key.write_bytes(b'synthetic-key-file')
        mode=QWebEnginePage.FileSelectOpen
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(key),'')):
            self.assertEqual(server_audio_permissions.choose(window,mode),[str(key)])
        key.write_bytes(b'x'*(1024**2+1))
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(key),'')),patch('server_audio_permissions.QMessageBox.warning'):
            self.assertEqual(server_audio_permissions.choose(window,mode),[])
        def revoke(*args):
            type(self).revoked=True
            return str(key),''
        with patch.object(QFileDialog,'getOpenFileName',side_effect=revoke):
            self.assertEqual(server_audio_permissions.choose(window,mode),[])

    def test_real_blob_export_uses_review_and_private_exclusive_file(self):
        window = self.import_window(drive=False, pilot=True, app='vault')
        target=self.import_root/'export.kdbx'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')) as choose:
            self.js(window,"const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['synthetic-ciphertext']));a.download='Lumen-Vault.kdbx';document.body.append(a);a.click()")
            self.wait(lambda:target.exists())
        self.assertEqual(target.read_bytes(),b'synthetic-ciphertext')
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        self.assertEqual(choose.call_count,1)
        self.assertFalse(list(Path(window._temporary.name).glob('export-*')))
