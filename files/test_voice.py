import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from lumen_voice import Utterance


class VoiceTest(unittest.TestCase):
    def test_silence_ends_only_a_real_utterance(self):
        detector = Utterance(450, .7)
        quiet = b'\0' * 640
        voice = struct.pack('<320h', *(int(3000 * math.sin(i/6)) for i in range(320)))
        self.assertFalse(any(detector.feed(quiet) for _ in range(100)))
        self.assertFalse(any(detector.feed(voice) for _ in range(30)))
        self.assertTrue(any(detector.feed(quiet) for _ in range(40)))
        self.assertGreater(len(detector.frames), 30)

    def test_native_turns_share_chat_and_interrupt_without_sending_audio(self):
        from PyQt5.QtCore import QSettings
        from PyQt5.QtWidgets import QApplication
        from assistant import ChatPanel
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            settings = QSettings(tmp + '/settings.ini', QSettings.IniFormat)
            model = Path(tmp) / 'model'; model.touch(); settings.setValue('speechModel', str(model))
            panel = ChatPanel(tmp, settings=settings); voice = panel.context_tools.conversation
            voice.active = True; voice.temp = tempfile.TemporaryDirectory()
            (Path(voice.temp.name) / 'words.txt').write_text('Zeige mir die Bilder.')
            calls = []
            with patch.object(panel, 'submit', side_effect=calls.append), patch.object(voice, 'run') as run:
                voice.transcribed(0, '')
                self.assertEqual(calls, ['Zeige mir die Bilder.']); self.assertEqual(voice.state, 'thinking')
                voice.answered(True, 'Hier sind deine **Bilder**.')
                self.assertEqual(voice.state, 'speaking'); self.assertIn('Bilder', run.call_args.kwargs['data'])
                with patch.object(voice, 'listen') as listen:
                    voice.synthesized(0, ''); run.call_args.args[2](0, '')
                    listen.assert_called_once(); voice.interrupt(); self.assertEqual(listen.call_count, 2)
            voice.stop(); self.assertFalse(voice.active); self.assertIsNone(voice.temp)
            panel.context_tools.close(); panel.backend.shutdown(); panel.close(); app.processEvents()
