"""Prompts require a chosen model and never create an anonymous free fallback."""
import tempfile
import unittest
from unittest.mock import patch

def catalogue():
    return {'all': [{'id': 'opencode', 'models': {
        'paid': {'cost': {'input': 1, 'output': 2}, 'capabilities': {'toolcall': True}},
        'free': {'cost': {'input': 0, 'output': 0, 'cache': {'read': 0, 'write': 0}},
                 'capabilities': {'toolcall': True}}}}],
        'connected': ['opencode'], 'default': {'opencode': 'paid'}}


class ModelDefaultTest(unittest.TestCase):
    def test_first_prompt_preserves_explicit_choices_and_requires_setup_without_a_model(self):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QSettings, QCoreApplication, QEvent
        from assistant_backend import OpenCodeBackend
        app = QApplication.instance() or create_app()
        for selected, configured, expected in (
                ('', '', ''),
                ('custom/chosen', '', 'custom/chosen'),
                ('opencode/free', '', 'opencode/free'),
                ('ollama/local', '', 'ollama/local'),
                ('', 'engine/chosen', 'engine/chosen')):
            with self.subTest(selected=selected, configured=configured), tempfile.TemporaryDirectory() as tmp, \
                    patch.dict('os.environ', {'LUMEN_DATA': tmp+'/data'}):
                backend = OpenCodeBackend(tmp)
                backend.settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
                if selected: backend.settings.setValue('model', selected)
                calls = []; failures = []
                backend.failed.connect(failures.append)
                backend.ensure_server = lambda callback: callback()
                backend.poll = lambda: None
                backend.refresh_sessions = lambda: None
                def request(method, path, body=None, callback=None, **kwargs):
                    calls.append((path, body))
                    if path == '/config': callback({'model': configured})
                    elif path == '/provider': callback(catalogue())
                    elif path == '/session': callback({'id': 'ses_test'})
                    elif callback: callback(None)
                backend.request = request
                try:
                    backend.send('Hello', proposal=True)
                    prompts = [body for path, body in calls if path.endswith('/prompt_async')]
                    if expected:
                        provider, model = expected.split('/', 1)
                        self.assertEqual(prompts[0]['model'], {'providerID': provider, 'modelID': model})
                        self.assertEqual(failures, [])
                        self.assertEqual(backend.settings.value('model', ''), selected)
                        if selected: self.assertNotIn('/config', [p for p, _ in calls])
                    else:
                        self.assertFalse(prompts)
                        self.assertIn('Modell auswählen', failures[0])
                        self.assertFalse(backend.settings.contains('model'))
                        self.assertNotIn('/session', [p for p, _ in calls])
                    if expected.startswith('opencode/'):
                        self.assertIn('/provider', [p for p, _ in calls])
                    else:
                        self.assertNotIn('/provider', [p for p, _ in calls])
                finally:
                    backend.shutdown(); backend.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()


    def test_saved_anonymous_model_is_blocked_without_rewriting_choices_or_other_connections(self):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QSettings, QCoreApplication, QEvent
        from assistant_backend import OpenCodeBackend
        app = QApplication.instance() or create_app()
        for options, endpoint, blocked in (({'apiKey': 'public'}, '', True),
                                           ({'apiKey': 'synthetic-user-key'}, '', False),
                                           ({}, '', False),
                                           ({'apiKey': 'public', 'baseURL': 'http://127.0.0.1:8080/v1'}, '', True),
                                           ({'apiKey': 'public'}, 'http://127.0.0.1:8080/v1', False),
                                           ({'apiKey': 'public'}, 'http://model.lan:8080/v1', False),
                                           ({'apiKey': 'public'}, 'https://models.example.test/v1', False)):
            with self.subTest(options=options, endpoint=endpoint), tempfile.TemporaryDirectory() as tmp, \
                    patch.dict('os.environ', {'LUMEN_DATA': tmp+'/data'}):
                backend = OpenCodeBackend(tmp)
                backend.settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
                backend.settings.setValue('model', 'opencode/chosen')
                backend.ensure_server = lambda callback: callback()
                backend.poll = lambda: None
                backend.refresh_sessions = lambda: None
                calls = []; failures = []
                backend.failed.connect(failures.append)
                def request(method, path, body=None, callback=None, **kwargs):
                    calls.append(path)
                    if path == '/provider': callback({'all': [{'id': 'opencode', 'source': 'custom', 'options': options}]})
                    elif path == '/config': callback({'provider': {'opencode': {'options': {'baseURL': endpoint}}}})
                    elif path == '/session': callback({'id': 'ses_test'})
                    elif callback: callback(None)
                backend.request = request
                try:
                    backend.send('Hello', proposal=True)
                    self.assertEqual(backend.settings.value('model'), 'opencode/chosen')
                    self.assertEqual(any(path.endswith('/prompt_async') for path in calls), not blocked)
                    if blocked:
                        self.assertNotIn('/session', calls)
                        self.assertIn('anonyme OpenCode-Zugang', failures[0])
                    else:
                        self.assertEqual(failures, [])
                finally:
                    backend.shutdown(); backend.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()


if __name__ == '__main__': unittest.main()
