import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QCoreApplication, QEvent, QProcessEnvironment, QTimer, QObject, Signal
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QDialog, QDialogButtonBox, QComboBox
from PySide6.QtTest import QTest

import interop_audio as audio


class Player(QWidget):
    def __init__(self):
        super().__init__()
        self.proc = object()
        self.paused = False
        self.time = QLabel(self)
        self.changes = []

    def set_paused(self, value):
        self.paused = value
        self.changes.append(value)


class Process(QObject):
    errorOccurred = Signal(int)
    finished = Signal(int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.env = QProcessEnvironment()
        self.command = None

    def processEnvironment(self): return self.env
    def setProcessEnvironment(self, value): self.env = value
    def setProcessChannelMode(self, _): pass
    def start(self, command, arguments): self.command = [command] + arguments
    def processId(self): return 123456
    def terminate(self): pass
    def kill(self): pass
    def waitForFinished(self, _): return True


class AudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.players = []
        self.controls = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for control in self.controls:
            control.stop()
        for player in self.players:
            player.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def control(self, app):
        player = Player()
        self.players.append(player)
        control = audio.Controller(player, app, self.root)
        self.controls.append(control)
        return control

    def wait(self, predicate):
        for _ in range(80):
            QTest.qWait(10)
            if predicate():
                return
        self.fail('Local playback coordination did not settle')

    def test_defaults_are_off_and_stream_identity_is_distinct(self):
        for app in ('reader', 'radio', 'meetings'):
            self.assertEqual(audio.preferences(app, self.root), audio.DEFAULTS)
            env = audio.playback_environment(QProcessEnvironment(), app)
            self.assertEqual(env.value('PULSE_PROP_application.id'), 'org.lumen.' + app)
            self.assertTrue(env.value('SDL_AUDIO_DEVICE_APP_NAME').startswith('Lumen'))
            self.assertFalse(env.contains('PULSE_SINK'))
        prefs = audio.save_preferences('reader', dict(sink='test-headphones', pause_radio=True, pause_disconnect=True), self.root)
        self.assertEqual(audio.preferences('reader', self.root), prefs)
        env = audio.playback_environment(QProcessEnvironment(), 'reader', prefs)
        self.assertEqual(env.value('PULSE_SINK'), 'test-headphones')
        self.assertEqual(audio.preferences('radio', self.root), audio.DEFAULTS)

    def test_overlapping_foreground_playback_resumes_only_after_last_release(self):
        radio = self.control('radio')
        reader = self.control('reader')
        meetings = self.control('meetings')
        for app in ('reader', 'meetings'):
            audio.save_preferences(app, dict(pause_radio=True), self.root)
        started = []
        reader.start(lambda: started.append('reader'))
        self.wait(lambda: len(started) == 1)
        self.assertTrue(radio.player.paused)
        meetings.start(lambda: started.append('meetings'))
        self.wait(lambda: len(started) == 2)
        self.assertTrue(reader.player.paused)
        reader.stop()
        self.wait(lambda: len(radio.holds) == 1)
        self.assertTrue(radio.player.paused)
        meetings.stop()
        self.wait(lambda: not radio.holds)
        self.assertFalse(radio.player.paused)
        self.assertEqual(radio.player.changes, [True, False])

    def test_manual_pause_and_user_override_are_never_automatically_resumed(self):
        radio = self.control('radio')
        reader = self.control('reader')
        audio.save_preferences('reader', dict(pause_radio=True), self.root)
        radio.player.paused = True
        reader.start(lambda: None)
        self.wait(lambda: bool(radio.holds))
        reader.stop()
        self.wait(lambda: not radio.holds)
        self.assertTrue(radio.player.paused)
        radio.player.paused = False
        reader.start(lambda: None)
        self.wait(lambda: bool(radio.holds))
        radio.manual()
        reader.stop()
        self.wait(lambda: not radio.holds)
        self.assertTrue(radio.player.paused)

    def test_missing_radio_allows_playback_and_disconnect_requires_explicit_output(self):
        reader = self.control('reader')
        audio.save_preferences('reader', dict(pause_radio=True), self.root)
        started = []
        reader.start(lambda: started.append(True))
        self.wait(lambda: bool(started))
        with self.assertRaises(ValueError):
            audio.save_preferences('reader', dict(pause_disconnect=True), self.root)
        reader.prefs = dict(sink='headphones', pause_radio=False, pause_disconnect=True)
        reader.observe_outputs({'headphones', 'speakers'})
        self.assertFalse(reader.player.paused)
        reader.observe_outputs({'speakers'})
        self.assertTrue(reader.player.paused)
        reader.observe_outputs({'headphones', 'speakers'})
        self.assertTrue(reader.player.paused)

    def test_failed_or_cancelled_route_preflight_never_starts_or_leaves_running_job(self):
        import threading
        from tools_ui import Job
        reader = self.control('reader')
        audio.save_preferences('reader', dict(sink='missing', strict_routing=True), self.root)
        started = []
        with patch('interop_audio_route.snapshot', return_value=dict(sinks=[])):
            reader.start(lambda: started.append(True))
            self.wait(lambda: reader.preflight is None)
        self.assertFalse(started)
        self.assertIn('nicht verbunden', reader.player.time.text())
        with patch('interop_audio_route.snapshot', side_effect=ValueError('Synthetic server failure')):
            reader.start(lambda: started.append(True))
            self.wait(lambda: reader.preflight is None)
        self.assertFalse(started)
        entered = threading.Event()
        def slow(job):
            entered.set()
            job.cancelled.wait(1)
            job.check()
            return dict(sinks=[])
        with patch('interop_audio_route.snapshot', side_effect=slow):
            reader.start(lambda: started.append(True))
            self.wait(entered.is_set)
            reader.stop()
        self.app.processEvents()
        self.assertFalse(started)
        self.assertTrue(all(not job.isRunning() for job in reader.findChildren(Job)))
        self.assertFalse(reader.leases)

    def test_audio_player_uses_native_controls_and_process_environment(self):
        from tools_ui import AudioPlayer
        from tools_data import Library
        window = QWidget()
        window.name = 'reader'
        window.library = Library('reader', self.root)
        self.players.append(window)
        player = AudioPlayer(window)
        audio.save_preferences('reader', dict(sink='headphones'), self.root)
        with patch('tools_ui.worker_process', side_effect=Process), patch('tools_ui.os.kill') as signal, patch('interop_audio_route.snapshot', return_value=dict(sinks=[dict(name='headphones',description='Headphones')])):
            player.load(self.root/'synthetic.wav', 30000)
            player.play_at(12500)
            self.controls.append(player._lumen_audio)
            self.wait(lambda: player.proc is not None)
            self.assertEqual(player.proc.command, ['ffplay', '-v', 'error', '-nodisp', '-autoexit', '-ss', '12.5', str(self.root/'synthetic.wav')])
            self.assertEqual(player.proc.env.value('PULSE_SINK'), 'headphones')
            self.assertEqual(player.proc.env.value('SDL_AUDIO_DEVICE_NAME'), 'Headphones')
            self.assertEqual(player.proc.env.value('PULSE_PROP_application.id'), 'org.lumen.reader')
            player.toggle()
            self.assertTrue(player.paused)
            player.toggle()
            self.wait(lambda: not player.paused)
            self.assertFalse(player.paused)
            self.assertEqual(signal.call_count, 2)
            signal.side_effect = ProcessLookupError()
            player.set_paused(True)
            self.assertIsNone(player.proc)
            player.stop()

    def test_project_profile_is_explicit_and_updates_only_future_preferences(self):
        from tools_data import Library
        library = Library('workbench', self.root)
        key = library.create('Research', notes='unchanged')
        audio.save_preferences('reader', dict(sink='headphones'), self.root)
        saved = audio.save_project_profile(library, key, 'Research audio')
        audio.save_preferences('reader', dict(sink='speakers'), self.root)
        self.assertEqual(audio.preferences('reader', self.root)['sink'], 'speakers')
        self.assertEqual(library.get(key)['audio_profile'], saved)
        audio.apply_project_profile(library, key)
        self.assertEqual(audio.preferences('reader', self.root)['sink'], 'headphones')
        self.assertEqual(library.get(key)['notes'], 'unchanged')
        library.update(key, audio_profile=dict(title='bad', players={'reader': dict(sink='new'), 'evil': {}}))
        with self.assertRaises(ValueError): audio.apply_project_profile(library, key)
        self.assertEqual(audio.preferences('reader', self.root)['sink'], 'headphones')



if __name__ == '__main__':
    unittest.main()
