"""Local continuous voice turns for the shared native chat."""
from lumen_i18n import worker_process, tr
from array import array
from collections import deque
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import wave


def pcm_rms(frame):
    samples = array('h', frame)
    if sys.byteorder != 'little': samples.byteswap()
    return math.sqrt(sum(v * v for v in samples) / max(1, len(samples)))


def normalized_level(rms):
    return min(1., math.sqrt(rms / 10000))


class Utterance:
    """PCM16 frame detector, with configurable threshold/pause for real microphones."""
    def __init__(self, threshold=450, silence=.9):
        self.threshold = threshold; self.silence = silence; self.frames = []; self.pre = deque(maxlen=10)
        self.voiced = 0; self.quiet = 0; self.started = False

    def feed(self, frame):
        rms = pcm_rms(frame); self.level = normalized_level(rms)
        duration = len(frame) / 32000
        if rms >= self.threshold:
            if not self.started: self.frames.extend(self.pre); self.started = True
            self.voiced += duration; self.quiet = 0
        else: self.quiet += duration
        if self.started: self.frames.append(frame)
        else: self.pre.append(frame)
        if self.started and self.quiet >= self.silence:
            if self.voiced >= .25: return True
            self.frames.clear(); self.started = False; self.voiced = 0
        return sum(map(len, self.frames)) >= 16000 * 2 * 45


def record(path, threshold, silence):
    detector = Utterance(threshold, silence)
    child = subprocess.Popen(['pw-cat', '--record', '--raw', '--rate', '16000', '--channels', '1', '--format', 's16',
                              '--properties', '{ media.role = Communication node.name = lumen-voice }', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def stop(*_): raise InterruptedError()
    signal.signal(signal.SIGTERM, stop)
    try:
        started = time.monotonic(); last_level = 0.
        while time.monotonic() - started < 180:
            frame = child.stdout.read(640)
            if not frame: raise ValueError(tr('Mikrofon liefert keine Audiodaten.'))
            finished = detector.feed(frame)
            if time.monotonic() - last_level >= .05:
                print(f'LEVEL {detector.level:.4f}', flush=True); last_level = time.monotonic()
            if finished:
                with wave.open(path, 'wb') as out:
                    out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b''.join(detector.frames))
                return
        raise ValueError(tr('Drei Minuten keine Sprache erkannt. Mikrofon wurde ausgeschaltet.'))
    finally:
        child.terminate()
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired: child.kill(); child.wait()


# Qt stays out of the capture worker.
if __name__ == '__main__':
    try: record(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
    except Exception as error: print(str(error), file=sys.stderr); sys.exit(1)
else:
    from PyQt5.QtCore import QObject, QProcess, QTimer, QEvent, pyqtSignal
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QPushButton, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QVBoxLayout
    from lumen_setup import executable, speech_root
    from lumen_voice_ui import VoiceActivity

    class VoiceConversation(QObject):
        started = pyqtSignal()

        def __init__(self, panel, row):
            super().__init__(panel); self.panel = panel; self.active = False; self.process = None; self.temp = None; self.state = ''; self.interrupting = False
            self.indicator = VoiceActivity(panel); self.level_buffer = ''; self.playback = None
            self.playback_timer = QTimer(self); self.playback_timer.setInterval(50); self.playback_timer.timeout.connect(self.playback_level)
            self.button = QPushButton(tr('Sprechen')); self.button.setIcon(QIcon.fromTheme('audio-input-microphone')); self.button.setAccessibleName(tr('Sprachgespräch starten oder beenden')); row.addWidget(self.button)
            self.button.setToolTip(tr('Sprachgespräch: Sprechpausen senden automatisch. Audio bleibt lokal; Text geht an deinen Lumen-Anbieter.')); self.button.clicked.connect(self.toggle)
            self.interrupt_button = QPushButton(tr('Unterbrechen')); self.interrupt_button.setToolTip(tr('Antwort unterbrechen und weiterreden')); self.interrupt_button.hide(); row.addWidget(self.interrupt_button); self.interrupt_button.clicked.connect(self.interrupt)
            self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(lambda: self.fail(tr('Sprachverarbeitung hat das Zeitlimit erreicht.')))
            panel.backend.completed.connect(self.answered); panel.backend.failed.connect(self.fail)
            panel.installEventFilter(self)

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Hide and self.active: self.stop()
            return False

        def controls(self):
            dialog = QDialog(self.panel); dialog.setWindowTitle(tr('Sprachgespräch')); layout = QVBoxLayout(dialog); form = QFormLayout(); layout.addLayout(form)
            from lumen_speech import add_recognition_fields
            self.panel.settings.sync(); save_recognition = add_recognition_fields(form, self.panel.settings)
            threshold = QSpinBox(); threshold.setRange(50,15000); threshold.setValue(self.panel.settings.value('voiceThreshold',450,type=int)); form.addRow(tr('Mikrofonschwelle (kleiner = empfindlicher)'), threshold)
            silence = QDoubleSpinBox(); silence.setRange(.3,4); silence.setSingleStep(.1); silence.setValue(self.panel.settings.value('voiceSilence',.9,type=float)); form.addRow(tr('Sprechpause vor dem Senden (Sekunden)'),silence)
            save = QPushButton(tr('Speichern')); layout.addWidget(save)
            def apply():
                self.panel.settings.setValue('voiceThreshold',threshold.value()); self.panel.settings.setValue('voiceSilence',silence.value()); save_recognition(); dialog.accept()
            save.clicked.connect(apply); dialog.exec_()

        def toggle(self):
            if self.active: self.stop(); return
            if self.panel.backend.busy or self.panel.context_tools.process: return
            self.panel.settings.sync(); model = self.panel.settings.value('speechModel','')
            if not executable('whisper-cli') or not Path(model).is_file() or not executable('piper-tts') or not (speech_root() / 'de_DE-thorsten-medium.onnx').is_file():
                from setup_dialog import open_setup
                open_setup(self.panel, self.panel.settings, page=2); return
            self.active = True; self.temp = tempfile.TemporaryDirectory(prefix='lumen-conversation-'); self.button.setText(tr('Beenden'))
            self.started.emit(); self.listen()

        def say_status(self, state, text):
            self.clear_playback(); self.indicator.set_state(state)
            self.state = state; self.panel.status.setText(text)
            self.button.setToolTip(text); self.interrupt_button.setVisible(self.active and state in ('thinking','preparing','speaking'))

        def run(self, program, arguments, callback, timeout=120000, data=None, meter=False, started=None):
            proc = worker_process(self); self.process = proc
            proc.setProcessChannelMode(QProcess.SeparateChannels if meter else QProcess.MergedChannels)
            if meter: proc.readyReadStandardOutput.connect(lambda: self.capture_level(proc))
            if started: proc.started.connect(started)
            def done(code):
                if self.process is not proc: return
                self.process = None; self.timer.stop(); output = bytes(proc.readAllStandardError() if meter else proc.readAllStandardOutput()).decode(errors='replace'); proc.deleteLater()
                if self.active: callback(code, output)
            proc.finished.connect(done); proc.errorOccurred.connect(lambda e: done(1) if e == QProcess.FailedToStart else None)
            proc.start(program, arguments)
            if data is not None: proc.write(data.encode()); proc.closeWriteChannel()
            self.timer.start(timeout)

        def listen(self):
            if not self.active: return
            self.level_buffer = ''
            self.say_status('listening', tr('Mikrofon aktiv · sprich mit Lumen · Sprechpause sendet automatisch'))
            self.run(sys.executable, [str(Path(__file__)), str(Path(self.temp.name) / 'speech.wav'), str(self.panel.settings.value('voiceThreshold',450,type=int)), str(self.panel.settings.value('voiceSilence',.9,type=float))], self.recorded, 190000, meter=True)

        def capture_level(self, proc):
            if self.process is not proc or self.state != 'listening': return
            self.level_buffer += bytes(proc.readAllStandardOutput()).decode(errors='replace')
            lines = self.level_buffer.split('\n'); self.level_buffer = lines.pop()[-100:]
            for line in lines:
                if line.startswith('LEVEL '):
                    try: self.indicator.set_level(float(line[6:]))
                    except ValueError: pass

        def recorded(self, code, output):
            if code: self.fail(output or tr('Mikrofonaufnahme fehlgeschlagen.')); return
            self.say_status('transcribing', tr('Sprache wird lokal erkannt …'))
            from lumen_speech import transcription_arguments
            self.run(executable('whisper-cli'), transcription_arguments(self.panel.settings, Path(self.temp.name) / 'speech.wav', Path(self.temp.name) / 'words'), self.transcribed)

        def transcribed(self, code, output):
            textfile = Path(self.temp.name) / 'words.txt'
            if code or not textfile.is_file(): self.fail(output[-500:] or tr('Spracherkennung fehlgeschlagen.')); return
            text = textfile.read_text().strip()
            if not text or re.fullmatch(r'[\[\(].*[\]\)]', text): self.listen(); return
            self.panel.composer.setPlainText(text)
            self.say_status('thinking', tr('Lumen antwortet … · Erkannt: ') + text[:140])
            self.panel.submit(text)

        def answered(self, success, answer):
            if not self.active: return
            if self.interrupting:
                self.interrupting = False; self.listen(); return
            if self.state != 'thinking': return
            if not success: self.fail(answer); return
            spoken = re.sub(r'```.*?```', tr('Code steht in der Antwort.'), answer, flags=re.S)
            spoken = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', spoken); spoken = re.sub(r'[*#_`]', '', spoken).strip()
            if not spoken: self.listen(); return
            self.say_status('preparing', tr('Lumen bereitet die Stimme lokal vor …'))
            self.run(executable('piper-tts'), ['-m', str(speech_root() / 'de_DE-thorsten-medium.onnx'), '-f', str(Path(self.temp.name) / 'reply.wav')], self.synthesized, data=spoken + '\n')

        def synthesized(self, code, output):
            if code: self.fail(tr('Sprachausgabe fehlgeschlagen: ') + output[-500:]); return
            path = str(Path(self.temp.name) / 'reply.wav')
            self.run('pw-play', [path], lambda code, text: self.fail(text) if code else self.listen(), 600000, started=lambda: self.start_playback(path))

        def start_playback(self, path):
            self.say_status('speaking', tr('Lumen spricht · zum Weiterreden „Unterbrechen“ wählen'))
            try:
                self.playback = wave.open(path, 'rb')
                if self.playback.getsampwidth() != 2: self.clear_playback(); return
                self.playback_started = time.monotonic(); self.playback_timer.start(); self.playback_level()
            except (OSError, EOFError, wave.Error): self.clear_playback()

        def playback_level(self):
            if not self.playback: return
            try:
                rate = self.playback.getframerate()
                self.playback.setpos(min(self.playback.getnframes(), int((time.monotonic()-self.playback_started)*rate)))
                self.indicator.set_level(normalized_level(pcm_rms(self.playback.readframes(rate//20))))
            except (OSError, EOFError, wave.Error): self.clear_playback()

        def clear_playback(self):
            self.playback_timer.stop()
            if self.playback: self.playback.close(); self.playback = None

        def cancel_process(self):
            self.clear_playback()
            self.timer.stop()
            if self.process:
                proc, self.process = self.process, None; proc.terminate()
                if not proc.waitForFinished(4000): proc.kill(); proc.waitForFinished(1000)
                proc.deleteLater()

        def interrupt(self):
            if not self.active: return
            self.cancel_process()
            if self.panel.backend.busy:
                self.interrupting = True; self.panel.backend.stop()
            else: self.listen()

        def fail(self, message):
            if self.active: self.stop(); self.panel.show_error(message)

        def stop(self):
            self.active = False; self.interrupting = False; self.cancel_process()
            self.state = ''; self.indicator.set_state('')
            self.button.setText(tr('Sprechen')); self.interrupt_button.hide(); self.panel.status.setText(tr('Sprachgespräch beendet · Mikrofon aus'))
            if self.temp: self.temp.cleanup(); self.temp = None
