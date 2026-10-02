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

    def test_existing_tools_and_models_are_reused_without_install_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / 'ggml-small-q5_1.bin'; model.write_bytes(b'model')
            with patch.object(setup, 'speech_root', return_value=root), patch.object(setup, 'executable', return_value='/existing/tool'), \
                    patch.object(setup, 'MODEL_SIZE', 5), patch.object(setup, 'MODEL_HASH', hashlib.sha256(b'model').hexdigest()), \
                    patch.object(setup, 'download') as download, patch.object(setup, 'run') as run, patch.object(setup, 'report'):
                self.assertEqual(setup.missing_packages(['engine', 'documents']), [])
                setup.install_dictation()
                download.assert_not_called(); run.assert_not_called()
                with self.assertRaises(ValueError): setup.install_packages(['unapproved-package'])

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
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_wizard_preserves_config_and_only_saves_auth_after_click(self):
        from PyQt5.QtCore import QSettings
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
                elif path == '/provider/auth': callback({})
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

    def test_desktop_is_only_changed_after_explicit_activation(self):
        from PyQt5.QtCore import QSettings
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

    def test_microphone_test_uses_shared_process_flow_without_sending(self):
        from PyQt5.QtCore import QSettings
        from PyQt5.QtTest import QTest
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
