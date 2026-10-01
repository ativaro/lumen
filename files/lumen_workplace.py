"""Native workplace: selected context, desktop modes, transfers and guarded history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from core import size_text
from file_spaces import Catalog, LIBRARY
from lumen_store import Store
from network import ConnectDialog, Network, is_network_address, server_label
import lumen_history as history
import lumen_modes as modes
import lumen_projects as projects
import lumen_transfers as transfers


def text(value, name=''):
    item = QLabel(value); item.setTextFormat(Qt.PlainText); item.setWordWrap(True)
    if name: item.setObjectName(name)
    return item


def button(label, callback, primary=False):
    item = QPushButton(label); item.clicked.connect(callback)
    if primary: item.setObjectName('primary')
    return item


def row(layout, actions):
    box = QHBoxLayout()
    for label, callback in actions: box.addWidget(button(label, callback))
    box.addStretch(); layout.addLayout(box)


def table(headers):
    widget = QTableWidget(0, len(headers)); widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows); widget.setSelectionMode(QAbstractItemView.SingleSelection)
    widget.setShowGrid(False); widget.verticalHeader().hide(); widget.verticalHeader().setDefaultSectionSize(44)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    widget.setObjectName('workplaceTable'); widget.setAccessibleName(' · '.join(headers))
    return widget


def fill(widget, values):
    chosen = widget.item(widget.currentRow(), 0)
    identity = chosen.data(Qt.UserRole) if chosen else None
    widget.setRowCount(len(values))
    for r, (identity_value, columns) in enumerate(values):
        for c, value in enumerate(columns):
            item = QTableWidgetItem(str(value)); item.setToolTip(str(value)); widget.setItem(r, c, item)
        widget.item(r, 0).setData(Qt.UserRole, identity_value)
        if identity_value == identity: widget.selectRow(r)


def chosen(widget):
    item = widget.item(widget.currentRow(), 0)
    return item.data(Qt.UserRole) if item else None


def date(value):
    return time.strftime('%d.%m. · %H:%M', time.localtime(value))


class ProjectDialog(QDialog):
    def __init__(self, store, project, parent):
        super().__init__(parent)
        self.store, self.project, self.saved = store, project, None
        self.setWindowTitle('Projekt bearbeiten' if project else 'Neues Projekt'); self.resize(760, 620)
        value = project or {}; layout = QVBoxLayout(self); layout.setSpacing(14)
        self.name = QLineEdit(value.get('name', '')); self.name.setPlaceholderText('Zum Beispiel: Reiseplanung')
        form = QFormLayout(); form.addRow('Projektname', self.name); layout.addLayout(form)
        tabs = QTabWidget(); layout.addWidget(tabs)
        sources = QWidget(); sources_box = QVBoxLayout(sources)
        sources_box.addWidget(text('Lokale Ordner und NAS gehören zusammen. Jede Datei behält ihre Herkunft.', 'muted'))
        self.sources = table(['Bezeichnung', 'Ordner oder Netzwerkadresse'])
        self.sources.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.sources.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sources.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        sources_box.addWidget(self.sources)
        for source in value.get('sources', []): self.add_source(source['label'], source['location'])
        row(sources_box, [('Ordner …', self.local), ('Netzwerk …', self.remote), ('Entfernen', self.remove_source)])
        tabs.addTab(sources, 'Dateiquellen')
        launch = QWidget(); launch_box = QVBoxLayout(launch)
        launch_box.addWidget(text('Diese Programme und Webseiten werden nur beim Klick auf „Weiterarbeiten“ geöffnet.', 'muted'))
        self.apps = QListWidget(); self.apps.setAccessibleName('Programme beim Weiterarbeiten')
        from gi.repository import Gio
        apps = sorted([a for a in Gio.AppInfo.get_all() if a.should_show() and a.get_id()], key=lambda a: a.get_display_name().casefold())
        selected = value.get('applications', [])
        for app in apps:
            item = QListWidgetItem(QIcon.fromTheme(app.get_icon().to_string()) if app.get_icon() else QIcon(), app.get_display_name())
            item.setData(Qt.UserRole, app.get_id()); item.setCheckState(Qt.Checked if app.get_id() in selected else Qt.Unchecked)
            self.apps.addItem(item)
        launch_box.addWidget(self.apps)
        self.urls = QPlainTextEdit('\n'.join(value.get('urls', []))); self.urls.setMaximumHeight(100)
        self.urls.setPlaceholderText('Webseiten · eine HTTP(S)-Adresse pro Zeile'); self.urls.setAccessibleName('Webseiten')
        launch_box.addWidget(self.urls); tabs.addTab(launch, 'Beim Fortsetzen öffnen')
        notes = QWidget(); notes_box = QVBoxLayout(notes)
        notes_box.addWidget(text('Wo bist du stehen geblieben? Was ist der nächste Schritt?', 'muted'))
        self.note = QPlainTextEdit(value.get('note', '')); self.note.setAccessibleName('Notiz zum Weiterarbeiten')
        notes_box.addWidget(self.note); tabs.addTab(notes, 'Weiterarbeiten')
        self.error = text(''); layout.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self.save); box.rejected.connect(self.reject); layout.addWidget(box)

    def add_source(self, label, location):
        r = self.sources.rowCount(); self.sources.insertRow(r)
        self.sources.setItem(r, 0, QTableWidgetItem(label)); self.sources.setItem(r, 1, QTableWidgetItem(location))

    def local(self):
        path = QFileDialog.getExistingDirectory(self, 'Projektordner wählen')
        if path: self.add_source(Path(path).name, path)

    def remote(self):
        dialog = ConnectDialog(self)
        if dialog.exec_() == QDialog.Accepted: self.add_source(server_label(dialog.url), dialog.url)
        dialog.deleteLater()

    def remove_source(self):
        if self.sources.currentRow() >= 0: self.sources.removeRow(self.sources.currentRow())

    def save(self):
        try:
            sources = [dict(label=self.sources.item(r, 0).text(), location=self.sources.item(r, 1).text())
                       for r in range(self.sources.rowCount())]
            apps = [self.apps.item(i).data(Qt.UserRole) for i in range(self.apps.count()) if self.apps.item(i).checkState() == Qt.Checked]
            self.saved = projects.save_project(self.store, self.project, self.name.text(), sources, apps,
                [url.strip() for url in self.urls.toPlainText().splitlines() if url.strip()], self.note.toPlainText())
            self.accept()
        except (ValueError, OSError) as error: self.error.setText(str(error))


class ModeDialog(QDialog):
    def __init__(self, store, mode, devices, parent):
        super().__init__(parent); self.store, self.mode = store, mode
        self.setWindowTitle('Arbeitsmodus anpassen'); self.resize(580, 530)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.name = QLineEdit(mode['name']); form.addRow('Name', self.name)
        self.audio = QComboBox(); self.audio.addItem('Aktuelles Ausgabegerät behalten', '')
        for d in devices: self.audio.addItem(d['description'], d['name'])
        if mode['audio'] and self.audio.findData(mode['audio']) < 0: self.audio.addItem(mode['audio'] + ' (nicht verfügbar)', mode['audio'])
        self.audio.setCurrentIndex(max(0, self.audio.findData(mode['audio']))); form.addRow('Audioausgabe', self.audio)
        self.volume = QSpinBox(); self.volume.setRange(-1, 100); self.volume.setSpecialValueText('Beibehalten')
        self.volume.setSuffix(' %'); self.volume.setValue(mode['volume']); form.addRow('Lautstärke', self.volume)
        self.quiet = QComboBox()
        for name, value in [('Beibehalten', -1), ('Nicht stören beenden', 0), ('30 Minuten Ruhe', 30), ('1 Stunde Ruhe', 60), ('3 Stunden Ruhe', 180)]: self.quiet.addItem(name, value)
        self.quiet.setCurrentIndex(self.quiet.findData(mode['quiet'])); form.addRow('Benachrichtigungen', self.quiet)
        self.arrange = QComboBox()
        for name, value in [('Anordnung beibehalten', 'keep'), ('Nebeneinander je Bildschirm', 'tile'), ('Sichtbare Fenster maximieren', 'maximize')]: self.arrange.addItem(name, value)
        self.arrange.setCurrentIndex(self.arrange.findData(mode['layout'])); form.addRow('Fenster', self.arrange)
        layout.addWidget(text('Netzwerkordner verbinden · eine Adresse pro Zeile. Bestehende Verbindungen bleiben erhalten.', 'muted'))
        self.connections = QPlainTextEdit('\n'.join(mode['connections'])); self.connections.setAccessibleName('Netzwerkordner des Modus')
        layout.addWidget(self.connections)
        def add():
            dialog = ConnectDialog(self)
            if dialog.exec_() == QDialog.Accepted: self.connections.appendPlainText(dialog.url)
            dialog.deleteLater()
        layout.addWidget(button('Netzwerk hinzufügen …', add))
        self.error = text(''); layout.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self.save); box.rejected.connect(self.reject); layout.addWidget(box)

    def save(self):
        try:
            modes.save_mode(self.store, self.mode, dict(name=self.name.text(), audio=self.audio.currentData(),
                volume=self.volume.value(), quiet=self.quiet.currentData(), layout=self.arrange.currentData(),
                connections=[v.strip() for v in self.connections.toPlainText().splitlines() if v.strip()]))
            self.accept()
        except (ValueError, OSError) as error: self.error.setText(str(error))


class Workplace(QWidget):
    def __init__(self, parent=None, store=None, files_provider=None):
        super().__init__(parent)
        self.store = store or Store(); self.files_provider = files_provider
        self.jobs, self.connections = [], []
        self.generation = 0; self.busy = False; self.project = None; self.cached_rows = []
        self.setObjectName('workplace'); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 18); layout.setSpacing(16)
        layout.addWidget(text('LUMEN  /  ARBEITSPLATZ', 'eyebrow'))
        layout.addWidget(text('Hier geht es weiter.', 'workplaceHeading'))
        self.summary = text('Deine Projekte, dein System und alles, was gerade unterwegs ist.', 'muted'); layout.addWidget(self.summary)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.projects_page(); self.modes_page(); self.transfers_page(); self.history_page()
        self.status = text('', 'muted'); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_activity); self.timer.start(1500)
        self.tabs.currentChanged.connect(lambda _: self.refresh_activity())
        self.refresh_projects(); self.refresh_modes(); self.refresh_activity()

    def page(self, name):
        widget = QWidget(); widget.setObjectName('workplacePage'); box = QVBoxLayout(widget); box.setContentsMargins(4, 18, 4, 4); box.setSpacing(12)
        self.tabs.addTab(widget, name); return box

    def guard(self, fn):
        try: return fn()
        except Exception as error: self.status.setText(str(error))

    def job(self, action, data, callback, timeout=30000, mutating=False):
        proc = QProcess(self); self.jobs.append(proc)
        env = QProcessEnvironment.systemEnvironment(); env.insert('LUMEN_DATA', str(self.store.directory)); proc.setProcessEnvironment(env)
        timer = QTimer(proc); timer.setSingleShot(True); expired = []
        def kill(): expired.append(True); proc.kill()
        timer.timeout.connect(kill)
        done = []
        if mutating: self.busy = True
        def finish(code):
            if done: return
            done.append(True); timer.stop()
            if proc in self.jobs: self.jobs.remove(proc)
            if mutating: self.busy = False
            error = 'Zeitlimit erreicht. Quelle ist derzeit nicht erreichbar.' if expired else ''
            result = None
            if not error:
                try:
                    if code: raise ValueError(bytes(proc.readAllStandardError()).decode(errors='replace')[-1200:] or 'Vorgang fehlgeschlagen.')
                    result = json.loads(bytes(proc.readAllStandardOutput()))
                except Exception as e: error = str(e)
            callback(result, error); proc.deleteLater()
        proc.finished.connect(finish)
        proc.errorOccurred.connect(lambda error: finish(1) if error == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__)), action])
        proc.write(json.dumps(data).encode()); proc.closeWriteChannel(); timer.start(timeout)

    def files(self, show=False):
        if not self.files_provider: raise ValueError('Kein Dateifenster verfügbar.')
        window = self.files_provider()
        if show:
            if hasattr(window, 'lumen_host'): window.lumen_host.show_page(3)
            else: window.raise_(); window.activateWindow()
        return window

    def projects_page(self):
        box = self.page('Projekte')
        top = QHBoxLayout(); self.project_choice = QComboBox(); self.project_choice.setMinimumWidth(230)
        self.project_choice.setAccessibleName('Projekt wählen'); top.addWidget(self.project_choice, 1)
        top.addWidget(button('Neues Projekt', lambda: self.edit_project(new=True)))
        top.addWidget(button('Bearbeiten', self.edit_project)); box.addLayout(top)
        self.project_choice.currentIndexChanged.connect(self.select_project)
        card = QFrame(); card.setObjectName('workplaceCard'); card_box = QVBoxLayout(card)
        self.project_title = text('Alles an einem Ort', 'heading'); card_box.addWidget(self.project_title)
        self.note = text('Lege ein Projekt mit lokalen Ordnern, NAS-Quellen und deinen nächsten Schritten an.'); card_box.addWidget(self.note)
        actions = QHBoxLayout(); self.resume_button = button('Weiterarbeiten', self.resume, True); actions.addWidget(self.resume_button)
        self.capture_button = button('Aktuellen Stand merken', self.capture); actions.addWidget(self.capture_button)
        actions.addStretch(); card_box.addLayout(actions); box.addWidget(card)
        box.addWidget(text('DATEIQUELLEN', 'eyebrow'))
        self.sources = table(['Herkunft', 'Ort', 'Verfügbarkeit']); self.sources.setMaximumHeight(165); box.addWidget(self.sources)
        self.sources.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.sources.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        row(box, [('Quellen prüfen', self.scan), ('Quelle öffnen / verbinden', self.open_source),
                  ('Alle Dateien gemeinsam', self.combined)])
        self.recent_label = text('ZULETZT GEÄNDERT', 'eyebrow'); box.addWidget(self.recent_label)
        self.recent = table(['Datei', 'Herkunft', 'Geändert', 'Größe']); box.addWidget(self.recent, 1)
        self.sources.cellDoubleClicked.connect(lambda *_: self.open_source())
        self.recent.cellDoubleClicked.connect(self.open_recent)

    def refresh_projects(self, identity=None):
        identity = identity or self.project_choice.currentData()
        self.project_choice.blockSignals(True); self.project_choice.clear()
        for project in projects.projects(self.store): self.project_choice.addItem(project['name'], project['id'])
        index = self.project_choice.findData(identity)
        self.project_choice.setCurrentIndex(max(0, index)); self.project_choice.blockSignals(False); self.select_project()

    def select_project(self):
        self.generation += 1
        self.project = next((p for p in projects.projects(self.store) if p['id'] == self.project_choice.currentData()), None)
        for control in (self.resume_button, self.capture_button): control.setEnabled(bool(self.project))
        if not self.project:
            self.project_title.setText('Alles an einem Ort')
            self.note.setText('Lege ein Projekt mit lokalen Ordnern, NAS-Quellen und deinen nächsten Schritten an.')
            self.sources.setRowCount(0); self.recent.setRowCount(0); return
        self.project_title.setText(self.project['name'])
        self.note.setText(self.project.get('note') or 'Noch keine Notiz. Halte unter „Bearbeiten“ fest, wo du weiterarbeiten möchtest.')
        fill(self.sources, [(s['location'], [s['label'], s['location'], 'Noch nicht geprüft']) for s in self.project['sources']])
        self.cached_rows = []; self.render_recent()

    def edit_project(self, _=False, new=False):
        dialog = ProjectDialog(self.store, None if new else self.project, self)
        if dialog.exec_() == QDialog.Accepted:
            window = self.guard(lambda: self.files())
            if window and window.spaces.active_room and window.spaces.active_room['id'] == dialog.saved['id']:
                window.spaces.active_room = dialog.saved
                window.room_button.setText(dialog.saved['name'])
            self.refresh_projects(dialog.saved['id'])
        dialog.deleteLater()

    def capture(self):
        if not self.project: return
        def save():
            window = self.files()
            latest = next(p for p in projects.projects(self.store) if p['id'] == self.project['id'])
            saved = projects.save_project(self.store, latest, latest['name'], latest['sources'], latest['applications'],
                latest['urls'], latest['note'], window.spaces.capture())
            if window.spaces.active_room and window.spaces.active_room['id'] == saved['id']: window.spaces.active_room = saved
            self.refresh_projects(saved['id']); self.status.setText('Tabs, Auswahl und Lumen-Kontext gespeichert.')
        self.guard(save)

    def resume(self):
        if not self.project or self.busy: return
        def open_project():
            window = self.files()
            chat = window.spaces.chat()
            if window.file_job or (chat and (chat.backend.busy or chat.context_tools.process)):
                raise ValueError('Bitte zuerst den laufenden Vorgang abschließen.')
            project = next(p for p in projects.projects(self.store) if p['id'] == self.project['id'])
            def restored():
                self.connect_sources([s['location'] for s in project['sources'] if is_network_address(s['location'])])
                self.job('launch', project, lambda result, error: self.status.setText(error or result), mutating=True)
                for url in project.get('urls', []):
                    if not QDesktopServices.openUrl(QUrl(transfers.web_url(url))): self.status.setText('Webseite konnte nicht geöffnet werden: ' + url)
                history.record(self.store, 'Projekt fortgesetzt: ' + project['name'])
            window.spaces.open_room(project, on_open=restored)
        self.guard(open_project)

    def combined(self):
        if self.project: self.guard(lambda: self.files(True).navigate(LIBRARY + 'project-' + self.project['id']))

    def open_source(self):
        location = chosen(self.sources)
        if location: self.guard(lambda: self.files(True).navigate(location))

    def connect_sources(self, addresses):
        pending = list(dict.fromkeys(addresses))
        if not pending: return
        window = self.files()
        def next_source():
            if not pending:
                self.scan(); return
            address = pending.pop(0)
            if window.spaces.local_reference(address) != address: next_source(); return
            connection = Network(self); self.connections.append(connection)
            def connected(url, path):
                window.network.mounts[path] = url
                self.status.setText('Verbunden: ' + server_label(url)); next_source()
            connection.connected.connect(connected)
            connection.failed.connect(lambda message: (self.status.setText(message), next_source()))
            try: connection.mount(address)
            except ValueError as error: self.status.setText(str(error)); next_source()
        next_source()

    def scan(self):
        if not self.project: return
        self.generation += 1; generation = self.generation; project = self.project
        self.cached_rows = []; self.render_recent()
        window = self.guard(lambda: self.files())
        if window is None: return
        for r, source in enumerate(project['sources']):
            root = window.spaces.local_reference(source['location'])
            cache_key = 'workplace/recent/' + project['id'] + '/' + str(r)
            def complete(value, error, r=r, source=source, cache_key=cache_key):
                if generation != self.generation: return
                if not error and value and value['errors'] and not value['files']:
                    error = '\n'.join(value['errors'])
                if error:
                    cached = self.store.setting(cache_key, {})
                    if cached.get('location') != source['location']: cached = {}
                    self.cached_rows.extend((entry, source['label'] + ' · offline', False) for entry in cached.get('files', []))
                    status = 'Offline / nicht verbunden' + (' · Stand ' + date(cached['checked']) if cached else '')
                    self.sources.item(r, 2).setToolTip(error)
                else:
                    self.store.set_setting(cache_key, dict(value, location=source['location']))
                    self.cached_rows.extend((entry, source['label'], True) for entry in value['files'])
                    status = 'Teilweise erreichbar' if value['errors'] else 'Erreichbar'
                    if value['limited']: status += ' · erste 5.000 Einträge'
                self.sources.item(r, 2).setText(status); self.render_recent()
            if is_network_address(root): complete(None, 'Zum Verbinden die Quelle öffnen.')
            else:
                self.sources.item(r, 2).setText('Wird geprüft …')
                self.job('scan', {'root': root}, complete, timeout=12000)

    def render_recent(self):
        self.cached_rows.sort(key=lambda r: r[0]['modified'], reverse=True)
        self.cached_rows = self.cached_rows[:60]
        fill(self.recent, [(e['path'], [e['name'], label, date(e['modified']), size_text(e['size'])])
                           for e, label, online in self.cached_rows])

    def open_recent(self, *_):
        identity = chosen(self.recent)
        if identity is None: return
        entry, _, online = next(value for value in self.cached_rows if value[0]['path'] == identity)
        if online: QDesktopServices.openUrl(QUrl.fromLocalFile(entry['path']))
        else: self.status.setText('Diese Quelle ist offline. Zuerst oben öffnen und verbinden.')

    def modes_page(self):
        box = self.page('Arbeitsmodi')
        box.addWidget(text('Ein Klick, ein passender Arbeitsplatz.', 'heading'))
        box.addWidget(text('Audioausgabe, Ruhezeit, Fensteranordnung und Netzwerkordner zusammen einstellen. Änderungen lassen sich im Verlauf einzeln zurücknehmen.', 'muted'))
        self.mode_table = table(['Modus', 'Fenster', 'Ruhezeit', 'Verbindungen']); box.addWidget(self.mode_table, 1)
        row(box, [('Modus anwenden', self.apply_mode), ('Anpassen …', self.edit_mode)])
        self.mode_status = text(''); box.addWidget(self.mode_status)

    def refresh_modes(self):
        self.mode_values = modes.modes(self.store)
        names = {'keep': 'Beibehalten', 'tile': 'Nebeneinander', 'maximize': 'Maximieren'}
        fill(self.mode_table, [(m['id'], [m['name'], names[m['layout']], 'Beibehalten' if m['quiet'] < 0 else 'Aus' if not m['quiet'] else str(m['quiet']) + ' min', len(m['connections'])]) for m in self.mode_values])
        if self.mode_table.currentRow() < 0: self.mode_table.selectRow(0)

    def mode(self):
        return next((m for m in self.mode_values if m['id'] == chosen(self.mode_table)), None)

    def edit_mode(self):
        mode = self.mode()
        if not mode or self.busy: return
        def ready(devices, error):
            dialog = ModeDialog(self.store, mode, devices or [], self)
            if error: dialog.error.setText('Audioausgaben derzeit nicht verfügbar: ' + error)
            if dialog.exec_() == QDialog.Accepted: self.refresh_modes()
            dialog.deleteLater()
        self.job('audio', {}, ready)

    def apply_mode(self):
        mode = self.mode()
        if not mode or self.busy: return
        self.mode_status.setText(mode['name'] + ' wird eingerichtet …')
        def complete(value, error):
            if error: self.mode_status.setText(error); return
            self.mode_status.setText(('Angewendet: ' + ', '.join(value['applied']) if value['applied'] else 'Systemeinstellungen beibehalten.') +
                ('\n' + '\n'.join(value['errors']) if value['errors'] else ''))
            self.connect_sources(mode['connections']); self.refresh_activity()
        self.job('mode', mode, complete, timeout=45000, mutating=True)

    def transfers_page(self):
        box = self.page('Transfers')
        box.addWidget(text('Alles, was unterwegs ist.', 'heading'))
        box.addWidget(text('Kopien, Verschiebungen und Downloads aus Lumen · auch zum NAS. Browser-Downloads bleiben in deinem Browser.', 'muted'))
        self.transfers = table(['Datei / Vorgang', 'Fortschritt', 'Status']); box.addWidget(self.transfers, 1)
        self.transfer_detail = text('Wähle einen Transfer für Details.'); box.addWidget(self.transfer_detail)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); box.addWidget(self.progress)
        row(box, [('Download starten …', self.new_download), ('Anhalten', self.pause_transfer), ('Fortsetzen / erneut versuchen', self.retry_transfer)])
        self.transfers.itemSelectionChanged.connect(self.transfer_details)

    def new_download(self):
        url, ok = QInputDialog.getText(self, 'Download starten', 'HTTP(S)-Adresse:')
        if not ok: return
        def start():
            transfers.web_url(url)
            filename = Path(QUrl(url).path()).name or 'Download'
            target, _ = QFileDialog.getSaveFileName(self, 'Download speichern', str(Path.home() / 'Downloads' / filename))
            if not target: return
            value = transfers.create(self.store, 'download', [url], target)
            transfers.start(self.store, value); self.refresh_activity()
        self.guard(start)

    def pause_transfer(self):
        if chosen(self.transfers): self.guard(lambda: transfers.pause(self.store, chosen(self.transfers)))

    def retry_transfer(self):
        if chosen(self.transfers): self.guard(lambda: transfers.retry(self.store, chosen(self.transfers)))

    def transfer_details(self):
        value = next((v for v in getattr(self, 'transfer_values', []) if v['id'] == chosen(self.transfers)), None)
        if not value: return
        self.transfer_detail.setText((value['target'] or '\n'.join(value['sources'])) + ('\n' + '\n'.join(value['errors']) if value['errors'] else ''))
        total = value['total'] if value['action'] == 'download' else len(value['sources'])
        done = value['bytes'] if value['action'] == 'download' else len(value['done'])
        self.progress.setRange(0, 100 if total or value['status'] not in transfers.ACTIVE else 0)
        self.progress.setValue(min(100, round(100 * done / total)) if total else 0)

    def history_page(self):
        box = self.page('Verlauf')
        box.addWidget(text('Änderungen nachvollziehen.', 'heading'))
        box.addWidget(text('Rückgängig ist verfügbar, solange der betroffene Zustand seitdem unverändert ist. Erstellte Dateien werden in den Papierkorb gelegt.', 'muted'))
        self.history = table(['Änderung', 'Wann', 'Rückgängig']); box.addWidget(self.history, 1)
        self.undo_button = button('Ausgewählte Änderung zurücknehmen', self.undo); box.addWidget(self.undo_button)
        self.history.itemSelectionChanged.connect(self.history_details)
        self.history_detail = text(''); box.addWidget(self.history_detail)

    def history_details(self):
        value = next((v for v in getattr(self, 'history_values', []) if v['id'] == chosen(self.history)), None)
        self.undo_button.setEnabled(bool(value and history.can_undo(value) and not self.busy))
        self.history_detail.setText(str(value.get('target') or '') if value else '')

    def undo(self):
        identity = chosen(self.history)
        if not identity or self.busy: return
        self.undo_button.setEnabled(False); self.status.setText('Änderung wird geprüft und zurückgenommen …')
        def complete(_, error):
            self.status.setText(error or 'Änderung zurückgenommen.'); self.refresh_activity(); self.refresh_modes(); self.refresh_projects()
            value = next((v for v in self.history_values if v['id'] == identity), None)
            if not error and value and value['kind'] == 'preferences':
                window = self.guard(lambda: self.files())
                if window:
                    keys = list(value['after'])
                    window.reload_settings(value['target'], keys)
                    chat = window.spaces.chat()
                    if chat: chat.reload_settings(value['target'], keys)
            if not error and value and value['kind'] == 'store-setting' and str(value['target']).startswith('files/spaces/room/'):
                window = self.guard(lambda: self.files())
                if window and window.spaces.active_room and value['target'].endswith('/' + window.spaces.active_room['id']):
                    # Do not let automatic room saving overwrite the restored snapshot.
                    window.spaces.active_room = None
                    window.room_button.setText('Arbeitsräume')
                    window.spaces.catalog.use_room_shelf(); window.spaces.update_shelf()
                    if window.current_location == 'lumen:shelf': window.spaces.reload()
                    self.status.setText('Projektänderung zurückgenommen. Den gespeicherten Stand mit „Weiterarbeiten“ öffnen.')
        self.job('undo', {'id': identity}, complete, mutating=True)

    def refresh_activity(self):
        if not self.isVisible() and hasattr(self, 'transfer_values'): return
        try:
            self.transfer_values = transfers.tickets(self.store)
            action_names = {'copy': 'Kopieren', 'move': 'Verschieben', 'rename': 'Umbenennen', 'mkdir': 'Neuer Ordner', 'trash': 'Papierkorb', 'download': 'Download'}
            fill(self.transfers, [(v['id'], [action_names[v['action']] + ' · ' + (Path(v['target']).name if v['action'] == 'download' else v['current'] or Path(v['sources'][0]).name),
                (size_text(v['bytes']) + (' / ' + size_text(v['total']) if v['total'] else '') if v['action'] == 'download'
                 else f"{len(v['done'])} / {len(v['sources'])}" + (' · ' + size_text(v['bytes']) if v['bytes'] else '')),
                'Wird angehalten' if v.get('cancel') and v['status'] in transfers.ACTIVE else transfers.LABELS[v['status']]]) for v in self.transfer_values[:200]])
            self.transfer_details()
            self.history_values = history.entries(self.store)
            fill(self.history, [(v['id'], [v['title'], date(v['created']), 'Verfügbar' if history.can_undo(v) else 'Zurückgenommen' if v['status'] == 'undone' else 'Nur Verlauf']) for v in self.history_values])
            self.history_details()
        except Exception as error: self.status.setText(str(error))

    def shutdown(self):
        self.timer.stop(); self.generation += 1
        for connection in self.connections: connection.close()
        for job in self.jobs[:]: job.kill(); job.waitForFinished(1000)


if __name__ == '__main__':
    try:
        store = Store(); action = sys.argv[1]; value = json.load(sys.stdin)
        if action == 'scan': result = projects.recent(value['root'])
        elif action == 'audio': result = modes.audio_devices()
        elif action == 'mode': result = modes.apply_mode(store, value)
        elif action == 'undo': history.undo_record(store, value['id']); result = True
        elif action == 'launch':
            from lumen_actions import desktop_file
            errors = []
            for application in value.get('applications', []):
                try:
                    subprocess.run(['gio', 'launch', str(desktop_file(application))], capture_output=True, check=True, timeout=5)
                except Exception as error: errors.append(application + ': ' + str(error))
            result = '\n'.join(errors) if errors else 'Projekt bereit. Deine Notiz und Dateien warten hier auf dich.'
        else: raise ValueError('Unbekannte Arbeitsplatz-Aktion.')
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
