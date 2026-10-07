"""One warm local speech process per active conversation, cancelled with its owner."""
import json
from pathlib import Path

from lumen_i18n import worker_process, tr
from lumen_qt import QObject, QProcess, Signal
from lumen_setup import speech_root
from lumen_tts import speaker


class VoiceOutput(QObject):
    completed = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None; self.pending = False; self.buffer = b''; self.error = b''
        self.voice = ''

    def synthesize(self, text, output, settings):
        selected = speaker(settings)
        if self.pending or (self.process and self.voice != selected): self.cancel()
        self.pending = True
        data = (json.dumps(dict(text=text, output=str(output)))+'\n').encode()
        if self.process:
            self.process.write(data); return
        proc = worker_process(self); self.process = proc; self.voice = selected
        self.buffer = b''; self.error = b''
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(lambda: self.read(proc))
        proc.readyReadStandardError.connect(lambda: self.read_error(proc))
        proc.finished.connect(lambda code: self.finished(proc, code))
        proc.errorOccurred.connect(lambda error: self.finished(proc, 1) if error == QProcess.FailedToStart else None)
        proc.started.connect(lambda: proc.write(data))
        proc.start(str(speech_root()/'qwen-env/bin/python'),
            [str(Path(__file__).with_name('speech_worker.py')), '--interactive', '--speaker', selected])

    def read_error(self, proc):
        if proc is self.process:
            self.error = (self.error + bytes(proc.readAllStandardError()))[-4000:]

    def read(self, proc):
        if proc is not self.process: return
        self.buffer += bytes(proc.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: result = json.loads(line)
            except ValueError: continue
            if self.pending and isinstance(result, dict) and type(result.get('ok')) is bool:
                self.pending = False
                self.completed.emit(0 if result.get('ok') else 1, result.get('error', ''))

    def finished(self, proc, code):
        if proc is not self.process: return
        self.read_error(proc); self.process = None; proc.deleteLater()
        if self.pending:
            self.pending = False
            self.completed.emit(code or 1, self.error.decode(errors='replace')[-500:] or tr('Die lokale Stimme wurde beendet.'))

    def cancel(self):
        self.pending = False
        proc, self.process = self.process, None
        if proc:
            proc.terminate()
            if not proc.waitForFinished(500): proc.kill(); proc.waitForFinished(500)
            proc.deleteLater()
