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
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest
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

    def test_empty_library_actions_busy_and_archive_preserve_records(self):
        meetings = self.window.pages['meetings']
        self.assertIs(meetings.surface.currentWidget(),meetings.empty)
        self.assertTrue(meetings.empty.action.isEnabled())
        with patch.object(meetings,'create') as create:
            meetings.empty.action.click(); create.assert_called_once_with()
        meetings.begin('Import'); self.assertFalse(meetings.empty.action.isEnabled())
        meetings.end(); self.assertTrue(meetings.empty.action.isEnabled())
        key=meetings.library.create('Vorbereitung',agenda='Offene Fragen',segments=[],results=[])
        meetings.focus_record(key)
        self.assertIs(meetings.surface.currentWidget(),meetings.body)
        self.assertIs(meetings.transcript_surface.currentWidget(),meetings.transcript_empty)
        with patch.object(meetings,'create') as create:
            meetings.transcript_empty.action.click(); create.assert_called_once_with()
        meetings.archive()
        self.assertIs(meetings.surface.currentWidget(),meetings.empty)
        self.assertTrue(meetings.library.get(key)['_archived'])
        meetings.archived.setChecked(True)
        meetings.entries.setCurrentRow(0)
        self.assertEqual(meetings.current,key)
        self.assertEqual(meetings.agenda.toPlainText(),'Offene Fragen')
        meetings.archive(); self.assertFalse(meetings.library.get(key)['_archived'])

    def test_transcript_edits_seek_export_and_source_metadata_survive(self):
        meetings = self.window.pages['meetings']
        key=meetings.library.create('Workshop',segments=[dict(start=2400,end=8500,text='Original')],
            results=[dict(kind='actions',text='Unterlagen ergänzen',segment=0,due='2026-10-23',source_url='https://example.org',done=False)],summary='Kurzfassung',agenda='Ziele')
        meetings.focus_record(key)
        self.assertIs(meetings.transcript_surface.currentWidget(),meetings.transcript)
        meetings.transcript.item(0,1).setText('Korrigiert')
        meetings.results.item(0,0).setCheckState(Qt.Checked)
        with patch.object(meetings.player,'play_at') as play:
            meetings.seek_segment(0,0); meetings.seek_result(0,2)
            self.assertEqual(play.call_args_list,[((2400,),),((2400,),)])
        with patch.object(meetings,'export_text') as export:
            meetings.export()
            text,name=export.call_args.args
            self.assertIn('[00:00:02] Korrigiert',text);self.assertIn('- [x] Unterlagen ergänzen',text)
            self.assertIn('Ziele',text); self.assertEqual(name,'meeting.md')
        saved=meetings.library.get(key)
        self.assertEqual(saved['results'][0]['due'],'2026-10-23')
        self.assertEqual(saved['results'][0]['source_url'],'https://example.org')
        meetings.focus_record(key);self.assertEqual(meetings.transcript.item(0,1).text(),'Korrigiert')

    def test_radio_sources_empty_state_and_mode_navigation_retain_edits(self):
        radio = self.window.pages['radio']
        key=radio.library.create('Ausgabe',sources=[],script='',minutes=5)
        radio.focus_record(key); self.window.modes.setCurrentIndex(1)
        self.assertIs(self.window.tabs.currentWidget(),radio)
        self.assertIs(radio.source_surface.currentWidget(),radio.sources_empty)
        with patch.object(radio,'add_text') as add:
            radio.sources_empty.action.click();add.assert_called_once_with()
        radio.append_source(dict(title='Notiz',text='Original',selected=True))
        self.assertEqual(radio.source_surface.currentIndex(),0)
        radio.source_text.setPlainText('Überarbeitet'); radio.script.setPlainText('Mein eigener Sprechtext')
        self.window.modes.setCurrentIndex(0);self.window.modes.setCurrentIndex(1)
        radio.save(); radio.focus_record(key)
        self.assertEqual(radio.library.get(key)['sources'][0]['text'],'Überarbeitet')
        self.assertEqual(radio.script.toPlainText(),'Mein eigener Sprechtext')
        radio.remove_source()
        self.assertIs(radio.source_surface.currentWidget(),radio.sources_empty)
        self.assertEqual(radio.library.get(key)['sources'],[])
        self.assertEqual(radio.script.toPlainText(),'Mein eigener Sprechtext')

    def test_long_transcript_reflows_when_window_narrows(self):
        from appearance import apply_design
        apply_design(self.app,'graphite')
        meetings=self.window.pages['meetings']
        key=meetings.library.create('Langer Text',segments=[dict(start=0,end=30000,text='Eine längere Aussage muss auch in einem schmalen Fenster vollständig lesbar bleiben. '*12)],results=[])
        self.window.resize(1440,900);meetings.focus_record(key);QTest.qWait(50)
        wide=meetings.transcript.rowHeight(0)
        self.window.resize(960,760);QTest.qWait(50)
        self.assertGreater(meetings.transcript.rowHeight(0),wide)
        self.assertLessEqual(meetings.transcript.columnWidth(0)+meetings.transcript.columnWidth(1),meetings.transcript.viewport().width())
        self.assertEqual(meetings.transcript.horizontalScrollBar().maximum(),0)

    def test_embedded_audio_fits_compact_window_without_changing_standalone_minimum(self):
        from tools_meetings import Meetings
        from tools_radio import Radio
        for kind in (Meetings, Radio):
            standalone = kind(self.root/'standalone')
            try:
                self.assertEqual((standalone.minimumWidth(),standalone.minimumHeight()),(840,600))
            finally:
                standalone.close(); standalone.deleteLater()
        self.window.resize(960,640)
        for name,page in self.window.pages.items():
            with self.subTest(page=name):
                key=page.library.create('Kompakte Ansicht',segments=[],results=[],agenda='',sources=[],script='',minutes=5)
                page.focus_record(key)
                self.window.select(name); QTest.qWait(30)
                self.assertEqual((self.window.width(),self.window.height()),(960,640))
                for control in (self.window.modes,page.tabs.tabBar(),page.status):
                    self.assertTrue(control.isVisibleTo(self.window))
                    top=control.mapTo(self.window,control.rect().topLeft())
                    self.assertGreaterEqual(top.y(),0)
                    self.assertLessEqual(top.y()+control.height(),self.window.height())

    def test_loaded_audio_titles_show_start_and_literal_full_tooltip(self):
        from PySide6.QtGui import QTextDocument
        title=('Sanierung <b>Haus</b> & Wartung – Angebote und offene Entscheidungen '*3).strip()
        for name,page in self.window.pages.items():
            with self.subTest(page=name):
                key=page.library.create(title,segments=[],results=[],agenda='',sources=[],script='',minutes=5)
                page.focus_record(key)
                self.assertEqual(page.title.cursorPosition(),0)
                tip=QTextDocument(); tip.setHtml(page.title.toolTip())
                self.assertEqual(tip.toPlainText(),title)
                page.title.setCursorPosition(len(title))
                QTest.keyClicks(page.title,' X'); page.save()
                self.assertEqual(page.title.cursorPosition(),len(title)+2)
                self.assertEqual(page.library.get(key)['title'],title+' X')
        radio=self.window.pages['radio']; radio.append_source(dict(title=title,text='Quelle',selected=True))
        self.assertEqual(radio.source_title.cursorPosition(),0)
        tip=QTextDocument(); tip.setHtml(radio.source_title.toolTip())
        self.assertEqual(tip.toPlainText(),title)
        radio.remove_source(); self.assertEqual(radio.source_title.toolTip(),'')

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
