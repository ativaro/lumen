"""Notes host construction uses the real AppSession and private Qt profile."""
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = '1'
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu --disable-dev-shm-usage --no-sandbox'

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop_design import AppHeader
from server_app_session import AppSession, Binding, SessionError
from server_app_window import (ServerAppWindow, QWebEngineScript, DRAFT_SCRIPT,
    NOTES_DRAFT_SCRIPT, WEBENGINE)


@unittest.skipUnless(WEBENGINE, 'Qt WebEngine is required for the real native host')
class NotesHostWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('LUMEN_NOTES_TEST_ROOT'))
        self.root = Path(self.temp.name)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
        deadline = time.monotonic() + 5
        while not all(window._disposed for window in self.windows) and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(all(window._disposed for window in self.windows))
        self.temp.cleanup()

    def session(self, app):
        binding = Binding('https://notes.example.invalid',
            '73000000-0000-4000-8000-000000000001',
            '73000000-0000-4000-8000-000000000002', app)
        return AppSession(dict(server=binding.origin, device_id=binding.device,
            token='synthetic-private-construction-only'), binding)

    def window(self, app):
        # No event-loop turn before assertions: the queued connection check has
        # not run, and close disables it before profile cleanup processes events.
        window = ServerAppWindow(self.session(app), self.root)
        self.windows.append(window)
        return window

    def test_notes_profile_uses_notes_identity_and_isolated_draft_guard(self):
        window = self.window('notes')
        self.assertEqual(window.windowTitle(), 'Lumen Notes')
        self.assertEqual(window.status_page.findChild(AppHeader).title.text(), 'Lumen Notes')
        self.assertEqual(window.copy.text(), 'Textkopie der ungespeicherten Notiz')
        script = window.page.scripts().find('Lumen Notes draft')[0]
        self.assertEqual(script.sourceCode(), NOTES_DRAFT_SCRIPT)
        self.assertEqual(script.worldId(), QWebEngineScript.ScriptWorldId.ApplicationWorld)
        self.assertFalse(script.runsOnSubFrames())
        self.assertIn("new Event('beforeunload',{cancelable:true})", script.sourceCode())
        self.assertNotIn('translation-text', script.sourceCode())
        self.assertIsNone(window._worker)
        self.assertEqual(window.session.state, 'disconnected')

    def test_notes_cannot_enter_compose_file_import(self):
        window = self.window('notes')
        with self.assertRaises(SessionError):
            window._lumen_file_import()
        self.assertIsNone(window._import_lease)
        self.assertIsNone(window._connection_watcher)
        self.assertIsNone(window._worker)

    def test_compose_keeps_existing_script_and_other_apps_are_rejected(self):
        window = self.window('compose')
        self.assertEqual(window.windowTitle(), 'Lumen Compose')
        self.assertEqual(window.copy.text(), 'Entwurf kopieren')
        self.assertEqual(window.page.scripts().find('Lumen Compose draft')[0].sourceCode(), DRAFT_SCRIPT)
        with self.assertRaises(SessionError):
            ServerAppWindow(self.session('projects'), self.root)


if __name__ == '__main__':
    unittest.main()
