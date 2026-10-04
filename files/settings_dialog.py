"""Shared native settings for Lumen, Files and their desktop integrations."""
from lumen_i18n import worker_process, tr, language
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PySide6.QtCore import QProcess, QSettings, QSize, Qt, QTimer, QTime, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QButtonGroup, QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTimeEdit, QVBoxLayout, QWidget)
from assistant_backend import OpenCodeBackend
from desktop_settings import SHORTCUTS


def text(value):
    item = QLabel(value)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    item.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return item


def button(title, callback):
    item = QPushButton(title)
    item.setAutoDefault(False)
    item.clicked.connect(callback)
    return item


def combo(items, value):
    item = QComboBox()
    for title, data in items:
        item.addItem(title, data)
    item.setCurrentIndex(max(0, item.findData(value)))
    return item


class SettingsDialog(QDialog):
    preferencesChanged = Signal(str, list)

    def __init__(self, parent=None, files_settings=None, assistant_settings=None, page=None, load_system=True, application=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Einstellungen — Lumen'))
        self.resize(1000, 760)
        self.setMinimumSize(800, 580)
        self.assistant = assistant_settings if assistant_settings is not None else QSettings('Lumen', 'Assistant')
        self.files = files_settings if files_settings is not None else QSettings('Lumen', 'Files')
        self.job = None
        self.engine = None
        self.desktop = {}
        self.original = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 18)
        self.stack = QStackedWidget()
        self.page_info = []
        self.status = text(tr('Änderungen mit „Übernehmen“ speichern. Systemdialoge übernehmen ihre eigenen Einstellungen.'))
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        bottom.addWidget(button(tr('Systemzustand neu laden'), self.reload))
        bottom.addStretch()
        bottom.addWidget(button(tr('Schließen'), self.reject))
        root.addLayout(bottom)
        self.build_lumen()
        self.build_files()
        self.shortcut_page = self.page(tr('Tastenkürzel'), tr('Lumen überall aufrufen'))
        self.shortcut_rows = QVBoxLayout()
        self.shortcut_page.addLayout(self.shortcut_rows)
        self.launcher(self.shortcut_page, tr('Alle globalen Tastenkürzel …'), 'kcmshell6', 'kcm_keys')
        self.shortcut_page.addWidget(text(tr('Files: Strg+F Suche · Strg+L Pfad · Strg+K Server · Strg+T/W Tab öffnen/schließen\n'
            'Alt+Links/Rechts oder Maustasten 4/5: Verlauf · Alt+Hoch: übergeordneter Ordner\n'
            'Leertaste: große Vorschau · F2: umbenennen · Entf: Papierkorb · Strg+J: Lumen\n'
            'Strg+Umschalt+F: Inhalte suchen · Strg+Komma: Einstellungen\n'
            'Galerie: Links/Rechts blättern · R/Umschalt+R drehen · H spiegeln · Strg+Z rückgängig · Strg+S speichern · F11 Vollbild')))
        self.shortcut_page.addStretch()
        self.build_appearance()
        self.build_panels()
        self.service_page = self.page(tr('Dienste & Berichte'), tr('Automatisch im Hintergrund'))
        self.service_page.addWidget(text(tr('Systemdienste verwenden bei Bedarf die KDE-Passwortabfrage. Berichtszeiten gelten in deiner lokalen Zeitzone.')))
        self.service_rows = QVBoxLayout()
        self.service_page.addLayout(self.service_rows)
        self.service_page.addStretch()
        self.build_integrations()
        self.build_recovery()
        self.build_setup()
        self.build_mcp()
        from hardware_ui import HardwareView
        self.hardware_page = self.stack.count()
        hardware = self.page('Lumen System', tr('Leistung, Geräte und Systemaktivität verstehen'))
        hardware.addWidget(HardwareView(self))
        self.app_pages = {'lumen': 0, 'files': 1, 'system': self.hardware_page}
        self.build_apps()
        self.build_speech_settings()
        from persona_settings import PersonaEditor
        self.persona_page = self.stack.count()
        personality = self.page(tr('Persönlichkeit'), tr('Wie Lumen mit dir spricht und zusammenarbeitet.'))
        self.persona_editor = PersonaEditor(self.assistant, lambda: self.open_page(self.speech_output_page), self)
        self.persona_editor.saved.connect(lambda: (
            self.preferencesChanged.emit(self.assistant.fileName(), ['personaProfile']),
            self.status.setText(tr('Persönlichkeit gespeichert. Gilt ab der nächsten Nachricht.'))))
        personality.addWidget(self.persona_editor); personality.addStretch()
        for action in self.stack.findChildren(QPushButton):
            action.setAutoDefault(False); action.setDefault(False)
        from settings_navigation import SettingsNavigation, categories
        self.navigation = SettingsNavigation(self.stack, self.page_info, categories(self), self)
        self.nav = self.navigation.nav; self.nav_search = self.navigation.search
        root.insertWidget(0, self.navigation, 1)
        destination = self.app_pages.get(application, page)
        if destination is not None: self.open_page(destination)
        if load_system:
            QTimer.singleShot(0, self.reload)

    def open_page(self, index, target=None):
        self.navigation.open_page(index, target)

    def build_apps(self):
        from lumen_apps import catalogue, COMPANIONS, launch
        explanations = {
            'translate': tr('Texte übersetzen, den Schreibstil ändern oder nur Fehler korrigieren. PDFs werden als neue Datei exportiert. Das konfigurierte Lumen-Modell wird erst nach deinem Start verwendet.'),
            'search': tr('Suche und Gespräch nutzen das gemeinsame Modell, die Sprache und das Erscheinungsbild von Lumen. Diktieren wird im Einrichtungsassistenten eingerichtet.'),
            'wissen': tr('Notizbuch, Sammlungen und Freigaben verwaltest du in „Meine Notizen“. Im Lumen-Gedächtnis steuerst du Erinnerungen und automatisches Lernen.'),
            'inbox': tr('Mail- und Kalenderkonten werden in der Inbox verwaltet. Die KI-Lesefreigabe für lokale Nachrichten findest du unter MCP.'),
            'vault': tr('Quellen, Ziele, Zeitpläne und Verschlüsselung werden je Sicherungsplan in Vault eingestellt.'),
            'reader': tr('Stimme und Audioausgabe wählst du im Reader. Bibliothek und Markierungen bleiben lokal gespeichert.'),
            'sound': tr('Ausgabegeräte, Lautstärken und Regeln für Anwendungen verwaltest du in Sound.'),
            'meetings': tr('Aufnahmen und Transkriptionen verwaltest du in der Meeting-Werkstatt. Lokale Spracherkennung wird über die gemeinsame Einrichtung installiert.'),
            'household': tr('Dokumente, Kategorien und Erinnerungsfristen stellst du je Eintrag im Digitalen Haushalt ein.'),
            'workbench': tr('Arbeitsordner, Aufgaben und Projektverknüpfungen verwaltest du je Projekt in der Projekt-Werkbank.'),
            'radio': tr('Quellen, Programme, Stimmen und Audioausgabe verwaltest du im Persönlichen Radio.'),
        }
        self.app_controls = {}
        def open_app(key, area=None):
            try: launch(key, area=area)
            except (OSError, ValueError) as error: self.status.setText(str(error))
        for key, title, description, icon in catalogue():
            if key in self.app_pages: continue
            self.app_pages[key] = self.stack.count()
            panel = self.page(title, description)
            panel.addWidget(text(explanations[key]))
            panel.addWidget(button(tr('App öffnen'), lambda _=False, app=key: open_app(app)))
            if key == 'translate':
                from translate_data import LANGUAGES, STYLES, MODES
                form = QFormLayout(); panel.addLayout(form); defaults = {}
                for pref, caption, choices, default in [('translateTarget', tr('Zielsprache'), LANGUAGES, 'de'), ('translateStyle', tr('Schreibstil'), STYLES, 'neutral'), ('translateMode', tr('Startmodus'), MODES, 'translate')]:
                    control = combo([(tr(title), value) for value, title in choices.items()], self.field(self.assistant, pref, default))
                    form.addRow(caption, control); defaults[pref] = control
                def save_translate():
                    try:
                        self.save(self.assistant, {pref: control.currentData() for pref, control in defaults.items()})
                        self.status.setText(tr('Translate-Vorgaben gespeichert. Gilt für neue Texte nach dem nächsten Start.'))
                    except (OSError, ValueError) as error: self.status.setText(str(error))
                panel.addWidget(button(tr('Translate-Vorgaben übernehmen'), save_translate))
            if key == 'wissen':
                panel.addWidget(button(tr('Lumen-Gedächtnis öffnen'), lambda: open_app('wissen', 'lumen')))
            if key in COMPANIONS:
                controls = {}
                for pref, caption in [('restoreGeometry', tr('Fenstergröße und Position wiederherstellen')), ('restoreSelection', tr('Letzten Eintrag wieder öffnen'))]:
                    control = QCheckBox(caption)
                    control.setChecked(self.field(self.assistant, f'apps/{key}/{pref}', True, bool))
                    panel.addWidget(control); controls[pref] = control
                self.app_controls[key] = controls
                def save_app(_=False, app=key, fields=controls):
                    try:
                        self.save(self.assistant, {f'apps/{app}/{pref}': control.isChecked() for pref, control in fields.items()})
                        self.status.setText(tr('App-Einstellungen gespeichert. Gilt beim nächsten Start.'))
                    except (OSError, ValueError) as error: self.status.setText(str(error))
                panel.addWidget(button(tr('App-Einstellungen übernehmen'), save_app))
            panel.addWidget(text(tr('Gemeinsam für alle Lumen-Apps')))
            panel.addWidget(button(tr('Sprache, Modell und Arbeitsweise'), lambda: self.open_page(0)))
            panel.addWidget(button(tr('Erscheinungsbild'), lambda: self.open_page(3)))
            if key in ('search', 'meetings', 'reader', 'radio'):
                panel.addWidget(button(tr('Spracheingabe und Einrichtung'), lambda: self.open_page(self.speech_input_page)))
            if key == 'inbox': panel.addWidget(button(tr('KI-Zugriff auf die Inbox'), lambda: self.open_page(9)))
            panel.addStretch()

    def build_mcp(self):
        page = self.page('MCP', tr('Lumen-Funktionen für die KI'))
        page.addWidget(text(tr('Die KI kann Dateien suchen, freigegebene Notizen lesen und Aufträge sowie Sicherungsstände abfragen. Wissen verwendet dieselben Freigaben wie Gespräche.')))
        self.mcp_inbox = QCheckBox(tr('Lokale Nachrichten und Termine über MCP lesen'))
        self.mcp_inbox.setChecked(self.field(self.assistant, 'mcpInboxRead', False, bool))
        page.addWidget(self.mcp_inbox)
        page.addWidget(text(tr('Standardmäßig aus. Gelesene Inhalte können an deinen konfigurierten KI-Anbieter übermittelt werden. Es werden keine Nachrichten versendet und keine Konten synchronisiert. Der Entzug gilt ab dem nächsten Werkzeugaufruf; bereits gelesene Chat-Inhalte bleiben erhalten.')))
        page.addWidget(text(tr('Ändernde Werkzeuge benötigen eine separate Freigabe in OpenCode. Die Lesefreigabe für die Inbox erlaubt keine Änderungen.')))
        def save():
            try:
                self.save(self.assistant, {'mcpInboxRead': self.mcp_inbox.isChecked()})
                self.status.setText(tr('MCP-Freigabe gespeichert.'))
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
        page.addWidget(button(tr('MCP-Einstellungen übernehmen'), save))
        page.addStretch()

    def build_speech_settings(self):
        from lumen_speech import add_recognition_fields
        from lumen_tts import add_voice_fields
        from settings_navigation import Details
        from PySide6.QtWidgets import QDoubleSpinBox
        self.speech_input_page = self.stack.count()
        page = self.page(tr('Spracheingabe'), tr('Mikrofon und Diktieren für alle Lumen-Apps'))
        form = QFormLayout(); page.addLayout(form)
        save_recognition = add_recognition_fields(form, self.assistant)
        self.recognition_form = form
        advanced = Details(tr('Erweitert · Gesprächserkennung')); page.addWidget(advanced)
        calibration = QFormLayout(); advanced.content.addLayout(calibration)
        threshold = QSpinBox(); threshold.setRange(50, 15000)
        threshold.setValue(self.assistant.value('voiceThreshold', 450, type=int))
        silence = QDoubleSpinBox(); silence.setRange(.3, 4); silence.setSingleStep(.1)
        silence.setValue(self.assistant.value('voiceSilence', .9, type=float))
        calibration.addRow(tr('Mikrofonschwelle (kleiner = empfindlicher)'), threshold)
        calibration.addRow(tr('Sprechpause vor dem Senden (Sekunden)'), silence)
        def save_input():
            save_recognition()
            self.assistant.setValue('voiceThreshold', threshold.value()); self.assistant.setValue('voiceSilence', silence.value())
            self.assistant.sync()
            self.preferencesChanged.emit(self.assistant.fileName(), ['speechLanguage', 'speechVocabulary', 'speechUseGPU', 'voiceThreshold', 'voiceSilence'])
            self.status.setText(tr('Spracheingabe gespeichert. Gilt ab der nächsten Aufnahme.'))
        page.addWidget(button(tr('Spracheingabe übernehmen'), save_input))
        self.speech_setup_link(page)
        page.addStretch()
        self.speech_output_page = self.stack.count()
        page = self.page(tr('Stimme & Vorlesen'), tr('Gemeinsame Stimme für Gespräche, Reader und Radio'))
        form = QFormLayout(); page.addLayout(form)
        save_voice = add_voice_fields(form, self.assistant)
        self.voice_form = form
        def save_output():
            save_voice()
            self.preferencesChanged.emit(self.assistant.fileName(), ['speechEngine', 'speechSpeaker'])
            self.status.setText(tr('Stimme gespeichert. Gilt ab der nächsten Sprachausgabe.'))
        page.addWidget(button(tr('Stimme übernehmen'), save_output))
        self.speech_setup_link(page)
        page.addStretch()

    def speech_setup_link(self, page):
        page.addWidget(text(tr('Modelle installieren oder wechseln und das Mikrofon testen:')))
        page.addWidget(button(tr('Sprache einrichten …'), lambda: self.open_setup_wizard(2)))

    def open_setup_wizard(self, page=0):
        from setup_dialog import open_setup
        open_setup(self, self.assistant, page=page)
        self.assistant.sync()
        selected = self.assistant.value('model', '')
        if self.model.findData(selected) < 0: self.model.addItem(selected, selected)
        self.model.setCurrentIndex(max(0, self.model.findData(selected)))
        self.original[(self.assistant.fileName(), 'model')] = selected
        from lumen_speech import VOCABULARY
        from lumen_tts import engine, speaker
        language_choice = self.recognition_form.itemAt(0, QFormLayout.FieldRole).widget()
        language_choice.setCurrentIndex(max(0, language_choice.findData(self.assistant.value('speechLanguage', 'de'))))
        self.recognition_form.itemAt(1, QFormLayout.FieldRole).widget().setText(str(self.assistant.value('speechVocabulary', VOCABULARY)))
        self.recognition_form.itemAt(2, QFormLayout.FieldRole).widget().setChecked(self.assistant.value('speechUseGPU', True, type=bool))
        voice_choice = self.voice_form.itemAt(0, QFormLayout.FieldRole).widget()
        voice_choice.setCurrentIndex(max(0, voice_choice.findData(engine(self.assistant))))
        self.voice_form.itemAt(1, QFormLayout.FieldRole).widget().setCurrentText(speaker(self.assistant))
        self.preferencesChanged.emit(self.assistant.fileName(), ['model', 'speechModel', 'speechEngine', 'speechSpeaker'])

    def build_setup(self):
        page = self.page(tr('Einrichtung'), tr('Lumen und optionale Erweiterungen vorbereiten'))
        page.addWidget(text(tr('Der Einrichtungsassistent prüft OpenCode, Vorschauen und Netzwerkfunktionen. '
            'Du kannst Anbieter verbinden, ein Modell auswählen und lokales Diktieren installieren und testen.')))
        page.addWidget(button(tr('Einrichtungsassistent öffnen'), self.open_setup_wizard))
        page.addStretch()

    def build_recovery(self):
        page = self.page(tr('Stabilität'), tr('Abstürze erkennen und die letzte Ansicht wiederherstellen'))
        self.crash_detection = QCheckBox(tr('Absturz- und Hängererkennung aktivieren'))
        self.crash_detection.setChecked(self.field(self.assistant, 'crashDetection', True, bool))
        page.addWidget(self.crash_detection)
        page.addWidget(text(tr('Lumen, Files und Suche werden unabhängig überwacht. Antwortet ein Fenster eine Minute lang nicht, '
            'kannst du weiter warten oder es beenden und neu öffnen. Beim nächsten Start werden letzte Ansichten und Entwürfe angeboten. '
            'Dateiaktionen und KI-Aufträge werden nicht automatisch wiederholt.')))
        page.addWidget(text(tr('Berichte und Wiederherstellungsdaten bleiben lokal. Sie können Dateipfade und Gesprächsentwürfe enthalten. '
            'Es werden höchstens 20 beendete Sitzungen aufbewahrt; normale Sitzungen werden beim Schließen entfernt. '
            'Ungespeicherte Bildbearbeitungen werden nicht wiederhergestellt.')))
        def open_reports():
            from lumen_crash import directory
            try:
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory()))):
                    self.status.setText(tr('Der Berichtsordner konnte nicht geöffnet werden.'))
            except OSError as error: self.status.setText(str(error))
        def save():
            try:
                self.save(self.assistant, {'crashDetection': self.crash_detection.isChecked()})
                self.status.setText(tr('Stabilität gespeichert. Gilt für neu gestartete Anwendungen.'))
            except (OSError, ValueError) as error: self.status.setText(str(error))
        page.addWidget(button(tr('Lokale Fehlerberichte öffnen'), open_reports))
        page.addWidget(button(tr('Stabilität übernehmen'), save))
        page.addStretch()

    def page(self, title, subtitle):
        self.page_info.append(dict(title=title, subtitle=subtitle))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(14)
        heading = text(title)
        heading.setObjectName('heading')
        layout.addWidget(heading)
        layout.addWidget(text(subtitle))
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return layout

    def field(self, settings, key, default, kind=None):
        value = settings.value(key, default, type=kind) if kind else settings.value(key, default)
        self.original[(settings.fileName(), key)] = value
        return value

    def save(self, settings, values):
        from lumen_preferences import save_preferences
        changes = save_preferences(settings, values,
            {key: self.original.get((settings.fileName(), key)) for key in values})
        for key, value in values.items():
            self.original[(settings.fileName(), key)] = value
        self.preferencesChanged.emit(settings.fileName(), list(changes))

    def folder_field(self, form, title, settings, key, default):
        edit = QLineEdit(self.field(settings, key, default))
        edit.setAccessibleName(title)
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        def choose():
            path = QFileDialog.getExistingDirectory(self, title, edit.text())
            if path:
                edit.setText(path)
        row.addWidget(button(tr('Wählen …'), choose))
        form.addRow(title, row)
        return edit

    def build_lumen(self):
        page = self.page('Lumen', tr('Vorgaben für neue Gespräche und Fenster'))
        form = QFormLayout()
        self.ui_language = combo([(tr('Systemsprache'), 'system'), ('Deutsch', 'de'), ('English', 'en')],
                                 self.field(self.assistant, 'uiLanguage', 'system'))
        self.ui_language.setAccessibleName(tr('Oberflächensprache'))
        form.addRow(tr('Oberflächensprache'), self.ui_language)
        form.addRow('', text(tr('Die Sprache gilt ab dem nächsten Start von Lumen und Files. Die Leisten übernehmen sie nach der nächsten Plasma-Anmeldung.')))
        self.workdir = self.folder_field(form, tr('Arbeitsordner'), self.assistant, 'workdir', str(Path.home() / 'Documents/work'))
        self.mode = combo([(tr('Aufgaben erledigen'), 'build'), (tr('Lesen & prüfen'), 'plan')], self.field(self.assistant, 'defaultMode', 'build'))
        form.addRow(tr('Arbeitsweise'), self.mode)
        self.language = QLineEdit(self.field(self.assistant, 'translationLanguage', 'Deutsch' if language() == 'de' else 'English'))
        form.addRow(tr('Übersetzen nach'), self.language)
        self.model = combo([(tr('Vorgabe der Engine'), '')], '')
        self.model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.model.setMinimumContentsLength(18)
        current = self.field(self.assistant, 'model', '')
        if current:
            self.model.addItem(current, current)
            self.model.setCurrentIndex(1)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model, 1)
        self.model_button = button(tr('Modelle laden'), self.load_models)
        model_row.addWidget(self.model_button)
        form.addRow(tr('Modell'), model_row)
        self.auto = QCheckBox(tr('Nicht mehr nachfragen'))
        self.auto.setChecked(self.field(self.assistant, 'autoApproveTools', False, bool))
        self.auto.setToolTip(tr('Erlaubt Werkzeugaufrufe einschließlich Befehlen und Dateiänderungen. Inhaltliche Rückfragen bleiben sichtbar.'))
        form.addRow(tr('Werkzeugfreigaben'), self.auto)
        page.addLayout(form)
        page.addWidget(text(tr('Die Modellwahl gilt für Lumen und die intelligenten Dateiaktionen. Provider und Zugangsdaten werden aus deiner bestehenden Engine-Konfiguration geladen.\n'
                            '„Nicht mehr nachfragen“ erlaubt auch Befehle und Dateiänderungen. Vorschläge zum Umbenennen und Sortieren bleiben ausdrücklich bestätigungspflichtig.')))
        page.addWidget(button(tr('Lumen-Einstellungen übernehmen'), self.save_lumen))
        page.addStretch()

    def save_lumen(self):
        try:
            directory = Path(self.workdir.text()).expanduser()
            if not directory.is_dir() or not os.access(directory, os.R_OK | os.X_OK):
                raise ValueError(tr('Bitte einen erreichbaren Arbeitsordner wählen.'))
            language = self.language.text().strip()
            if not language or len(language) > 80:
                raise ValueError(tr('Bitte eine Übersetzungssprache eingeben (maximal 80 Zeichen).'))
            self.save(self.assistant, {'workdir': str(directory.resolve()), 'defaultMode': self.mode.currentData(),
                'translationLanguage': language, 'model': self.model.currentData(), 'autoApproveTools': self.auto.isChecked(),
                'uiLanguage': self.ui_language.currentData()})
            self.status.setText(tr('Lumen-Einstellungen gespeichert. Sprache, Startordner und Arbeitsweise gelten beim nächsten Start.'))
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def load_models(self):
        self.model_button.setEnabled(False)
        self.status.setText(tr('Eingerichtete Modelle werden geladen …'))
        if self.engine is None:
            self.engine = OpenCodeBackend(str(Path.home()), self, project_config=False)
            self.engine.failed.connect(self.models_failed)
        def loaded(data):
            selected = self.model.currentData()
            try:
                models = sorted({(p['id'] + '/' + key, model.get('name', key))
                                 for p in data['providers'] for key, model in p['models'].items()})
            except (AttributeError, KeyError, TypeError, ValueError):
                self.models_failed(tr('Die Engine hat eine ungültige Modellliste geliefert.'))
                return
            self.model.clear()
            self.model.addItem(tr('Vorgabe der Engine'), '')
            for identifier, name in models:
                self.model.addItem(f'{name}  ·  {identifier}', identifier)
            if selected and self.model.findData(selected) < 0:
                self.model.addItem(selected, selected)
            self.model.setCurrentIndex(max(0, self.model.findData(selected)))
            self.model_button.setEnabled(True)
            self.status.setText(tr('{0} Modelle geladen. Änderungen mit „Übernehmen“ speichern.', len(models)))
        self.engine.ensure_server(lambda: self.engine.request('GET', '/config/providers', callback=loaded, error=self.models_failed))

    def models_failed(self, error):
        self.model_button.setEnabled(True)
        self.status.setText(tr('Modelle konnten nicht geladen werden: ') + error)

    def build_files(self):
        page = self.page('Lumen Files', tr('Navigation, Vorschau und schnelle Suche'))
        form = QFormLayout()
        self.resume = QCheckBox(tr('Geöffnete Tabs wiederherstellen'))
        self.resume.setChecked(self.field(self.files, 'restoreLastFolder', True, bool))
        form.addRow(tr('Beim Start'), self.resume)
        self.startdir = self.folder_field(form, tr('Startordner'), self.files, 'startFolder', str(Path.home()))
        self.startdir.setEnabled(not self.resume.isChecked())
        self.resume.toggled.connect(lambda value: self.startdir.setEnabled(not value))
        self.hidden = QCheckBox(tr('Versteckte Dateien anzeigen'))
        self.hidden.setChecked(self.field(self.files, 'hidden', False, bool))
        form.addRow(tr('Dateien'), self.hidden)
        self.preview = QCheckBox(tr('Vorschauleiste anzeigen'))
        self.preview.setChecked(self.field(self.files, 'previewVisible', True, bool))
        form.addRow(tr('Vorschau'), self.preview)
        self.document_workshop = QCheckBox(tr('Dokumentenwerkstatt aktivieren'))
        self.document_workshop.setChecked(self.field(self.files, 'documentWorkshopEnabled', False, bool))
        self.document_workshop.setToolTip(tr('PDF-Seiten zusammenstellen, drehen, schwärzen und mit Texterkennung exportieren. Standardmäßig ausgeschaltet.'))
        form.addRow(tr('PDF-Bearbeitung'), self.document_workshop)
        page.addLayout(form)
        from settings_navigation import Details
        tuning = Details(tr('Erweitert · Suchverhalten'))
        page.addWidget(tuning)
        form = QFormLayout(); tuning.content.addLayout(form)
        self.delay = QSpinBox()
        self.delay.setRange(100, 1500)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(' ms')
        self.delay.setValue(self.field(self.files, 'searchDelay', 250, int))
        form.addRow(tr('Suche nach Tipp-Pause'), self.delay)
        self.limit = QSpinBox()
        self.limit.setRange(100, 50000)
        self.limit.setSingleStep(500)
        self.limit.setValue(self.field(self.files, 'searchLimit', 5000, int))
        form.addRow(tr('Max. Dateinamen-Treffer'), self.limit)
        sources = Details(tr('Orte, Server und Bibliotheken'))
        page.addWidget(sources)
        main_page = page; page = sources.content
        page.addWidget(text(tr('Gespeicherte Orte & Server — Entfernen löscht nur den Eintrag, keine Dateien oder Zugangsdaten.')))
        self.places = QListWidget()
        self.places.setAccessibleName(tr('Gespeicherte Orte und Server'))
        self.places.setMaximumHeight(120)
        for key in ('favorites', 'network_servers'):
            for value in self.field(self.files, key, [], list):
                item = QListWidgetItem(str(value))
                item.setData(Qt.UserRole, key)
                self.places.addItem(item)
        page.addWidget(self.places)
        remove = button(tr('Ausgewählten Eintrag entfernen'), lambda: self.places.takeItem(self.places.currentRow()) if self.places.currentRow() >= 0 else None)
        remove.setObjectName('danger'); page.addWidget(remove)
        page.addWidget(button(tr('Bibliotheken und Quellen verwalten …'), self.manage_libraries))
        page.addWidget(text(tr('Neue Server: Strg+K in Files (SMB, SFTP, WebDAV, NFS).\n'
            'Bilder bearbeiten: Leertaste auf einem Bild. Originale werden vor dem Speichern gesichert.\n'
            'Speicheranalyse: Menü ••• → Speicher analysieren. Umbenennen/Sortieren: Auswahl → Kontextmenü.')))
        main_page.addWidget(button(tr('Files-Einstellungen übernehmen'), self.save_files))
        main_page.addStretch()

    def manage_libraries(self):
        from file_spaces import Catalog
        from file_spaces_ui import LibraryDialog
        from PySide6.QtWidgets import QMenu
        catalog = self.parent().spaces.catalog if hasattr(self.parent(), 'spaces') else Catalog()
        menu = QMenu(self)
        def edit(library=None):
            dialog = LibraryDialog(catalog, library, self)
            if dialog.exec() == QDialog.Accepted:
                self.preferencesChanged.emit(self.files.fileName(), ['libraries'])
            dialog.deleteLater()
        for library in catalog.libraries():
            menu.addAction(library['name'], lambda _=False, value=library: edit(value))
        menu.addAction(tr('Neue Bibliothek …'), lambda: edit())
        menu.exec(self.mapToGlobal(self.rect().center()))

    def save_files(self):
        try:
            folder = Path(self.startdir.text()).expanduser()
            if not self.resume.isChecked() and (not folder.is_dir() or not os.access(folder, os.R_OK | os.X_OK)):
                raise ValueError(tr('Bitte einen erreichbaren Startordner wählen.'))
            values = {'restoreLastFolder': self.resume.isChecked(), 'startFolder': str(folder),
                'hidden': self.hidden.isChecked(), 'previewVisible': self.preview.isChecked(),
                'documentWorkshopEnabled': self.document_workshop.isChecked(),
                'searchDelay': self.delay.value(), 'searchLimit': self.limit.value()}
            for key in ('favorites', 'network_servers'):
                values[key] = [self.places.item(i).text() for i in range(self.places.count()) if self.places.item(i).data(Qt.UserRole) == key]
            self.save(self.files, values)
            self.status.setText(tr('Files-Einstellungen gespeichert. Der Startordner gilt ab dem nächsten Fenster.'))
        except (ValueError, OSError) as error:
            self.status.setText(str(error))

    def launcher(self, layout, title, program, *args):
        item = button(title, lambda: self.launch(program, list(args)))
        if not shutil.which(program):
            item.setEnabled(False)
            item.setToolTip(program + tr(' ist nicht installiert.'))
        layout.addWidget(item)

    def launch(self, program, arguments):
        okay, _pid = QProcess.startDetached(program, arguments, str(Path.home()))
        self.status.setText(tr('Nativer Einstellungsdialog geöffnet.') if okay else tr('Der Einstellungsdialog konnte nicht geöffnet werden.'))

    def build_appearance(self):
        page = self.page(tr('Erscheinungsbild'), tr('Lumen und dein KDE-Desktop'))
        from appearance import DEFAULT_DESIGN, DESIGNS, DESCRIPTIONS, apply_design, normalize_design, theme_icon
        page.addWidget(text(tr('Ein Design für Lumen, Files, Leisten, Panels und Fensterdekorationen.')))
        value = normalize_design(self.field(self.assistant, 'appearance', DEFAULT_DESIGN))
        self.appearance = QButtonGroup(self)
        choices = QGridLayout(); choices.setSpacing(12)
        self.theme_buttons = {}
        for index, (title, name) in enumerate(DESIGNS):
            choice = QPushButton(title + ('\nStandard' if name == DEFAULT_DESIGN else ''))
            choice.setObjectName('themeChoice'); choice.setCheckable(True)
            choice.setProperty('design', name); choice.setIcon(theme_icon(name)); choice.setIconSize(QSize(100, 60))
            choice.setMinimumHeight(90); choice.setAccessibleName(title + ': ' + DESCRIPTIONS[name])
            choice.setToolTip(DESCRIPTIONS[name]); self.appearance.addButton(choice)
            choice.setChecked(value == name); self.theme_buttons[name] = choice
            choices.addWidget(choice, index // 2, index % 2)
        page.addLayout(choices)
        extras = QHBoxLayout()
        for title, name in [(tr('KDE-Systemstil'), 'system')] + ([(tr('Bisheriges helles Design'), 'clear')] if value == 'clear' else []):
            choice = QPushButton(title); choice.setObjectName('chip'); choice.setCheckable(True)
            choice.setProperty('design', name); self.appearance.addButton(choice)
            choice.setChecked(value == name); self.theme_buttons[name] = choice; extras.addWidget(choice)
        extras.addStretch(); page.addLayout(extras)
        description = text(DESCRIPTIONS.get(value, tr('Die Farben deines KDE-Desktops.')))
        page.addWidget(description)
        self.appearance.buttonClicked.connect(lambda selected: description.setText(DESCRIPTIONS.get(selected.property('design'), tr('Die Farben deines KDE-Desktops.'))))
        def save():
            try:
                design = self.appearance.checkedButton().property('design')
                self.save(self.assistant, {'appearance': design})
                apply_design(QApplication.instance(), design)
                self.status.setText(tr('App-Design übernommen. Leisten und Fenster werden angepasst …'))
                self.perform('appearance', {'design': design}, lambda result: self.status.setText(
                    tr('Design übernommen — inklusive Leisten, Panels und Fensterdekoration.') if result.get('desktop')
                    else tr('App-Design übernommen. Der gewählte Plasma-Stil bleibt erhalten.')))
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
        self.apply_appearance = button(tr('Design übernehmen'), save); self.apply_appearance.setObjectName('primary')
        page.addWidget(self.apply_appearance, 0, Qt.AlignLeft)
        reading = QFormLayout()
        self.text_size = QSpinBox(); self.text_size.setRange(14, 22); self.text_size.setSuffix(' px')
        self.text_size.setValue(self.field(self.assistant, 'textSize', 17))
        reading.addRow(tr('Schriftgröße · Lumen und Suche'), self.text_size)
        self.content_density = combo([(tr('Komfortabel'), 'comfortable'), (tr('Kompakt'), 'compact')],
            self.field(self.assistant, 'contentDensity', 'comfortable'))
        reading.addRow(tr('Darstellungsdichte'), self.content_density); page.addLayout(reading)
        def save_reading():
            try:
                self.save(self.assistant, dict(textSize=self.text_size.value(), contentDensity=self.content_density.currentData()))
                self.status.setText(tr('Textdarstellung übernommen.'))
            except (OSError, ValueError) as error: self.status.setText(str(error))
        page.addWidget(button(tr('Textdarstellung übernehmen'), save_reading), 0, Qt.AlignLeft)
        desktop = QWidget(); desktop.hide(); desktop_layout = QVBoxLayout(desktop)
        desktop_layout.setContentsMargins(0, 0, 0, 0)
        advanced = QPushButton(tr('KDE-Desktop anpassen …')); advanced.setObjectName('quiet'); advanced.setCheckable(True)
        desktop.settings_toggle = advanced
        advanced.toggled.connect(desktop.setVisible); page.addWidget(advanced, 0, Qt.AlignLeft)
        page.addWidget(desktop)
        self.theme_state = text(tr('Aktuelles KDE-Design wird geladen …'))
        desktop_layout.addWidget(self.theme_state)
        for title, module in [(tr('Globales Design'), 'kcm_lookandfeel'), (tr('Farben'), 'kcm_colors'),
            (tr('Plasma-Stil'), 'kcm_desktoptheme'), (tr('Symbole'), 'kcm_icons'), (tr('Mauszeiger'), 'kcm_cursortheme'),
            (tr('Schriften'), 'kcm_fonts'), (tr('Anwendungsstil'), 'kcm_style'), (tr('Fensterdekoration'), 'kcm_kwindecoration'),
            (tr('Arbeitsflächeneffekte / Blur'), 'kcm_kwin_effects'), (tr('Fensterregeln'), 'kcm_kwinrules'),
            (tr('Bildschirme & Skalierung'), 'kcm_kscreen')]:
            self.launcher(desktop_layout, title + ' …', 'kcmshell6', module)
        self.launcher(desktop_layout, tr('Kvantum-Theme & Transparenz …'), 'kvantummanager')
        self.launcher(desktop_layout, tr('Hintergrundbild & Desktop bearbeiten …'), 'qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.editMode', 'true')
        page.addStretch()

    def build_panels(self):
        page = self.page(tr('Leisten & Systemablage'), tr('Jede Leiste einzeln einstellen'))
        self.panel_list = QComboBox()
        self.panel_list.setAccessibleName(tr('Leiste nach Bildschirm und Position auswählen'))
        self.panel_list.currentIndexChanged.connect(self.select_panel)
        page.addWidget(self.panel_list)
        form = QFormLayout()
        self.position = combo([(tr('Oben'), 'top'), (tr('Unten'), 'bottom'), (tr('Links'), 'left'), (tr('Rechts'), 'right')], 'top')
        form.addRow(tr('Position'), self.position)
        self.height = QSpinBox()
        self.height.setRange(20, 160)
        self.height.setSuffix(' px')
        form.addRow(tr('Leistengröße'), self.height)
        self.floating = QCheckBox(tr('Schwebende Leiste'))
        form.addRow(tr('Darstellung'), self.floating)
        self.hiding = combo([(tr('Immer sichtbar'), 'none'), (tr('Automatisch ausblenden'), 'autohide'),
                            (tr('Fenstern ausweichen'), 'dodgewindows'), (tr('Fenster dürfen verdecken'), 'windowsgobelow')], 'none')
        form.addRow(tr('Sichtbarkeit'), self.hiding)
        page.addLayout(form)
        self.panel_apply = button(tr('Diese Leiste übernehmen'), self.save_panel)
        self.panel_apply.setEnabled(False)
        page.addWidget(self.panel_apply)
        self.widgets = QComboBox()
        self.widgets.setAccessibleName(tr('Element der ausgewählten Leiste'))
        page.addWidget(self.widgets)
        self.widget_button = button(tr('Element / Systemablage konfigurieren …'), self.configure_widget)
        self.widget_button.setEnabled(False)
        page.addWidget(self.widget_button)
        self.launcher(page, tr('Leisten und Widgets auf dem Desktop bearbeiten …'), 'qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.editMode', 'true')
        page.addWidget(text(tr('Der native Editor des Elements bietet dessen vollständige Optionen — etwa sichtbare Tray-Symbole, Uhr, CPU/RAM-Anzeige, Startmenü oder Taskleiste.')))
        page.addStretch()

    def select_panel(self, _index):
        panel = self.panel_list.currentData()
        self.panel_apply.setEnabled(bool(panel))
        self.widget_button.setEnabled(bool(panel and panel.get('widgets')))
        self.widgets.clear()
        if not panel:
            return
        self.position.setCurrentIndex(self.position.findData(panel['location']))
        self.height.setRange(min(20, panel['height']), max(160, panel['height']))
        self.height.setValue(panel['height'])
        self.floating.setChecked(panel['floating'])
        self.hiding.setCurrentIndex(self.hiding.findData(panel['hiding']))
        names = {'systemtray': tr('Systemablage'), 'systemmonitor': tr('Systemmonitor'), 'icontasks': tr('Taskleiste'),
                 'kickerdash': tr('Startmenü'), 'digitalclock': tr('Uhr'), 'appmenu': tr('Anwendungsmenü')}
        for widget in panel['widgets']:
            kind = widget['type'].split('.')[-1]
            self.widgets.addItem(f'{names.get(kind, kind)} · {widget["id"]}', widget['id'])

    def save_panel(self):
        panel = self.panel_list.currentData()
        if panel:
            values = {'location': self.position.currentData(), 'height': self.height.value(),
                      'floating': self.floating.isChecked(), 'hiding': self.hiding.currentData()}
            self.perform('panel', {'id': panel['id'], 'before': panel,
                'changes': {key: value for key, value in values.items() if value != panel[key]}}, self.reload)

    def configure_widget(self):
        panel = self.panel_list.currentData()
        if panel and self.widgets.currentData() is not None:
            self.perform('widget', {'panel': panel['id'], 'widget': self.widgets.currentData()})

    def build_integrations(self):
        page = self.page(tr('Integrationen'), tr('Vorhandene Funktionen und Systemanpassungen'))
        for title, module in [(tr('KRunner & Suchmodule'), 'kcm_plasmasearch'), (tr('Autostart / Lumen-Runner'), 'kcm_autostart'),
            (tr('Standardprogramme & Dateimanager'), 'kcm_componentchooser'), (tr('Netzwerkverbindungen'), 'kcm_networkmanagement'),
            (tr('Benachrichtigungen'), 'kcm_notifications')]:
            self.launcher(page, title + ' …', 'kcmshell6', module)
        self.launcher(page, tr('Systemmonitor öffnen …'), 'plasma-systemmonitor')
        page.addWidget(text(tr('Lumen nutzt die vorhandene Engine-Konfiguration einschließlich Provider, MCP-Werkzeugen und persönlichen Anweisungen. '
            'Zugangsdaten werden hier weder angezeigt noch überschrieben.\n'
            'Dateiaktionen sind über Lumen Files und die installierten Dolphin-Kontextmenüs erreichbar. '
            'Galerie, Speicheranalyse, Inhaltsuche sowie Umbenennen und Sortieren arbeiten in ihren nativen Dialogen.')))
        references = [(tr('Systemreferenz'), Path.home() / 'Documents/work/system.md'),
                      (tr('Änderungshistorie'), Path.home() / 'Documents/work/sync.md'),
                      (tr('Desktop-Anpassungen & Rückwege'), Path.home() / 'Documents/work/lumen-kde/README.md')]
        for title, path in references:
            if path.exists():
                page.addWidget(button(tr('{0} öffnen …', title), lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))))
        page.addStretch()

    @staticmethod
    def clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                SettingsDialog.clear(item.layout())

    def reload(self, _result=None):
        if self.job:
            return
        self.perform('snapshot', {}, self.loaded)

    def loaded(self, data):
        if not isinstance(data, dict):
            self.status.setText(tr('Der Systemzustand konnte nicht gelesen werden.'))
            return
        self.desktop = data
        self.clear(self.shortcut_rows)
        for component, title in SHORTCUTS.items():
            row = QHBoxLayout()
            row.addWidget(text(title), 1)
            keys = data.get('shortcuts', {}).get(component)
            edit = QKeySequenceEdit(QKeySequence(keys[0]) if keys else QKeySequence())
            edit.setAccessibleName(title)
            edit.setEnabled(keys is not None)
            row.addWidget(edit)
            def save(_=False, c=component, e=edit, before=keys):
                sequence = e.keySequence()
                if sequence.count() > 1:
                    self.status.setText(tr('Bitte eine einzelne Tastenkombination verwenden.'))
                    return
                self.perform('shortcut', {'component': c, 'before': before, 'key': sequence[0] if sequence.count() else 0}, self.reload)
            apply = button(tr('Übernehmen'), save)
            apply.setEnabled(keys is not None)
            row.addWidget(apply)
            self.shortcut_rows.addLayout(row)
        theme_labels = {'Plasma-Stil': tr('Plasma-Stil'), 'Farbschema': tr('Farbschema'),
                        'Symbole': tr('Symbole'), 'Anwendungsstil': tr('Anwendungsstil'), 'Kvantum': 'Kvantum'}
        self.theme_state.setText('\n'.join(f'{theme_labels.get(key, key)}: {value}' for key, value in data.get('themes', {}).items()) or tr('Design nicht verfügbar.'))
        selected = (self.panel_list.currentData() or {}).get('id')
        self.panel_list.clear()
        for panel in data.get('panels', []):
            location = {'top': tr('Oben'), 'bottom': tr('Unten'), 'left': tr('Links'), 'right': tr('Rechts')}.get(panel['location'], panel['location'])
            self.panel_list.addItem(tr('Bildschirm {0} · {1} · Leiste {2}', panel["screen"] + 1, location, panel["id"]), panel)
            if panel['id'] == selected:
                self.panel_list.setCurrentIndex(self.panel_list.count() - 1)
        self.clear(self.service_rows)
        for service in data.get('services', []):
            self.service_row(service, data.get('analysis', {}))
        errors = [str(value) for key, value in data.items() if key.endswith('_error')]
        self.status.setText(tr('Nicht vollständig verfügbar: ') + ' · '.join(errors) if errors else tr('Aktueller Systemzustand geladen.'))

    def service_row(self, service, analysis):
        unit, scope = service['unit'], service['scope']
        active = service.get('ActiveState') == 'active'
        enabled = service.get('UnitFileState') in ('enabled', 'enabled-runtime')
        switch_off = enabled if unit == 'lumen-agentd.service' else active or enabled
        row = QHBoxLayout()
        row.addWidget(text(f'{service["title"]}\n{tr("Aktiv") if active else tr("Inaktiv")} · {tr("Autostart an") if enabled else tr("Autostart aus")}'), 1)
        title = (tr('Autostart aus') if enabled else tr('Autostart ein')) if unit == 'lumen-agentd.service' else (tr('Ausschalten') if switch_off else tr('Einschalten'))
        item = button(title, lambda: self.perform('service', {'scope': scope, 'unit': unit, 'enabled': not switch_off}, self.reload))
        item.setEnabled(service.get('LoadState') == 'loaded' and service.get('UnitFileState') != 'static')
        item.setToolTip(unit)
        row.addWidget(item)
        self.service_rows.addLayout(row)
        if unit == 'lumen-agentd.service':
            self.service_rows.addWidget(text(tr('Die Systemintegration kann bei einer Lumen-Systemaktion auch bei ausgeschaltetem Autostart bedarfsweise starten.')))
        if unit in ('lumen-digest.timer', 'lumen-nightly.timer'):
            schedule = QHBoxLayout()
            clock = QTimeEdit()
            clock.setDisplayFormat('HH:mm')
            clock.setAccessibleName(service['title'] + tr(' Uhrzeit'))
            expression = service.get('TimersCalendar', '')
            match = re.search(r'\*-\*-\* (\d\d:\d\d):00', expression)
            clock.setTime(QTime.fromString(match[1], 'HH:mm') if match else QTime(8 if 'digest' in unit else 3, 0 if 'digest' in unit else 30))
            schedule.addWidget(text(tr('Täglich um') if match else tr('Neuer täglicher Zeitplan (ersetzt aktuellen)')))
            schedule.addWidget(clock)
            schedule.addWidget(button(tr('Zeit übernehmen'), lambda _=False, c=clock: self.perform('schedule', {'unit': unit, 'time': c.time().toString('HH:mm')}, self.reload)))
            self.service_rows.addLayout(schedule)
        report_unit = unit.replace('.timer', '.service').replace('.path', '.service')
        if report_unit in analysis:
            check = QCheckBox(tr('Bericht automatisch mit Lumen analysieren'))
            check.setChecked(analysis[report_unit])
            row = QHBoxLayout()
            row.addWidget(check, 1)
            row.addWidget(button(tr('Übernehmen'), lambda: self.perform('analysis', {'unit': report_unit, 'enabled': check.isChecked()}, self.reload)))
            self.service_rows.addLayout(row)

    def perform(self, action, data, callback=None):
        if self.job:
            return
        self.stack.setEnabled(False)
        self.status.setText(tr('Systemzustand wird geladen …') if action == 'snapshot' else tr('Änderung wird übernommen …'))
        job = worker_process(self)
        self.job = job
        timer = QTimer(job)
        timer.setSingleShot(True)
        timed_out = False
        def timeout():
            nonlocal timed_out
            timed_out = True
            job.kill()
        timer.timeout.connect(timeout)
        def done(code):
            if self.job is not job:
                return
            timer.stop()
            self.job = None
            output = bytes(job.readAllStandardOutput()).decode(errors='replace')
            error = bytes(job.readAllStandardError()).decode(errors='replace')
            job.deleteLater()
            self.stack.setEnabled(True)
            if code:
                self.status.setText(tr('Zeitüberschreitung. Bitte Systemzustand neu laden.') if timed_out else (error.strip() or tr('Systemfunktion konnte nicht gestartet werden.')))
                return
            try:
                result = json.loads(output)
            except ValueError:
                self.status.setText(tr('Ungültige Antwort der Systemfunktion. Bitte neu laden.'))
                return
            self.status.setText(tr('Übernommen.') if action != 'snapshot' else tr('Aktualisiert.'))
            if callback:
                callback(result)
        job.finished.connect(lambda code, _status: done(code))
        job.errorOccurred.connect(lambda error: done(-1) if error == QProcess.FailedToStart else None)
        job.start(sys.executable, [str(Path(__file__).with_name('desktop_settings.py')), action])
        job.write(json.dumps(data).encode())
        job.closeWriteChannel()
        timer.start(100000 if action == 'service' and data.get('scope') == 'system' else 60000)

    def done(self, result):
        if self.job:
            self.status.setText(tr('Bitte die laufende Systemaktion abwarten.'))
            return
        if self.engine:
            self.engine.shutdown()
        super().done(result)


if __name__ == '__main__':
    if '--hardware' in sys.argv:
        from lumen_launch import executable
        import subprocess
        sys.exit(subprocess.call([executable('lumen-system')]))
    from app import create_app
    from PySide6.QtGui import QIcon
    app = create_app()
    app.setApplicationName('lumen-settings'); app.setApplicationDisplayName(tr('Lumen Einstellungen'))
    dialog = SettingsDialog(page=3 if '--appearance' in sys.argv else None); dialog.setWindowIcon(QIcon.fromTheme('configure'))
    if '--system-settings' in sys.argv: dialog.open_page(dialog.hardware_page)
    if '--personality' in sys.argv: dialog.open_page(dialog.persona_page)
    dialog.show()
    sys.exit(app.exec())
