"""The persona of conversations and the settings view, through the built service (native/service/src/persona.rs
with the crate native/persona, whose own tests pin profiles, presets and style texts) against an engine stand-in
and a local HTTPS server with a throwaway CA for the account persona."""
import json
import os
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

import lumen_service
from persona_settings import load

KATE = 'Kate character:'


def save(settings, value):
    settings.setValue('personaProfile', json.dumps(value, ensure_ascii=False)); settings.sync()


def serve(handler, context=None):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    if context: server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True).start()
    return server


class PersonaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def setUp(self):
        from assistant_backend import OpenCodeBackend
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        # A runtime folder of its own: the test never reaches the user's service.
        self.enterContext(patch.dict(os.environ, {'LUMEN_DATA': self.tmp + '/data', 'XDG_RUNTIME_DIR': self.tmp,
                                                  'XDG_CONFIG_HOME': self.tmp + '/config'}))
        self.enterContext(patch.object(lumen_service, '_checked', None))
        self.prompts, self.sessions = [], []
        test = self

        class Engine(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self): self.reply()
            def do_POST(self): self.reply()

            def reply(self):
                path = self.path.split('?')[0]
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or 'null')
                if path == '/event': self.send_error(404); return
                data = {}
                if path == '/session' and self.command == 'POST':
                    test.sessions.append('ses_%d' % (len(test.sessions) + 1)); data = {'id': test.sessions[-1]}
                elif path.endswith('/prompt_async'): test.prompts.append(dict(body, session=path.split('/')[2]))
                elif path.endswith('/message'):
                    data = [{'info': {'role': 'assistant', 'parentID': test.prompts[-1]['messageID'], 'finish': 'stop',
                                      'time': {'completed': 1}}, 'parts': [{'type': 'text', 'text': 'ok'}]}]
                elif path in ('/permission', '/question'): data = []
                raw = json.dumps(data).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        engine = serve(Engine)
        self.addCleanup(engine.server_close); self.addCleanup(engine.shutdown)
        self.backend = OpenCodeBackend(self.tmp, server_url='http://127.0.0.1:%d' % engine.server_port)
        self.settings = QSettings(self.tmp + '/assistant.ini', QSettings.IniFormat)
        self.backend.settings = self.settings
        self.backend.selected_model = 'test/model'
        self.backend.refresh_sessions = lambda: None
        self.messages, self.failures = [], []
        self.backend.memoryStatus.connect(self.messages.append)
        self.backend.failed.connect(self.failures.append)
        self.enterContext(patch('lumen_memory.options', return_value={'enabled': False}))
        self.addCleanup(self.dispose)

    def dispose(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        self.backend.shutdown(); self.backend.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def prompt(self, **kwargs):
        """One turn through the service; the system text the engine received, or None."""
        from PySide6.QtTest import QTest
        done = []
        self.backend.completed.connect(lambda ok, _: done.append(ok))
        before = len(self.prompts)
        self.backend.send('Test', **kwargs)
        deadline = time.monotonic() + 15
        while not done and time.monotonic() < deadline: QTest.qWait(10)
        self.backend.completed.disconnect()
        self.assertTrue(done, 'the turn did not end')
        return self.prompts[-1]['system'] if len(self.prompts) > before else None

    def pair(self, mode=0o600):
        """A pairing with a local HTTPS server for the account persona; returns its answers and requests."""
        certificates = Path(self.tmp) / 'ca'; certificates.mkdir()
        (certificates / 'server.ext').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,'
                                                'keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n')
        for command in (['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=Persona Fixture CA',
                         '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign',
                         '-keyout', 'ca.key', '-out', 'ca.pem'],
                        ['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=127.0.0.1', '-keyout', 'server.key',
                         '-out', 'server.csr'],
                        ['x509', '-req', '-days', '1', '-in', 'server.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
                         '-set_serial', '2', '-extfile', 'server.ext', '-out', 'server.pem']):
            subprocess.run(['openssl', *command], cwd=certificates, check=True, capture_output=True, timeout=20)
        account = dict(status=200, body={}, requests=0)

        class Account(BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def do_GET(self):
                account['requests'] += 1
                raw = json.dumps(account['body']).encode()
                self.send_response(account['status']); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificates / 'server.pem', certificates / 'server.key')
        server = serve(Account, context)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        path = Path(self.tmp) / 'config/lumen-server/connection.json'; path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(server='https://127.0.0.1:%d' % server.server_port, token='synthetic-token',
                                        device_id='a5c704e4-c826-479b-bcde-41b2c8dc8efb', ca_file=str(certificates / 'ca.pem'))))
        path.chmod(mode)
        return account

    def test_corrupt_preferences_give_the_default_profile(self):
        self.assertEqual(load(self.settings)['preset'], 'guide')
        for bad in ('broken', '[]', 'null', '{"preset": []}'):
            self.settings.setValue('personaProfile', bad)
            self.assertEqual(load(self.settings)['preset'], 'guide')

    def test_actual_request_refreshes_global_settings_and_excludes_proposals(self):
        save(self.settings, dict(preset='companion', name='Nova'))
        first = self.prompt()
        self.assertIn('"display_name": "Nova"', first); self.assertIn('"persona": "companion"', first)
        save(QSettings(self.settings.fileName(), QSettings.IniFormat), dict(preset='professional', name='Atlas'))
        second = self.prompt()
        self.assertIn('"display_name": "Atlas"', second); self.assertIn('"persona": "professional"', second)
        # Another profile begins the conversation anew.
        self.assertEqual([p['session'] for p in self.prompts], ['ses_1', 'ses_2'])
        proposal = self.prompt(proposal=True)
        self.assertNotIn('Conversation style', proposal)
        # Saved with sorted keys, the same profile keeps the conversation.
        self.backend.new_conversation()
        self.prompt(); self.settings.setValue('personaProfile', json.dumps(load(self.settings), sort_keys=True)); self.prompt()
        self.assertEqual(self.prompts[-1]['session'], self.prompts[-2]['session'])

    def test_session_override_survives_switch_and_new_chat_resets(self):
        from lumen_store import Store
        self.assertTrue(self.backend.set_persona('kate'))
        self.assertIn(KATE, self.prompt())
        session = self.backend.session
        self.assertEqual(Store().setting('persona/session/' + session), 'kate')
        self.assertIn(KATE, self.prompt()); self.assertEqual(self.prompts[-1]['session'], session)
        self.backend.new_conversation(); self.assertEqual(self.backend.persona_choice(), '')
        self.backend.ask = lambda op, done, error=None, **values: done(dict(messages=[], permissions=[], questions=[],
                                                                          busy=False, status='Bereit'))
        self.backend.select_session(session); self.assertEqual(self.backend.persona_choice(), 'kate')
        self.assertTrue(self.backend.set_persona(''))
        self.assertEqual(self.backend.persona_choice(), ''); self.assertEqual(Store().setting('persona/session/' + session), '')
        self.backend.set_busy(True)
        self.assertFalse(self.backend.set_persona('maker'))
        self.backend.set_busy(False)
        self.assertFalse(self.backend.set_persona(['bad'])); self.assertFalse(self.backend.set_persona('nobody'))

    def test_account_profile_refresh_local_override_and_unavailable_status_with_memory_off(self):
        account = self.pair()
        profile = load(self.settings) | dict(name='Account guide', preset='companion', closeness='personal',
                                             directness='gentle', humor='casual')
        account['body'] = dict(profile=profile, revision=1)
        save(self.settings, dict(name='Local guide', preset='professional'))
        first = self.prompt(); self.assertIn('Account guide', first); self.assertNotIn('Local guide', first)
        self.prompt(); self.assertEqual([p['session'] for p in self.prompts], ['ses_1', 'ses_1'])
        account['body'] = dict(profile=dict(profile, name='Changed guide'), revision=2)
        self.assertIn('Changed guide', self.prompt()); self.assertEqual(self.prompts[-1]['session'], 'ses_2')
        self.settings.setValue('personaLocalOverride', True)
        before = account['requests']
        self.assertIn('Local guide', self.prompt()); self.assertEqual(account['requests'], before)
        self.settings.setValue('personaLocalOverride', False)
        account['status'] = 503
        fallback = self.prompt(); self.assertNotIn('Local guide', fallback); self.assertNotIn('Changed guide', fallback)
        self.assertIn('"display_name": "Lumen"', fallback)
        self.assertTrue(any('Standardstil' in m for m in self.messages))
        self.assertEqual(self.failures, [])

    def test_an_unreadable_pairing_is_named_and_nothing_is_sent(self):
        self.pair(mode=0o644)
        self.assertIsNone(self.prompt())
        self.assertEqual(self.failures, ['Persona- oder Serverbindung nicht lesbar. Bitte Einstellungen prüfen.'])

    def test_editor_unsaved_preview_identity_and_conflicting_window(self):
        from persona_settings import PersonaEditor
        editor = PersonaEditor(self.settings, lambda: None)
        other = PersonaEditor(self.settings, lambda: None)
        try:
            editor.fields['name'].setText('Nova')
            editor.preset.setCurrentIndex(editor.preset.findData('kate'))
            editor.choose_preset(0)
            self.assertEqual(editor.fields['name'].text(), 'Nova')
            self.assertEqual(load(self.settings)['name'], 'Lumen')
            self.assertEqual(editor.fields['length'].currentData(), 'short')
            self.assertEqual(editor.example.text(), 'Das ist lästig. Ich würde zuerst die Erreichbarkeit prüfen, '
                                                    'bevor wir Einstellungen ändern.')
            editor.commit(); self.assertEqual(load(self.settings)['name'], 'Nova')
            self.assertEqual(load(self.settings)['preset'], 'kate')
            other.fields['name'].setText('Conflict'); other.commit()
            self.assertEqual(load(self.settings)['name'], 'Nova')
            self.assertIn('anderen Fenster', other.description.text())
        finally: editor.deleteLater(); other.deleteLater()

    def test_without_the_service_the_page_opens_with_a_notice_and_changes_nothing(self):
        from persona_settings import PersonaEditor
        from PySide6.QtWidgets import QLabel
        with patch('persona_settings.persona_catalogue', side_effect=TimeoutError('Lumen service did not start')):
            editor = PersonaEditor(self.settings, lambda: None)
        try:
            self.assertIn('Lumen-Dienst nicht antwortet', editor.findChildren(QLabel)[0].text())
            self.assertTrue(editor.apply.isHidden() and editor.preset.isHidden())
            # The setup summary saves only a changed persona.
            self.assertEqual(editor.value(), editor.initial)
        finally: editor.deleteLater()

    def test_paired_editor_keeps_local_profile_and_requires_explicit_override(self):
        from persona_settings import PersonaEditor
        config = dict(server='https://synthetic.invalid', device_id='synthetic', token='synthetic')
        save(self.settings, dict(name='Preserved local'))
        with patch('lumen_connect.read_config', return_value=config):
            editor = PersonaEditor(self.settings, lambda: None)
            try:
                self.assertTrue(editor.local_panel.isHidden()); self.assertFalse(editor.override.isChecked())
                editor.commit(); self.assertEqual(load(self.settings)['name'], 'Preserved local')
                editor.override.setChecked(True); self.assertFalse(editor.local_panel.isHidden())
                editor.fields['name'].setText('Explicit local'); editor.commit()
                self.assertTrue(self.settings.value('personaLocalOverride', type=bool))
                self.assertEqual(load(self.settings)['name'], 'Explicit local')
                editor.override.setChecked(False); editor.commit()
                self.assertFalse(self.settings.value('personaLocalOverride', type=bool))
                self.assertEqual(load(self.settings)['name'], 'Explicit local')
            finally: editor.deleteLater()


if __name__ == '__main__': unittest.main()
