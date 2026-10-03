"""Local voice turns independent of QWidget or QML presentation."""
from lumen_i18n import worker_process, tr
from lumen_qt import QObject, QProcess, QTimer, pyqtSignal
from pathlib import Path
import math
import re
import sys
import tempfile
import time
import wave
from lumen_setup import executable, speech_root
from voice_capture import pcm_rms, normalized_level


class VoiceSession(QObject):
    started = pyqtSignal()
    changed = pyqtSignal()
    levelChanged = pyqtSignal(float)
    transcribedText = pyqtSignal(str)
    failed = pyqtSignal(str)
    setupRequested = pyqtSignal()

    def __init__(self, backend, settings, parent=None):
        super().__init__(parent)
        self.backend = backend; self.settings = settings
        self.active = False; self.process = None; self.temp = None
        self.state = ''; self.status = ''; self.interrupting = False
        self.level_buffer = ''; self.playback = None
        self.playback_timer = QTimer(self); self.playback_timer.setInterval(50)
        self.playback_timer.timeout.connect(self.playback_level)
        self.timer = QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.fail(tr('Sprachverarbeitung hat das Zeitlimit erreicht.')))
        backend.completed.connect(self.answered); backend.failed.connect(self.fail)

    def toggle(self):
        if self.active: self.stop(); return
        if self.backend.busy: return
        self.settings.sync(); model = self.settings.value('speechModel', '')
        if not executable('whisper-cli') or not Path(model).is_file() or not executable('piper-tts') or not (speech_root() / 'de_DE-thorsten-medium.onnx').is_file():
            self.setupRequested.emit(); return
        self.active = True; self.temp = tempfile.TemporaryDirectory(prefix='lumen-conversation-')
        self.started.emit(); self.listen()

    def say_status(self, state, text):
        self.clear_playback(); self.state = state; self.status = text
        self.levelChanged.emit(0.); self.changed.emit()

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
        self.run(sys.executable, [str(Path(__file__).with_name('voice_capture.py')), str(Path(self.temp.name) / 'speech.wav'), str(self.settings.value('voiceThreshold',450,type=int)), str(self.settings.value('voiceSilence',.9,type=float))], self.recorded, 190000, meter=True)

    def capture_level(self, proc):
        if self.process is not proc or self.state != 'listening': return
        self.level_buffer += bytes(proc.readAllStandardOutput()).decode(errors='replace')
        lines = self.level_buffer.split('\n'); self.level_buffer = lines.pop()[-100:]
        for line in lines:
            if line.startswith('LEVEL '):
                try:
                    value = float(line[6:])
                    if math.isfinite(value): self.levelChanged.emit(max(0., min(1., value)))
                except ValueError: pass

    def recorded(self, code, output):
        if code: self.fail(output or tr('Mikrofonaufnahme fehlgeschlagen.')); return
        self.say_status('transcribing', tr('Sprache wird lokal erkannt …'))
        from lumen_speech import transcription_arguments
        self.run(executable('whisper-cli'), transcription_arguments(self.settings, Path(self.temp.name) / 'speech.wav', Path(self.temp.name) / 'words'), self.transcribed)

    def transcribed(self, code, output):
        textfile = Path(self.temp.name) / 'words.txt'
        if code or not textfile.is_file(): self.fail(output[-500:] or tr('Spracherkennung fehlgeschlagen.')); return
        text = textfile.read_text().strip()
        if not text or re.fullmatch(r'[\[\(].*[\]\)]', text): self.listen(); return
        self.say_status('thinking', tr('Lumen antwortet … · Erkannt: ') + text[:140])
        self.transcribedText.emit(text)

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
            self.levelChanged.emit(normalized_level(pcm_rms(self.playback.readframes(rate//20))))
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
        if self.backend.busy:
            self.interrupting = True; self.backend.stop()
        else: self.listen()

    def fail(self, message):
        if self.active: self.stop(); self.failed.emit(message)

    def stop(self):
        self.active = False; self.interrupting = False; self.cancel_process()
        self.say_status('', tr('Sprachgespräch beendet · Mikrofon aus'))
        if self.temp: self.temp.cleanup(); self.temp = None
