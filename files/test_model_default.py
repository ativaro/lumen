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


def engine(test, answer):
    """A caller's engine that answers like OpenCode: `answer(path)` for the setup routes, a session
    and a finished reply to every prompt. Returns its address and the requests it saw."""
    import json, threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    calls, prompts = [], []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self): self.reply()
        def do_POST(self): self.reply()
        def reply(self):
            path = self.path.split('?')[0]
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
            if path == '/event': self.send_error(404); return
            calls.append((path, body))
            data = answer(path)
            if path == '/session' and self.command == 'POST': data = {'id': 'ses_test'}
            elif path.endswith('/prompt_async'): prompts.append(body)
            elif path.endswith('/message'):
                data = [{'info': {'role': 'assistant', 'parentID': prompts[-1]['messageID'], 'finish': 'stop',
                                  'time': {'completed': 1}}, 'parts': [{'type': 'text', 'text': '{}'}]}]
            elif path in ('/permission', '/question'): data = []
            raw = json.dumps(data if data is not None else {}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.server_close); test.addCleanup(server.shutdown)
    return f'http://127.0.0.1:{server.server_port}', calls


def settle(backend):
    import time
    from PySide6.QtTest import QTest
    deadline = time.monotonic() + 8
    while backend.busy and time.monotonic() < deadline: QTest.qWait(10)


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
                # The service chooses the model (native/service: a_local_only_policy_fails_closed).
                address, calls = engine(self, lambda path: {'model': configured} if path == '/config' else
                                        catalogue() if path == '/provider' else None)
                backend = OpenCodeBackend(tmp, server_url=address)
                backend.settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
                if selected: backend.settings.setValue('model', selected)
                failures = []
                backend.failed.connect(failures.append)
                try:
                    backend.send('Hello', proposal=True); settle(backend)
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
                address, seen = engine(self, lambda path: {'all': [{'id': 'opencode', 'source': 'custom', 'options': options}]}
                                       if path == '/provider' else {'provider': {'opencode': {'options': {'baseURL': endpoint}}}}
                                       if path == '/config' else None)
                backend = OpenCodeBackend(tmp, server_url=address)
                backend.settings = QSettings(tmp+'/prefs.ini', QSettings.IniFormat)
                backend.settings.setValue('model', 'opencode/chosen')
                failures = []
                backend.failed.connect(failures.append)
                try:
                    backend.send('Hello', proposal=True); settle(backend)
                    calls = [path for path, _ in seen]
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
