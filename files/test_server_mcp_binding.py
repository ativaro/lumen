"""Paired server tools belong only to the effective private engine profile, which lumen-service builds
(native/service/src/engine.rs; the pairing checks themselves are its Rust tests). These tests run the
service with an engine stand-in that records what it was started with and answers like OpenCode."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from assistant_backend import OpenCodeBackend

ENGINE = r'''#!{python}
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
base = sys.argv[0]
open(base + '.env', 'w').write(json.dumps(dict(os.environ)))
open(base + '.pid', 'w').write(str(os.getpid()))
sessions = json.load(open(base + '.sessions')) if os.path.exists(base + '.sessions') else {{}}
prompts = {{}}
class Engine(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self): self.answer()
    def do_POST(self): self.answer()
    def answer(self):
        url = urlsplit(self.path); path = url.path
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
        with open(base + '.log', 'a') as log: log.write(json.dumps([self.command, path, body]) + '\n')
        if path == '/event': self.send_error(404); return
        data = {{}}
        if path == '/session' and self.command == 'POST':
            data = dict(body, id='ses_new' + str(len(sessions)), directory=parse_qs(url.query)['directory'][0])
            sessions[data['id']] = data
        elif path == '/session': data = list(sessions.values())
        elif path.startswith('/session/') and path.count('/') == 2 and path != '/session/status':
            data = sessions.get(path.split('/')[2], {{}})
        elif path.endswith('/prompt_async'): prompts[path.split('/')[2]] = body['messageID']
        elif path.endswith('/message'):
            parent = prompts.get(path.split('/')[2])
            data = [dict(info=dict(id='msg_a', role='assistant', parentID=parent, finish='stop', time=dict(completed=1)),
                         parts=[dict(type='text', text='Fertig')])] if parent and not os.path.exists(base + '.hold') else []
        elif path in ('/permission', '/question'): data = []
        raw = json.dumps(data).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
server = ThreadingHTTPServer(('127.0.0.1', 0), Engine)
print('opencode server listening on http://127.0.0.1:%d' % server.server_port, flush=True)
server.serve_forever()
'''


class ServerMCPBindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.environment = dict(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root/'config'),
            XDG_DATA_HOME=str(self.root/'data'), XDG_CACHE_HOME=str(self.root/'cache'),
            XDG_STATE_HOME=str(self.root/'state'), LUMEN_DATA=str(self.root/'lumen'), OPENCODE_CONFIG_CONTENT='{}')
        self.engine = self.root/'engine'
        self.engine.write_text(ENGINE.format(python=sys.executable)); self.engine.chmod(0o700)
        self.environment['LUMEN_OPENCODE_BIN'] = str(self.engine)
        self.enterContext(patch.dict(os.environ, self.environment))
        self.config = self.root/'config/lumen-server/connection.json'
        self.write_pairing()

    def write_pairing(self, **changes):
        value = dict(server='https://staging.invalid', token='synthetic-device-token',
            device_id='a5c704e4-c826-479b-bcde-41b2c8dc8efb')
        value.update(changes)
        self.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config.write_text(json.dumps(value)); self.config.chmod(0o600)
        return value

    def stamp(self, pairing):
        """The binding as the earlier Python computed it; the service keeps it byte-identical."""
        fields = {k: pairing.get(k) for k in ('server', 'device_id', 'token', 'account', 'ca_file')}
        return hashlib.sha256(json.dumps([str(self.root), str(self.root/'config'), fields], sort_keys=True).encode()).hexdigest()

    def wait(self, condition, limit=8):
        until = time.monotonic()+limit
        while not condition() and time.monotonic() < until:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(condition())

    def backend(self, **kwargs):
        backend = OpenCodeBackend(str(self.root), **kwargs)
        backend.settings = QSettings(str(self.root/'assistant.ini'), QSettings.IniFormat)
        backend.selected_model = 'test/model'
        self.addCleanup(backend.shutdown)
        return backend

    def started(self):
        return json.loads(Path(str(self.engine)+'.env').read_text())

    def start(self, backend):
        for name in ('.env', '.pid'): Path(str(self.engine)+name).unlink(missing_ok=True)
        ready = []
        backend.ensure_server(lambda: ready.append(True))
        self.wait(lambda: bool(ready))
        return json.loads(self.started()['OPENCODE_CONFIG_CONTENT'])

    def requests(self):
        log = Path(str(self.engine)+'.log')
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def ended(self, pid):
        # A process reaped between the two looks has ended too.
        try:
            os.kill(pid, 0)
            return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].startswith('Z')
        except (ProcessLookupError, FileNotFoundError): return True

    def test_private_engine_merges_current_pairing_and_the_crates_plugin_without_touching_disk_config(self):
        original = dict(model='provider/model', plugin=['@example/owned@1.0.0'], permission={'edit': 'ask'},
            mcp={'other': {'type': 'local', 'command': ['true']}, 'lumen-server': {'enabled': False}})
        os.environ['OPENCODE_CONFIG_CONTENT'] = json.dumps(original)
        before = self.config.read_bytes()
        result = self.start(self.backend())
        self.assertEqual(result['mcp']['lumen-server'], dict(type='remote', url='https://staging.invalid/mcp/',
            headers={'Authorization': 'Bearer synthetic-device-token'}, enabled=True, oauth=False))
        self.assertEqual(result['mcp']['other'], original['mcp']['other'])
        self.assertEqual(result['skills'], {'urls': ['https://staging.invalid/api/skills/']})
        self.assertEqual(result['plugin'][0], '@example/owned@1.0.0')
        self.assertEqual(len(result['plugin']), 2)
        plugin = Path(result['plugin'][1].removeprefix('file://'))
        self.assertEqual(plugin.read_text(), (Path(__file__).parents[1]/'native/engine/src/lumen-continuity.mjs').read_text())
        self.assertEqual(plugin.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(os.environ['OPENCODE_CONFIG_CONTENT'], json.dumps(original))
        self.assertEqual(self.started()['OPENCODE_SERVER_USERNAME'], 'opencode')
        self.assertGreaterEqual(len(self.started()['OPENCODE_SERVER_PASSWORD']), 32)
        self.assertFalse(any(p.name in ('opencode.json', 'opencode.jsonc') for p in self.root.rglob('*')))

    def test_learning_environment_uses_its_effective_profile_without_personal_fallback(self):
        profile = self.root/'learning'
        backend = self.backend()
        # The service's own learning engine (native/service/src/learning.rs) names its profile so.
        environment = dict(HOME=str(profile), XDG_CONFIG_HOME=str(profile/'config'),
            OPENCODE_CONFIG_CONTENT=json.dumps(dict(model='learning/model', mcp={'lumen_learning': {'type': 'local', 'command': ['true']}})))
        engine = backend.engine
        backend.engine = lambda: dict(engine(), environment=environment)
        result = self.start(backend)
        self.assertEqual(result['mcp']['lumen-server'], {'enabled': False})
        self.assertEqual(result['mcp']['lumen_learning'], {'type': 'local', 'command': ['true']})
        self.assertEqual(result['model'], 'learning/model')
        self.assertEqual(self.started()['HOME'], str(profile))

    def test_invalid_configuration_never_starts_an_engine_or_exposes_secrets(self):
        for changes in (dict(server='https://user@host.invalid'), dict(token='secret\r\nHeader: no'), dict(device_id='invalid')):
            with self.subTest(changes=changes):
                self.write_pairing(**changes); backend = self.backend(); errors = []; ready = []
                backend.failed.connect(errors.append)
                backend.ensure_server(lambda: ready.append(True))
                self.wait(lambda: bool(errors))
                self.assertFalse(ready); self.assertFalse(Path(str(self.engine)+'.env').exists())
                self.assertNotIn(str(changes), str(errors))
        self.write_pairing()
        os.environ['OPENCODE_CONFIG_CONTENT'] = '{"mcp": []}'
        backend = self.backend(); errors = []
        backend.failed.connect(errors.append); backend.ensure_server(lambda: None)
        self.wait(lambda: bool(errors)); self.assertFalse(Path(str(self.engine)+'.env').exists())

    def test_binding_change_fences_ensure_request_send_and_poll_then_resets_conversation(self):
        for operation in ('ensure', 'request', 'poll', 'send'):
            with self.subTest(operation=operation):
                self.write_pairing(); backend = self.backend(); self.start(backend)
                pid = int(Path(str(self.engine)+'.pid').read_text())
                backend.session = 'ses_old'; backend.messages = [{'info': {'role': 'user'}, 'parts': []}]
                failures = []; backend.failed.connect(failures.append)
                self.write_pairing(server='https://replacement.invalid', token='replacement-token',
                    device_id='b5c704e4-c826-479b-bcde-41b2c8dc8efb')
                sent = len(self.requests())
                if operation == 'ensure': backend.ensure_server(lambda: self.fail('Old callback used'))
                elif operation == 'request': backend.request('GET', '/config', callback=lambda _: self.fail('Old answer used'))
                elif operation == 'poll': backend.poll()
                else: backend.send('Do not attach this to the previous account')
                self.wait(lambda: bool(failures))
                self.assertEqual(self.requests()[sent:], [], 'nothing reaches the engine of the old pairing')
                self.assertEqual(backend.session, ''); self.assertEqual(backend.messages, []); self.assertFalse(backend.busy)
                self.wait(lambda: self.ended(pid))
                result = self.start(backend)
                self.assertEqual(result['mcp']['lumen-server']['url'], 'https://replacement.invalid/mcp/')
                self.assertEqual(result['mcp']['lumen-server']['headers']['Authorization'], 'Bearer replacement-token')
                backend.shutdown()

    def test_a_running_turn_stops_when_the_pairing_is_removed(self):
        backend = self.backend(); self.start(backend)
        Path(str(self.engine)+'.hold').touch()
        failures = []; backend.failed.connect(failures.append)
        backend.send('Wait for the answer', proposal=True)
        self.wait(lambda: any(path.endswith('/prompt_async') for _, path, _ in self.requests()))
        self.assertTrue(backend.busy)
        self.config.unlink()
        self.wait(lambda: bool(failures))
        self.assertIn('Serververbindung', failures[-1])
        self.assertEqual(backend.session, ''); self.assertFalse(backend.busy)
        self.assertEqual(sum(path.endswith('/prompt_async') for _, path, _ in self.requests()), 1)

    def test_history_and_live_selection_cannot_restore_a_different_binding(self):
        current = self.stamp(self.write_pairing())
        rows = {name: dict(id=name, directory=str(self.root), metadata=metadata) for name, metadata in (
            ('ses_current', dict(client='lumen', lumen_server_binding=current)),
            ('ses_previous', dict(client='lumen', lumen_server_binding='old')),
            ('ses_legacy', dict(client='lumen')))}
        Path(str(self.engine)+'.sessions').write_text(json.dumps(rows))
        backend = self.backend(); captured = []; backend.sessionsChanged.connect(captured.append)
        backend.refresh_sessions()
        self.wait(lambda: bool(captured))
        self.assertEqual([r['id'] for r in captured[-1]], ['ses_current'])
        backend.select_session('ses_current')
        self.wait(lambda: backend.session == 'ses_current')
        failures = []; backend.failed.connect(failures.append)
        backend.select_session('ses_previous')
        self.wait(lambda: bool(failures))
        self.assertEqual(backend.session, ''); self.assertEqual(captured[-1], [])
        # Nothing in the engine database was deleted or rewritten.
        self.assertFalse(any(method != 'GET' for method, _, _ in self.requests()))

    def test_recovery_assigned_session_id_is_checked_before_messages_or_prompt(self):
        rows = {'ses_restored': dict(id='ses_restored', directory=str(self.root),
                                     metadata=dict(client='lumen', lumen_server_binding='previous-account'))}
        Path(str(self.engine)+'.sessions').write_text(json.dumps(rows))
        backend = self.backend(); failures = []; backend.failed.connect(failures.append)
        # A companion turn keeps the session and needs no account persona from the paired server.
        backend.session = 'ses_restored'; backend.screen_guidance = True
        backend.send('Continue the restored conversation')
        self.wait(lambda: bool(failures))
        paths = [path for _, path, _ in self.requests()]
        self.assertIn('/session/ses_restored', paths)
        self.assertFalse(any(path.startswith('/session/ses_restored/') for path in paths))
        self.assertEqual(backend.session, '')

    def test_explicit_external_engine_is_not_claimed_or_reconfigured(self):
        backend = self.backend(server_url='http://127.0.0.1:54321')
        self.config.write_text('broken pairing must not configure an external engine')
        ready = []; backend.ensure_server(lambda: ready.append(True))
        self.wait(lambda: bool(ready))
        self.assertFalse(Path(str(self.engine)+'.env').exists())


if __name__ == '__main__': unittest.main()
