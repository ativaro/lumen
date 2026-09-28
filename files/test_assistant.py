import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from assistant_backend import OpenCodeBackend


class AssistantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        from PyQt5.QtTest import QTest
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Assistant request timed out')

    def test_native_engine_messages_questions_permissions_and_abort(self):
        state = {'requests': [], 'messages': [], 'busy': True, 'permission': True, 'question': True}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.handle_request('GET')

            def do_POST(self):
                self.handle_request('POST')

            def handle_request(self, method):
                path = self.path.split('?')[0]
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
                state['requests'].append((method, path, body, self.headers.get('Authorization')))
                data = {}
                if path == '/session' and method == 'POST':
                    data = {'id': 'ses_lumen'}
                elif path.endswith('/prompt_async'):
                    state['messages'] = [{'info': {'id': body['messageID'], 'role': 'user'}, 'parts': body['parts']},
                        {'info': {'id': 'msg_answer', 'role': 'assistant', 'parentID': body['messageID'], 'time': {}},
                         'parts': [{'type': 'text', 'text': 'Erste Antwort'}]}]
                elif path.endswith('/message'):
                    data = state['messages']
                elif path == '/permission':
                    data = [{'id': 'per_lumen', 'sessionID': 'ses_lumen', 'permission': 'edit', 'patterns': ['note.txt']},
                            {'id': 'per_other', 'sessionID': 'ses_other', 'permission': 'bash', 'patterns': ['other']}] if state['permission'] else []
                    if state.get('child_permission'):
                        data.append({'id': 'per_child', 'sessionID': 'ses_child', 'permission': 'read', 'patterns': ['child.txt']})
                elif path == '/session/ses_child':
                    data = {'id': 'ses_child', 'parentID': 'ses_lumen'}
                elif path == '/question':
                    data = [{'id': 'que_lumen', 'sessionID': 'ses_lumen', 'questions': [{'question': 'Welche Sprache?',
                        'header': 'Sprache', 'options': [{'label': 'Deutsch', 'description': 'Deutsche Ausgabe'}]}]}] if state['question'] else []
                elif path == '/session/status':
                    data = {'ses_lumen': {'type': 'busy'}} if state['busy'] else {}
                elif path.endswith('/abort'):
                    state['busy'] = False
                    data = True
                elif path.startswith('/permission/'):
                    if path == '/permission/per_child/reply':
                        state['child_permission'] = False
                    else:
                        state['permission'] = False
                    data = True
                elif path.startswith('/question/'):
                    state['question'] = False
                    data = True
                elif path == '/session':
                    data = []
                raw = json.dumps(data).encode()
                self.send_response(503 if state.get('error') else 200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as tmp:
            backend = OpenCodeBackend(tmp, server_url=f'http://127.0.0.1:{server.server_port}', password='test-token')
            try:
                from assistant import ChatPanel
                from PyQt5.QtWidgets import QPushButton, QComboBox
                panel = ChatPanel(tmp, backend=backend)
                panel.show()
                panel.composer.setPlainText('Erkläre die Auswahl')
                panel.send_button.click()
                self.wait(lambda: bool(backend.permissions and backend.questions))
                self.assertEqual(len(backend.permissions), 1)
                self.assertEqual(backend.messages[-1]['parts'][0]['text'], 'Erste Antwort')
                self.assertTrue(backend.busy)
                backend.permission_reply('per_other', True)
                self.assertFalse(any(path == '/permission/per_other/reply' for _, path, _, _ in state['requests']))
                self.assertIn('Erste Antwort', panel.transcript.toPlainText())
                reject = next(b for b in panel.requests.findChildren(QPushButton) if b.text() == 'Ablehnen')
                reject.click()
                panel.requests.findChild(QComboBox).setCurrentIndex(1)
                answer = next(b for b in panel.requests.findChildren(QPushButton) if b.text() == 'Antwort senden')
                answer.click()
                self.wait(lambda: not state['question'] and not state['permission'])
                self.assertIn(('POST', '/permission/per_lumen/reply', {'reply': 'reject'}), [r[:3] for r in state['requests']])
                state['child_permission'] = True
                self.wait(lambda: any(p['id'] == 'per_child' for p in backend.permissions))
                backend.permission_reply('per_child', False)
                self.wait(lambda: not state['child_permission'])
                self.assertIn(('POST', '/permission/per_child/reply', {'reply': 'reject'}), [r[:3] for r in state['requests']])
                state['messages'][-1]['parts'][0]['text'] = 'Fertige Antwort'
                state['messages'][-1]['info']['time']['completed'] = 123
                state['busy'] = False
                self.wait(lambda: not backend.busy)
                self.assertEqual(backend.messages[-1]['parts'][0]['text'], 'Fertige Antwort')
                backend.send('Noch eine Frage')
                self.wait(lambda: len([r for r in state['requests'] if r[1].endswith('/prompt_async')]) == 2)
                panel.stop.click()
                self.wait(lambda: not backend.busy)
                self.assertTrue(any(path.endswith('/abort') for _, path, _, _ in state['requests']))
                self.assertTrue(all(auth and auth.startswith('Basic ') for *_, auth in state['requests']))
                state['error'] = True
                errors = []
                backend.failed.connect(errors.append)
                panel.composer.setPlainText('Bei Fehler behalten')
                panel.send()
                self.wait(lambda: bool(errors))
                self.assertFalse(backend.busy)
                self.assertEqual(panel.composer.toPlainText(), 'Bei Fehler behalten')
                self.assertTrue(panel.error.isVisible())
                panel.show_sessions([{'id': 'ses_old', 'title': 'Vorheriger Ordner'}])
                backend.new_conversation(str(Path(tmp) / 'other'))
                self.assertEqual(panel.sessions.count(), 1)
                self.assertEqual(panel.sessions.itemData(0), '')
                # An accepted request can end before an assistant is created (invalid model).
                backend.url = f'http://127.0.0.1:{server.server_port}'
                state['error'] = False
                backend.session = 'ses_lumen'
                backend.message_id = 'msg_missing'
                backend.set_busy(True)
                backend.idle_since = time.monotonic() - 31
                state['messages'] = []
                state['busy'] = False
                errors.clear()
                backend.poll()
                self.wait(lambda: bool(errors))
                self.assertFalse(backend.busy)
                self.assertIn('keine abgeschlossene Antwort', errors[-1])
            finally:
                panel.close()
                backend.shutdown()
                server.shutdown()
                server.server_close()

    def test_start_failure_and_native_launchers(self):
        import os
        import shutil
        import subprocess
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            backend = OpenCodeBackend(tmp)
            failures = []
            backend.failed.connect(failures.append)
            with patch.dict(os.environ, {'LUMEN_OPENCODE_BIN': tmp + '/missing'}):
                backend.send('Start prüfen')
                self.wait(lambda: bool(failures))
            self.assertFalse(backend.busy)
            self.assertIsNone(backend.proc)
            backend.shutdown()
            root = Path(__file__).resolve().parents[1]
            target = Path(tmp)
            stub = target / 'lumen-agent-app'
            stub.write_text('#!/usr/bin/python3\nimport json,sys;print(json.dumps(sys.argv[1:]))\n')
            stub.chmod(0o755)
            for name in ('lumen-context', 'lumen-quick', 'lumen-sel'):
                shutil.copy2(root / 'bin' / name, target / name)
            paths = ['/tmp/Bilder mit Leerzeichen', '/tmp/$(touch should-not-exist);ä.txt']
            def invoke(name, *args):
                return json.loads(subprocess.check_output([str(target / name), *args], text=True))
            self.assertEqual(invoke('lumen-context', 'explain', *paths), ['--action', 'explain', '--context', *paths])
            self.assertEqual(invoke('lumen-quick', 'ask'), [])
            self.assertEqual(invoke('lumen-quick', 'ask-sel'), ['--selection', 'explain'])
            self.assertEqual(invoke('lumen-sel', 'translate'), ['--selection=translate'])
            import importlib.util
            spec = importlib.util.spec_from_file_location('lumen_runner_test', root / 'bin/lumen_krunner.py')
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            command = runner.build_command('--help')
            self.assertIn('--prompt=--help', command)
            result = subprocess.run(command + ['--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
