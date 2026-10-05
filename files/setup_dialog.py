"""Native first-run setup shared by Lumen, Files and Search."""
from lumen_i18n import worker_process, tr
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import quote

from PySide6.QtCore import QLockFile, QProcess, QSettings, QSize, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QProgressBar,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from assistant_backend import OpenCodeBackend
from lumen_setup import FEATURES, executable
from settings_dialog import button, text
from settings_navigation import Details

RECOMMENDED = ('engine', 'documents', 'media', 'network')


class DictationTest(QWidget):
    """Reuse the real dictation path, with no agent or send action attached."""
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings; self.backend = SimpleNamespace(busy=False)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.status = text(tr('Ein kurzer Testsatz bleibt hier auf deinem Rechner.'))
        self.composer = QPlainTextEdit(); self.composer.setReadOnly(True)
        self.composer.setAccessibleName(tr('Erkannter Testsatz')); self.composer.setMaximumHeight(110)
        from lumen_context import ContextTools
        hidden = QWidget(self); hidden.hide()
        self.tools = ContextTools(self, QVBoxLayout(hidden))
        self.record = button(tr('Mikrofon testen'), self.tools.dictate)
        self.tools.voice.changed.connect(self.update_button)
        layout.addWidget(self.record); layout.addWidget(self.status); layout.addWidget(self.composer)

    def update_button(self):
        self.record.setText(tr('Mikrofon testen') if self.tools.voice.text() == tr('Diktieren') else self.tools.voice.text())
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
        self.result_model = ''; self.cancellable = False; self.providers = []; self.advance_after_job = False
        self.setWindowTitle(tr('Lumen einrichten')); self.setWindowIcon(QIcon.fromTheme('lumen'))
        self.resize(780, 690); self.setMinimumSize(600, 540)
        root = QVBoxLayout(self); root.setContentsMargins(28, 24, 28, 22); root.setSpacing(16)
        header = QHBoxLayout(); header.setSpacing(20)
        self.mark = text(''); self.mark.setFixedSize(64, 64); header.addWidget(self.mark)
        copy = QVBoxLayout(); copy.setSpacing(6)
        self.step = text(''); self.step.setObjectName('eyebrow'); copy.addWidget(self.step)
        self.heading = text(''); self.heading.setObjectName('heading'); copy.addWidget(self.heading)
        header.addLayout(copy, 1); root.addLayout(header)
        self.setObjectName('setupWizard')
        self.setStyleSheet('QDialog#setupWizard QLabel#heading { font-size: 24px; font-weight: 600; }')
        self.stack = QStackedWidget(); root.addWidget(self.stack, 1)
        self.titles = (tr('Willkommen bei Lumen'), tr('Deine KI-Anbindung'), tr('Mit deiner Stimme'), tr('Dein Desktop'), tr('Deine Einrichtung im Überblick'))
        self.build_dependencies(); self.build_engine(); self.build_speech(); self.build_desktop(); self.build_summary()
        self.progress = QProgressBar(); self.progress.hide(); self.progress.setAccessibleName(tr('Einrichtungsfortschritt'))
        root.addWidget(self.progress)
        self.status = text(tr('Empfohlen starten. Jederzeit anpassen.')); root.addWidget(self.status)
        footer = QHBoxLayout()
        self.later = button(tr('Später'), self.reject); footer.addWidget(self.later)
        self.cancel = button(tr('Vorgang abbrechen'), self.cancel_job); self.cancel.hide(); footer.addWidget(self.cancel)
        self.skip = button(tr('Ohne Ergänzungen weiter'), self.advance_page); footer.addWidget(self.skip)
        footer.addStretch()
        self.back = button(tr('Zurück'), lambda: self.change_page(-1)); footer.addWidget(self.back)
        self.next = button(tr('Weiter'), lambda: self.change_page(1)); self.next.setObjectName('primary'); footer.addWidget(self.next)
        root.addLayout(footer)
        self.stack.setCurrentIndex(page); self.update_page(); self.refresh()

    def page(self):
        scroll = QScrollArea(); scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidgetResizable(True)
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(0, 0, 8, 0); layout.setSpacing(14)
        scroll.setWidget(widget); self.stack.addWidget(scroll)
        return layout

    def build_dependencies(self):
        page = self.page()
        page.addWidget(text(tr('Dateien finden. Fragen stellen. Dinge erledigen.')))
        page.addWidget(text(tr('Wir richten die Grundlagen für dich ein. Vorhandene Einstellungen bleiben erhalten.')))
        page.addWidget(button(tr('Aus einer Sicherung wiederherstellen …'), lambda: QProcess.startDetached('lumen-vault', ['--backups'])))
        self.recommendation = text(''); page.addWidget(self.recommendation)
        page.addWidget(text(tr('Empfohlen: Assistenz, Datei- und Medienvorschauen sowie Netzwerkordner.')))
        details = Details(tr('Einrichtung anpassen')); self.dependency_details = details
        page.addWidget(details); page.addStretch(); page = details.content
        language_form = QFormLayout()
        self.ui_language = QComboBox()
        for title, code in [(tr('Systemsprache'), 'system'), ('Deutsch', 'de'), ('English', 'en')]:
            self.ui_language.addItem(title, code)
        self.ui_language.setCurrentIndex(max(0, self.ui_language.findData(self.settings.value('uiLanguage', 'system'))))
        self.ui_language.setAccessibleName(tr('Oberflächensprache'))
        language_form.addRow(tr('Oberflächensprache'), self.ui_language)
        page.addLayout(language_form)
        page.addWidget(text(tr('Die Sprache gilt ab dem nächsten Start von Lumen und Files. Die Leisten übernehmen sie nach der nächsten Plasma-Anmeldung.')))
        def save_language():
            self.settings.setValue('uiLanguage', self.ui_language.currentData()); self.settings.sync()
            if self.settings.status() != QSettings.NoError:
                self.status.setText(tr('Einstellungen konnten nicht gespeichert werden.'))
        self.ui_language.activated.connect(save_language)
        page.addWidget(text(tr('Lumen verbindet Dateien, Suche und Assistenz. Wir prüfen, was bereits vorhanden ist. '
            'Die Auswahl wird mit „Einrichten und weiter“ installiert.')))
        self.features = {}
        for key, (title, _commands, _packages) in FEATURES.items():
            item = QCheckBox(title); item.setAccessibleName(title); page.addWidget(item); self.features[key] = item
        for key in RECOMMENDED: self.features[key].setChecked(True)
        self.install = button(tr('Auswahl installieren'), self.install_selected); page.addWidget(self.install)
        for item in self.features.values(): item.toggled.connect(self.update_install)
        page.addWidget(text(tr('Systempakete: Arch/CachyOS mit grafischer Passwortabfrage. '
            'Dateien lassen sich auch ohne KI-Anbindung verwenden.')))
        page.addWidget(button(tr('Lokale Bildsuche einrichten · ca. 2 GB'), lambda: self.start_job('image-search')))
        page.addWidget(text(tr('Mehrsprachige CLIP-Bildsuche inklusive deutscher Suchbegriffe. Modelle werden einmalig '
            'heruntergeladen; Fotos und Suchbegriffe bleiben danach auf diesem Rechner. Kein Administratorpasswort nötig.')))
        page.addWidget(button(tr('Vault vorbereiten · verschlüsselte Sicherungen'), lambda: self.start_job('vault')))
        page.addWidget(button(tr('Inbox vorbereiten · IMAP/SMTP und Kalender'), lambda: self.start_job('inbox')))
        page.addWidget(button(tr('Proton Mail Bridge herunterladen …'), lambda: QDesktopServices.openUrl(QUrl('https://proton.me/mail/bridge'))))
        page.addStretch()

    def build_engine(self):
        page = self.page()
        page.addWidget(text(tr('OpenCode arbeitet im Hintergrund. Vorhandene Anbieter und Zugangsdaten werden übernommen. '
            'Die Prüfung lädt die Modellliste und sendet keinen Gesprächsinhalt an einen KI-Anbieter.')))
        self.engine_status = text(tr('Noch nicht geprüft.')); page.addWidget(self.engine_status)
        self.check_engine = button(tr('Anbindung prüfen und Modelle laden'), self.load_engine); page.addWidget(self.check_engine)
        self.repair_engine = button(tr('Kompatible Engine einrichten · ca. 61 MB'), self.install_engine)
        self.repair_engine.hide(); page.addWidget(self.repair_engine)
        self.models = QComboBox(); self.models.setAccessibleName(tr('Modell für Lumen'))
        self.models.setMinimumContentsLength(15); self.models.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.models.addItem(tr('Bisherige Modellwahl beibehalten'), '')
        self.model_details = Details(tr('Modell anpassen')); page.addWidget(self.model_details)
        form = QFormLayout(); form.addRow(tr('Modell'), self.models); self.model_details.content.addLayout(form)
        toggle = button(tr('Weiteren Anbieter verbinden …'), lambda: self.auth_box.setVisible(toggle.isChecked()))
        toggle.setCheckable(True); page.addWidget(toggle); self.auth_toggle = toggle
        self.auth_box = QWidget(); self.auth_box.hide()
        auth = QVBoxLayout(self.auth_box); auth.setContentsMargins(0, 0, 0, 0); auth.setSpacing(12)
        self.provider = QComboBox(); self.provider.setAccessibleName(tr('Anbieter mit API-Schlüssel'))
        self.provider.addItem(tr('Zuerst die Anbindung prüfen'), '')
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password); self.key.setAccessibleName(tr('API-Schlüssel'))
        self.key.setPlaceholderText(tr('Neuen API-Schlüssel einfügen'))
        form = QFormLayout(); form.addRow(tr('Anbieter'), self.provider); form.addRow(tr('API-Schlüssel'), self.key); auth.addLayout(form)
        self.connect_provider = button(tr('Zugang speichern'), self.save_auth); self.connect_provider.setEnabled(False)
        auth.addWidget(self.connect_provider)
        auth.addWidget(button(tr('Ollama-Cloud-Schlüssel verwalten …'), lambda: QDesktopServices.openUrl(QUrl('https://ollama.com/settings/keys'))))
        auth.addWidget(text(tr('Schlüssel speichert OpenCode in seinem Benutzerprofil. Bestehende Schlüssel werden nicht angezeigt. '
            'Andere Anmeldearten können weiterhin über die vorhandene OpenCode-Einrichtung verbunden werden.')))
        page.addWidget(self.auth_box)
        page.addStretch()

    def build_speech(self):
        page = self.page()
        page.addWidget(text(tr('Diktiere Texte direkt in Lumen. Aufnahme und Erkennung bleiben lokal. '
            'Erst beim Senden gelangt der Text an deinen eingestellten KI-Anbieter.')))
        self.speech_status = text(''); page.addWidget(self.speech_status)
        self.setup_speech = button(tr('Diktieren einrichten · 190 MB Modell'), lambda: self.start_job('dictation'))
        page.addWidget(self.setup_speech)
        self.speech_test = DictationTest(self.settings, self); page.addWidget(self.speech_test)
        details = Details(tr('Stimme und Erkennung anpassen')); self.speech_details = details
        page.addWidget(details); page.addStretch(); page = details.content
        page.addWidget(text(tr('Mehrsprachiges Whisper Small, platzsparend gespeichert. Unterstützt Deutsch. '
            'Die Erkennung läuft auf CPU oder verfügbarer GPU. Falls nötig werden Build-Werkzeuge über die Paketverwaltung ergänzt; '
            'das Vorbereiten kann einige Minuten dauern.')))
        page.addWidget(button(tr('Genauere Erkennung einrichten · 874 MB Modell'), lambda: self.start_job('dictation-quality')))
        page.addWidget(text(tr('Whisper Large v3 Turbo: größeres Modell für anspruchsvollere Sprache. '
            'Auf der CPU langsamer; das bisherige Modell bleibt für einen Wechsel zurück erhalten.')))
        page.addWidget(button(tr('Vorhandenes Sprachmodell auswählen …'), self.choose_model))
        page.addWidget(button(tr('Sprachgespräch einrichten · zusätzlich ca. 65 MB Stimme und Laufzeit'), lambda: self.start_job('voice')))
        page.addWidget(text(tr('Deutsche Piper-Stimme Thorsten (CC0), lokal. Nur erkannter Text geht an deinen Lumen-Modellanbieter.')))
        page.addWidget(button(tr('Mehrsprachige Stimme einrichten · ca. 2,5 GB Modell'), lambda: self.start_job('voice-multilingual')))
        page.addWidget(text(tr('Deutsch und englische Begriffe in derselben Stimme, vollständig lokal. '
            'Zusätzliche Laufzeit benötigt mehrere GB. Eine NVIDIA-GPU beschleunigt die Ausgabe; auf CPU dauert sie länger.')))
        from lumen_speech import add_recognition_fields
        form = QFormLayout(); page.addLayout(form)
        save_recognition = add_recognition_fields(form, self.settings)
        page.addWidget(button(tr('Erkennungseinstellungen speichern'), save_recognition))
        from lumen_tts import add_voice_fields
        voice_form = QFormLayout(); page.addLayout(voice_form)
        save_voice = add_voice_fields(voice_form, self.settings)
        self.voice_choice = voice_form.itemAt(0, QFormLayout.FieldRole).widget()
        page.addWidget(button(tr('Stimmeinstellungen speichern'), save_voice))
        page.addWidget(text(tr('Der Mikrofontest startet nur auf Klick und stoppt nach spätestens 60 Sekunden. '
            'Für Gespräche mit automatischen Runden zusätzlich die lokale Sprachausgabe einrichten.')))
        page.addStretch()

    def build_desktop(self):
        from appearance import DEFAULT_DESIGN, DESIGNS, theme_icon
        page = self.page()
        page.addWidget(text(tr('Lumen ist installiert. Du kannst deinen aktuellen Desktop behalten oder '
            'die Lumen-Leisten mit Suche, Systemübersicht und Einstellungen aktivieren.')))
        self.desktop_theme = QComboBox(); self.desktop_theme.setAccessibleName(tr('Design für den Lumen-Desktop'))
        self.desktop_theme.setIconSize(QSize(96, 60))
        for title, name in DESIGNS: self.desktop_theme.addItem(theme_icon(name), title, name)
        self.desktop_theme.setCurrentIndex(max(0, self.desktop_theme.findData(self.settings.value('appearance', DEFAULT_DESIGN))))
        self.design_summary = text(''); page.addWidget(self.design_summary)
        details = Details(tr('Design anpassen')); page.addWidget(details)
        form = QFormLayout(); form.addRow(tr('Design'), self.desktop_theme); details.content.addLayout(form)
        self.desktop_theme.currentIndexChanged.connect(lambda: self.design_summary.setText(
            tr('Dein Design: {0}', self.desktop_theme.currentText())))
        self.design_summary.setText(tr('Dein Design: {0}', self.desktop_theme.currentText()))
        page.addWidget(text(tr('Das gewählte Design gilt für Panels und Fensterrahmen. Dazu kommt das '
            'Lumen-Hintergrundbild. Deine bisherigen Panels werden ersetzt; zuvor wird ihre '
            'Konfiguration lokal gesichert. Deine Dateien und Programme bleiben erhalten.')))
        self.apply_desktop = button(tr('Lumen-Desktop aktivieren'), lambda: self.start_job('desktop'))
        self.apply_desktop.setAutoDefault(False); page.addWidget(self.apply_desktop)
        self.desktop_status = text(tr('Ohne Aktivierung bleibt dein aktueller Desktop erhalten.'))
        page.addWidget(self.desktop_status)
        page.addWidget(text(tr('Mit „Weiter“ kannst du diesen Schritt überspringen und Lumen trotzdem nutzen.')))
        page.addStretch()

    def build_summary(self):
        from setup_preferences import SetupPreferences
        page = self.page()
        self.personal = SetupPreferences(self.settings, lambda: self.go_to_page(2), self)
        page.addWidget(self.personal)
        details = Details(tr('Einrichtung prüfen')); page.addWidget(details)
        self.summary = text(''); details.content.addWidget(self.summary)
        page.addWidget(text(tr('Du findest diesen Assistenten jederzeit unter Einstellungen → Einrichtung. '
            'Übersprungene Erweiterungen kannst du dort später ergänzen.')))
        page.addStretch()

    def refresh(self):
        for key, (title, commands, _packages) in FEATURES.items():
            ready = all(executable(command) for command in commands)
            self.features[key].setText(title + (tr('  ·  Installiert') if ready else tr('  ·  Fehlt teilweise') if any(executable(c) for c in commands) else tr('  ·  Fehlt')))
            self.features[key].setEnabled(not ready)
            if ready: self.features[key].setChecked(True)
        self.update_install()
        self.settings.sync()
        model = self.settings.value('speechModel', '')
        ready = bool(executable('whisper-cli') and executable('pw-record') and Path(model).is_file())
        self.speech_status.setText(tr('Diktieren verfügbar · ') + Path(model).name if ready else tr('Diktieren ist noch nicht vollständig eingerichtet.'))
        self.speech_test.setVisible(ready)
        self.speech_test.record.setEnabled(ready)
        self.setup_speech.setVisible(not ready or not executable('voice-vad'))
        self.setup_speech.setText(tr('Sprechpausenerkennung einrichten') if ready else tr('Diktieren einrichten · 190 MB Modell'))
        self.summary.setText('\n\n'.join([item.text() for item in self.features.values()] +
            [self.engine_status.text(), self.speech_status.text(), self.desktop_status.text()]))

    def install_selected(self):
        groups = [key for key, item in self.features.items() if item.isChecked() and item.isEnabled()]
        if groups: self.start_job('packages', groups)
        else: self.status.setText(tr('Wähle zuerst eine fehlende Erweiterung aus.'))

    def update_install(self):
        pending = [item for item in self.features.values() if item.isEnabled() and item.isChecked()]
        self.install.setEnabled(bool(pending))
        self.recommendation.setText(tr('Keine weiteren Installationen ausgewählt.') if not pending else
            tr('{0} Komponenten werden noch ergänzt. Dafür kann dein Systempasswort nötig sein.', len(pending)))
        if hasattr(self, 'next'): self.update_page()

    def start_job(self, action, groups=()):
        if self.job or self.checking or self.speech_test.tools.process: return
        self.last_message = ''; self.result_model = ''; self.buffer = b''; self.cancellable = False
        proc = worker_process(self); self.job = proc
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_job)
        def finished(code):
            if self.job is not proc: return
            self.read_job(); self.job = None; proc.deleteLater()
            if code == 0 and self.result_model:
                self.settings.setValue('speechModel', self.result_model); self.settings.sync()
                if self.settings.status() != QSettings.NoError:
                    self.last_message = tr('Installiert, aber die Modellwahl konnte nicht gespeichert werden.')
            if code == 0 and action == 'desktop':
                self.desktop_status.setText(tr('Lumen-Desktop aktiviert · ') + self.desktop_theme.currentText())
            if code == 0 and action == 'voice-multilingual':
                self.settings.setValue('speechEngine', 'qwen'); self.settings.sync()
                self.voice_choice.setCurrentIndex(self.voice_choice.findData('qwen'))
            advance = self.advance_after_job and code == 0
            self.advance_after_job = False
            self.set_busy(False); self.refresh()
            self.status.setText((self.last_message or tr('Einrichtung abgeschlossen.')) if code == 0 else
                tr('Einrichtung nicht abgeschlossen. ') + (self.last_message or tr('Bitte erneut versuchen.')))
            if advance: self.advance_page()
            elif code == 0 and action == 'engine': self.load_engine()
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda error: finished(1) if error == QProcess.FailedToStart else None)
        self.set_busy(True); self.status.setText(tr('Einrichtung wird gestartet …'))
        arguments = [str(Path(__file__).with_name('lumen_setup.py')), action, *groups]
        if action == 'desktop': arguments.extend(['--theme', self.desktop_theme.currentData()])
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
            self.advance_after_job = False
            self.cancel.setEnabled(False); self.job.terminate()

    def set_busy(self, busy):
        self.skip.setEnabled(not busy)
        self.stack.setEnabled(not busy); self.next.setEnabled(not busy); self.later.setEnabled(not busy)
        self.back.setEnabled(not busy and self.stack.currentIndex() > 0)
        self.progress.setVisible(busy); self.progress.setRange(0, 0)
        self.cancel.setVisible(busy and self.job is not None); self.cancel.setEnabled(self.cancellable)

    def load_engine(self):
        if self.job or self.checking: return
        self.connect_provider.setEnabled(False)
        self.checking = True; self.set_busy(True); self.status.setText(tr('Vorhandene KI-Anbindung prüfen …'))
        self.engine.ensure_server(lambda: self.engine.request('GET', '/provider', callback=self.loaded_providers, error=self.engine_failed))

    def loaded_providers(self, data):
        if not isinstance(data, dict) or not isinstance(data.get('all'), list) or not isinstance(data.get('connected'), list):
            raise ValueError('Invalid provider inventory')
        if any(not isinstance(p, dict) or not isinstance(p.get('id'), str) or
               not isinstance(p.get('models', {}), dict) for p in data['all']):
            raise ValueError('Invalid provider')
        self.providers = data['all']; connected = set(data['connected']); self.connected = connected
        selected = self.models.currentData() or self.settings.value('model', '')
        self.models.clear(); self.models.addItem(tr('Bisherige Modellwahl beibehalten'), '')
        names = []
        for provider in self.providers:
            if provider['id'] not in connected: continue
            names.append(provider.get('name', provider['id']))
            for identifier, model in provider.get('models', {}).items():
                self.models.addItem(provider.get('name', provider['id']) + ' · ' + model.get('name', identifier), provider['id'] + '/' + identifier)
        self.models.setCurrentIndex(max(0, self.models.findData(selected)))
        self.engine_status.setText(tr('Engine erreichbar · Konfiguriert: ') + (', '.join(names) or tr('noch kein Anbieter')) +
            tr('\nZugang und Antwortqualität der Anbieter wurden nicht mit einer Testanfrage geprüft.'))
        self.engine.request('GET', '/provider/auth', callback=self.loaded_auth, error=self.engine_failed)

    def loaded_auth(self, data):
        if not isinstance(data, dict): raise ValueError('Invalid authentication methods')
        self.provider.clear()
        for provider in sorted(self.providers, key=lambda p: (p['id'] != 'ollama-cloud', p.get('name', p['id']))):
            # /provider/auth lists plugin overrides. Ordinary providers use API keys.
            methods = data.get(provider['id'], [{'type': 'api'}])
            if any(method.get('type') == 'api' and not method.get('prompts') for method in methods):
                self.provider.addItem(provider.get('name', provider['id']), provider['id'])
        self.connect_provider.setEnabled(self.provider.count() > 0)
        if not any(provider['id'] in self.connected for provider in self.providers):
            self.auth_toggle.setChecked(True); self.auth_box.show()
        self.checking = False; self.set_busy(False); self.refresh()
        self.status.setText(tr('Vorhandene Konfiguration geladen. Wähle bei Bedarf ein Modell für Lumen.'))
        self.repair_engine.hide()

    def save_auth(self):
        identifier = self.provider.currentData(); key = self.key.text().strip()
        if not identifier or not key or not self.engine.url:
            self.status.setText(tr('Bitte einen Anbieter auswählen und einen API-Schlüssel eingeben.')); return
        self.checking = True; self.set_busy(True)
        self.status.setText(tr('Zugang im OpenCode-Benutzerprofil speichern …'))
        def saved(_):
            self.key.clear(); self.engine.shutdown(); self.checking = False; self.load_engine()
        # Errors never display provider response bodies, which might echo a credential.
        self.engine.request('PUT', '/auth/' + quote(identifier, safe=''), {'type': 'api', 'key': key}, callback=saved,
            error=lambda _: self.engine_failed(tr('Zugang konnte nicht gespeichert werden. Bitte erneut versuchen.')))

    def engine_failed(self, message):
        self.checking = False; self.set_busy(False)
        self.connect_provider.setEnabled(False); self.repair_engine.show()
        self.engine_status.setText(tr('Anbindung konnte nicht geprüft werden.')); self.status.setText(message)

    def install_engine(self):
        if self.job or self.checking: return
        self.engine.shutdown()
        self.start_job('engine')

    def choose_model(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Sprachmodell auswählen'), str(Path.home()), tr('Whisper-Modell (*.bin)'))
        if path:
            self.settings.setValue('speechModel', path); self.settings.sync(); self.refresh()

    def change_page(self, direction):
        if self.job or self.checking: return
        if self.speech_test.tools.process:
            self.status.setText(tr('Bitte den Mikrofontest zuerst beenden und die Erkennung abwarten.')); return
        if direction > 0 and self.stack.currentIndex() == 0:
            groups = [key for key, item in self.features.items() if item.isEnabled() and item.isChecked()]
            if groups:
                self.advance_after_job = True
                self.start_job('packages', groups)
                return
        if direction > 0 and self.stack.currentIndex() == 1 and self.models.currentData():
            self.settings.setValue('model', self.models.currentData()); self.settings.sync()
        if direction > 0 and self.stack.currentIndex() == self.stack.count() - 1:
            self.accept(); return
        self.go_to_page(self.stack.currentIndex() + direction)

    def advance_page(self):
        if self.job or self.checking or self.speech_test.tools.process: return
        self.go_to_page(self.stack.currentIndex() + 1)

    def go_to_page(self, index):
        self.stack.setCurrentIndex(index); self.update_page(); self.refresh()
        self.next.setFocus()
        if self.stack.currentIndex() == 1 and not self.providers and executable('opencode'): self.load_engine()

    def update_page(self):
        index = self.stack.currentIndex()
        self.step.setText(tr('LUMEN EINRICHTEN   ·   {0} / {1}', index + 1, self.stack.count()))
        self.heading.setText(self.titles[index]); self.back.setEnabled(index > 0)
        self.mark.setPixmap(QIcon.fromTheme('lumen', QIcon.fromTheme('system-run')).pixmap(64, 64))
        selected = index == 0 and any(item.isEnabled() and item.isChecked() for item in self.features.values())
        self.skip.setVisible(selected)
        self.next.setText(tr('Einrichten und weiter') if selected else
            tr('Einrichtung beenden') if index == self.stack.count() - 1 else tr('Weiter'))
        self.next.setAccessibleName(self.next.text())

    def done(self, result):
        if self.job:
            self.status.setText(tr('Bitte den Vorgang abwarten oder abbrechen. Eine laufende Paketinstallation muss zuerst fertig werden.')); return
        if result == QDialog.Accepted:
            try: self.personal.commit()
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc)); return
        self.speech_test.tools.close(); self.engine.shutdown(); self.key.clear()
        self.settings.setValue('setupSeen', True)
        if result == QDialog.Accepted: self.settings.setValue('setupCompleted', True)
        self.settings.sync()
        super().done(result)


def open_setup(parent=None, settings=None, page=0):
    dialog = SetupDialog(parent, settings, page)
    try: return dialog.exec()
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
    sys.exit(app.exec())
