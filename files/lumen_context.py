"""Explicit context capture and optional offline dictation for the shared chat."""
from pathlib import Path
import shutil
import tempfile
from PyQt5.QtCore import QObject, QProcess, QTimer
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QPushButton, QCheckBox, QMenu
from lumen_setup import executable


class ContextTools(QObject):
    def __init__(self, panel, layout):
        super().__init__(panel); self.panel = panel; self.process = None; self.temp = None; self.recording = False
        row = QHBoxLayout(); layout.addLayout(row)
        for title, callback in [('Dateien', self.files), ('Bildschirm', self.screenshot)]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button)
        more = QPushButton('···'); more.setAccessibleName('Weitere Kontextaktionen'); more.setToolTip('Mehr: Zwischenablage, Diktieren und Kontext entfernen')
        menu = QMenu(more)
        menu.addAction('Zwischenablage einfügen', self.clipboard)
        self.voice = menu.addAction('Diktieren', self.dictate)
        menu.addSeparator()
        menu.addAction('Kontext entfernen', self.clear)
        self.conversation = None
        if hasattr(panel, 'submit'):
            from lumen_voice import VoiceConversation
            voice_row = QHBoxLayout(); layout.addLayout(voice_row)
            self.conversation = VoiceConversation(panel, voice_row)
            layout.addWidget(self.conversation.indicator)
            menu.addAction('Sprachgespräch einstellen …', self.conversation.controls)
        more.setMenu(menu); row.addWidget(more)
        self.learn = QCheckBox('Schritte erklären'); layout.addWidget(self.learn)
        self.limit = QTimer(self); self.limit.setSingleShot(True); self.limit.timeout.connect(self.finish_recording)

    def files(self):
        if self.panel.backend.busy: return
        paths, _ = QFileDialog.getOpenFileNames(self.panel, 'Kontext auswählen', self.panel.backend.directory)
        if paths: self.panel.paths = list(dict.fromkeys(self.panel.paths + paths)); self.panel.update_context()

    def screenshot(self):
        if self.process is not None or self.panel.backend.busy: return
        if not shutil.which('spectacle'):
            self.panel.show_error('Für die Bereichsauswahl wird Spectacle benötigt.'); return
        path, _ = QFileDialog.getSaveFileName(self.panel, 'Bildschirmkontext speichern', self.panel.backend.directory + '/lumen-kontext.png', 'PNG (*.png)')
        if not path: return
        def captured(code, output):
            if code == 0 and Path(path).is_file():
                self.panel.paths = list(dict.fromkeys(self.panel.paths + [path])); self.panel.update_context()
            elif code: self.panel.show_error('Bildschirmaufnahme abgebrochen oder fehlgeschlagen.')
        self.start('spectacle', ['-b', '-r', '-n', '-o', path], captured)

    def clear(self):
        if not self.panel.backend.busy: self.panel.paths = []; self.panel.update_context()

    def clipboard(self):
        if not self.panel.backend.busy: self.panel.composer.insertPlainText(QApplication.clipboard().text())

    def dictate(self):
        if self.conversation and self.conversation.active: self.conversation.stop()
        if self.recording: self.finish_recording(); return
        if self.process is not None or self.panel.backend.busy: return
        binary = executable('whisper-cli')
        self.panel.settings.sync()
        model = self.panel.settings.value('speechModel', '')
        if not binary or not shutil.which('pw-record') or not Path(model).is_file():
            from setup_dialog import open_setup
            open_setup(self.panel, self.panel.settings, page=2)
            self.panel.status.setText('Einrichtung geschlossen · zum Aufnehmen erneut „Diktieren“ wählen.')
            return
        self.temp = tempfile.TemporaryDirectory(prefix='lumen-voice-'); self.binary = binary; self.model = model
        self.recording = True; self.voice.setText('Aufnahme beenden'); self.panel.status.setText('Mikrofon aktiv · maximal 60 Sekunden · Verarbeitung lokal')
        self.start('pw-record', ['--rate', '16000', '--channels', '1', str(Path(self.temp.name) / 'audio.wav')], self.recorded)
        self.limit.start(60000)

    def start(self, binary, args, callback):
        proc = QProcess(self); self.process = proc
        proc.setProcessChannelMode(QProcess.MergedChannels)
        def finished(code):
            if self.process is not proc: return
            self.process = None; output = bytes(proc.readAllStandardOutput()).decode(errors='replace')
            proc.deleteLater(); callback(code, output)
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda error: finished(1) if error == QProcess.FailedToStart else None)
        proc.start(binary, args)

    def finish_recording(self):
        if self.recording and self.process:
            self.recording = False; self.limit.stop(); self.voice.setText('Transkribiere …'); self.voice.setEnabled(False)
            # PipeWire closes the WAV file on SIGTERM; no audio leaves this process tree.
            self.process.terminate()

    def recorded(self, code, output):
        self.limit.stop()
        if self.recording:
            self.recording = False; self.panel.show_error('Mikrofonaufnahme fehlgeschlagen: ' + output[-500:]); self.cleanup(); return
        wav = Path(self.temp.name) / 'audio.wav'
        if not wav.exists() or wav.stat().st_size <= 44:
            self.panel.show_error('Keine Audioaufnahme vorhanden.'); self.cleanup(); return
        self.start(self.binary, ['-m', self.model, '-f', str(wav), '-l', 'auto', '-otxt', '-of', str(Path(self.temp.name) / 'transcript'), '-nt'], self.transcribed)
        self.limit.timeout.disconnect(); self.limit.timeout.connect(self.timeout); self.limit.start(120000)

    def timeout(self):
        if self.process: self.process.kill()
        self.panel.show_error('Lokale Transkription hat das Zeitlimit erreicht.')

    def transcribed(self, code, output):
        result = Path(self.temp.name) / 'transcript.txt'
        if code == 0 and result.exists():
            self.panel.composer.insertPlainText(result.read_text().strip()); self.panel.status.setText('Diktat bereit — vor dem Senden prüfen')
        else: self.panel.show_error('Transkription fehlgeschlagen: ' + output[-500:])
        self.cleanup()

    def cleanup(self):
        self.limit.stop(); self.limit.timeout.disconnect(); self.limit.timeout.connect(self.finish_recording)
        self.voice.setEnabled(True); self.voice.setText('Diktieren')
        if self.temp: self.temp.cleanup(); self.temp = None

    def close(self):
        if self.conversation: self.conversation.stop()
        if self.process:
            proc = self.process; self.process = None; proc.kill(); proc.waitForFinished(1000); proc.deleteLater()
        self.recording = False; self.cleanup()
