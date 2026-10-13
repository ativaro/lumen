"""Native workplace: selected context, desktop modes, transfers and guarded history."""
from lumen_i18n import worker_process, tr
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
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




class ModeDialog(QDialog):
    def __init__(self, store, mode, devices, parent):
        super().__init__(parent); self.store, self.mode = store, mode
        self.setWindowTitle(tr('Arbeitsmodus anpassen')); self.resize(580, 530)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.name = QLineEdit(mode['name']); form.addRow(tr('Name'), self.name)
        self.audio = QComboBox(); self.audio.addItem(tr('Aktuelles Ausgabegerät behalten'), '')
        for d in devices: self.audio.addItem(d['description'], d['name'])
        if mode['audio'] and self.audio.findData(mode['audio']) < 0: self.audio.addItem(mode['audio'] + tr(' (nicht verfügbar)'), mode['audio'])
        self.audio.setCurrentIndex(max(0, self.audio.findData(mode['audio']))); form.addRow(tr('Audioausgabe'), self.audio)
        self.volume = QSpinBox(); self.volume.setRange(-1, 100); self.volume.setSpecialValueText(tr('Beibehalten'))
        self.volume.setSuffix(' %'); self.volume.setValue(mode['volume']); form.addRow(tr('Lautstärke'), self.volume)
        self.quiet = QComboBox()
        for name, value in [(tr('Beibehalten'), -1), (tr('Nicht stören beenden'), 0), (tr('30 Minuten Ruhe'), 30), (tr('1 Stunde Ruhe'), 60), (tr('3 Stunden Ruhe'), 180)]: self.quiet.addItem(name, value)
        self.quiet.setCurrentIndex(self.quiet.findData(mode['quiet'])); form.addRow(tr('Benachrichtigungen'), self.quiet)
        self.arrange = QComboBox()
        for name, value in [(tr('Anordnung beibehalten'), 'keep'), (tr('Nebeneinander je Bildschirm'), 'tile'), (tr('Sichtbare Fenster maximieren'), 'maximize')]: self.arrange.addItem(name, value)
        self.arrange.setCurrentIndex(self.arrange.findData(mode['layout'])); form.addRow(tr('Fenster'), self.arrange)
        layout.addWidget(text(tr('Netzwerkordner verbinden · eine Adresse pro Zeile. Bestehende Verbindungen bleiben erhalten.'), 'muted'))
        self.connections = QPlainTextEdit('\n'.join(mode['connections'])); self.connections.setAccessibleName(tr('Netzwerkordner des Modus'))
        layout.addWidget(self.connections)
        def add():
            dialog = ConnectDialog(self)
            if dialog.exec() == QDialog.Accepted: self.connections.appendPlainText(dialog.url)
            dialog.deleteLater()
        layout.addWidget(button(tr('Netzwerk hinzufügen …'), add))
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
    def __init__(self, parent=None, store=None, files_provider=None, system_only=False, activity_only=False):
        super().__init__(parent)
        self.system_only = system_only
        self.store = store or Store(); self.files_provider = files_provider
        self.jobs, self.connections = [], []
        self.generation = 0; self.busy = False; self.project = None; self.cached_rows = []
        self.setObjectName('workplace'); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 18); layout.setSpacing(16)
        if system_only:
            layout.addWidget(text(tr('Arbeitsmodi'),'workplaceHeading'))
            self.summary=text(tr('Audio, Ruhezeit, Fenster und Netzwerkordner gemeinsam steuern.'),'muted');layout.addWidget(self.summary)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        if system_only: self.modes_page()
        else:
            if not activity_only: self.projects_page()
            self.transfers_page()
        self.history_page()
        self.status = text('', 'muted'); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_activity); self.timer.start(1500)
        self.tabs.currentChanged.connect(lambda _: self.refresh_activity())
        if not system_only and not activity_only:
            self.tabs.tabBar().hide()
            self.tabs.currentChanged.connect(lambda index:self.tabs.tabBar().setVisible(index!=0))
        if system_only: self.refresh_modes()
        elif not activity_only: self.refresh_projects()
        self.refresh_activity()

    def open_modes(self):
        from lumen_apps import launch
        self.guard(lambda: launch('system', page='modes'))

    def page(self, name):
        widget = QWidget(); widget.setObjectName('workplacePage'); box = QVBoxLayout(widget); box.setContentsMargins(4, 18, 4, 4); box.setSpacing(12)
        self.tabs.addTab(widget, name); return box

    def guard(self, fn):
        try: return fn()
        except Exception as error: self.status.setText(str(error))

    def job(self, action, data, callback, timeout=30000, mutating=False):
        proc = worker_process(self); self.jobs.append(proc)
        env = proc.processEnvironment(); env.insert('LUMEN_DATA', str(self.store.directory)); proc.setProcessEnvironment(env)
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
            error = tr('Zeitlimit erreicht. Quelle ist derzeit nicht erreichbar.') if expired else ''
            result = None
            if not error:
                try:
                    if code: raise ValueError(bytes(proc.readAllStandardError()).decode(errors='replace')[-1200:] or tr('Vorgang fehlgeschlagen.'))
                    result = json.loads(bytes(proc.readAllStandardOutput()))
                except Exception as e: error = str(e)
            callback(result, error); proc.deleteLater()
        proc.finished.connect(finish)
        proc.errorOccurred.connect(lambda error: finish(1) if error == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__)), action])
        proc.write(json.dumps(data).encode()); proc.closeWriteChannel(); timer.start(timeout)

    def files(self, show=False):
        if not self.files_provider: raise ValueError(tr('Kein Dateifenster verfügbar.'))
        window = self.files_provider()
        if show:
            if hasattr(window, 'lumen_host'): window.lumen_host.show_page(3)
            else: window.show(); window.raise_(); window.activateWindow()
        return window

    def projects_page(self):
        from workplace_rooms import Rooms
        box=self.page(tr('Projekte'));self.rooms=Rooms(self);box.addWidget(self.rooms)

    def refresh_projects(self, identity=None):
        if self.system_only or not hasattr(self, 'rooms'):return
        self.select_project(identity or (self.project or {}).get('id'))

    def select_project(self, identity=None):
        self.generation+=1
        values=projects.projects(self.store)
        self.project=next((p for p in values if p['id']==identity),values[0] if values else None)
        self.cached_rows=[];self.render_recent()
        fill(self.sources,[(s['location'],[s['label'],s['location'],tr('Noch nicht geprüft')]) for s in (self.project or {}).get('sources',[])])
        self.rooms.render(values)

    def edit_project(self, _=False, new=False):
        owner=self.window()
        if hasattr(owner, 'home'):
            owner.home.create() if new else owner.home.edit_environment()
        else:
            from lumen_detail_routes import open_page
            open_page(8)

    def remote_action(self, action, value=''):
        if not self.project: raise ValueError(tr('Bitte zuerst ein Projekt wählen.'))
        from lumen_detail_routes import room_action
        result = room_action(self.project['id'], action, value)
        self.refresh_projects(self.project['id'])
        self.status.setText(result.get('status') or tr('In Lumen übernommen.'))

    def capture(self):
        if getattr(self, 'remote_conversations', False): return self.remote_action('capture')
        if not self.project: return
        def save():
            window = self.files()
            latest = next(p for p in projects.projects(self.store) if p['id'] == self.project['id'])
            saved = projects.save_project(self.store, latest, latest['name'], latest['sources'], latest['applications'],
                latest['urls'], latest['note'], window.spaces.capture())
            if window.spaces.active_room and window.spaces.active_room['id'] == saved['id']: window.spaces.active_room = saved
            self.refresh_projects(saved['id']); self.status.setText(tr('Tabs, Auswahl und Lumen-Kontext gespeichert.'))
        self.guard(save)

    def resume(self):
        if getattr(self, 'remote_conversations', False): return self.remote_action('resume')
        if not self.project or self.busy: return
        def open_project():
            window = self.files()
            chat = window.spaces.chat()
            if window.file_job or (chat and (chat.backend.busy or chat.context_tools.process)):
                raise ValueError(tr('Bitte zuerst den laufenden Vorgang abschließen.'))
            if chat and chat.composer.toPlainText().strip() and (window.spaces.active_room or {}).get('id')!=self.project['id']:
                if QMessageBox.question(self,tr('Entwurf behalten?'),tr('Der aktuelle Gesprächsentwurf würde ersetzt. Fortfahren?'),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            project = next(p for p in projects.projects(self.store) if p['id'] == self.project['id'])
            def restored():
                self.connect_sources([s['location'] for s in project['sources'] if is_network_address(s['location'])])
                self.job('launch', project, lambda result, error: self.status.setText(error or result), mutating=True)
                for url in project.get('urls', []):
                    if not QDesktopServices.openUrl(QUrl(transfers.web_url(url))): self.status.setText(tr('Webseite konnte nicht geöffnet werden: ') + url)
                history.record(self.store, tr('Projekt fortgesetzt: ') + project['name'],target='files/spaces/room/'+project['id'])
                self.store.set_setting('workplace/last',project['id'])
                self.files(True);self.rooms.resume_pins(project)
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
        window = self.files() if self.files_provider else None
        def next_source():
            if not pending:
                self.scan(); return
            address = pending.pop(0)
            if window and window.spaces.local_reference(address) != address: next_source(); return
            connection = Network(self); self.connections.append(connection)
            def connected(url, path):
                if window: window.network.mounts[path] = url
                self.status.setText(tr('Verbunden: ') + server_label(url)); next_source()
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
                    status = tr('Offline / nicht verbunden') + (tr(' · Stand ') + date(cached['checked']) if cached else '')
                    self.sources.item(r, 2).setToolTip(error)
                else:
                    self.store.set_setting(cache_key, dict(value, location=source['location']))
                    self.cached_rows.extend((entry, source['label'], True) for entry in value['files'])
                    status = tr('Teilweise erreichbar') if value['errors'] else tr('Erreichbar')
                    if value['limited']: status += tr(' · erste 5.000 Einträge')
                self.sources.item(r, 2).setText(status); self.render_recent()
            if is_network_address(root): complete(None, tr('Zum Verbinden die Quelle öffnen.'))
            else:
                self.sources.item(r, 2).setText(tr('Wird geprüft …'))
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
        else: self.status.setText(tr('Diese Quelle ist offline. Zuerst oben öffnen und verbinden.'))

    def modes_page(self):
        box = self.page(tr('Arbeitsmodi'))
        box.addWidget(text(tr('Ein Klick, ein passender Arbeitsplatz.'), 'heading'))
        box.addWidget(text(tr('Audioausgabe, Ruhezeit, Fensteranordnung und Netzwerkordner zusammen einstellen. Änderungen lassen sich im Verlauf einzeln zurücknehmen.'), 'muted'))
        self.mode_table = table([tr('Modus'), tr('Fenster'), tr('Ruhezeit'), tr('Verbindungen')]); box.addWidget(self.mode_table, 1)
        row(box, [(tr('Modus anwenden'), self.apply_mode), (tr('Anpassen …'), self.edit_mode)])
        self.mode_status = text(''); box.addWidget(self.mode_status)

    def refresh_modes(self):
        if not self.system_only:return
        self.mode_values = modes.modes(self.store)
        names = {'keep': tr('Beibehalten'), 'tile': tr('Nebeneinander'), 'maximize': tr('Maximieren')}
        fill(self.mode_table, [(m['id'], [m['name'], names[m['layout']], tr('Beibehalten') if m['quiet'] < 0 else tr('Aus') if not m['quiet'] else str(m['quiet']) + ' min', len(m['connections'])]) for m in self.mode_values])
        if self.mode_table.currentRow() < 0: self.mode_table.selectRow(0)

    def mode(self):
        return next((m for m in self.mode_values if m['id'] == chosen(self.mode_table)), None)

    def edit_mode(self):
        mode = self.mode()
        if not mode or self.busy: return
        def ready(devices, error):
            dialog = ModeDialog(self.store, mode, devices or [], self)
            if error: dialog.error.setText(tr('Audioausgaben derzeit nicht verfügbar: ') + error)
            if dialog.exec() == QDialog.Accepted: self.refresh_modes()
            dialog.deleteLater()
        self.job('audio', {}, ready)

    def apply_mode(self):
        mode = self.mode()
        if not mode or self.busy: return
        self.mode_status.setText(mode['name'] + tr(' wird eingerichtet …'))
        def complete(value, error):
            if error: self.mode_status.setText(error); return
            self.mode_status.setText((tr('Angewendet: ') + ', '.join(value['applied']) if value['applied'] else tr('Systemeinstellungen beibehalten.')) +
                ('\n' + '\n'.join(value['errors']) if value['errors'] else ''))
            self.connect_sources(mode['connections']); self.refresh_activity()
        self.job('mode', mode, complete, timeout=45000, mutating=True)

    def transfers_page(self):
        box = self.page(tr('Transfers'))
        box.addWidget(text(tr('Alles, was unterwegs ist.'), 'heading'))
        box.addWidget(text(tr('Kopien, Verschiebungen und Downloads aus Lumen · auch zum NAS. Browser-Downloads bleiben in deinem Browser.'), 'muted'))
        self.transfers = table([tr('Datei / Vorgang'), tr('Fortschritt'), tr('Status')]); box.addWidget(self.transfers, 1)
        self.transfer_detail = text(tr('Wähle einen Transfer für Details.')); box.addWidget(self.transfer_detail)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); box.addWidget(self.progress)
        row(box, [(tr('Download starten …'), self.new_download), (tr('Anhalten'), self.pause_transfer), (tr('Fortsetzen / erneut versuchen'), self.retry_transfer)])
        self.transfers.itemSelectionChanged.connect(self.transfer_details)

    def new_download(self):
        url, ok = QInputDialog.getText(self, tr('Download starten'), 'HTTP(S)-Adresse:')
        if not ok: return
        def start():
            transfers.web_url(url)
            filename = Path(QUrl(url).path()).name or tr('Download')
            target, _ = QFileDialog.getSaveFileName(self, tr('Download speichern'), str(Path.home() / 'Downloads' / filename))
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
        box = self.page(tr('Verlauf'))
        box.addWidget(text(tr('Änderungen nachvollziehen.'), 'heading'))
        box.addWidget(text(tr('Rückgängig ist verfügbar, solange der betroffene Zustand seitdem unverändert ist. Erstellte Dateien werden in den Papierkorb gelegt.'), 'muted'))
        self.history = table([tr('Änderung'), tr('Wann'), tr('Rückgängig')]); box.addWidget(self.history, 1)
        self.undo_button = button(tr('Ausgewählte Änderung zurücknehmen'), self.undo); box.addWidget(self.undo_button)
        self.history.itemSelectionChanged.connect(self.history_details)
        self.history_detail = text(''); box.addWidget(self.history_detail)

    def history_details(self):
        value = next((v for v in getattr(self, 'history_values', []) if v['id'] == chosen(self.history)), None)
        self.undo_button.setEnabled(bool(value and history.can_undo(value) and not self.busy))
        self.history_detail.setText(str(value.get('target') or '') if value else '')

    def undo(self):
        identity = chosen(self.history)
        if not identity or self.busy: return
        self.undo_button.setEnabled(False); self.status.setText(tr('Änderung wird geprüft und zurückgenommen …'))
        def complete(_, error):
            self.status.setText(error or tr('Änderung zurückgenommen.')); self.refresh_activity()
            if self.system_only: self.refresh_modes()
            else: self.refresh_projects()
            value = next((v for v in self.history_values if v['id'] == identity), None)
            if self.files_provider and not error and value and value['kind'] == 'preferences':
                window = self.guard(lambda: self.files())
                if window:
                    keys = list(value['after'])
                    window.reload_settings(value['target'], keys)
                    chat = window.spaces.chat()
                    if chat: chat.reload_settings(value['target'], keys)
            if self.files_provider and not error and value and value['kind'] == 'store-setting' and str(value['target']).startswith('files/spaces/room/'):
                window = self.guard(lambda: self.files())
                if window and window.spaces.active_room and value['target'].endswith('/' + window.spaces.active_room['id']):
                    # Do not let automatic room saving overwrite the restored snapshot.
                    window.spaces.active_room = None
                    window.room_button.setText(tr('Projekte'))
                    window.spaces.catalog.use_room_shelf(); window.spaces.update_shelf()
                    if window.current_location == 'lumen:shelf': window.spaces.reload()
                    self.status.setText(tr('Projektänderung zurückgenommen. Den gespeicherten Stand mit „Arbeitsstand laden“ öffnen.'))
        self.job('undo', {'id': identity}, complete, mutating=True)

    def refresh_activity(self):
        if not self.isVisible() and hasattr(self, 'transfer_values'): return
        try:
            if not self.system_only:
                if hasattr(self, 'rooms'): self.rooms.refresh_tasks()
                self.transfer_values = transfers.tickets(self.store)
                action_names = {'copy': tr('Kopieren'), 'move': tr('Verschieben'), 'rename': tr('Umbenennen'), 'mkdir': tr('Neuer Ordner'), 'trash': tr('Papierkorb'), 'download': tr('Download')}
                fill(self.transfers, [(v['id'], [action_names.get(v['action'], v['action']) + ' · ' + (Path(v['target']).name if v['action'] == 'download' else v['current'] or Path(v['sources'][0]).name),
                    (size_text(v['bytes']) + (' / ' + size_text(v['total']) if v['total'] else '') if v['action'] == 'download'
                     else f"{len(v['done'])} / {len(v['sources'])}" + (' · ' + size_text(v['bytes']) if v['bytes'] else '')),
                    tr('Wird angehalten') if v.get('cancel') and v['status'] in transfers.ACTIVE else transfers.LABELS[v['status']]]) for v in self.transfer_values[:200]])
                self.transfer_details()
            self.history_values = history.entries(self.store)
            if self.system_only:
                self.history_values = [value for value in self.history_values if value['kind'] == 'mode' or
                    (value['kind'] == 'store-setting' and str(value['target']).startswith('files/spaces/mode/'))]
            fill(self.history, [(v['id'], [v['title'], date(v['created']), tr('Verfügbar') if history.can_undo(v) else tr('Zurückgenommen') if v['status'] == 'undone' else tr('Nur Verlauf')]) for v in self.history_values])
            self.history_details()
        except Exception as error: self.status.setText(str(error))

    def can_close(self):
        try: return not hasattr(self, 'rooms') or self.rooms.can_close()
        except Exception as error:
            self.status.setText(str(error)); return False

    def shutdown(self):
        if hasattr(self, 'rooms') and self.rooms.household is not None:
            self.rooms.household.close()
        self.timer.stop(); self.generation += 1
        for connection in self.connections: connection.close()
        for job in self.jobs[:]: job.kill(); job.waitForFinished(1000)


if __name__ == '__main__':
    try:
        store = Store(); action = sys.argv[1]; value = json.load(sys.stdin)
        if action == 'scan': result = projects.recent(value['root'])
        elif action == 'notes':
            from wissen_data import Notebook
            book=Notebook(store);notes=book.scan()['notes']
            result=[dict(app='wissen',kind='note',id=n['path'],title=n['title'],path=str(book.root/n['path']),locator=dict(root=str(book.root),area='user')) for n in notes]
        elif action == 'room-notes':
            from interop_data import Registry
            from wissen_data import Notebook
            result={}
            for url in value['urls'][:8]:
                try:
                    ref=Registry().resolve(url)
                    if ref['app']!='wissen':continue
                    note=Notebook(store,root=ref['locator']['root']).read(ref['id'])
                    result[url]=note['text'][:350]
                except (OSError,ValueError,KeyError):result[url]=tr('Vorschau nicht verfügbar')
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
            result = '\n'.join(errors) if errors else tr('Projekt bereit. Deine Notiz und Dateien warten hier auf dich.')
        else: raise ValueError(tr('Unbekannte Arbeitsplatz-Aktion.'))
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
