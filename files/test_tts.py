import tempfile
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from lumen_tts import command, engine, prepare_text
from speech_worker import chunks


class SpeechOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = QSettings(str(self.root/'settings.ini'), QSettings.IniFormat)

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from app import create_app
        cls.app = QApplication.instance() or create_app()

    def test_controls_only_change_preferences_on_save(self):
        from PySide6.QtWidgets import QWidget, QFormLayout, QComboBox
        from lumen_tts import add_voice_fields
        widget = QWidget(); form = QFormLayout(widget)
        save = add_voice_fields(form, self.settings)
        voices, speaker = widget.findChildren(QComboBox)
        self.assertFalse(self.settings.contains('speechEngine'))
        voices.setCurrentIndex(voices.findData('qwen')); speaker.setCurrentText('Aiden')
        self.assertEqual(engine(self.settings), 'piper'); save()
        self.assertEqual(engine(self.settings), 'qwen')
        self.assertEqual(self.settings.value('speechSpeaker'), 'Aiden')

    def test_warm_worker_reuses_process_and_cancellation_is_quiet(self):
        from voice_output import VoiceOutput
        root = self.root/'qwen-env/bin'; root.mkdir(parents=True)
        fake = root/'python'
        fake.write_text('#!'+sys.executable+'\n' +
            "import sys,json,time\n" +
            "for line in sys.stdin:\n" +
            " request=json.loads(line)\n" +
            " if request['text']=='wait': time.sleep(30)\n" +
            " print(json.dumps({'ok':True}),flush=True)\n")
        fake.chmod(0o700)
        output = VoiceOutput(); results = []; output.completed.connect(lambda *args: results.append(args))
        def dispose():
            from PySide6.QtCore import QCoreApplication, QEvent
            output.cancel(); output.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.addCleanup(dispose)
        def wait_for(count):
            until = time.monotonic()+5
            while len(results)<count and time.monotonic()<until:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(len(results), count)
        with patch('voice_output.speech_root', return_value=self.root):
            output.synthesize('Files', self.root/'audio.wav', self.settings); wait_for(1)
            pid = output.process.processId()
            output.synthesize('Kubernetes', self.root/'audio.wav', self.settings); wait_for(2)
            self.assertEqual(output.process.processId(), pid)
            output.synthesize('wait', self.root/'audio.wav', self.settings)
            output.cancel(); self.app.processEvents()
            self.assertIsNone(output.process); self.assertEqual(len(results),2)
            self.assertTrue(all(code==0 for code, error in results))

    def test_conversation_routes_plain_mixed_text_to_selected_voice(self):
        from assistant import ChatPanel
        panel = ChatPanel(self.tmp.name, settings=self.settings)
        voice = panel.context_tools.conversation
        self.settings.setValue('speechEngine', 'qwen')
        voice.active = True; voice.state = 'thinking'
        voice.temp = tempfile.TemporaryDirectory()
        try:
            with patch.object(voice.speech_output, 'synthesize') as render, patch.object(voice, 'run') as run:
                voice.answered(True, 'Öffne **Files** und Vault. Der Kubernetes-Cluster läuft.')
                self.assertEqual(render.call_args.args[0], 'Öffne Files und Vault. Der Kubernetes-Cluster läuft.')
                run.assert_not_called(); self.assertEqual(voice.state, 'preparing')
                self.assertTrue(voice.timer.isActive())
        finally:
            voice.stop(); panel.context_tools.close(); panel.backend.shutdown(); panel.close()
            self.app.processEvents()

    def test_existing_installation_keeps_lightweight_voice(self):
        self.assertEqual(engine(self.settings), 'piper')
        with patch('lumen_setup.executable', return_value='/piper'), patch('lumen_setup.speech_root', return_value=self.root):
            args = command(self.root/'result.wav', settings=self.settings)
        self.assertEqual(args[0], '/piper'); self.assertIn('-f', args)

    def test_multilingual_voice_receives_arbitrary_words_without_dictionary(self):
        self.settings.setValue('speechEngine', 'qwen')
        self.settings.setValue('speechSpeaker', 'not-a-voice')
        with patch('lumen_setup.speech_root', return_value=self.root):
            args = command(self.root/'sections', directory=True, settings=self.settings)
        self.assertIn('--output-dir', args); self.assertIn('Ryan', args)
        text = 'Öffne Files, Vault und das Dashboard.\nDer Kubernetes-Cluster braucht ein Deployment.'
        self.assertEqual(prepare_text(text), text)
        self.assertNotIn('piper', str(args))

    def test_symbols_are_spoken_without_rewriting_regular_paths_or_newlines(self):
        text = '~/Dokumente\nDas Zeichen ~ heißt Tilde; Datei.txt~ und ~~Text~~ bleiben.'
        self.assertEqual(prepare_text(text), 'Benutzerordner/Dokumente\nDas Zeichen Tilde heißt Tilde; Datei.txt~ und ~~Text~~ bleiben.')

    def test_long_script_is_bounded_without_dropping_words(self):
        for text in ['Ein kurzer Satz.', 'Ein Satz. Noch ein Satz! ' * 90, 'x'*900]:
            parts = list(chunks(text))
            self.assertTrue(all(0 < len(part) <= 300 for part in parts))
            self.assertEqual(''.join(''.join(parts).split()), ''.join(text.split()))


if __name__ == '__main__': unittest.main()
