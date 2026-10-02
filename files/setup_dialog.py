"""Native first-run setup shared by Lumen, Files and Search."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote

from PyQt5.QtCore import QLockFile, QProcess, QSettings, QStandardPaths, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QProgressBar,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from assistant_backend import OpenCodeBackend
from lumen_setup import FEATURES, executable, missing_packages
from settings_dialog import button, text


class DictationTest(QWidget):
    """Reuse the real dictation path, with no agent or send action attached."""
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings; self.backend = SimpleNamespace(busy=False)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.status = text('Ein kurzer Testsatz bleibt hier auf deinem Rechner.')
        self.composer = QPlainTextEdit(); self.composer.setReadOnly(True)
        self.composer.setAccessibleName('Erkannter Testsatz'); self.composer.setMaximumHeight(110)
        from lumen_context import ContextTools
        hidden = QWidget(self); hidden.hide()
        self.tools = ContextTools(self, QVBoxLayout(hidden))
        self.record = button('Mikrofon testen', self.tools.dictate)
        self.tools.voice.changed.connect(self.update_button)
        layout.addWidget(self.record); layout.addWidget(self.status); layout.addWidget(self.composer)

    def update_button(self):
        self.record.setText('Mikrofon testen' if self.tools.voice.text() == 'Diktieren' else self.tools.voice.text())
        self.record.setEnabled(self.tools.voice.isEnabled())

    def show_error(self, message): self.status.setText(message)


class SetupDialog(QDialog):
    def __init__(self, parent=None, settings=None, page=0):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings('Lumen', 'Assistant')
        self.settings.sync()
        self.engine = OpenCodeBackend(str(Path.home()), self, project_config=False)
        self.engine.settings = self.settings
        self.engine.failed.connect(self.engine_failed)
        self.job = None; self.checking = False; self.buffer = b''; self.last_message = ''
        self.result_model = ''; self.cancellable = False; self.providers = []
        self.setWindowTitle('Lumen einrichten'); self.setWindowIcon(QIcon.fromTheme('lumen'))
        self.resize(780, 690); self.setMinimumSize(600, 540)
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 22); root.setSpacing(16)
        self.step = text(''); self.step.setObjectName('eyebrow'); root.addWidget(self.step)
        self.heading = text(''); self.heading.setObjectName('heading'); root.addWidget(self.heading)
        self.stack = QStackedWidget(); root.addWidget(self.stack, 1)
        self.titles = ('Willkommen bei Lumen', 'Deine KI-Anbindung', 'Mit deiner Stimme', 'Deine Einrichtung im Überblick')
        self.build_dependencies(); self.build_engine(); self.build_speech(); self.build_summary()
        self.progress = QProgressBar(); self.progress.hide(); self.progress.setAccessibleName('Einrichtungsfortschritt')
        root.addWidget(self.progress)
        self.status = text('Du entscheidest, welche Erweiterungen du nutzen möchtest.'); root.addWidget(self.status)
        footer = QHBoxLayout()
        self.later = button('Später', self.reject); footer.addWidget(self.later)
        self.cancel = button('Vorgang abbrechen', self.cancel_job); self.cancel.hide(); footer.addWidget(self.cancel)
        footer.addStretch()
        self.back = button('Zurück', lambda: self.change_page(-1)); footer.addWidget(self.back)
        self.next = button('Weiter', lambda: self.change_page(1)); self.next.setObjectName('primary'); footer.addWidget(self.next)
        root.addLayout(footer)
        self.stack.setCurrentIndex(page); self.update_page(); self.refresh()

    def page(self):
        scroll = QScrollArea(); scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidgetResizable(True)
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(0, 0, 8, 0); layout.setSpacing(14)
        scroll.setWidget(widget); self.stack.addWidget(scroll)
        return layout

    def build_dependencies(self):
        page = self.page()
        page.addWidget(text('Lumen verbindet Dateien, Suche und Assistenz. Wir prüfen, was bereits vorhanden ist. '
            'Zusätzliche Programme werden nur über „Auswahl installieren“ eingerichtet.'))
        self.features = {}
        for key, (title, _commands, _packages) in FEATURES.items():
            item = QCheckBox(title); item.setAccessibleName(title); page.addWidget(item); self.features[key] = item
        self.features['engine'].setChecked(bool(missing_packages(['engine'])))
        self.install = button('Auswahl installieren', self.install_selected); page.addWidget(self.install)
        for item in self.features.values(): item.toggled.connect(self.update_install)
        page.addWidget(text('Systempakete: Arch/CachyOS mit grafischer Passwortabfrage. '
            'Dateien lassen sich auch ohne KI-Anbindung verwenden.'))
        page.addStretch()

    def build_engine(self):
        page = self.page()
        page.addWidget(text('OpenCode arbeitet im Hintergrund. Vorhandene Anbieter und Zugangsdaten werden übernommen. '
            'Die Prüfung lädt die Modellliste und sendet keinen Gesprächsinhalt an einen KI-Anbieter.'))
        self.engine_status = text('Noch nicht geprüft.'); page.addWidget(self.engine_status)
        self.check_engine = button('Anbindung prüfen und Modelle laden', self.load_engine); page.addWidget(self.check_engine)
        self.models = QComboBox(); self.models.setAccessibleName('Modell für Lumen')
        self.models.setMinimumContentsLength(15); self.models.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.models.addItem('Bisherige Modellwahl beibehalten', '')
        form = QFormLayout(); form.addRow('Modell', self.models); page.addLayout(form)
        toggle = button('Weiteren Anbieter verbinden …', lambda: self.auth_box.setVisible(toggle.isChecked()))
        toggle.setCheckable(True); page.addWidget(toggle)
        self.auth_box = QWidget(); self.auth_box.hide()
        auth = QVBoxLayout(self.auth_box); auth.setContentsMargins(0, 0, 0, 0); auth.setSpacing(12)
        self.provider = QComboBox(); self.provider.setAccessibleName('Anbieter mit API-Schlüssel')
        self.provider.addItem('Zuerst die Anbindung prüfen', '')
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password); self.key.setAccessibleName('API-Schlüssel')
        self.key.setPlaceholderText('Neuen API-Schlüssel einfügen')
        form = QFormLayout(); form.addRow('Anbieter', self.provider); form.addRow('API-Schlüssel', self.key); auth.addLayout(form)
        self.connect_provider = button('Zugang speichern', self.save_auth); self.connect_provider.setEnabled(False)
        auth.addWidget(self.connect_provider)
        auth.addWidget(button('Ollama-Cloud-Schlüssel verwalten …', lambda: QDesktopServices.openUrl(QUrl('https://ollama.com/settings/keys'))))
        auth.addWidget(text('Schlüssel speichert OpenCode in seinem Benutzerprofil. Bestehende Schlüssel werden nicht angezeigt. '
            'Andere Anmeldearten können weiterhin über die vorhandene OpenCode-Einrichtung verbunden werden.'))
        page.addWidget(self.auth_box)
        page.addStretch()

    def build_speech(self):
        page = self.page()
        page.addWidget(text('Diktiere Texte direkt in Lumen. Aufnahme und Erkennung bleiben lokal. '
            'Erst beim Senden gelangt der Text an deinen eingestellten KI-Anbieter.'))
        self.speech_status = text(''); page.addWidget(self.speech_status)
        self.setup_speech = button('Diktieren einrichten · 190 MB Modell', lambda: self.start_job('dictation'))
        page.addWidget(self.setup_speech)
        page.addWidget(text('Mehrsprachiges Whisper Small, platzsparend gespeichert. Unterstützt Deutsch. '
            'Die Erkennung nutzt zunächst die CPU. Falls nötig werden Build-Werkzeuge über die Paketverwaltung ergänzt; '
            'das Vorbereiten kann einige Minuten dauern.'))
        page.addWidget(button('Vorhandenes Sprachmodell auswählen …', self.choose_model))
        page.addWidget(button('Sprachgespräch einrichten · zusätzlich ca. 65 MB Stimme und Laufzeit', lambda: self.start_job('voice')))
        page.addWidget(text('Deutsche Piper-Stimme Thorsten (CC0), lokal. Nur erkannter Text geht an deinen Lumen-Modellanbieter.'))
        self.speech_test = DictationTest(self.settings, self); page.addWidget(self.speech_test)
        page.addWidget(text('Der Mikrofontest startet nur auf Klick und stoppt nach spätestens 60 Sekunden. '
            'Für Gespräche mit automatischen Runden zusätzlich die lokale Sprachausgabe einrichten.'))
        page.addStretch()

    def build_summary(self):
        page = self.page(); self.summary = text(''); page.addWidget(self.summary)
        page.addWidget(text('Du findest diesen Assistenten jederzeit unter Einstellungen → Einrichtung. '
            'Übersprungene Erweiterungen kannst du dort später ergänzen.'))
        page.addStretch()

    def refresh(self):
        for key, (title, commands, _packages) in FEATURES.items():
            ready = all(executable(command) for command in commands)
            self.features[key].setText(title + ('  ·  Installiert' if ready else '  ·  Fehlt teilweise' if any(executable(c) for c in commands) else '  ·  Fehlt'))
            self.features[key].setEnabled(not ready)
            if ready: self.features[key].setChecked(True)
        self.update_install()
        self.settings.sync()
        model = self.settings.value('speechModel', '')
        ready = bool(executable('whisper-cli') and executable('pw-record') and Path(model).is_file())
        self.speech_status.setText('Diktieren verfügbar · ' + Path(model).name if ready else 'Diktieren ist noch nicht vollständig eingerichtet.')
        self.speech_test.record.setEnabled(ready)
        self.summary.setText('\n\n'.join([item.text() for item in self.features.values()] +
            [self.engine_status.text(), self.speech_status.text()]))

    def install_selected(self):
        groups = [key for key, item in self.features.items() if item.isChecked() and item.isEnabled()]
        if groups: self.start_job('packages', groups)
        else: self.status.setText('Wähle zuerst eine fehlende Erweiterung aus.')

    def update_install(self):
        self.install.setEnabled(any(item.isEnabled() and item.isChecked() for item in self.features.values()))

    def start_job(self, action, groups=()):
        if self.job or self.checking or self.speech_test.tools.process: return
        self.last_message = ''; self.result_model = ''; self.buffer = b''; self.cancellable = False
        proc = QProcess(self); self.job = proc
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_job)
        def finished(code):
            if self.job is not proc: return
            self.read_job(); self.job = None; proc.deleteLater()
            if code == 0 and self.result_model:
                self.settings.setValue('speechModel', self.result_model); self.settings.sync()
                if self.settings.status() != QSettings.NoError:
                    self.last_message = 'Installiert, aber die Modellwahl konnte nicht gespeichert werden.'
            self.set_busy(False); self.refresh()
            self.status.setText((self.last_message or 'Einrichtung abgeschlossen.') if code == 0 else
                'Einrichtung nicht abgeschlossen. ' + (self.last_message or 'Bitte erneut versuchen.'))
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda error: finished(1) if error == QProcess.FailedToStart else None)
        self.set_busy(True); self.status.setText('Einrichtung wird gestartet …')
        arguments = [str(Path(__file__).with_name('lumen_setup.py')), action, *groups]
        model = self.settings.value('speechModel', '')
        if action in ('dictation', 'voice') and Path(model).is_file(): arguments.extend(['--existing-model', model])
        proc.start(sys.executable, arguments)

    def read_job(self):
        if not self.job: return
        self.buffer += bytes(self.job.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: data = json.loads(line)
            except ValueError: continue
            self.last_message = str(data.get('message', ''))
            self.status.setText(self.last_message)
            percent = data.get('percent', -1)
            self.progress.setRange(0, 100 if percent >= 0 else 0)
            if percent >= 0: self.progress.setValue(percent)
            self.cancellable = bool(data.get('cancellable', False)); self.cancel.setEnabled(self.cancellable)
            self.result_model = data.get('model', self.result_model)

    def cancel_job(self):
        if self.job and self.cancellable:
            self.cancel.setEnabled(False); self.job.terminate()

    def set_busy(self, busy):
        self.stack.setEnabled(not busy); self.next.setEnabled(not busy); self.later.setEnabled(not busy)
        self.back.setEnabled(not busy and self.stack.currentIndex() > 0)
        self.progress.setVisible(busy); self.progress.setRange(0, 0)
        self.cancel.setVisible(busy and self.job is not None); self.cancel.setEnabled(self.cancellable)

    def load_engine(self):
        if self.job or self.checking: return
        self.checking = True; self.set_busy(True); self.status.setText('Vorhandene KI-Anbindung prüfen …')
        self.engine.ensure_server(lambda: self.engine.request('GET', '/provider', callback=self.loaded_providers, error=self.engine_failed))

    def loaded_providers(self, data):
        self.providers = data['all']; connected = set(data['connected'])
        selected = self.models.currentData() or self.settings.value('model', '')
        self.models.clear(); self.models.addItem('Bisherige Modellwahl beibehalten', '')
        names = []
        for provider in self.providers:
            if provider['id'] not in connected: continue
            names.append(provider.get('name', provider['id']))
            for identifier, model in provider.get('models', {}).items():
                self.models.addItem(provider.get('name', provider['id']) + ' · ' + model.get('name', identifier), provider['id'] + '/' + identifier)
        self.models.setCurrentIndex(max(0, self.models.findData(selected)))
        self.engine_status.setText('Engine erreichbar · Konfiguriert: ' + (', '.join(names) or 'noch kein Anbieter') +
            '\nZugang und Antwortqualität der Anbieter wurden nicht mit einer Testanfrage geprüft.')
        self.engine.request('GET', '/provider/auth', callback=self.loaded_auth, error=self.engine_failed)

    def loaded_auth(self, data):
        self.provider.clear()
        for provider in sorted(self.providers, key=lambda p: (p['id'] != 'ollama-cloud', p.get('name', p['id']))):
            # /provider/auth lists plugin overrides. Ordinary providers use API keys.
            methods = data.get(provider['id'], [{'type': 'api'}])
            if any(method.get('type') == 'api' and not method.get('prompts') for method in methods):
                self.provider.addItem(provider.get('name', provider['id']), provider['id'])
        self.connect_provider.setEnabled(self.provider.count() > 0)
        self.checking = False; self.set_busy(False); self.refresh()
        self.status.setText('Vorhandene Konfiguration geladen. Wähle bei Bedarf ein Modell für Lumen.')

    def save_auth(self):
        identifier = self.provider.currentData(); key = self.key.text().strip()
        if not identifier or not key or not self.engine.url:
            self.status.setText('Bitte einen Anbieter auswählen und einen API-Schlüssel eingeben.'); return
        self.checking = True; self.set_busy(True)
        self.status.setText('Zugang im OpenCode-Benutzerprofil speichern …')
        def saved(_):
            self.key.clear(); self.engine.shutdown(); self.checking = False; self.load_engine()
        # Errors never display provider response bodies, which might echo a credential.
        self.engine.request('PUT', '/auth/' + quote(identifier, safe=''), {'type': 'api', 'key': key}, callback=saved,
            error=lambda _: self.engine_failed('Zugang konnte nicht gespeichert werden. Bitte erneut versuchen.'))

    def engine_failed(self, message):
        self.checking = False; self.set_busy(False)
        self.engine_status.setText('Anbindung konnte nicht geprüft werden.'); self.status.setText(message)

    def choose_model(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Sprachmodell auswählen', str(Path.home()), 'Whisper-Modell (*.bin)')
        if path:
            self.settings.setValue('speechModel', path); self.settings.sync(); self.refresh()

    def change_page(self, direction):
        if self.speech_test.tools.process:
            self.status.setText('Bitte den Mikrofontest zuerst beenden und die Erkennung abwarten.'); return
        if direction > 0 and self.stack.currentIndex() == 1 and self.models.currentData():
            self.settings.setValue('model', self.models.currentData()); self.settings.sync()
        if direction > 0 and self.stack.currentIndex() == self.stack.count() - 1:
            self.accept(); return
        self.stack.setCurrentIndex(self.stack.currentIndex() + direction); self.update_page(); self.refresh()
        if self.stack.currentIndex() == 1 and not self.providers and executable('opencode'): self.load_engine()

    def update_page(self):
        index = self.stack.currentIndex()
        self.step.setText(f'LUMEN EINRICHTEN   ·   {index + 1} / {self.stack.count()}')
        self.heading.setText(self.titles[index]); self.back.setEnabled(index > 0)
        self.next.setText('Einrichtung beenden' if index == self.stack.count() - 1 else 'Weiter')

    def done(self, result):
        if self.job:
            self.status.setText('Bitte den Vorgang abwarten oder abbrechen. Eine laufende Paketinstallation muss zuerst fertig werden.'); return
        self.speech_test.tools.close(); self.engine.shutdown(); self.key.clear()
        self.settings.setValue('setupSeen', True)
        if result == QDialog.Accepted: self.settings.setValue('setupCompleted', True)
        self.settings.sync()
        super().done(result)


def open_setup(parent=None, settings=None, page=0):
    dialog = SetupDialog(parent, settings, page)
    try: return dialog.exec_()
    finally: dialog.deleteLater()


def offer_setup(parent):
    settings = QSettings('Lumen', 'Assistant'); settings.sync()
    if settings.value('setupSeen', False, type=bool) or QApplication.activeModalWidget(): return
    # One wizard across independently launched native apps; stale locks expire on exit.
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation))
    folder.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(folder / 'lumen-setup.lock'))
    if not lock.tryLock(0): return
    try: open_setup(parent, settings)
    finally: lock.unlock()


if __name__ == '__main__':
    from app import create_app
    app = create_app(); app.setApplicationName('lumen-setup-wizard')
    dialog = SetupDialog(); dialog.show()
    sys.exit(app.exec_())
