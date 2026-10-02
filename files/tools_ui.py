"""Native shell, cancellable jobs and audio controls shared by four desktop apps."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

from PyQt5.QtCore import Qt, QProcess, QTimer, QThread, QSettings, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QFileDialog, QInputDialog, QCheckBox, QSlider, QProgressBar)
from tools_data import Library, Cancelled, clock_text


def button(text, callback, icon='', primary=False):
    b = QPushButton(text); b.setCursor(Qt.PointingHandCursor)
    if icon: b.setIcon(QIcon.fromTheme(icon))
    b.setObjectName('primary' if primary else 'toolButton')
    b.setAccessibleName(text); b.clicked.connect(callback)
    return b


def label(text, name=''):
    w = QLabel(text); w.setTextFormat(Qt.PlainText); w.setWordWrap(True)
    if name: w.setObjectName(name)
    return w


def row(*widgets):
    widget = QWidget(); layout = QHBoxLayout(widget); layout.setContentsMargins(0,0,0,0); layout.setSpacing(8)
    for w in widgets: layout.addWidget(w)
    return widget


def open_path(path):
    path = Path(path)
    if not path.exists(): raise ValueError('Die Datei ist nicht erreichbar. Laufwerk oder NAS-Verbindung prüfen.')
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))): raise ValueError('Keine Anwendung konnte die Datei öffnen.')


class Job(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent); self.function = function; self.cancelled = threading.Event()

    def check(self):
        if self.cancelled.is_set(): raise Cancelled('Abgebrochen')

    def command(self, args, data=None, timeout=300):
        self.check()
        # Files prevent large decoder/model stderr output from filling RAM or a pipe.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr, tempfile.TemporaryFile() as stdin:
            if data: stdin.write(data); stdin.seek(0)
            proc = subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            started = time.monotonic()
            try:
                while proc.poll() is None:
                    self.check()
                    if time.monotonic()-started > timeout: raise ValueError('Die Verarbeitung hat zu lange gedauert.')
                    self.cancelled.wait(.1)
                self.check()
                if proc.returncode:
                    stderr.seek(max(0, stderr.tell()-3000))
                    raise ValueError(f'{Path(args[0]).name}: ' + stderr.read(3000).decode(errors='replace').strip())
                stdout.seek(0); output = stdout.read(2*1024**2+1)
                if len(output) > 2*1024**2: raise ValueError('Verarbeitungsergebnis zu groß.')
                return output
            finally:
                if proc.poll() is None:
                    try: os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        proc.wait()

    def run(self):
        try: self.result.emit(self.function(self))
        except Exception as error: self.failed.emit(str(error) or type(error).__name__)


class AudioPlayer(QFrame):
    """ffplay handles codecs; the controls remain native and do not open a terminal."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName('toolAudio')
        self.setStyleSheet('QFrame#toolAudio { background: palette(base); border: 1px solid palette(mid); border-radius: 12px; }')
        self.path = None; self.duration = 0; self.position = 0; self.proc = None; self.paused = False
        self.play_button = button('Abspielen', self.toggle, 'media-playback-start')
        self.seek = QSlider(Qt.Horizontal); self.seek.setAccessibleName('Wiedergabeposition')
        self.seek.sliderReleased.connect(lambda: self.play_at(self.seek.value()))
        self.time = label('00:00:00 / 00:00:00', 'muted')
        layout = QHBoxLayout(self); layout.setContentsMargins(12,4,12,4); layout.addWidget(self.play_button); layout.addWidget(self.seek,1); layout.addWidget(self.time)
        self.timer = QTimer(self); self.timer.setInterval(150); self.timer.timeout.connect(self.tick)
        self.setEnabled(False)

    def load(self, path, duration):
        self.stop(); self.path = str(path) if path else None; self.duration = int(duration or 0)
        self.position = 0; self.seek.setRange(0, self.duration); self.setEnabled(bool(path)); self.tick()

    def stop(self):
        self.timer.stop()
        if self.proc:
            proc, self.proc = self.proc, None
            if self.paused and proc.processId(): os.kill(proc.processId(), signal.SIGCONT)
            proc.terminate()
            if not proc.waitForFinished(600): proc.kill(); proc.waitForFinished(600)
            proc.deleteLater()
        self.paused = False; self.play_button.setText('Abspielen')

    def play_at(self, position=0):
        self.stop()
        if not self.path: return
        self.position = max(0, min(int(position), self.duration)); self.start_position = self.position
        self.started = time.monotonic(); proc = QProcess(self); self.proc = proc
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.errorOccurred.connect(lambda *_: self.playback_error(proc))
        proc.finished.connect(lambda code, _status: self.ended(proc, code))
        proc.start('ffplay', ['-v','error','-nodisp','-autoexit','-ss',str(self.position/1000),self.path])
        self.play_button.setText('Pause'); self.timer.start()

    def playback_error(self, proc):
        if self.proc is proc:
            self.stop(); self.time.setText('Wiedergabe nicht verfügbar; ffmpeg/ffplay prüfen.')

    def ended(self, proc, code):
        if self.proc is not proc: return
        self.proc = None; self.timer.stop(); self.paused = False; self.play_button.setText('Abspielen')
        self.position = 0; self.tick()
        if code: self.time.setText('Audiodatei konnte nicht abgespielt werden.')
        proc.deleteLater()

    def toggle(self):
        if not self.proc: self.play_at(self.position); return
        pid = self.proc.processId()
        if not pid: return
        if self.paused:
            os.kill(pid, signal.SIGCONT); self.started = time.monotonic(); self.start_position = self.position
            self.paused = False; self.timer.start(); self.play_button.setText('Pause')
        else:
            self.tick(); os.kill(pid, signal.SIGSTOP); self.paused = True; self.timer.stop(); self.play_button.setText('Fortsetzen')

    def tick(self):
        if self.proc and not self.paused: self.position = min(self.duration, self.start_position+int((time.monotonic()-self.started)*1000))
        if not self.seek.isSliderDown(): self.seek.setValue(self.position)
        self.time.setText(clock_text(self.position)+' / '+clock_text(self.duration))


class ToolWindow(QMainWindow):
    def __init__(self, name, title, tagline, icon, root=None):
        super().__init__(); self.name = name; self.library = Library(name, root); self.current = ''; self.loading = False
        self.job = None; self.engine = None; self.ai_callback = None
        self.settings = QSettings('Lumen', 'Assistant')
        self.setWindowTitle(title); self.setWindowIcon(QIcon.fromTheme(icon)); self.resize(1180,800); self.setMinimumSize(840,600)
        shell = QWidget(); shell.setObjectName('workplace'); self.setCentralWidget(shell)
        shell.setStyleSheet('QDateEdit, QSpinBox { background: palette(base); color: palette(text); border: 1px solid palette(mid); border-radius: 8px; padding: 8px; } QCheckBox::indicator { width: 16px; height: 16px; }')
        outer = QVBoxLayout(shell); outer.setContentsMargins(24,20,24,16); outer.setSpacing(16)
        title_area = QWidget(); tl = QVBoxLayout(title_area); tl.setContentsMargins(0,0,0,0)
        tl.addWidget(label(title, 'workplaceHeading')); tl.addWidget(label(tagline, 'muted'))
        head = QHBoxLayout(); head.addWidget(title_area,1); head.addWidget(button('Einrichtung', self.setup, 'configure'))
        outer.addLayout(head)
        self.split = QSplitter(); outer.addWidget(self.split,1)
        self.sidebar = QWidget(); side = QVBoxLayout(self.sidebar); side.setContentsMargins(0,0,16,0); side.setSpacing(12)
        self.search = QLineEdit(); self.search.setPlaceholderText('Bibliothek durchsuchen …'); self.search.setAccessibleName('Bibliothek durchsuchen')
        self.search.textChanged.connect(self.refresh); side.addWidget(self.search)
        self.add_button = button('Neu', lambda: self.safe(self.create), 'list-add', True); side.addWidget(self.add_button)
        self.entries = QListWidget(); self.entries.setObjectName('searchResults'); self.entries.setAccessibleName('Bibliothek')
        self.entries.currentItemChanged.connect(self.select); side.addWidget(self.entries,1)
        self.archived = QCheckBox('Archiv anzeigen'); self.archived.toggled.connect(self.refresh); side.addWidget(self.archived)
        self.archive_button = button('Archivieren / wiederherstellen', lambda: self.safe(self.archive), 'archive-insert'); side.addWidget(self.archive_button)
        self.split.addWidget(self.sidebar)
        self.body = QWidget(); self.content = QVBoxLayout(self.body); self.content.setContentsMargins(16,0,0,0); self.content.setSpacing(12)
        self.split.addWidget(self.body); self.split.setSizes([280,850]); self.split.setStretchFactor(1,1)
        self.status = label('Lokal gespeichert · Bereit', 'muted')
        self.progress = QProgressBar(); self.progress.setRange(0,0); self.progress.setMaximumWidth(100); self.progress.hide()
        self.cancel_button = button('Abbrechen', self.cancel, 'process-stop'); self.cancel_button.hide()
        outer.addWidget(row(self.status, self.progress, self.cancel_button))
        self.save_timer = QTimer(self); self.save_timer.setSingleShot(True); self.save_timer.setInterval(450)
        self.save_timer.timeout.connect(lambda: self.safe(self.save))

    def safe(self, callback, *args):
        try: return callback(*args)
        except Exception as error: self.error(str(error))

    def error(self, text):
        self.status.setText(text)
        QMessageBox.warning(self, self.windowTitle(), text[:3000])

    def setup(self):
        from setup_dialog import open_setup
        open_setup(self, self.settings)

    def edited(self):
        if not self.loading and self.current: self.save_timer.start(); self.status.setText('Änderungen werden gespeichert …')

    def save(self):
        self.save_timer.stop()

    def refresh(self, *_):
        key = self.current; rows = self.library.all(self.archived.isChecked(), self.search.text())
        self.entries.blockSignals(True); self.entries.clear(); selected = None
        for record in rows:
            item = QListWidgetItem(record['title']); item.setData(Qt.UserRole, record['id']); self.entries.addItem(item)
            if record['id'] == key: selected = item
        self.entries.setCurrentItem(selected); self.entries.blockSignals(False)
        self.archive_button.setEnabled(bool(key))
        self.archive_button.setText('Wiederherstellen' if self.archived.isChecked() else 'Archivieren')

    def focus_record(self, key):
        record = self.library.get(key)
        self.save_timer.stop(); self.current = key; self.search.clear(); self.archived.setChecked(record['_archived']); self.refresh()
        self.loading = True
        try: self.load(record)
        finally: self.loading = False
        self.body.setEnabled(True)

    def select(self, item, old):
        if not item: return
        self.safe(self.switch_record, item.data(Qt.UserRole))

    def switch_record(self, key):
        self.save(); self.focus_record(key)

    def archive(self):
        if not self.current: return
        self.save(); self.library.archive(self.current, not self.archived.isChecked()); self.current = ''
        self.body.setEnabled(False); self.refresh(); self.status.setText('Eintrag im Archiv. Originaldateien bleiben erhalten.')

    def begin(self, text):
        self.save(); self.sidebar.setEnabled(False); self.body.setEnabled(False)
        self.status.setText(text); self.progress.show(); self.cancel_button.show()

    def end(self):
        self.sidebar.setEnabled(True); self.body.setEnabled(bool(self.current)); self.progress.hide(); self.cancel_button.hide()

    def work(self, text, function, done):
        if self.job or (self.engine and self.engine.busy): return
        self.begin(text); self.job = Job(function, self)
        self.job.result.connect(lambda value: self.safe(done, value)); self.job.failed.connect(self.job_failed)
        self.job.progress.connect(self.status.setText)
        self.job.finished.connect(self.job_finished); self.job.start()

    def job_failed(self, message):
        if message == 'Abgebrochen': self.status.setText(message)
        else: self.error(message)

    def job_finished(self):
        self.job.deleteLater(); self.job = None; self.end()

    def ai(self, prompt, done):
        from assistant_backend import OpenCodeBackend
        if self.job or (self.engine and self.engine.busy): return
        if not self.engine:
            self.engine = OpenCodeBackend(self.library.root, self, project_config=False)
            self.engine.completed.connect(self.ai_done)
        self.begin('Der eingerichtete KI-Provider erstellt einen Vorschlag …'); self.ai_callback = done
        self.engine.send(prompt, title=self.windowTitle(), proposal=True)

    def ai_done(self, success, result):
        self.end(); callback, self.ai_callback = self.ai_callback, None
        if success and callback: self.safe(callback, result)
        elif result != 'Abgebrochen': self.error(result)
        else: self.status.setText(result)

    def cancel(self):
        if self.job: self.job.cancelled.set(); self.status.setText('Wird abgebrochen …')
        if self.engine and self.engine.busy: self.engine.stop()

    def export_text(self, text, default):
        path, _ = QFileDialog.getSaveFileName(self, 'Exportieren', str(Path.home()/default), 'Markdown (*.md);;Text (*.txt)')
        if path:
            # Native dialog confirms overwrite; replace atomically after complete write.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=Path(path).parent, delete=False) as f:
                temporary = Path(f.name)
                try: f.write(text); f.flush(); os.fsync(f.fileno()); os.replace(temporary,path)
                finally: temporary.unlink(missing_ok=True)
            self.status.setText('Export gespeichert.')

    def closeEvent(self, event):
        if self.job:
            self.cancel(); self.status.setText('Abbruch läuft. Danach kann das Fenster geschlossen werden.'); event.ignore(); return
        try: self.save()
        except Exception as error: self.error(str(error)); event.ignore(); return
        if self.engine: self.engine.shutdown()
        player = getattr(self, 'player', None)
        if player: player.stop()
        event.accept()
