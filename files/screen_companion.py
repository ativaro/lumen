"""Native, explicitly shared window guidance using Lumen's existing engine and voice."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from PySide6.QtCore import Qt, QEvent, QProcess, QTimer, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFrame, QTextBrowser, QDialog, QDialogButtonBox, QScrollArea)
from assistant_backend import OpenCodeBackend
from private_input import AssistantInput
from lumen_i18n import tr, worker_process
from voice_session import VoiceSession
from lumen_voice_ui import VoiceActivity
from vault_privacy import capture_guard


class Composer(AssistantInput):
    submitted = Signal()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit(); event.accept()
        else: super().keyPressEvent(event)


class AnswerView(QTextBrowser):
    def loadResource(self, *_): return None


class FrameGate:
    """Ignore small visual noise; require two stable changed samples before sending."""
    def __init__(self): self.sent = self.previous = None
    @staticmethod
    def signature(image):
        tiny = image.scaled(64, 48, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_Grayscale8)
        return bytes(tiny.constBits())
    @staticmethod
    def different(a, b):
        return a is None or len(a) != len(b) or sum(abs(x-y) > 20 for x, y in zip(a, b)) > len(b)*.025
    def changed(self, image):
        current = self.signature(image)
        stable = self.previous is not None and not self.different(self.previous, current)
        self.previous = current
        return stable and self.different(self.sent, current)
    def mark(self, image): self.sent = self.previous = self.signature(image)


class Companion(QWidget):
    def __init__(self, parent=None, leave=None):
        super().__init__(parent)
        self.leave = leave
        self.setWindowTitle('Lumen Companion'); self.setWindowIcon(QIcon.fromTheme('lumen'))
        if parent is None: self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(460, 820); self.setMinimumSize(420, 720)
        from ui_typography import font
        compact_font = font(); compact_font.setPixelSize(14); self.setFont(compact_font)
        # Empty private working directory prevents project instructions from becoming screen context.
        self.workspace = tempfile.TemporaryDirectory(prefix='lumen-guide-', dir=os.environ.get('XDG_RUNTIME_DIR'))
        self.backend = OpenCodeBackend(self.workspace.name, self, project_config=False)
        self.backend.screen_guidance = True; self.backend.read_only = True
        self.voice = VoiceSession(self.backend, self.backend.settings, self)
        self.proc = None; self.generation = 0; self.target = None; self.active = False
        self.image = QImage(); self.png = b''; self.pending = ''; self.goal = ''; self.reviewed = False
        self.gate = FrameGate(); self.turns = 0; self.started = 0.; self.closing = False
        self.timer = QTimer(self); self.timer.setInterval(5000); self.timer.timeout.connect(self.observe)
        self.worker_limit = QTimer(self); self.worker_limit.setSingleShot(True)
        self.worker_limit.timeout.connect(lambda: self.pause(tr('Fensterzugriff hat zu lange gedauert. Erneut auswählen oder fortsetzen.')))
        layout = QVBoxLayout(self); layout.setContentsMargins(22, 18, 22, 18); layout.setSpacing(12)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(0,0,0,0); body.setSpacing(12)
        scroll.setWidget(content); layout.addWidget(scroll,1)
        header = QHBoxLayout(); body.addLayout(header)
        title = QLabel(tr('An deiner Seite')); title.setObjectName('guideTitle'); header.addWidget(title); header.addStretch()
        self.end = QPushButton(tr('Zurück zu Lumen') if leave else tr('Beenden'))
        self.end.clicked.connect(self.leave_help); header.addWidget(self.end)
        self.history = QCheckBox(tr('Gespräch anzeigen')); self.history.toggled.connect(self.render_answer)
        body.addWidget(self.history)
        caption = QLabel(tr('Ein Fenster. Dein Ziel. Schritt für Schritt.')); caption.setWordWrap(True); body.addWidget(caption)
        self.choose = QPushButton(QIcon.fromTheme('window'), tr('Fenster auswählen'))
        self.choose.clicked.connect(self.select); body.addWidget(self.choose)
        self.selected = QLabel(tr('Noch kein Fenster freigegeben')); self.selected.setWordWrap(True)
        self.selected.setTextFormat(Qt.PlainText); body.addWidget(self.selected)
        self.preview = QPushButton(tr('Hier erscheint deine lokale Vorschau'))
        self.preview.setObjectName('guidePreview')
        self.preview.setAccessibleName(tr('Fensterbild vergrößern')); self.preview.clicked.connect(self.enlarge)
        body.addWidget(self.preview)
        self.notice = QLabel(tr('Nur das gewählte Fenster wird geteilt. Bilder gehen an deinen eingestellten Modellanbieter; bei Cloud-Modellen verlassen sie den Rechner. Engine und Anbieter können den Verlauf speichern. Sichtbare Geheimnisse werden nicht zuverlässig erkannt. Vor ihrer Eingabe pausieren.'))
        self.notice.setWordWrap(True); self.notice.setObjectName('guideNotice'); body.addWidget(self.notice)
        self.auto = QCheckBox(tr('Änderungen automatisch begleiten'))
        self.auto.setToolTip(tr('Nach der ersten Bildfreigabe: höchstens alle 5 Sekunden prüfen. Bei unklarem Schutzstatus wird pausiert.'))
        self.auto.toggled.connect(self.automatic_changed); body.addWidget(self.auto)
        self.approve = QPushButton(tr('Dieses Bild freigeben und starten')); self.approve.setObjectName('guidePrimary')
        self.approve.clicked.connect(self.send_image); self.approve.hide(); body.addWidget(self.approve)
        self.answer = AnswerView(); self.answer.setOpenLinks(False)
        # No external resources or automatic remote image downloads from model output.
        self.answer.setFrameShape(QFrame.NoFrame)
        self.answer.setPlainText(tr('Wähle ein Fenster und beschreibe, wobei ich dich begleiten soll.'))
        body.addWidget(self.answer, 1)
        self.status = QLabel(tr('Bereit · Bildschirm und Mikrofon aus')); self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        self.indicator = VoiceActivity(self); layout.addWidget(self.indicator)
        self.composer = Composer(); self.composer.setPlaceholderText(tr('Was möchtest du erreichen?'))
        self.composer.setAccessibleName(tr('Dein Ziel oder deine nächste Frage'))
        self.composer.setFixedHeight(72); self.composer.submitted.connect(self.submit); layout.addWidget(self.composer)
        controls = QHBoxLayout(); layout.addLayout(controls)
        self.mic = QPushButton(QIcon.fromTheme('audio-input-microphone'), tr('Sprechen'))
        self.mic.clicked.connect(self.toggle_voice); controls.addWidget(self.mic)
        self.pause_button = QPushButton(tr('Pause')); self.pause_button.clicked.connect(self.toggle_pause); controls.addWidget(self.pause_button)
        self.next = QPushButton(tr('Nächster Schritt')); self.next.setObjectName('guidePrimary')
        self.next.clicked.connect(self.submit); controls.addWidget(self.next)
        self.voice.transcribedText.connect(self.submit)
        self.voice.changed.connect(self.voice_changed); self.voice.levelChanged.connect(self.indicator.set_level)
        self.voice.failed.connect(self.show_error); self.voice.setupRequested.connect(self.speech_setup)
        self.backend.completed.connect(self.completed)
        self.backend.busyChanged.connect(lambda _: self.update_controls())
        self.setStyleSheet('''QLabel#guideTitle {font-size:24px; font-weight:600;}
            QLabel#guideNotice {font-size:12px;}
            QPushButton {padding:8px 10px; border-radius:10px;}
            QPushButton#guidePrimary {background:palette(highlight);color:palette(highlighted-text);}
            QPushButton#guidePreview {min-height:120px; max-height:140px; padding:4px;}
            QTextBrowser {background:transparent;}''')
        self.update_controls()

    def update_controls(self):
        busy = self.proc is not None or self.backend.busy
        self.choose.setEnabled(not busy)
        self.next.setEnabled(bool(self.target) and not busy and not self.approve.isVisible())
        self.mic.setEnabled(bool(self.target) and (self.voice.active or not busy) and not self.approve.isVisible())
        self.pause_button.setEnabled(bool(self.target) or busy)
        self.pause_button.setText(tr('Pause') if self.active or busy else tr('Fortsetzen'))
        self.approve.setEnabled(bool(self.png) and not busy)

    def leave_help(self):
        if self.leave:
            self.pause(); self.leave()
        else: self.close()

    def render_answer(self):
        from search_document import message_rows, render
        rows, last = message_rows(self.backend.messages)
        if self.history.isChecked():
            self.answer.setHtml(''.join(render(('### '+(tr('Du') if row['role']=='user' else 'Lumen')+'\n\n'+row['text'])) for row in rows))
        elif last: self.answer.setHtml(render(last))

    def run_worker(self, mode, callback):
        generation = self.generation
        proc = worker_process(self); self.proc = proc; output = bytearray()
        def receive():
            if self.proc is not proc: return
            output.extend(bytes(proc.readAllStandardOutput()))
            if len(output) > 20 * 1024**2: self.pause(tr('Fensteraufnahme ist zu groß.'))
        def finished(code, *_):
            if self.proc is not proc: return
            receive()
            if self.proc is not proc: return
            self.worker_limit.stop(); self.proc = None; proc.deleteLater()
            if generation != self.generation or self.closing: return
            try:
                data = json.loads(output)
                if code or data.get('error'): raise ValueError(data.get('error') or tr('Fensterzugriff fehlgeschlagen.'))
                callback(data)
            except (ValueError, TypeError, KeyError) as error: self.pause(str(error))
            self.update_controls()
        proc.readyReadStandardOutput.connect(receive)
        proc.readyReadStandardError.connect(lambda: proc.readAllStandardError())
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda error: self.pause(tr('Bildschirmfunktion konnte nicht gestartet werden.')) if error == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__).with_name('screen_capture.py')), mode])
        if mode != 'select': proc.write(json.dumps(self.target).encode())
        proc.closeWriteChannel(); self.worker_limit.start(95000 if mode == 'select' else 12000)
        self.update_controls()

    def select(self):
        self.pause(); self.target = None; self.reviewed = False; self.goal = ''; self.gate = FrameGate()
        self.turns = 0; self.backend.new_conversation(); self.status.setText(tr('Klicke auf das gewünschte Fenster · Esc bricht ab'))
        self.run_worker('select', self.selected_window)

    def selected_window(self, target):
        if target['pid'] == os.getpid() or target['app'] == 'lumen-companion':
            raise ValueError(tr('Bitte das Fenster auswählen, in dem du Hilfe brauchst.'))
        self.target = target; self.selected.setText(target['caption'])
        self.active = True; self.started = time.monotonic()
        self.status.setText(tr('Fenster ausgewählt · Ziel eingeben und nächsten Schritt starten'))
        self.composer.setFocus()

    def submit(self, text=None):
        if not self.target or self.proc or self.backend.busy or self.approve.isVisible(): return
        if not isinstance(text, str): text = self.composer.toPlainText().strip()
        if not text: text = tr('Was ist mein nächster Schritt?') if self.goal else ''
        if not text: self.composer.setFocus(); return
        if self.voice.active and self.voice.state != 'thinking':
            self.voice.cancel_process(); self.voice.say_status('thinking', tr('Lumen antwortet …'))
        if not self.goal: self.goal = text
        self.composer.clear(); self.pending = text; self.active = True
        self.started = self.started or time.monotonic()
        self.status.setText(tr('Nur das ausgewählte Fenster wird geprüft …'))
        self.run_worker('capture', lambda data: self.captured(data, False))

    def captured(self, data, automatic):
        if not self.active or self.closing: return
        state = data['protection']
        if state == 'password':
            self.pause(tr('Passwortfeld erkannt · Begleitung pausiert. Erst nach der Eingabe fortsetzen.')); return
        if automatic and state != 'clear':
            self.auto.setChecked(False)
            self.pause(tr('Schutzstatus unklar · mit „Fortsetzen“ ein Bild einzeln prüfen.')); return
        png = base64.b64decode(data['png'], validate=True); image = QImage.fromData(png)
        if image.isNull(): raise ValueError(tr('Ungültige Fensteraufnahme.'))
        if automatic and not self.gate.changed(image): return
        self.png, self.image = png, image; self.protection = state
        self.preview.setText(''); self.preview.setIcon(QIcon(QPixmap.fromImage(image)))
        self.preview.setIconSize(self.preview.size() - QSize(16, 16))
        if automatic: self.pending = tr('Das Fenster hat sich verändert. Was ist jetzt der nächste Schritt für mein Ziel?')
        if self.reviewed and self.auto.isChecked() and state == 'clear': self.send_image()
        else:
            self.timer.stop(); self.approve.show(); self.approve.setText(tr('Dieses Bild freigeben und weiter'))
            self.status.setText(tr('Lokale Vorschau · zum Prüfen vergrößern · noch nicht gesendet'))
            if state != 'clear': self.auto.setChecked(False)

    def send_image(self):
        if not self.png or not self.pending or self.backend.busy or not self.active: return
        try:
            with capture_guard():
                self.gate.mark(self.image); self.reviewed = True; self.turns += 1
                self.approve.hide(); self.status.setText(tr('Lumen betrachtet dein freigegebenes Fenster …'))
                self.backend.send(self.pending, screen_image=self.png, context_data={'goal': self.goal})
        except OSError:
            self.pause(tr('Lumen Vault ist geöffnet. Begleitung pausiert.')); return
        self.png = b''; self.pending = ''; self.update_controls()

    def completed(self, success, answer):
        if not self.active or self.closing: return
        if success:
            from search_document import render
            self.answer.setHtml(render(answer))
            if self.history.isChecked(): self.render_answer()
            self.status.setText(tr('Dein nächster Schritt · du bedienst das Fenster'))
            if self.auto.isChecked(): self.timer.start()
        else:
            self.pause(tr('Modellanfrage fehlgeschlagen. Ein bildfähiges Modell ist nötig. ') + answer)
        self.update_controls()

    def observe(self):
        if not self.active or not self.auto.isChecked() or not self.reviewed or self.proc or self.backend.busy or self.voice.active: return
        if self.turns >= 30 or time.monotonic()-self.started >= 20*60:
            self.pause(tr('Begleitung pausiert · Sitzungslimit erreicht. Bewusst fortsetzen.')); return
        self.run_worker('automatic', lambda data: self.captured(data, True))

    def automatic_changed(self, checked):
        if checked and self.active and self.reviewed and not self.approve.isVisible(): self.timer.start()
        else: self.timer.stop()

    def toggle_pause(self):
        if self.active or self.proc or self.backend.busy: self.pause()
        elif self.target:
            self.active = True; self.started = time.monotonic(); self.turns = 0; self.submit()

    def pause(self, message=None):
        self.active = False; self.reviewed = False; self.generation += 1; self.timer.stop(); self.worker_limit.stop()
        self.voice.stop()
        if self.proc:
            proc, self.proc = self.proc, None; proc.kill(); proc.waitForFinished(1000); proc.deleteLater()
        self.backend.shutdown(); self.backend.set_busy(False)
        self.png = b''; self.image = QImage(); self.pending = ''; self.approve.hide()
        self.preview.setIcon(QIcon()); self.preview.setText(tr('Pausiert · kein Fensterbild'))
        self.status.setText(message or tr('Pausiert · Bildschirm und Mikrofon aus'))
        self.update_controls()

    def show_error(self, message): self.status.setText(message)

    def toggle_voice(self):
        if not self.target: return
        self.active = True; self.voice.toggle(); self.update_controls()

    def voice_changed(self):
        self.indicator.set_state(self.voice.state if self.voice.active else '')
        self.mic.setText(tr('Mikrofon aus') if self.voice.active else tr('Sprechen'))
        if self.voice.active: self.status.setText(self.voice.status)
        self.update_controls()

    def speech_setup(self):
        self.pause()
        from setup_dialog import open_setup
        open_setup(self, self.backend.settings, page=2)

    def enlarge(self):
        if self.image.isNull(): return
        dialog = QDialog(self); dialog.setWindowTitle(tr('Lokale Bildvorschau')); dialog.resize(1000, 750)
        layout = QVBoxLayout(dialog); scroll = QScrollArea(); label = QLabel()
        label.setPixmap(QPixmap.fromImage(self.image)); scroll.setWidget(label); layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.exec()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and self.isMinimized(): self.pause()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.closing = True; self.pause(); self.workspace.cleanup(); event.accept()


def main():
    from app import create_app
    app = create_app(); app.setApplicationName('lumen-companion'); app.setApplicationDisplayName('Lumen Companion')
    app.setDesktopFileName('lumen-companion')
    from lumen_activation import SingleWindow, present
    activation = SingleWindow('org.lumen.Companion')
    if activation.running: return activation.forward()
    window = Companion(); window.show(); app.aboutToQuit.connect(window.pause)
    activation.bind(lambda request: present(window))
    return app.exec()


if __name__ == '__main__': sys.exit(main())
