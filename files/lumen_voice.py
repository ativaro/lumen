"""Local continuous voice turns for the shared native chat."""
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


class Utterance:
    """PCM16 frame detector, with configurable threshold/pause for real microphones."""
    def __init__(self, threshold=450, silence=.9):
        self.threshold = threshold; self.silence = silence; self.frames = []; self.pre = deque(maxlen=10)
        self.voiced = 0; self.quiet = 0; self.started = False

    def feed(self, frame):
        samples = array('h', frame)
        if sys.byteorder != 'little': samples.byteswap()
        rms = math.sqrt(sum(v * v for v in samples) / max(1, len(samples)))
        duration = len(samples) / 16000
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
        started = time.monotonic()
        while time.monotonic() - started < 180:
            frame = child.stdout.read(640)
            if not frame: raise ValueError('Mikrofon liefert keine Audiodaten.')
            if detector.feed(frame):
                with wave.open(path, 'wb') as out:
                    out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b''.join(detector.frames))
                return
        raise ValueError('Drei Minuten keine Sprache erkannt. Mikrofon wurde ausgeschaltet.')
    finally:
        child.terminate()
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired: child.kill(); child.wait()


# Qt stays out of the capture worker.
if __name__ == '__main__':
    try: record(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
    except Exception as error: print(str(error)); sys.exit(1)
else:
    from PyQt5.QtCore import QObject, QProcess, QTimer, QEvent, pyqtSignal
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QPushButton, QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QVBoxLayout
    from lumen_setup import executable, speech_root

    class VoiceConversation(QObject):
        started = pyqtSignal()

        def __init__(self, panel, row):
            super().__init__(panel); self.panel = panel; self.active = False; self.process = None; self.temp = None; self.state = ''; self.interrupting = False
            self.button = QPushButton('Sprechen'); self.button.setIcon(QIcon.fromTheme('audio-input-microphone')); self.button.setAccessibleName('Sprachgespräch starten oder beenden'); row.addWidget(self.button)
            self.button.setToolTip('Sprachgespräch: Sprechpausen senden automatisch. Audio bleibt lokal; Text geht an deinen Lumen-Anbieter.'); self.button.clicked.connect(self.toggle)
            self.interrupt_button = QPushButton('Unterbrechen'); self.interrupt_button.setToolTip('Antwort unterbrechen und weiterreden'); self.interrupt_button.hide(); row.addWidget(self.interrupt_button); self.interrupt_button.clicked.connect(self.interrupt)
            self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(lambda: self.fail('Sprachverarbeitung hat das Zeitlimit erreicht.'))
            panel.backend.completed.connect(self.answered); panel.backend.failed.connect(self.fail)
            panel.installEventFilter(self)

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Hide and self.active: self.stop()
            return False

        def controls(self):
            dialog = QDialog(self.panel); dialog.setWindowTitle('Sprachgespräch'); layout = QVBoxLayout(dialog); form = QFormLayout(); layout.addLayout(form)
            threshold = QSpinBox(); threshold.setRange(50,15000); threshold.setValue(self.panel.settings.value('voiceThreshold',450,type=int)); form.addRow('Mikrofonschwelle (kleiner = empfindlicher)', threshold)
            silence = QDoubleSpinBox(); silence.setRange(.3,4); silence.setSingleStep(.1); silence.setValue(self.panel.settings.value('voiceSilence',.9,type=float)); form.addRow('Sprechpause vor dem Senden (Sekunden)',silence)
            save = QPushButton('Speichern'); layout.addWidget(save)
            def apply():
                self.panel.settings.setValue('voiceThreshold',threshold.value()); self.panel.settings.setValue('voiceSilence',silence.value()); dialog.accept()
            save.clicked.connect(apply); dialog.exec_()

        def toggle(self):
            if self.active: self.stop(); return
            if self.panel.backend.busy or self.panel.context_tools.process: return
            self.panel.settings.sync(); model = self.panel.settings.value('speechModel','')
            if not executable('whisper-cli') or not Path(model).is_file() or not executable('piper-tts') or not (speech_root() / 'de_DE-thorsten-medium.onnx').is_file():
                from setup_dialog import open_setup
                open_setup(self.panel, self.panel.settings, page=2); return
            self.active = True; self.temp = tempfile.TemporaryDirectory(prefix='lumen-conversation-'); self.button.setText('Beenden')
            self.started.emit(); self.listen()

        def say_status(self, state, text):
            self.state = state; self.panel.status.setText(text)
            self.button.setToolTip(text); self.interrupt_button.setVisible(self.active and state in ('thinking','speaking'))

        def run(self, program, arguments, callback, timeout=120000, data=None):
            proc = QProcess(self); self.process = proc; proc.setProcessChannelMode(QProcess.MergedChannels)
            def done(code):
                if self.process is not proc: return
                self.process = None; self.timer.stop(); output = bytes(proc.readAllStandardOutput()).decode(errors='replace'); proc.deleteLater()
                if self.active: callback(code, output)
            proc.finished.connect(done); proc.errorOccurred.connect(lambda e: done(1) if e == QProcess.FailedToStart else None)
            proc.start(program, arguments)
            if data is not None: proc.write(data.encode()); proc.closeWriteChannel()
            self.timer.start(timeout)

        def listen(self):
            if not self.active: return
            self.say_status('listening', 'Mikrofon aktiv · sprich mit Lumen · Sprechpause sendet automatisch')
            self.run(sys.executable, [str(Path(__file__)), str(Path(self.temp.name) / 'speech.wav'), str(self.panel.settings.value('voiceThreshold',450,type=int)), str(self.panel.settings.value('voiceSilence',.9,type=float))], self.recorded, 190000)

        def recorded(self, code, output):
            if code: self.fail(output or 'Mikrofonaufnahme fehlgeschlagen.'); return
            self.say_status('transcribing', 'Sprache wird lokal erkannt …')
            self.run(executable('whisper-cli'), ['-m', self.panel.settings.value('speechModel',''), '-f', str(Path(self.temp.name) / 'speech.wav'), '-l', 'auto', '-nt', '-otxt', '-of', str(Path(self.temp.name) / 'words')], self.transcribed)

        def transcribed(self, code, output):
            textfile = Path(self.temp.name) / 'words.txt'
            if code or not textfile.is_file(): self.fail(output[-500:] or 'Spracherkennung fehlgeschlagen.'); return
            text = textfile.read_text().strip()
            if not text or re.fullmatch(r'[\[\(].*[\]\)]', text): self.listen(); return
            self.panel.composer.setPlainText(text)
            self.say_status('thinking', 'Lumen antwortet … · Erkannt: ' + text[:140])
            self.panel.submit(text)

        def answered(self, success, answer):
            if not self.active: return
            if self.interrupting:
                self.interrupting = False; self.listen(); return
            if self.state != 'thinking': return
            if not success: self.fail(answer); return
            spoken = re.sub(r'```.*?```', 'Code steht in der Antwort.', answer, flags=re.S)
            spoken = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', spoken); spoken = re.sub(r'[*#_`]', '', spoken).strip()
            if not spoken: self.listen(); return
            self.say_status('speaking', 'Lumen spricht · zum Weiterreden „Unterbrechen“ wählen')
            self.run(executable('piper-tts'), ['-m', str(speech_root() / 'de_DE-thorsten-medium.onnx'), '-f', str(Path(self.temp.name) / 'reply.wav')], self.synthesized, data=spoken + '\n')

        def synthesized(self, code, output):
            if code: self.fail('Sprachausgabe fehlgeschlagen: ' + output[-500:]); return
            self.run('pw-play', [str(Path(self.temp.name) / 'reply.wav')], lambda code, text: self.fail(text) if code else self.listen(), 600000)

        def cancel_process(self):
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
            self.button.setText('Sprechen'); self.interrupt_button.hide(); self.panel.status.setText('Sprachgespräch beendet · Mikrofon aus')
            if self.temp: self.temp.cleanup(); self.temp = None
