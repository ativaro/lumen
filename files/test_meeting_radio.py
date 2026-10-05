"""Shared tabs retain edits/audio and both legacy entry points use one process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication
from tools_meeting_radio import MeetingRadio
from interop_flush import server_name


class MeetingRadioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        cls.app = QApplication.instance() or create_app()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MeetingRadio('meetings', self.root)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        for page in self.window.pages.values(): page.job = None; page.engine = None
        self.window.close(); self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def test_switch_retains_pages_edits_and_audio_ownership(self):
        from interop_audio import audio_page, controller
        meetings, radio = self.window.pages.values()
        key = meetings.library.create('Planning', agenda='Before', segments=[], results=[])
        meetings.focus_record(key); meetings.agenda.setPlainText('Unsaved agenda')
        radio.focus_record(radio.library.create('Edition', sources=[], script='', minutes=5))
        radio.script.setPlainText('Unsaved script')
        with patch.object(meetings.player, 'stop') as stop_meeting, patch.object(radio.player, 'stop') as stop_radio:
            self.window.select('radio'); self.window.select('meetings')
            self.assertIs(self.window.tabs.currentWidget(), meetings)
            self.assertEqual(meetings.agenda.toPlainText(), 'Unsaved agenda')
            self.assertEqual(radio.script.toPlainText(), 'Unsaved script')
            stop_meeting.assert_not_called(); stop_radio.assert_not_called()
        for name, page in self.window.pages.items():
            self.assertIs(audio_page(page.player), page)
            self.assertEqual(controller(page.player).app, name)
        self.assertTrue(self.window.close())
        self.assertEqual(meetings.library.get(key)['agenda'], 'Unsaved agenda')
        self.assertEqual(radio.library.get(radio.current)['script'], 'Unsaved script')

    def test_hidden_busy_or_failed_page_prevents_partial_close(self):
        meetings, radio = self.window.pages.values()
        radio.job = Mock()
        with patch.object(meetings.player, 'stop') as stop:
            event = QCloseEvent(); self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertIs(self.window.tabs.currentWidget(), radio)
            radio.job.cancelled.set.assert_called_once(); stop.assert_not_called()
        radio.job = None
        with patch.object(radio, 'save', side_effect=OSError('disk full')), patch.object(radio, 'error') as error, patch.object(meetings.player, 'stop') as stop:
            event = QCloseEvent(); self.window.closeEvent(event)
            self.assertFalse(event.isAccepted()); error.assert_called_once_with('disk full'); stop.assert_not_called()

    def test_catalogue_and_legacy_settings_route(self):
        from lumen_apps import catalogue, launch
        from settings_dialog import SettingsDialog
        keys = [row[0] for row in catalogue()]
        self.assertIn('meetings', keys); self.assertNotIn('radio', keys)
        with patch('lumen_apps.QProcess.startDetached', return_value=(True, 42)) as start:
            launch('radio'); self.assertEqual(start.call_args.args[1][-1], 'radio')
        dialog = SettingsDialog(application='radio', load_system=False)
        self.assertEqual(dialog.stack.currentIndex(), dialog.app_pages['meetings'])
        self.assertIn('radio', dialog.app_controls); self.assertIn('meetings', dialog.app_controls)
        dialog.deleteLater()

    def test_both_launchers_share_process_and_backup_endpoints(self):
        root = self.root/'process'
        command = [sys.executable, str(Path(__file__).with_name('tools_app.py'))]
        env = dict(os.environ, LUMEN_TOOLS_DATA=str(root))
        with tempfile.TemporaryFile() as output:
            proc = subprocess.Popen(command+['radio'], env=env, stdout=output, stderr=output)
            try:
                deadline = time.monotonic()+20
                while not all((root/name/'window.lock').exists() for name in ('meetings','radio')):
                    self.assertIsNone(proc.poll())
                    if time.monotonic() > deadline: self.fail('Window did not start')
                    time.sleep(.05)
                for name in ('meetings', 'radio'):
                    result = subprocess.run(command+[name], env=env, stdout=output, stderr=output, timeout=15)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(int((root/name/'window.lock').read_text().splitlines()[0]), proc.pid)
                    socket = QLocalSocket(); socket.connectToServer(server_name(root/name))
                    self.assertTrue(socket.waitForConnected(2000))
                    socket.write(json.dumps({'vault_flush':'a'*32}).encode()+b'\n'); socket.waitForBytesWritten(1000)
                    self.assertTrue(socket.waitForReadyRead(5000))
                    response = json.loads(bytes(socket.readAll()))
                    self.assertTrue(response['ok'], response); self.assertEqual(response['app'], name)
                    socket.disconnectFromServer()
            finally:
                proc.terminate(); proc.wait(timeout=10)
