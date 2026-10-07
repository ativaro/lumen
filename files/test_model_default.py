"""Fresh setup must send an explicit free model, without changing existing choices."""
import copy
import tempfile
import unittest
from unittest.mock import patch

from lumen_models import free_default


def catalogue():
    return {'all': [{'id': 'opencode', 'models': {
        'paid': {'cost': {'input': 1, 'output': 2}, 'capabilities': {'toolcall': True}},
        'free': {'cost': {'input': 0, 'output': 0, 'cache': {'read': 0, 'write': 0}},
                 'capabilities': {'toolcall': True}}}}],
        'connected': ['opencode'], 'default': {'opencode': 'paid'}}


class ModelDefaultTest(unittest.TestCase):
    def test_only_confirmed_free_connected_tool_models_are_automatic(self):
        inventory = catalogue()
        self.assertEqual(free_default(inventory), 'opencode/free')
        for change in ({'cost': None}, {'cost': {'input': 0}}, {'cost': {'input': 0, 'output': 1}},
                       {'cost': {'input': 0, 'output': 0, 'cache': {'read': .1}}},
                       {'capabilities': {'toolcall': False}}, {'status': 'deprecated'}):
            modified = copy.deepcopy(inventory)
            modified['all'][0]['models']['free'].update(change)
            self.assertEqual(free_default(modified), '')
        inventory['connected'] = []
        self.assertEqual(free_default(inventory), '')
        with self.assertRaises(ValueError): free_default(None)

    def test_first_prompt_resolves_persists_and_sends_default_or_fails_without_paid_fallback(self):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QSettings, QCoreApplication, QEvent
        from assistant_backend import OpenCodeBackend
        app = QApplication.instance() or create_app()
        for selected, configured, available, expected in (
                ('', '', True, 'opencode/free'),
                ('custom/chosen', '', True, 'custom/chosen'),
                ('', 'engine/chosen', True, 'engine/chosen'),
                ('', '', False, '')):
            with self.subTest(selected=selected, configured=configured, available=available), tempfile.TemporaryDirectory() as tmp, \
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
                    elif path == '/provider': callback(catalogue() if available else {'all': [], 'connected': []})
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
                        self.assertEqual(backend.settings.value('model', ''), selected or ('opencode/free' if not configured else ''))
                        if selected: self.assertNotIn('/config', [p for p, _ in calls])
                    else:
                        self.assertFalse(prompts)
                        self.assertIn('Gratis-Modell', failures[0])
                        self.assertFalse(backend.settings.contains('model'))
                finally:
                    backend.shutdown(); backend.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()


if __name__ == '__main__': unittest.main()
