"""Shared native settings for Lumen, Files and their desktop integrations."""
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PyQt5.QtCore import QProcess, QSettings, Qt, QTimer, QTime, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem,
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
    item.clicked.connect(callback)
    return item


def combo(items, value):
    item = QComboBox()
    for title, data in items:
        item.addItem(title, data)
    item.setCurrentIndex(max(0, item.findData(value)))
    return item


class SettingsDialog(QDialog):
    preferencesChanged = pyqtSignal(str, list)

    def __init__(self, parent=None, files_settings=None, assistant_settings=None, page=0, load_system=True):
        super().__init__(parent)
        self.setWindowTitle('Einstellungen — Lumen & Files')
        self.resize(1000, 760)
        self.setMinimumSize(800, 580)
        self.assistant = assistant_settings if assistant_settings is not None else QSettings('Lumen', 'Assistant')
        self.files = files_settings if files_settings is not None else QSettings('Lumen', 'Files')
        self.job = None
        self.engine = None
        self.desktop = {}
        self.original = {}
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setAccessibleName('Einstellungsbereiche')
        self.nav.setFixedWidth(205)
        self.nav.setSpacing(5)
        self.stack = QStackedWidget()
        row.addWidget(self.nav)
        row.addWidget(self.stack, 1)
        root.addLayout(row, 1)
        self.status = text('Änderungen mit „Übernehmen“ speichern. Systemdialoge übernehmen ihre eigenen Einstellungen.')
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        bottom.addWidget(button('Systemzustand neu laden', self.reload))
        bottom.addStretch()
        bottom.addWidget(button('Schließen', self.reject))
        root.addLayout(bottom)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.build_lumen()
        self.build_files()
        self.shortcut_page = self.page('Tastenkürzel', 'Lumen überall aufrufen')
        self.shortcut_rows = QVBoxLayout()
        self.shortcut_page.addLayout(self.shortcut_rows)
        self.launcher(self.shortcut_page, 'Alle globalen Tastenkürzel …', 'kcmshell6', 'kcm_keys')
        self.shortcut_page.addWidget(text('Files: Strg+F Suche · Strg+L Pfad · Strg+K Server · Strg+T/W Tab öffnen/schließen\n'
            'Alt+Links/Rechts oder Maustasten 4/5: Verlauf · Alt+Hoch: übergeordneter Ordner\n'
            'Leertaste: große Vorschau · F2: umbenennen · Entf: Papierkorb · Strg+J: Lumen\n'
            'Strg+Umschalt+F: Inhalte suchen · Strg+Komma: Einstellungen\n'
            'Galerie: Links/Rechts blättern · R/Umschalt+R drehen · H spiegeln · Strg+Z rückgängig · Strg+S speichern · F11 Vollbild'))
        self.shortcut_page.addStretch()
        self.build_appearance()
        self.build_panels()
        self.service_page = self.page('Dienste & Berichte', 'Automatisch im Hintergrund')
        self.service_page.addWidget(text('Systemdienste verwenden bei Bedarf die KDE-Passwortabfrage. Berichtszeiten gelten in deiner lokalen Zeitzone.'))
        self.service_rows = QVBoxLayout()
        self.service_page.addLayout(self.service_rows)
        self.service_page.addStretch()
        self.build_integrations()
        self.nav.setCurrentRow(page)
        if load_system:
            QTimer.singleShot(0, self.reload)

    def page(self, title, subtitle):
        self.nav.addItem(title)
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
        settings.sync()
        changes = {}
        for key, value in values.items():
            before = self.original.get((settings.fileName(), key))
            if value != before:
                current = settings.value(key, before, type=type(before))
                if current != before and current != value:
                    raise ValueError('Diese Einstellung wurde in einem anderen Fenster geändert. Bitte die Einstellungen erneut öffnen.')
                changes[key] = value
        for key, value in changes.items():
            settings.setValue(key, value)
        settings.sync()
        if settings.status() != QSettings.NoError:
            raise OSError('Einstellungen konnten nicht gespeichert werden.')
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
        row.addWidget(button('Wählen …', choose))
        form.addRow(title, row)
        return edit

    def build_lumen(self):
        page = self.page('Lumen', 'Vorgaben für neue Gespräche und Fenster')
        form = QFormLayout()
        self.workdir = self.folder_field(form, 'Arbeitsordner', self.assistant, 'workdir', str(Path.home() / 'Documents/work'))
        self.mode = combo([('Aufgaben erledigen', 'build'), ('Lesen & prüfen', 'plan')], self.field(self.assistant, 'defaultMode', 'build'))
        form.addRow('Arbeitsweise', self.mode)
        self.language = QLineEdit(self.field(self.assistant, 'translationLanguage', 'Deutsch'))
        form.addRow('Übersetzen nach', self.language)
        self.model = combo([('Vorgabe der Engine', '')], '')
        self.model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.model.setMinimumContentsLength(18)
        current = self.field(self.assistant, 'model', '')
        if current:
            self.model.addItem(current, current)
            self.model.setCurrentIndex(1)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model, 1)
        self.model_button = button('Modelle laden', self.load_models)
        model_row.addWidget(self.model_button)
        form.addRow('Modell', model_row)
        self.auto = QCheckBox('Nicht mehr nachfragen')
        self.auto.setChecked(self.field(self.assistant, 'autoApproveTools', False, bool))
        self.auto.setToolTip('Erlaubt Werkzeugaufrufe einschließlich Befehlen und Dateiänderungen. Inhaltliche Rückfragen bleiben sichtbar.')
        form.addRow('Werkzeugfreigaben', self.auto)
        page.addLayout(form)
        page.addWidget(text('Die Modellwahl gilt für Lumen und die intelligenten Dateiaktionen. Provider und Zugangsdaten werden aus deiner bestehenden Engine-Konfiguration geladen.\n'
                            '„Nicht mehr nachfragen“ erlaubt auch Befehle und Dateiänderungen. Vorschläge zum Umbenennen und Sortieren bleiben ausdrücklich bestätigungspflichtig.'))
        page.addWidget(button('Lumen-Einstellungen übernehmen', self.save_lumen))
        page.addStretch()

    def save_lumen(self):
        try:
            directory = Path(self.workdir.text()).expanduser()
            if not directory.is_dir() or not os.access(directory, os.R_OK | os.X_OK):
                raise ValueError('Bitte einen erreichbaren Arbeitsordner wählen.')
            language = self.language.text().strip()
            if not language or len(language) > 80:
                raise ValueError('Bitte eine Übersetzungssprache eingeben (maximal 80 Zeichen).')
            self.save(self.assistant, {'workdir': str(directory.resolve()), 'defaultMode': self.mode.currentData(),
                'translationLanguage': language, 'model': self.model.currentData(), 'autoApproveTools': self.auto.isChecked()})
            self.status.setText('Lumen-Einstellungen gespeichert. Startordner und Arbeitsweise gelten für neue Fenster/Gespräche.')
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def load_models(self):
        self.model_button.setEnabled(False)
        self.status.setText('Eingerichtete Modelle werden geladen …')
        if self.engine is None:
            self.engine = OpenCodeBackend(str(Path.home()), self, project_config=False)
            self.engine.failed.connect(self.models_failed)
        def loaded(data):
            selected = self.model.currentData()
            try:
                models = sorted({(p['id'] + '/' + key, model.get('name', key))
                                 for p in data['providers'] for key, model in p['models'].items()})
            except (AttributeError, KeyError, TypeError, ValueError):
                self.models_failed('Die Engine hat eine ungültige Modellliste geliefert.')
                return
            self.model.clear()
            self.model.addItem('Vorgabe der Engine', '')
            for identifier, name in models:
                self.model.addItem(f'{name}  ·  {identifier}', identifier)
            if selected and self.model.findData(selected) < 0:
                self.model.addItem(selected, selected)
            self.model.setCurrentIndex(max(0, self.model.findData(selected)))
            self.model_button.setEnabled(True)
            self.status.setText(f'{len(models)} Modelle geladen. Änderungen mit „Übernehmen“ speichern.')
        self.engine.ensure_server(lambda: self.engine.request('GET', '/config/providers', callback=loaded, error=self.models_failed))

    def models_failed(self, error):
        self.model_button.setEnabled(True)
        self.status.setText('Modelle konnten nicht geladen werden: ' + error)

    def build_files(self):
        page = self.page('Lumen Files', 'Navigation, Vorschau und schnelle Suche')
        form = QFormLayout()
        self.resume = QCheckBox('Geöffnete Tabs wiederherstellen')
        self.resume.setChecked(self.field(self.files, 'restoreLastFolder', True, bool))
        form.addRow('Beim Start', self.resume)
        self.startdir = self.folder_field(form, 'Startordner', self.files, 'startFolder', str(Path.home()))
        self.startdir.setEnabled(not self.resume.isChecked())
        self.resume.toggled.connect(lambda value: self.startdir.setEnabled(not value))
        self.hidden = QCheckBox('Versteckte Dateien anzeigen')
        self.hidden.setChecked(self.field(self.files, 'hidden', False, bool))
        form.addRow('Dateien', self.hidden)
        self.preview = QCheckBox('Vorschauleiste anzeigen')
        self.preview.setChecked(self.field(self.files, 'previewVisible', True, bool))
        form.addRow('Vorschau', self.preview)
        self.delay = QSpinBox()
        self.delay.setRange(100, 1500)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(' ms')
        self.delay.setValue(self.field(self.files, 'searchDelay', 250, int))
        form.addRow('Suche nach Tipp-Pause', self.delay)
        self.limit = QSpinBox()
        self.limit.setRange(100, 50000)
        self.limit.setSingleStep(500)
        self.limit.setValue(self.field(self.files, 'searchLimit', 5000, int))
        form.addRow('Max. Dateinamen-Treffer', self.limit)
        page.addLayout(form)
        page.addWidget(text('Gespeicherte Orte & Server — Entfernen löscht nur den Eintrag, keine Dateien oder Zugangsdaten.'))
        self.places = QListWidget()
        self.places.setAccessibleName('Gespeicherte Orte und Server')
        self.places.setMaximumHeight(120)
        for key in ('favorites', 'network_servers'):
            for value in self.field(self.files, key, [], list):
                item = QListWidgetItem(str(value))
                item.setData(Qt.UserRole, key)
                self.places.addItem(item)
        page.addWidget(self.places)
        page.addWidget(button('Ausgewählten Eintrag entfernen', lambda: self.places.takeItem(self.places.currentRow()) if self.places.currentRow() >= 0 else None))
        page.addWidget(button('Files-Einstellungen übernehmen', self.save_files))
        page.addWidget(text('Neue Server: Strg+K in Files (SMB, SFTP, WebDAV, NFS).\n'
            'Bilder bearbeiten: Leertaste auf einem Bild. Originale werden vor dem Speichern gesichert.\n'
            'Speicheranalyse: Menü ••• → Speicher analysieren. Umbenennen/Sortieren: Auswahl → Kontextmenü.'))
        page.addStretch()

    def save_files(self):
        try:
            folder = Path(self.startdir.text()).expanduser()
            if not self.resume.isChecked() and (not folder.is_dir() or not os.access(folder, os.R_OK | os.X_OK)):
                raise ValueError('Bitte einen erreichbaren Startordner wählen.')
            values = {'restoreLastFolder': self.resume.isChecked(), 'startFolder': str(folder),
                'hidden': self.hidden.isChecked(), 'previewVisible': self.preview.isChecked(),
                'searchDelay': self.delay.value(), 'searchLimit': self.limit.value()}
            for key in ('favorites', 'network_servers'):
                values[key] = [self.places.item(i).text() for i in range(self.places.count()) if self.places.item(i).data(Qt.UserRole) == key]
            self.save(self.files, values)
            self.status.setText('Files-Einstellungen gespeichert. Der Startordner gilt ab dem nächsten Fenster.')
        except (ValueError, OSError) as error:
            self.status.setText(str(error))

    def launcher(self, layout, title, program, *args):
        item = button(title, lambda: self.launch(program, list(args)))
        if not shutil.which(program):
            item.setEnabled(False)
            item.setToolTip(program + ' ist nicht installiert.')
        layout.addWidget(item)

    def launch(self, program, arguments):
        okay, _pid = QProcess.startDetached(program, arguments, str(Path.home()))
        self.status.setText('Nativer Einstellungsdialog geöffnet.' if okay else 'Der Einstellungsdialog konnte nicht geöffnet werden.')

    def build_appearance(self):
        page = self.page('Erscheinungsbild', 'Lumen und dein KDE-Desktop')
        page.addWidget(text('Lumen Files folgt automatisch den KDE-Farben, Symbolen und der Systemschrift.'))
        page.addWidget(text('Darstellung des Lumen-Assistenten:'))
        self.appearance = combo([('Lumen Dunkel', 'lumen'), ('Systemstil', 'system')], self.field(self.assistant, 'appearance', 'lumen'))
        page.addWidget(self.appearance)
        def save():
            try:
                self.save(self.assistant, {'appearance': self.appearance.currentData()})
                self.status.setText('Darstellung gespeichert. Sie gilt für neu gestartete Lumen-Fenster. Files folgt dem System.')
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
        page.addWidget(button('Lumen-Darstellung übernehmen', save))
        self.theme_state = text('Aktuelles KDE-Design wird geladen …')
        page.addWidget(self.theme_state)
        for title, module in [('Globales Design', 'kcm_lookandfeel'), ('Farben', 'kcm_colors'),
            ('Plasma-Stil', 'kcm_desktoptheme'), ('Symbole', 'kcm_icons'), ('Mauszeiger', 'kcm_cursortheme'),
            ('Schriften', 'kcm_fonts'), ('Anwendungsstil', 'kcm_style'), ('Fensterdekoration', 'kcm_kwindecoration'),
            ('Arbeitsflächeneffekte / Blur', 'kcm_kwin_effects'), ('Fensterregeln', 'kcm_kwinrules'),
            ('Bildschirme & Skalierung', 'kcm_kscreen')]:
            self.launcher(page, title + ' …', 'kcmshell6', module)
        self.launcher(page, 'Kvantum-Theme & Transparenz …', 'kvantummanager')
        self.launcher(page, 'Hintergrundbild & Desktop bearbeiten …', 'qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.editMode', 'true')
        page.addStretch()

    def build_panels(self):
        page = self.page('Leisten & Systemablage', 'Jede Leiste einzeln einstellen')
        self.panel_list = QComboBox()
        self.panel_list.setAccessibleName('Leiste nach Bildschirm und Position auswählen')
        self.panel_list.currentIndexChanged.connect(self.select_panel)
        page.addWidget(self.panel_list)
        form = QFormLayout()
        self.position = combo([('Oben', 'top'), ('Unten', 'bottom'), ('Links', 'left'), ('Rechts', 'right')], 'top')
        form.addRow('Position', self.position)
        self.height = QSpinBox()
        self.height.setRange(20, 160)
        self.height.setSuffix(' px')
        form.addRow('Leistengröße', self.height)
        self.floating = QCheckBox('Schwebende Leiste')
        form.addRow('Darstellung', self.floating)
        self.hiding = combo([('Immer sichtbar', 'none'), ('Automatisch ausblenden', 'autohide'),
                            ('Fenstern ausweichen', 'dodgewindows'), ('Fenster dürfen verdecken', 'windowsgobelow')], 'none')
        form.addRow('Sichtbarkeit', self.hiding)
        page.addLayout(form)
        self.panel_apply = button('Diese Leiste übernehmen', self.save_panel)
        self.panel_apply.setEnabled(False)
        page.addWidget(self.panel_apply)
        self.widgets = QComboBox()
        self.widgets.setAccessibleName('Element der ausgewählten Leiste')
        page.addWidget(self.widgets)
        self.widget_button = button('Element / Systemablage konfigurieren …', self.configure_widget)
        self.widget_button.setEnabled(False)
        page.addWidget(self.widget_button)
        self.launcher(page, 'Leisten und Widgets auf dem Desktop bearbeiten …', 'qdbus6', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.editMode', 'true')
        page.addWidget(text('Der native Editor des Elements bietet dessen vollständige Optionen — etwa sichtbare Tray-Symbole, Uhr, CPU/RAM-Anzeige, Startmenü oder Taskleiste.'))
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
        names = {'systemtray': 'Systemablage', 'systemmonitor': 'Systemmonitor', 'icontasks': 'Taskleiste',
                 'kickerdash': 'Startmenü', 'digitalclock': 'Uhr', 'appmenu': 'Anwendungsmenü'}
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
        page = self.page('Integrationen', 'Vorhandene Funktionen und Systemanpassungen')
        for title, module in [('KRunner & Suchmodule', 'kcm_plasmasearch'), ('Autostart / Lumen-Runner', 'kcm_autostart'),
            ('Standardprogramme & Dateimanager', 'kcm_componentchooser'), ('Netzwerkverbindungen', 'kcm_networkmanagement'),
            ('Benachrichtigungen', 'kcm_notifications')]:
            self.launcher(page, title + ' …', 'kcmshell6', module)
        self.launcher(page, 'Systemmonitor öffnen …', 'plasma-systemmonitor')
        page.addWidget(text('Lumen nutzt die vorhandene Engine-Konfiguration einschließlich Provider, MCP-Werkzeugen und persönlichen Anweisungen. '
            'Zugangsdaten werden hier weder angezeigt noch überschrieben.\n'
            'Dateiaktionen sind über Lumen Files und die installierten Dolphin-Kontextmenüs erreichbar. '
            'Galerie, Speicheranalyse, Inhaltsuche sowie Umbenennen und Sortieren arbeiten in ihren nativen Dialogen.'))
        references = [('Systemreferenz', Path.home() / 'Documents/work/system.md'),
                      ('Änderungshistorie', Path.home() / 'Documents/work/sync.md'),
                      ('Desktop-Anpassungen & Rückwege', Path.home() / 'Documents/work/lumen-kde/README.md')]
        for title, path in references:
            if path.exists():
                page.addWidget(button(title + ' öffnen …', lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))))
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
            self.status.setText('Der Systemzustand konnte nicht gelesen werden.')
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
                    self.status.setText('Bitte eine einzelne Tastenkombination verwenden.')
                    return
                self.perform('shortcut', {'component': c, 'before': before, 'key': sequence[0] if sequence.count() else 0}, self.reload)
            apply = button('Übernehmen', save)
            apply.setEnabled(keys is not None)
            row.addWidget(apply)
            self.shortcut_rows.addLayout(row)
        self.theme_state.setText('\n'.join(f'{key}: {value}' for key, value in data.get('themes', {}).items()) or 'Design nicht verfügbar.')
        selected = (self.panel_list.currentData() or {}).get('id')
        self.panel_list.clear()
        for panel in data.get('panels', []):
            location = {'top': 'Oben', 'bottom': 'Unten', 'left': 'Links', 'right': 'Rechts'}.get(panel['location'], panel['location'])
            self.panel_list.addItem(f'Bildschirm {panel["screen"] + 1} · {location} · Leiste {panel["id"]}', panel)
            if panel['id'] == selected:
                self.panel_list.setCurrentIndex(self.panel_list.count() - 1)
        self.clear(self.service_rows)
        for service in data.get('services', []):
            self.service_row(service, data.get('analysis', {}))
        errors = [str(value) for key, value in data.items() if key.endswith('_error')]
        self.status.setText('Nicht vollständig verfügbar: ' + ' · '.join(errors) if errors else 'Aktueller Systemzustand geladen.')

    def service_row(self, service, analysis):
        unit, scope = service['unit'], service['scope']
        active = service.get('ActiveState') == 'active'
        enabled = service.get('UnitFileState') in ('enabled', 'enabled-runtime')
        switch_off = enabled if unit == 'lumen-agentd.service' else active or enabled
        row = QHBoxLayout()
        row.addWidget(text(f'{service["title"]}\n{"Aktiv" if active else "Inaktiv"} · {"Autostart an" if enabled else "Autostart aus"}'), 1)
        title = ('Autostart aus' if enabled else 'Autostart ein') if unit == 'lumen-agentd.service' else ('Ausschalten' if switch_off else 'Einschalten')
        item = button(title, lambda: self.perform('service', {'scope': scope, 'unit': unit, 'enabled': not switch_off}, self.reload))
        item.setEnabled(service.get('LoadState') == 'loaded' and service.get('UnitFileState') != 'static')
        item.setToolTip(unit)
        row.addWidget(item)
        self.service_rows.addLayout(row)
        if unit == 'lumen-agentd.service':
            self.service_rows.addWidget(text('Die Systemintegration kann bei einer Lumen-Systemaktion auch bei ausgeschaltetem Autostart bedarfsweise starten.'))
        if unit in ('lumen-digest.timer', 'lumen-nightly.timer'):
            schedule = QHBoxLayout()
            clock = QTimeEdit()
            clock.setDisplayFormat('HH:mm')
            clock.setAccessibleName(service['title'] + ' Uhrzeit')
            expression = service.get('TimersCalendar', '')
            match = re.search(r'\*-\*-\* (\d\d:\d\d):00', expression)
            clock.setTime(QTime.fromString(match[1], 'HH:mm') if match else QTime(8 if 'digest' in unit else 3, 0 if 'digest' in unit else 30))
            schedule.addWidget(text('Täglich um' if match else 'Neuer täglicher Zeitplan (ersetzt aktuellen)'))
            schedule.addWidget(clock)
            schedule.addWidget(button('Zeit übernehmen', lambda _=False, c=clock: self.perform('schedule', {'unit': unit, 'time': c.time().toString('HH:mm')}, self.reload)))
            self.service_rows.addLayout(schedule)
        report_unit = unit.replace('.timer', '.service').replace('.path', '.service')
        if report_unit in analysis:
            check = QCheckBox('Bericht automatisch mit Lumen analysieren')
            check.setChecked(analysis[report_unit])
            row = QHBoxLayout()
            row.addWidget(check, 1)
            row.addWidget(button('Übernehmen', lambda: self.perform('analysis', {'unit': report_unit, 'enabled': check.isChecked()}, self.reload)))
            self.service_rows.addLayout(row)

    def perform(self, action, data, callback=None):
        if self.job:
            return
        self.stack.setEnabled(False)
        self.status.setText('Systemzustand wird geladen …' if action == 'snapshot' else 'Änderung wird übernommen …')
        job = QProcess(self)
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
                self.status.setText('Zeitüberschreitung. Bitte Systemzustand neu laden.' if timed_out else (error.strip() or 'Systemfunktion konnte nicht gestartet werden.'))
                return
            try:
                result = json.loads(output)
            except ValueError:
                self.status.setText('Ungültige Antwort der Systemfunktion. Bitte neu laden.')
                return
            self.status.setText('Übernommen.' if action != 'snapshot' else 'Aktualisiert.')
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
            self.status.setText('Bitte die laufende Systemaktion abwarten.')
            return
        if self.engine:
            self.engine.shutdown()
        super().done(result)
