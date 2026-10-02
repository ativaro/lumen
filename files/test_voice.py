import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch
from lumen_voice import Utterance


class VoiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_app
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_app()

    def test_silence_ends_only_a_real_utterance(self):
        detector = Utterance(450, .7)
        quiet = b'\0' * 640
        voice = struct.pack('<320h', *(int(3000 * math.sin(i/6)) for i in range(320)))
        self.assertFalse(any(detector.feed(quiet) for _ in range(100)))
        self.assertFalse(any(detector.feed(voice) for _ in range(30)))
        self.assertTrue(any(detector.feed(quiet) for _ in range(40)))
        self.assertGreater(len(detector.frames), 30)

    def test_capture_worker_reports_levels_without_changing_recorded_audio(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'pw-cat'
            fake.write_text('#!/usr/bin/python3\nimport math,struct,sys,time\n'
                            'voice=struct.pack("<320h",*(int(3000*math.sin(i/6)) for i in range(320)))\n'
                            'for frame in [voice]*20+[b"\\0"*640]*50:\n'
                            ' sys.stdout.buffer.write(frame);sys.stdout.buffer.flush();time.sleep(.02)\n')
            fake.chmod(0o700); target = Path(tmp) / 'speech.wav'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('lumen_voice.py')), str(target), '450', '.3'],
                                    env=os.environ | {'PATH':tmp+os.pathsep+os.environ['PATH']}, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            levels = [float(line.removeprefix('LEVEL ')) for line in result.stdout.splitlines()]
            self.assertGreater(max(levels), .4); self.assertEqual(min(levels), 0.)
            with wave.open(str(target), 'rb') as audio:
                self.assertEqual(audio.getframerate(), 16000); self.assertGreater(audio.getnframes(), 10000)

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
                self.assertEqual(voice.state, 'preparing'); self.assertIn('Bilder', run.call_args.kwargs['data'])
                with patch.object(voice, 'listen') as listen:
                    voice.synthesized(0, ''); run.call_args.args[2](0, '')
                    listen.assert_called_once(); voice.interrupt(); self.assertEqual(listen.call_count, 2)
            voice.stop(); self.assertFalse(voice.active); self.assertIsNone(voice.temp)
            panel.context_tools.close(); panel.backend.shutdown(); panel.close(); app.processEvents()

    def test_live_levels_playback_and_visibility_follow_real_audio(self):
        import sys
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QApplication
        from assistant import ChatPanel
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'LUMEN_DATA': tmp + '/state'}):
            panel = ChatPanel(tmp); panel.resize(350, 640); panel.show()
            voice = panel.context_tools.conversation; indicator = voice.indicator
            try:
                voice.active = True; voice.say_status('listening', 'Listening')
                self.assertTrue(indicator.isVisible()); self.assertTrue(indicator.animation.isActive())
                completed = []
                # Real QProcess, fragmented stdout; meter data stays out of errors/transcripts.
                script = "import sys,time; print('LEVEL 0.',end='',flush=True); time.sleep(.05); print('75',flush=True); print('LEVEL nan',flush=True); time.sleep(.15); print('capture error',file=sys.stderr)"
                voice.run(sys.executable, ['-c', script], lambda code, text: completed.append((code,text)), meter=True)
                QTest.qWait(150); self.assertEqual(indicator.target, .75)
                QTest.qWait(200); self.assertEqual(completed, [(0,'capture error\n')])
                indicator.updated -= 1; indicator.tick(); self.assertEqual(indicator.target, 0.)
                path = Path(tmp) / 'reply.wav'
                with wave.open(str(path), 'wb') as out:
                    out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
                    out.writeframes(b'\0'*3200 + struct.pack('<h', 4000)*6400)
                voice.start_playback(str(path)); self.assertEqual(indicator.target, 0.)
                with patch('lumen_voice.time.monotonic', return_value=voice.playback_started + .2): voice.playback_level()
                self.assertGreater(indicator.target, .5); self.assertEqual(indicator.state, 'speaking')
                voice.say_status('thinking', 'Thinking'); self.assertIsNone(voice.playback)
                self.assertFalse(voice.playback_timer.isActive()); self.assertEqual(indicator.target, 0.)
                panel.hide(); self.assertFalse(voice.active); self.assertFalse(indicator.animation.isActive())
                self.assertFalse(indicator.isVisible()); self.assertEqual(indicator.state, '')
            finally: voice.stop(); panel.context_tools.close(); panel.backend.shutdown(); panel.close(); app.processEvents()
