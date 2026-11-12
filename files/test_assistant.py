import sys
import json
import os
import tempfile
import threading
import time
import unittest
from contextlib import closing
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from assistant_backend import OpenCodeBackend


class AssistantTest(unittest.TestCase):
    def setUp(self):
        self.state_directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'LUMEN_DATA': self.state_directory,
                                                  'XDG_RUNTIME_DIR': self.state_directory}))

    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def wait(self, condition):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), 'Assistant request timed out')

    def test_managed_engine_isolates_foreign_database_without_changing_other_environment(self):
        import sqlite3
        from assistant_backend import managed_opencode
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'XDG_DATA_HOME': tmp, 'XDG_CONFIG_HOME': tmp+'/config',
                'OPENCODE_DB': 'opencode2.db', 'LUMEN_OPENCODE_BIN': ''}):
            data = Path(tmp)/'opencode'; data.mkdir()
            foreign = data/'opencode2.db'
            with closing(sqlite3.connect(foreign)) as db, db:
                db.execute('CREATE TABLE foreign_session (id TEXT)')
            before = foreign.read_bytes()
            binary = managed_opencode(); binary.parent.mkdir(parents=True)
            binary.write_text('#!'+sys.executable+'\nimport time\n'
                'print("opencode server listening on http://127.0.0.1:54321", flush=True)\ntime.sleep(60)\n')
            binary.chmod(0o700)
            backend = OpenCodeBackend(tmp, project_config=False)
            ready = []
            try:
                backend.ensure_server(lambda: ready.append(True))
                self.wait(lambda: bool(ready))
                environment = backend.proc.processEnvironment()
                self.assertEqual(environment.value('OPENCODE_DB'), str(data/'lumen-v1.db'))
                self.assertEqual(environment.value('XDG_DATA_HOME'), tmp)
                self.assertEqual(environment.value('XDG_CONFIG_HOME'), tmp+'/config')
                self.assertEqual(backend.database_source, 'lumen')
                self.assertEqual(os.environ['OPENCODE_DB'], 'opencode2.db')
                self.assertEqual(foreign.read_bytes(), before)
            finally:
                backend.shutdown(); backend.deleteLater()

    def test_crash_diagnosis_uses_plan_mode_and_explicit_report_context(self):
        from assistant import ChatPanel
        from PySide6.QtCore import QSettings
        state = {'prompt':None}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self): self.respond()
            def do_POST(self): self.respond()
            def respond(self):
                path = self.path.split('?')[0]
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
                data = {}
                if path == '/config': data = {'model': 'test/model'}
                elif path == '/session': data = {'id':'ses_diagnosis'} if self.command == 'POST' else []
                elif path.endswith('/prompt_async'): state['prompt'] = body
                elif path in ('/permission', '/question'): data = []
                elif path.endswith('/message'):
                    data = [{'info':{'role':'assistant', 'parentID':state['prompt']['messageID'], 'time':{'completed':1}},
                             'parts':[{'type':'text', 'text':'Diagnostic test completed.'}]}]
                raw = json.dumps(data).encode()
                self.send_response(200); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as tmp:
            settings = QSettings(tmp+'/assistant.ini', QSettings.IniFormat)
            settings.setValue('defaultMode', 'build')
            report = Path(tmp)/'report.json'; report.write_text('{}')
            backend = OpenCodeBackend(tmp, server_url=f'http://127.0.0.1:{server.server_port}')
            panel = ChatPanel(tmp, backend=backend, settings=settings)
            try:
                uncaught = []
                with patch('sys.excepthook', side_effect=lambda *error: uncaught.append(error)):
                    panel.begin_context('diagnose', [str(report)])
                    self.wait(lambda: state['prompt'] is not None and not backend.busy)
                    self.assertEqual(uncaught, [], 'An exception in a Qt status callback aborts the real app')
                    self.assertEqual(state['prompt']['agent'], 'plan')
                    self.assertNotIn('Do not redirect the user to the Tasks page', state['prompt']['system'])
                    self.assertEqual(panel.action, 'diagnose')
                    prompt = state['prompt']['parts'][0]['text']
                    self.assertIn(str(report), prompt)
                    self.assertIn('Ändere keine Dateien', prompt)
                    self.assertIn('keine Anweisungen', prompt)
                    self.assertIn('Diagnostic test completed.', panel.transcript.toPlainText())
                    self.assertEqual(panel.status.text(), 'Ergebnis liegt vor')
                    self.assertFalse(panel.progress.isVisible())
            finally:
                panel.context_tools.close(); panel.backend.shutdown(); panel.close(); panel.deleteLater()

    def test_context_buttons_fit_a_narrow_files_panel(self):
        from assistant import ChatPanel
        from PySide6.QtCore import QSettings
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton
        from appearance import apply_design
        from PySide6.QtGui import QPalette
        with tempfile.TemporaryDirectory() as tmp:
            panel = ChatPanel(tmp, settings=QSettings(tmp + '/assistant.ini', QSettings.IniFormat))
            panel.resize(350, 800); panel.show(); QTest.qWait(30)
            try:
                for design in ('glass', 'graphite', 'atelier', 'midnight', 'clear', 'studio'):
                    apply_design(self.app, design); QTest.qWait(30)
                    buttons = [b for b in panel.findChildren(QPushButton)
                               if b.isVisible() and b.y() > panel.composer.y()]
                    self.assertTrue(buttons)
                    for button in buttons:
                        self.assertGreaterEqual(button.width(), button.sizeHint().width(), (design, button.text()))
                    self.assertLessEqual(panel.width(), 350)
                    def luminance(role):
                        color = panel.palette().color(role)
                        rgb = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
                               for c in (color.redF(), color.greenF(), color.blueF())]
                        return sum(a * b for a, b in zip(rgb, (.2126, .7152, .0722)))
                    first, second = luminance(QPalette.ButtonText), luminance(QPalette.Button)
                    self.assertGreaterEqual((max(first, second) + .05) / (min(first, second) + .05), 4.5)
            finally:
                panel.context_tools.close(); panel.backend.shutdown()
                panel.close(); panel.deleteLater(); QTest.qWait(10)

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
                if path == '/config': data = {'model': 'test/model'}
                elif path == '/session' and method == 'POST':
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
                from PySide6.QtCore import QSettings
                from PySide6.QtWidgets import QPushButton, QComboBox
                settings = QSettings(tmp + '/assistant.ini', QSettings.IniFormat)
                panel = ChatPanel(tmp, backend=backend, settings=settings)
                self.assertEqual(panel.tracker.store.directory, Path(self.state_directory))
                panel.show()
                self.assertFalse(panel.dont_ask.isChecked())
                panel.composer.setPlainText('Erkläre die Auswahl')
                panel.send_button.click()
                self.wait(lambda: bool(backend.permissions and backend.questions))
                submitted = next(body for _, path, body, _ in state['requests'] if path.endswith('/prompt_async'))
                self.assertNotIn('Native user-text source', submitted['system'])
                self.assertIn('Do not redirect the user to the Tasks page', submitted['system'])
                self.assertIn('pkexec', submitted['system'])
                self.assertNotIn('tools', submitted)  # Existing engine permission policy remains in force.
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
                self.wait(lambda: not backend.permissions and not backend.questions)
                state['permission'] = state['question'] = True
                self.wait(lambda: bool(backend.permissions))
                panel.dont_ask.click()
                backend.set_auto_approve(True)
                backend.publish_requests()
                self.wait(lambda: not state['permission'])
                self.assertIn(('POST', '/permission/per_lumen/reply', {'reply': 'once'}), [r[:3] for r in state['requests']])
                self.assertEqual(sum(path == '/permission/per_lumen/reply' and body == {'reply': 'once'}
                                     for _, path, body, _ in state['requests']), 1)
                self.assertTrue(state['question'])
                self.assertFalse(any(path == '/permission/per_other/reply' for _, path, _, _ in state['requests']))
                another = ChatPanel(tmp, settings=QSettings(tmp + '/assistant.ini', QSettings.IniFormat))
                self.assertTrue(another.dont_ask.isChecked())
                self.assertTrue(another.backend.auto_approve)
                another.backend.shutdown()
                another.close()
                state['child_permission'] = True
                self.wait(lambda: not state['child_permission'])
                self.assertIn(('POST', '/permission/per_child/reply', {'reply': 'once'}), [r[:3] for r in state['requests']])
                self.wait(lambda: not backend.permissions)
                self.assertFalse(any(b.text() == 'Einmal erlauben' for b in panel.requests.findChildren(QPushButton)))
                panel.requests.findChild(QComboBox).setCurrentIndex(1)
                next(b for b in panel.requests.findChildren(QPushButton) if b.text() == 'Antwort senden').click()
                self.wait(lambda: not state['question'])
                panel.dont_ask.click()
                self.assertFalse(settings.value('autoApproveTools', True, type=bool))
                state['child_permission'] = True
                self.wait(lambda: any(p['id'] == 'per_child' for p in backend.permissions))
                self.assertTrue(state['child_permission'])
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
                # Both the initial turn and continuation carry the shared execution
                # policy to OpenCode, including when general auto-approve changed.
                prompts = [body for _, path, body, _ in state['requests'] if path.endswith('/prompt_async')]
                for prompt in prompts:
                    self.assertIn('Do not redirect the user to the Tasks page', prompt['system'])
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
                self.assertEqual(len(panel.tracker.store.tasks()), 3)
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
            self.assertEqual(backend.startup_diagnostic['outcome'], 'start_error')
            self.assertEqual(backend.startup_diagnostic['process_error'], 0)
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
            # The assistant and file manager have distinct entry points, even
            # though both are distributed in the same Lumen package.
            bins = target / 'bin'; bins.mkdir()
            files = target / 'files'; files.mkdir()
            shutil.copy2(stub, bins / 'lumen-agent-app')
            for name in ('lumen', 'lumen-files', 'lumen-python'):
                shutil.copy2(root / 'bin' / name, bins / name)
            (files / 'app.py').write_text('import json,sys;print(json.dumps(["files", *sys.argv[1:]]))\n')
            self.assertEqual(json.loads(subprocess.check_output([str(bins / 'lumen')], text=True)), [])
            for args in ([], [paths[0]], ['sftp://example.test/home/user'], ['--settings']):
                result = subprocess.check_output([str(bins / 'lumen-files'), *args], text=True)
                self.assertEqual(json.loads(result), ['files', *args])
            import importlib.util
            spec = importlib.util.spec_from_file_location('lumen_runner_test', root / 'bin/lumen_krunner.py')
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            command = runner.build_command('--help')
            self.assertIn('--prompt=--help', command)
            self.assertFalse(any(argument.startswith('--directory') for argument in command))
            result = subprocess.run(command + ['--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_file_actions_show_native_results_instead_of_chat(self):
        from assistant import ChatPanel
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp:
            backend = OpenCodeBackend(tmp)
            calls = []
            backend.refresh_sessions = lambda: None
            def send(text, files=None, agent='build', title=None,memory_text=None,context_data=None):
                calls.append((text, agent, title))
                backend.message_id = 'msg_action'
                backend.set_busy(True)
                backend.statusChanged.emit('Lumen arbeitet …')
            backend.send = send
            panel = ChatPanel(tmp, backend=backend, settings=QSettings(tmp + '/assistant.ini', QSettings.IniFormat))
            panel.show()
            try:
                selection = [str(Path(tmp) / 'notiz.txt')]
                panel.begin_context('explain', selection)
                self.assertEqual(panel.heading.text(), 'Erklärung')
                self.assertTrue(panel.composer.isHidden())
                self.assertTrue(panel.sessions.isHidden())
                self.assertTrue(panel.mode.isHidden())
                self.assertTrue(panel.dont_ask.isVisible())
                self.assertTrue(panel.progress.isVisible())
                self.assertEqual(calls[-1][1], 'plan')
                self.assertEqual(calls[-1][2], 'Erklärung · notiz.txt')
                backend.messages = [
                    {'info': {'role': 'user'}, 'parts': [{'type': 'text', 'text': calls[-1][0]}]},
                    {'info': {'role': 'assistant', 'parentID': 'msg_action'},
                     'parts': [{'type': 'text', 'text': 'Diese Datei enthält persönliche Notizen.'}]}]
                backend.messagesChanged.emit(backend.messages)
                backend.set_busy(False)
                backend.statusChanged.emit('Bereit')
                result = panel.transcript.toPlainText()
                self.assertIn('persönliche Notizen', result)
                self.assertNotIn('Ausgewählte Pfade', result)
                self.assertNotIn('LUMEN', result)
                self.assertEqual(panel.status.text(), 'Erklärung bereit')
                panel.action_more.click()
                self.assertEqual(calls[-1][1], 'plan')
                backend.set_busy(False)
                panel.begin_context('fix', selection)
                self.assertEqual(panel.heading.text(), 'Fehler beheben')
                self.assertEqual(calls[-1][1], 'build')
                backend.set_busy(False)
                backend.failed.emit('Verbindung unterbrochen')
                self.assertTrue(panel.retry.isVisible())
                panel.retry.click()
                self.assertIn(selection[0], calls[-1][0])
                backend.set_busy(False)
                panel.begin_context('open', selection)
                self.assertFalse(panel.composer.isHidden())
                self.assertTrue(panel.sessions.isHidden())
                panel.options.click()
                self.assertFalse(panel.sessions.isHidden())
                self.assertTrue(panel.progress.isHidden())
            finally:
                backend.set_busy(False)
                backend.shutdown()
                panel.close()

    def test_english_cancellation_exposes_retry_and_keeps_tracking_sentinel(self):
        from assistant import ChatPanel
        from PySide6.QtCore import QSettings
        with tempfile.TemporaryDirectory() as tmp, patch('lumen_i18n.language', return_value='en'):
            backend = OpenCodeBackend(tmp)
            panel = ChatPanel(tmp, backend=backend, settings=QSettings(tmp + '/assistant.ini', QSettings.IniFormat))
            completed = []
            backend.completed.connect(lambda ok, message: completed.append((ok, message)))
            try:
                panel.set_action('explain')
                backend.set_busy(True)
                self.assertTrue(panel.retry.isHidden())
                backend.stopped()
                self.assertEqual(panel.status.text(), 'Cancelled')
                self.assertFalse(panel.retry.isHidden())
                self.assertFalse(panel.action_more.isEnabled())
                self.assertEqual(completed, [(False, 'Abgebrochen')])
            finally:
                backend.shutdown(); panel.close()

    def test_auto_permissions_keep_proposals_locked_and_clear_on_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = OpenCodeBackend(tmp)
            calls = []
            shown = []
            backend.request = lambda method, path, body=None, callback=None, **kwargs: calls.append((method, path, body))
            backend.ensure_server = lambda callback: callback()
            backend.requestsChanged.connect(lambda permissions, questions: shown.append((permissions, questions)))
            try:
                backend.set_auto_approve(True)
                backend.selected_model = 'test/model'
                backend.send('Vorschläge erstellen', proposal=True)
                self.assertEqual(calls[-1][2]['permission'], [{'permission': '*', 'pattern': '*', 'action': 'deny'}])
                backend.permissions = [{'id': 'per_proposal', 'permission': 'edit'}]
                backend.publish_requests()
                self.assertEqual(len(calls), 1)
                backend.stop()
                backend.set_auto_approve(True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(shown[-1], ([], []))
            finally:
                backend.shutdown()

    def test_memory_version_drift_stops_before_creating_empty_sessions(self):
        from memory_bridge import MemoryBridge
        from lumen_store import Store
        Store().set_setting('memory/options', {'enabled': True, 'learn': False})
        backend = OpenCodeBackend(self.state_directory)
        backend.selected_model = 'test/model'
        backend.ensure_server = lambda callback: callback()
        calls, failures, requests = [], [], []
        backend.failed.connect(failures.append)
        backend.request = lambda *args, **kwargs: requests.append(args)
        def prepared(bridge, text, directory, done):
            calls.append(text)
            self.assertLessEqual(len(calls), 3, 'Memory drift must not retry forever')
            done(dict(stamp=[True, 0, 'new-worker'], context='', notes=[], candidates=[], revision=0))
        try:
            with patch('lumen_memory.stamp', return_value=[True, 0]), patch.object(MemoryBridge, 'prepare', prepared):
                backend.send('Synthetic memory compatibility check')
            self.assertEqual(len(calls), 3)
            self.assertFalse(backend.busy)
            self.assertEqual(len(failures), 1)
            self.assertIn('neu starten', failures[0])
            self.assertEqual(requests, [], 'Inconsistent context must not create sessions or send prompts')
        finally:
            backend.shutdown()

    def test_native_process_closes_during_engine_startup(self):
        import os
        import shutil
        import subprocess
        if not (shutil.which('opencode') or (Path.home() / '.opencode/bin/opencode').exists()):
            self.skipTest('Real local engine not installed')
        root = Path(__file__).resolve().parents[1]
        script = """
import sys,tempfile,os,importlib.util
sys.path.insert(0,'files')
from app import create_app,Window
from PySide6.QtCore import QSettings,QTimer
with tempfile.TemporaryDirectory() as tmp:
    os.environ['XDG_CONFIG_HOME']=tmp+'/config'
    os.environ['LUMEN_DATA']=tmp+'/state'
    app=create_app()
    if sys.argv[2] == 'quit':
        spec=importlib.util.spec_from_file_location('desktop','agent-app/main.py')
        desktop=importlib.util.module_from_spec(spec);spec.loader.exec_module(desktop)
        window=desktop.LumenWindow(tmp)
        app.aboutToQuit.connect(window.chat.backend.shutdown)
        window.chat.begin_context('open',[tmp])
    else:
        window=Window(tmp,QSettings(tmp+'/ui.ini',QSettings.IniFormat))
        window.ask_lumen('open',[tmp])
    window.show()
    # Run the real lifecycle so Qt handles deferred deletions before Python exits.
    QTimer.singleShot(int(sys.argv[1]),app.quit if sys.argv[2] == 'quit' else window.close)
    app.exec()
"""
        for mode in ('close', 'quit'):
            for delay in (0, 150, 500):
                result = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', script, str(delay), mode],
                                        cwd=root, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
