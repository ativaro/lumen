"""Real private Qt pages; synthetic data only, no personal pairing or secrets."""
import json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from test_server_app_window import PrivateHostFixture
import server_audio_permissions


class VaultInboxHostTest(PrivateHostFixture):
    def test_inbox_authorization_opens_system_browser_without_leaving_bound_page(self):
        window=self.import_window(drive=False,pilot=True,app='inbox')
        address=self.origin+'/api/inbox/oauth/launch/'+'a'*43
        kind=QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        with patch.object(QDesktopServices,'openUrl',return_value=True) as opened:
            self.assertFalse(window.page.acceptNavigationRequest(QUrl(address),kind,True))
            opened.assert_called_once_with(QUrl(address))
            opened.reset_mock()
            self.assertFalse(window.page.acceptNavigationRequest(QUrl('https://accounts.google.com/'),kind,True))
            opened.assert_not_called()
        self.assertTrue(window._binding.navigation(window.page.url().toString()))

    def test_photos_selects_multiple_files_and_rejects_symlinks(self):
        window = self.import_window(drive=False, pilot=True, app='photos')
        first = self.import_root/'one.heic'; first.write_bytes(b'synthetic selection')
        second = self.import_root/'two.mov'; second.write_bytes(b'synthetic selection')
        mode = QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
        paths = [str(first), str(second)]
        with patch.object(QFileDialog,'getOpenFileNames',return_value=(paths,'')):
            self.assertEqual(server_audio_permissions.choose(window,mode),paths)
        link = self.import_root/'linked.heic'; link.symlink_to(first)
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(link)],'')), patch('server_audio_permissions.QMessageBox.warning'):
            self.assertEqual(server_audio_permissions.choose(window,mode),[])

    def test_inbox_selects_multiple_regular_attachments_without_vault_size_cap(self):
        window = self.import_window(drive=False, pilot=True, app='inbox')
        first=self.import_root/'synthetic-large.bin'
        with first.open('wb') as file:file.truncate(80*1024**2)
        second=self.import_root/'synthetic-note.txt';second.write_text('Attachment')
        paths=[str(first),str(second)]
        mode=QWebEnginePage.FileSelectionMode.FileSelectOpenMultiple
        with patch.object(QFileDialog,'getOpenFileNames',return_value=(paths,'')):
            self.assertEqual(server_audio_permissions.choose(window,mode),paths)
        link=self.import_root/'synthetic-link';link.symlink_to(second)
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(link)],'')),patch('server_audio_permissions.QMessageBox.warning'):
            self.assertEqual(server_audio_permissions.choose(window,mode),[])

    def test_inbox_displays_sandboxed_mail_text_and_blob_image(self):
        window = self.import_window(drive=False, pilot=True, app='inbox')
        self.js(window, """
            window.mailReady=false;window.mailScriptRan=false;
            const frame=document.createElement('iframe');frame.title='Nachrichteninhalt';
            frame.sandbox='allow-same-origin allow-popups allow-popups-to-escape-sandbox';
            frame.onload=()=>{
                const doc=frame.contentDocument;if(doc?.title!=='Mail')return;
                doc.body.innerHTML='<h1>Eigene Testnachricht</h1><p>Diese Nachricht ist lesbar.</p>';
                const script=doc.createElement('script');script.textContent='parent.mailScriptRan=true';doc.body.append(script);
                const image=doc.createElement('img');image.alt='Eigenes Testbild';
                image.onload=()=>window.mailReady=true;
                const pixels=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACXBIWXMAAA9hAAAPYQGoP6dpAAAADUlEQVQImWOY/fTGfwAHzwNY8lBVJwAAAABJRU5ErkJggg=='),c=>c.charCodeAt(0));
                image.src=URL.createObjectURL(new Blob([pixels],{type:'image/png'}));doc.body.append(image);
            };
            frame.src=""" + json.dumps(self.origin+'/inbox-message.html') + ";document.body.append(frame)")
        self.wait(lambda: self.js(window, 'window.mailReady'), timeout=5000)
        self.assertIn('Diese Nachricht ist lesbar.',self.js(window,"document.querySelector('iframe').contentDocument.body.innerText"))
        self.assertFalse(self.js(window,'window.mailScriptRan'))
        calls=[row for row in self.calls[self.import_call_start:] if row['path']=='/inbox-message.html']
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0]['cookie']);self.assertFalse(calls[0]['bearer'])

    def test_each_app_opens_only_its_private_bound_page(self):
        for app in ('vault', 'inbox', 'photos'):
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
