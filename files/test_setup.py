import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
import time
from unittest.mock import patch

import lumen_setup as setup


class SetupTest(unittest.TestCase):
    def test_managed_engine_install_is_verified_atomic_and_used_by_lumen(self):
        import tarfile
        from types import SimpleNamespace
        from assistant_backend import ENGINE_VERSION, managed_opencode, opencode_binary
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME':tmp, 'LUMEN_OPENCODE_BIN':''}):
            target = managed_opencode(); target.parent.mkdir(parents=True)
            target.write_bytes(b'previous-engine'); target.chmod(0o700)
            def archive(_url, path, checksum, size):
                self.assertIn('/v'+ENGINE_VERSION+'/', _url)
                self.assertEqual(len(checksum), 64); self.assertGreater(size, 50_000_000)
                with tarfile.open(path, 'w:gz') as bundle:
                    data=b'verified-test-engine'; info=tarfile.TarInfo('opencode'); info.size=len(data)
                    bundle.addfile(info, io.BytesIO(data))
            with patch.object(setup.platform, 'machine', return_value='x86_64'), \
                    patch.object(setup, 'download', side_effect=archive), patch.object(setup, 'report'), \
                    patch.object(setup.subprocess, 'run', return_value=SimpleNamespace(stdout='wrong')) as version:
                with self.assertRaises(ValueError): setup.install_engine()
                self.assertEqual(target.read_bytes(), b'previous-engine')
                version.return_value.stdout=ENGINE_VERSION+'\n'; setup.install_engine()
                self.assertEqual(target.read_bytes(), b'verified-test-engine')
                self.assertEqual(target.stat().st_mode & 0o777, 0o700)
                self.assertEqual(opencode_binary(), str(target))
                self.assertEqual(setup.executable('opencode'), str(target))
                self.assertEqual(list(target.parent.iterdir()), [target])
                with patch.dict(os.environ, {'LUMEN_OPENCODE_BIN':'/explicit/opencode'}):
                    self.assertEqual(opencode_binary(), '/explicit/opencode')
                    with self.assertRaises(RuntimeError): setup.install_engine()
            with patch('sys.argv', ['lumen_setup.py','packages','engine']), \
                    patch.object(setup, 'install_engine') as install, patch.object(setup, 'install_packages') as packages, \
                    patch.object(setup, 'report'):
                self.assertEqual(setup.main(), 0)
                install.assert_called_once(); packages.assert_called_once_with([])

    def test_desktop_job_uses_existing_backup_flow_and_reports_failure(self):
        with patch('sys.argv', ['lumen_setup.py', 'desktop', '--theme', 'atelier']), \
                patch('lumen_desktop_setup.configure_desktop') as configure, patch.object(setup, 'report') as report:
            self.assertEqual(setup.main(), 0)
            configure.assert_called_once_with('atelier', replace_panels=True)
            self.assertFalse(report.call_args.kwargs['cancellable'])
            configure.side_effect = RuntimeError('Plasma nicht erreichbar')
            self.assertEqual(setup.main(), 1)
            self.assertIn('Plasma nicht erreichbar', report.call_args.args[0])

    def test_download_is_verified_and_atomic(self):
        data = b'a multilingual speech model'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model'; path.write_bytes(b'previous model')
            def response(*_args, **_kwargs):
                stream = io.BytesIO(data); stream.url = 'https://example.test/model'; return stream
            with patch.object(setup.urllib.request, 'urlopen', side_effect=response), patch.object(setup, 'report'):
                for checksum, size in [('0' * 64, len(data)), (hashlib.sha256(data).hexdigest(), 1)]:
                    with self.assertRaises(ValueError): setup.download('https://example.test/model', path, checksum, size)
                    self.assertEqual(path.read_bytes(), b'previous model')
                    self.assertEqual(list(Path(tmp).iterdir()), [path])
                setup.download('https://example.test/model', path, hashlib.sha256(data).hexdigest(), len(data))
                self.assertEqual(path.read_bytes(), data)

    def test_multilingual_voice_is_ready_only_after_verified_files_and_smoke_test(self):
        payload = b'verified model'
        manifest = (('model.safetensors', hashlib.sha256(payload).hexdigest(), len(payload)),)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'qwen-env/bin').mkdir(parents=True)
            (root/'qwen-env/bin/python').touch()
            def download(url, target, checksum, size):
                target.write_bytes(payload)
            def failed_check(args, **kwargs):
                if '--check' in args: raise RuntimeError('GPU test failed')
            with patch.object(setup, 'speech_root', return_value=root), patch('speech_model.MODEL_FILES', manifest), \
                    patch.object(setup, 'download', side_effect=download) as fetch, patch.object(setup, 'report'), \
                    patch.object(setup, 'run', side_effect=failed_check) as run:
                with self.assertRaises(RuntimeError): setup.install_multilingual_voice()
                self.assertFalse((root/'qwen-0.6b/.ready').exists())
                fetch.assert_called_once()
                run.side_effect = None
                setup.install_multilingual_voice()
                self.assertTrue((root/'qwen-0.6b/.ready').is_file())
                fetch.assert_called_once()  # A valid download is reused on retry.

    def test_existing_tools_and_models_are_reused_without_install_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / 'ggml-small-q5_1.bin'; model.write_bytes(b'model')
            (root/'vad-env').mkdir(); (root/'vad-env/.ready').write_text('webrtcvad-wheels==2.0.14\n')
            with patch.object(setup, 'speech_root', return_value=root), patch.object(setup, 'executable', return_value='/existing/tool'), \
                    patch.object(setup, 'MODEL_SIZE', 5), patch.object(setup, 'MODEL_HASH', hashlib.sha256(b'model').hexdigest()), \
                    patch.object(setup, 'download') as download, patch.object(setup, 'run') as run, patch.object(setup, 'report'):
                self.assertEqual(setup.missing_packages(['engine', 'documents']), [])
                setup.install_dictation()
                download.assert_not_called(); run.assert_not_called()
                with self.assertRaises(ValueError): setup.install_packages(['unapproved-package'])

    def test_pause_detector_is_marked_ready_only_after_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'vad-env/bin').mkdir(parents=True)
            (root/'vad-env/bin/python').touch()
            def fail_check(args, **kwargs):
                if '-c' in args: raise RuntimeError('VAD unavailable')
            with patch.object(setup, 'speech_root', return_value=root), patch.object(setup, 'executable', return_value=''), \
                    patch.object(setup, 'install_packages'), patch.object(setup, 'report'), \
                    patch.object(setup, 'run', side_effect=fail_check) as run:
                with self.assertRaises(RuntimeError): setup.install_vad()
                self.assertFalse((root/'vad-env/.ready').exists())
                run.side_effect = None; setup.install_vad()
                self.assertEqual((root/'vad-env/.ready').read_text(), 'webrtcvad-wheels==2.0.14\n')
                (root/'vad-env/.ready').write_text('webrtcvad-wheels==2.0.13\n')
                with patch.object(setup, 'executable', return_value='/existing/python'):
                    run.reset_mock(); setup.install_vad()
                    self.assertTrue(any('webrtcvad-wheels==2.0.14' in call.args[0] for call in run.call_args_list))
                    run.reset_mock(); setup.install_vad(); run.assert_not_called()

    def test_discovery_uses_same_user_install_for_setup_and_dictation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp}), \
                patch.object(setup.shutil, 'which', return_value=None):
            binary = setup.speech_root() / ('whisper-' + setup.VERSION)
            binary.parent.mkdir(parents=True); binary.write_text('#!/bin/sh\nexit 0\n'); binary.chmod(0o755)
            self.assertEqual(setup.executable('whisper-cli'), str(binary))
            binary.chmod(0o644)
            self.assertFalse(setup.executable('whisper-cli'))

    def test_quality_model_is_verified_and_preserves_existing_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); small = root / 'ggml-small-q5_1.bin'; small.write_bytes(b'old')
            def download(url, path, checksum, size):
                self.assertTrue(url.endswith('/' + setup.QUALITY_MODEL))
                self.assertEqual((checksum,size),(setup.QUALITY_HASH,setup.QUALITY_SIZE))
                path.write_bytes(b'quality')
            with patch.object(setup,'speech_root',return_value=root), patch.object(setup,'executable',return_value='/existing/tool'), \
                    patch.object(setup,'download',side_effect=download) as fetch, patch.object(setup,'report') as report:
                setup.install_dictation(str(small),quality=True)
                fetch.assert_called_once(); self.assertEqual(small.read_bytes(),b'old')
                self.assertEqual(report.call_args.kwargs['model'],str(root/setup.QUALITY_MODEL))


class SetupDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = create_app()

    def test_wizard_preserves_config_and_only_saves_auth_after_click(self):
        from PySide6.QtCore import QSettings
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            settings = QSettings(tmp + '/preferences.ini', QSettings.IniFormat)
            settings.setValue('model', 'ollama-cloud/existing'); settings.setValue('autoApproveTools', False)
            dialog = SetupDialog(settings=settings)
            calls = []
            def request(method, path, body=None, callback=None, error=None):
                calls.append((method, path, body))
                if path == '/provider': callback({'all': [{'id': 'ollama-cloud', 'name': 'Ollama Cloud',
                    'models': {'existing': {'name': 'Existing'}}}], 'connected': ['ollama-cloud']})
                elif path in ('/config', '/provider/auth'): callback({})
                elif path == '/auth/ollama-cloud': callback(True)
                else: self.fail('Unexpected endpoint: ' + path)
            def ensure(callback): dialog.engine.url = 'http://127.0.0.1:1'; callback()
            with patch.object(dialog.engine, 'ensure_server', side_effect=ensure), patch.object(dialog.engine, 'request', side_effect=request):
                self.assertEqual(calls, [])
                dialog.load_engine()
                self.assertEqual(dialog.models.currentData(), 'ollama-cloud/existing')
                self.assertTrue(all(method == 'GET' for method, _, _ in calls))
                dialog.key.setText('test-only-key'); dialog.connect_provider.click()
                self.assertEqual([c for c in calls if c[0] == 'PUT'],
                                 [('PUT', '/auth/ollama-cloud', {'type': 'api', 'key': 'test-only-key'})])
                self.assertEqual(dialog.key.text(), '')
            dialog.reject()
            self.assertEqual(settings.value('model'), 'ollama-cloud/existing')
            self.assertFalse(settings.value('autoApproveTools', type=bool))
            self.assertTrue(settings.value('setupSeen', type=bool))
            self.assertFalse(settings.value('setupCompleted', False, type=bool))
            from setup_dialog import offer_setup
            with patch('setup_dialog.QSettings', return_value=settings), patch('setup_dialog.open_setup') as opened:
                offer_setup(None); opened.assert_not_called()
                settings.setValue('setupSeen', False)
                offer_setup(None); opened.assert_called_once()
            reopened = SetupDialog(settings=settings, page=4)
            reopened.next.click()
            self.assertTrue(settings.value('setupCompleted', type=bool))
            dialog.deleteLater(); reopened.deleteLater()

    def test_fresh_zen_profile_selects_engine_default_without_api_key(self):
        from PySide6.QtCore import QSettings
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
            dialog = SetupDialog(settings=settings)
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            inventory = {'all': [{'id': 'opencode', 'name': 'OpenCode Zen', 'models': {
                'free-a': {'name': 'Free A', 'cost': {'input': 0, 'output': 0}, 'capabilities': {'toolcall': True}},
                'free-b': {'name': None, 'cost': {'input': 0, 'output': 0}, 'capabilities': {'toolcall': True}},
                'paid': {'cost': {'input': 1, 'output': 2}}, 'unavailable': None}}],
                'connected': ['opencode'], 'default': {'opencode': 'free-b'}}
            def request(method, path, body=None, callback=None, error=None):
                self.assertEqual((method, path), ('GET', '/provider/auth'))
                callback({})
            with patch.object(dialog.engine, 'request', side_effect=request):
                dialog.loaded_providers(inventory)
                self.assertEqual(dialog.models.currentData(), 'opencode/free-b')
                self.assertEqual(dialog.models.currentText(), 'OpenCode Zen · free-b')
                self.assertEqual(settings.value('model'), 'opencode/free-b')
                self.assertIn('Gratis-Modell bereit', dialog.model_summary.text())
                self.assertEqual(dialog.key.text(), '')
                dialog.models.setCurrentIndex(dialog.models.findData('opencode/free-a'))
                dialog.loaded_providers(inventory)
                self.assertEqual(dialog.models.currentData(), 'opencode/free-a')
                dialog.stack.setCurrentIndex(1); dialog.change_page(1)
                self.assertEqual(settings.value('model'), 'opencode/free-a')
                inventory['all'][0]['models'] = {}
                dialog.loaded_providers(inventory)
                self.assertFalse(dialog.models.isEnabled())
                self.assertIn('keine verfügbaren Modelle', dialog.status.text())
                self.assertEqual(settings.value('model'), 'opencode/free-a')

    def test_direct_model_setup_loads_automatically_and_keeps_engine_choice(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        from test_model_default import catalogue
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp+'/data'}), \
                patch('setup_dialog.executable', return_value='/test/opencode'):
            settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
            dialog = SetupDialog(settings=settings, page=1)
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            paths = []
            def request(method, path, body=None, callback=None, **kwargs):
                paths.append(path)
                callback({'model': 'opencode/paid'} if path == '/config' else catalogue() if path == '/provider' else {})
            with patch.object(dialog.engine, 'ensure_server', side_effect=lambda cb: cb()), \
                    patch.object(dialog.engine, 'request', side_effect=request):
                QTest.qWait(10)
            self.assertEqual(paths, ['/config', '/provider', '/provider/auth'])
            self.assertEqual(dialog.models.currentData(), 'opencode/paid')
            self.assertFalse(settings.contains('model'))
            dialog.models.setCurrentIndex(dialog.models.findData('opencode/free'))
            dialog.models.activated.emit(dialog.models.currentIndex())
            self.assertEqual(settings.value('model'), 'opencode/free')
            self.assertIn('Dein Modell', dialog.model_summary.text())

    def test_shareable_diagnostic_copies_metadata_without_credentials(self):
        import json
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        from setup_diagnostics import response_summary, version_text
        with tempfile.TemporaryDirectory() as tmp:
            settings=QSettings(tmp+'/prefs.ini',QSettings.IniFormat)
            secret='DO_NOT_SHARE_CREDENTIAL_OR_PRIVATE_PATH'
            settings.setValue('model',secret)
            dialog=SetupDialog(settings=settings)
            self.addCleanup(dialog.deleteLater);self.addCleanup(dialog.reject)
            dialog.key.setText(secret);dialog.engine.password=secret
            data={'all':[{'id':secret,'name':secret,'models':{'private-model':{'name':secret,'apiKey':secret}}}],
                  'connected':[secret],'default':{secret:secret},'message':secret}
            event=response_summary('/provider',200,0,'application/json; '+secret,data,123)
            dialog.record_diagnostic(event)
            dialog.record_diagnostic(response_summary('/auth/'+secret,401,204,'application/json',{'message':secret},100))
            dialog.diagnostic_stage='save_auth';dialog.engine_failed(secret)
            binary=Path(tmp)/'test-engine';binary.write_text('#!/bin/sh\nprintf "2.1.0\\n"\n');binary.chmod(0o755)
            with patch('assistant_backend.opencode_binary',return_value=str(binary)):
                dialog.copy_diagnostic.click()
                deadline=time.monotonic()+5
                while dialog.diagnostic_process and time.monotonic()<deadline:QTest.qWait(10)
                self.assertIsNone(dialog.diagnostic_process)
            raw=QApplication.clipboard().text();report=json.loads(raw)
            self.assertEqual(report['engine_version'],'2.1.0')
            self.assertEqual(report['stage'],'save_auth');self.assertEqual(report['outcome'],'failed')
            self.assertEqual(report['requests'][-1]['http'],401)
            self.assertNotIn(secret,raw);self.assertNotIn(tmp,raw);self.assertNotIn('private-model',raw)
            self.assertEqual(dialog.key.text(),secret)
            self.assertEqual(version_text('2.1.0 '+secret),'unavailable')
            self.assertIsNone(response_summary('/session/'+secret,200,0,'application/json',data,123))
            QApplication.clipboard().clear()

    def test_diagnostic_version_timeout_still_produces_report(self):
        import json,sys
        from PySide6.QtCore import QSettings,QTimer
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'slow-engine'
            binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(60)\n');binary.chmod(0o755)
            dialog=SetupDialog(settings=QSettings(tmp+'/prefs.ini',QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater);self.addCleanup(dialog.reject)
            with patch('assistant_backend.opencode_binary',return_value=str(binary)):
                dialog.copy_diagnostic.click()
                self.assertIsNotNone(dialog.diagnostic_process)
                dialog.diagnostic_process.findChild(QTimer).start(30)
                deadline=time.monotonic()+3
                while dialog.diagnostic_process and time.monotonic()<deadline:QTest.qWait(10)
                self.assertIsNone(dialog.diagnostic_process)
            self.assertEqual(json.loads(QApplication.clipboard().text())['engine_version'],'unavailable')
            self.assertTrue(dialog.copy_diagnostic.isEnabled())
            QApplication.clipboard().clear()

    def test_diagnostic_survives_missing_metadata_after_update(self):
        import json, sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'engine'
            binary.write_text('#!/bin/sh\nprintf "1.18.34\\n"\n'); binary.chmod(0o700)
            dialog = SetupDialog(settings=QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            # An open wizard can retain the old backend across an on-disk update.
            del dialog.engine.startup_diagnostic
            for unreadable in (False, True):
                with self.subTest(unreadable=unreadable), \
                        patch('assistant_backend.opencode_binary', return_value=str(binary)), \
                        patch.object(Path, 'read_bytes', side_effect=OSError('private-path') if unreadable else None,
                                     return_value=b'source'), patch.object(sys, 'excepthook') as errors:
                    QApplication.clipboard().clear()
                    dialog.copy_diagnostic.click()
                    deadline = time.monotonic()+3
                    while dialog.diagnostic_process and time.monotonic()<deadline: QTest.qWait(10)
                    self.assertIsNone(dialog.diagnostic_process)
                    errors.assert_not_called()
                    report = json.loads(QApplication.clipboard().text())
                    self.assertEqual(report['startup']['outcome'], 'unavailable')
                    if unreadable: self.assertEqual(report['code_fingerprint'], 'unavailable')
                    self.assertIn('Diagnose kopiert', dialog.status.text())
                    self.assertTrue(dialog.copy_diagnostic.isEnabled())
            QApplication.clipboard().clear()

    def test_diagnostic_deadline_does_not_wait_for_process_exit(self):
        import json, sys
        from PySide6.QtCore import QProcess, QSettings, QTimer
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'engine'
            binary.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(60)\n'); binary.chmod(0o700)
            dialog = SetupDialog(settings=QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            class DelayedExit(QProcess):
                def kill(self): pass
            with patch('assistant_backend.opencode_binary', return_value=str(binary)), \
                    patch('setup_dialog.worker_process', side_effect=DelayedExit):
                QApplication.clipboard().clear(); dialog.copy_diagnostic.click()
                proc = dialog.diagnostic_process
                self.assertTrue(proc.waitForStarted(1000))
                try:
                    proc.findChild(QTimer).start(20)
                    QTest.qWait(100)
                    self.assertIsNone(dialog.diagnostic_process)
                    report = QApplication.clipboard().text()
                    self.assertEqual(json.loads(report)['engine_version'], 'unavailable')
                    self.assertTrue(dialog.copy_diagnostic.isEnabled())
                finally:
                    QProcess.kill(proc); proc.waitForFinished(1000)
                self.assertEqual(QApplication.clipboard().text(), report)
            QApplication.clipboard().clear()

    def test_diagnostic_reports_internal_errors_and_can_retry(self):
        import json, sys
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'engine'
            binary.write_text('#!/bin/sh\nprintf "1.18.34\\n"\n'); binary.chmod(0o700)
            dialog = SetupDialog(settings=QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            def copy():
                dialog.copy_diagnostic.click()
                deadline = time.monotonic()+3
                while dialog.diagnostic_process and time.monotonic()<deadline: QTest.qWait(10)
                self.assertIsNone(dialog.diagnostic_process)
                self.assertTrue(dialog.copy_diagnostic.isEnabled())
                self.assertNotIn('wird erstellt', dialog.status.text())
            with patch('assistant_backend.opencode_binary', return_value=str(binary)), \
                    patch.object(sys, 'excepthook') as errors:
                with patch('setup_diagnostics.build_report', side_effect=RuntimeError('PRIVATE_CREDENTIAL')):
                    copy()
                raw = QApplication.clipboard().text()
                self.assertEqual(json.loads(raw)['diagnostic_error'], 'RuntimeError')
                self.assertNotIn('PRIVATE_CREDENTIAL', raw)
                self.assertIn('Unvollständige Diagnose', dialog.status.text())
                with patch('setup_dialog.QApplication.clipboard') as clipboard:
                    clipboard.return_value.setText.side_effect = RuntimeError('clipboard unavailable')
                    copy()
                    self.assertIn('konnte nicht kopiert', dialog.status.text())
                copy()
                self.assertEqual(json.loads(QApplication.clipboard().text())['engine_version'], '1.18.34')
                self.assertIn('Diagnose kopiert', dialog.status.text())
                errors.assert_not_called()
            QApplication.clipboard().clear()

    def test_engine_exit_diagnostic_survives_cleanup_and_retry_without_raw_output(self):
        import json, sys
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        from setup_diagnostics import build_report
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            secret = 'PRIVATE_KEY_AND_CONFIG_CONTENT'
            binary = Path(tmp) / 'engine'
            binary.write_text('#!' + sys.executable + '\nimport sys\n'
                'print("Configuration is invalid at /private/opencode.json\\n' + secret + '", file=sys.stderr)\n'
                'sys.exit(23)\n')
            binary.chmod(0o700)
            dialog = SetupDialog(settings=QSettings(tmp + '/prefs.ini', QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            def wait():
                deadline = time.monotonic() + 3
                while dialog.checking and time.monotonic() < deadline: QTest.qWait(10)
                self.assertFalse(dialog.checking)
            with patch('assistant_backend.opencode_binary', return_value=str(binary)):
                dialog.load_engine(); wait()
                self.assertIsNone(dialog.engine.proc)
                raw = build_report(dialog, '1.18.34'); report = json.loads(raw)
                self.assertEqual(report['startup']['outcome'], 'exited')
                self.assertEqual(report['startup']['exit_code'], 23)
                self.assertEqual(report['startup']['hint'], 'invalid_config')
                self.assertGreater(report['startup']['captured_bytes'], 0)
                self.assertIn('Konfiguration', dialog.status.text())
                self.assertNotIn(secret, raw); self.assertNotIn('/private', raw); self.assertNotIn(tmp, raw)
                binary.write_text('#!' + sys.executable + '\nimport os,signal\nos.kill(os.getpid(), signal.SIGKILL)\n')
                dialog.load_engine(); wait()
                report = json.loads(build_report(dialog, '1.18.34'))
                self.assertEqual(report['startup']['outcome'], 'crashed')
                self.assertEqual(report['startup']['exit_code'], 9)
                self.assertEqual(report['startup']['hint'], 'unknown')
                binary.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(60)\n')
                dialog.load_engine(); dialog.engine.start_timer.start(30); wait()
                report = json.loads(build_report(dialog, '1.18.34'))
                self.assertEqual(report['startup']['outcome'], 'timeout')
                self.assertNotIn('exit_code', report['startup'])
                self.assertEqual(report['startup']['hint'], 'unknown')
            self.assertEqual(dialog.engine.log, b'')

    def test_startup_hints_export_only_fixed_categories(self):
        import json
        from setup_diagnostics import startup_summary
        for hint, raw in [('database', 'SQLiteError: /private/profile'),
                          ('permission_denied', 'EACCES: private-file'),
                          ('disk_full', 'ENOSPC: secret'),
                          ('address_in_use', 'EADDRINUSE: private-host'),
                          ('tls', 'CERTIFICATE_VERIFY_FAILED: secret'),
                          ('unknown', 'some completely private output')]:
            summary = startup_summary('exited', raw.encode(), 100, 1)
            self.assertEqual(summary['hint'], hint)
            self.assertNotIn(raw, json.dumps(summary))

    def test_provider_check_rejects_non_api_responses_and_recovers(self):
        import threading
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        state = {'response': b'<html>OpenCode</html>', 'writes': [], 'auth_code': 200,
                 'auth_response': b'<html>test-only-secret</html>'}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                raw = state['response'] if self.path.split('?')[0] == '/provider' else b'{}'
                self.send_response(200); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
            def do_PUT(self):
                state['writes'].append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(state['auth_code']); self.end_headers(); self.wfile.write(state['auth_response'])
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as tmp:
            dialog = SetupDialog(settings=QSettings(tmp+'/prefs.ini', QSettings.IniFormat))
            self.addCleanup(dialog.deleteLater); self.addCleanup(dialog.reject)
            def ensure(callback):
                dialog.engine.url = f'http://127.0.0.1:{server.server_port}'; callback()
            def wait():
                deadline = time.monotonic()+5
                while dialog.checking and time.monotonic() < deadline: QTest.qWait(10)
                self.assertFalse(dialog.checking)
            with patch.object(dialog.engine, 'ensure_server', side_effect=ensure):
                dialog.key.setText('test-only-secret')
                for raw in (b'<html>OpenCode</html>', b'null', b'', b'{broken'):
                    state['response'] = raw; dialog.load_engine(); wait()
                    self.assertIn('API-Daten', dialog.status.text())
                    self.assertEqual(dialog.diagnostic_events[-1]['http'],200)
                    self.assertEqual(dialog.diagnostic_outcome,'failed')
                    self.assertEqual(dialog.diagnostic_stage,'provider_list')
                    self.assertTrue(dialog.check_engine.isEnabled())
                    self.assertFalse(dialog.connect_provider.isEnabled())
                    self.assertFalse(dialog.repair_engine.isHidden())
                    self.assertEqual(dialog.key.text(), 'test-only-secret')
                    self.assertEqual(state['writes'], [])
                for raw in (b'{}', b'{"all":null,"connected":[]}', b'{"all":[null],"connected":[]}'):
                    state['response'] = raw; dialog.load_engine(); wait()
                    self.assertNotIn('NoneType', dialog.status.text())
                    self.assertEqual(dialog.diagnostic_events[-1]['callback_error'],'ValueError')
                    self.assertFalse(dialog.connect_provider.isEnabled())
                state['response'] = json.dumps({'all':[{'id':'example', 'name':'Example',
                    'models':{'test':{'name':'Test'}}}], 'connected':['example']}).encode()
                dialog.load_engine(); wait()
                self.assertTrue(dialog.connect_provider.isEnabled())
                self.assertTrue(dialog.repair_engine.isHidden())
                self.assertEqual(dialog.models.currentData(), '')
                self.assertFalse(dialog.settings.contains('model'))
                self.assertIn('Kein verfügbares Gratis-Modell', dialog.model_summary.text())
                dialog.models.setCurrentIndex(dialog.models.findData('example/test'))
                dialog.connect_provider.click(); wait()
                self.assertEqual(dialog.key.text(), 'test-only-secret')
                self.assertNotIn('test-only-secret', dialog.status.text())
                self.assertIn('Zugang konnte nicht gespeichert', dialog.status.text())
                # Empty 204 is a valid success, unlike an empty 200 response.
                state.update(auth_code=204, auth_response=b'')
                dialog.load_engine(); wait(); dialog.connect_provider.click(); wait()
                self.assertEqual(state['writes'], [{'type':'api','key':'test-only-secret'}]*2)
                self.assertEqual(dialog.key.text(), '')

    def test_desktop_is_only_changed_after_explicit_activation(self):
        from PySide6.QtCore import QSettings
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(tmp + '/preferences.ini', QSettings.IniFormat)
            settings.setValue('appearance', 'midnight')
            dialog = SetupDialog(settings=settings, page=3)
            with patch.object(dialog, 'start_job') as start:
                self.assertEqual(dialog.desktop_theme.currentData(), 'midnight')
                dialog.desktop_theme.setCurrentIndex(dialog.desktop_theme.findData('atelier'))
                dialog.next.click(); start.assert_not_called()
                dialog.back.click(); dialog.apply_desktop.click()
                start.assert_called_once_with('desktop')
                self.assertEqual(settings.value('appearance'), 'midnight')
            dialog.reject(); dialog.deleteLater()

    def test_recommended_install_customization_failure_retry_and_skip(self):
        from PySide6.QtCore import QSettings, QProcess
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog, RECOMMENDED
        import sys
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/data'}), \
                patch('setup_dialog.executable', return_value=''):
            dialog = SetupDialog(settings=QSettings(tmp + '/prefs.ini', QSettings.IniFormat))
            self.assertTrue(dialog.dependency_details.body.isHidden())
            self.assertEqual([key for key, item in dialog.features.items() if item.isChecked()],
                             [key for key in dialog.features if key in RECOMMENDED])
            dialog.features['network'].setChecked(False)
            dialog.features['ocr'].setChecked(True)
            attempts = []; codes = iter([1, 0])
            class Worker(QProcess):
                def start(self, program, arguments):
                    attempts.append(arguments)
                    super().start(sys.executable, ['-c', 'import sys; sys.exit(' + str(next(codes)) + ')'])
            with patch('setup_dialog.worker_process', side_effect=lambda parent: Worker(parent)):
                for expected_page in (0, 1):
                    dialog.next.click()
                    self.assertFalse(dialog.next.isEnabled()); self.assertFalse(dialog.skip.isEnabled())
                    dialog.reject()  # A running installation must not close the wizard.
                    self.assertIsNotNone(dialog.job)
                    until = time.monotonic() + 5
                    while dialog.job and time.monotonic() < until: QTest.qWait(10)
                    self.assertIsNone(dialog.job)
                    self.assertEqual(dialog.stack.currentIndex(), expected_page)
                    self.assertTrue(dialog.next.isEnabled())
            self.assertEqual(attempts[0][1:], ['packages', 'engine', 'documents', 'media', 'ocr'])
            self.assertEqual(attempts[0], attempts[1])
            dialog.back.click()
            with patch.object(dialog, 'start_job') as start:
                dialog.skip.click(); start.assert_not_called()
                self.assertEqual(dialog.stack.currentIndex(), 1)
            dialog.reject(); dialog.deleteLater()

    def test_cancelled_install_never_advances(self):
        from PySide6.QtCore import QSettings, QProcess
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        import sys
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/data'}), \
                patch('setup_dialog.executable', return_value=''):
            dialog = SetupDialog(settings=QSettings(tmp + '/prefs.ini', QSettings.IniFormat))
            class Worker(QProcess):
                def start(self, program, arguments):
                    super().start(sys.executable, ['-c', 'import time; time.sleep(10)'])
            with patch('setup_dialog.worker_process', side_effect=lambda parent: Worker(parent)):
                dialog.next.click(); self.assertTrue(dialog.job.waitForStarted(1000))
                dialog.cancellable = True; dialog.cancel_job()
                until = time.monotonic() + 5
                while dialog.job and time.monotonic() < until: QTest.qWait(10)
                self.assertIsNone(dialog.job)
                self.assertEqual(dialog.stack.currentIndex(), 0)
                self.assertFalse(dialog.advance_after_job)
            dialog.reject(); dialog.deleteLater()

    def test_fresh_defaults_are_preserved_and_personalization_is_committed_only_on_finish(self):
        from PySide6.QtCore import QSettings
        from setup_dialog import SetupDialog
        from lumen_store import Store
        from lumen_memory import options
        from lumen_persona import load
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/data'}):
            settings = QSettings(tmp + '/prefs.ini', QSettings.IniFormat)
            dialog = SetupDialog(settings=settings, page=4)
            self.assertEqual(options(Store()), {'enabled': False, 'learn': False})
            dialog.personal.memory.setCurrentIndex(2)
            dialog.personal.persona.preset.setCurrentIndex(1)
            dialog.personal.persona.choose_preset(1)
            dialog.reject()
            self.assertFalse(options(Store())['enabled']); self.assertEqual(load(settings)['preset'], 'guide')
            dialog.deleteLater()
            dialog = SetupDialog(settings=settings, page=4)
            dialog.personal.memory.setCurrentIndex(2)
            dialog.personal.persona.preset.setCurrentIndex(1)
            dialog.personal.persona.choose_preset(1)
            dialog.next.click()
            self.assertEqual(options(Store()), {'enabled': True, 'learn': True})
            self.assertEqual(load(settings)['preset'], 'professional')
            dialog.deleteLater()

    def test_concurrent_privacy_change_is_preserved(self):
        from PySide6.QtCore import QSettings
        from setup_dialog import SetupDialog
        from lumen_store import Store
        from lumen_memory import Memory, options
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/data'}):
            settings = QSettings(tmp + '/prefs.ini', QSettings.IniFormat)
            dialog = SetupDialog(settings=settings, page=4)
            dialog.personal.memory.setCurrentIndex(2)
            Memory(Store()).configure(True, False)
            dialog.next.click()
            self.assertFalse(settings.value('setupCompleted', False, type=bool))
            self.assertEqual(options(Store()), {'enabled': True, 'learn': False})
            self.assertIn('anderen Fenster', dialog.status.text())
            dialog.reject(); dialog.deleteLater()

    def test_microphone_test_uses_shared_process_flow_without_sending(self):
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from setup_dialog import SetupDialog
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root / 'pw-record'
            record.write_text('#!/usr/bin/python3\nimport signal,sys,time,wave\n'
                'with wave.open(sys.argv[-1], "wb") as w:\n'
                ' w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\\x00" * 3200)\n'
                'signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\nwhile True: time.sleep(.01)\n')
            transcribe = root / 'whisper-cli'
            transcribe.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n'
                'Path(sys.argv[sys.argv.index("-of")+1]+".txt").write_text("Hallo Lumen")\n')
            for path in (record, transcribe): path.chmod(0o755)
            model = root / 'model.bin'; model.write_bytes(b'test')
            settings = QSettings(tmp + '/preferences.ini', QSettings.IniFormat); settings.setValue('speechModel', str(model))
            with patch.dict(os.environ, {'PATH': tmp + ':' + os.environ['PATH']}):
                dialog = SetupDialog(settings=settings, page=2)
                with patch.object(dialog.engine, 'send', side_effect=AssertionError('Test must stay local')):
                    test = dialog.speech_test
                    test.record.click(); QTest.qWait(150)
                    self.assertTrue(test.tools.recording)
                    test.record.click()
                    until = time.monotonic() + 4
                    while test.tools.process and time.monotonic() < until: QTest.qWait(30)
                    self.assertEqual(test.composer.toPlainText(), 'Hallo Lumen')
                    self.assertIsNone(test.tools.process)
                    self.assertFalse(test.tools.recording)
                    self.assertIsNone(test.tools.temp)
                    dialog.reject(); dialog.deleteLater()


if __name__ == '__main__': unittest.main()
