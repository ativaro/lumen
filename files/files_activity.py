"""Transfers and guarded history for Lumen Files."""
from lumen_i18n import worker_process, tr
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox,
    QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from core import size_text
from lumen_store import Store
from network import is_network_address
import lumen_history as history
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
    widget.setObjectName('activityTable'); widget.setAccessibleName(' · '.join(headers))
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


class FilesActivity(QWidget):
    def __init__(self, parent=None, store=None, files_provider=None):
        super().__init__(parent)
        self.store = store or Store(); self.files_provider = files_provider
        self.jobs = []
        self.generation = 0; self.busy = False
        self.setObjectName('activity'); layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 18); layout.setSpacing(16)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.transfers_page()
        self.history_page()
        self.status = text('', 'muted'); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_activity); self.timer.start(1500)
        self.tabs.currentChanged.connect(lambda _: self.refresh_activity())
        self.refresh_activity()

    def page(self, name):
        widget = QWidget(); widget.setObjectName('activityPage'); box = QVBoxLayout(widget); box.setContentsMargins(4, 18, 4, 4); box.setSpacing(12)
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

    def transfers_page(self):
        box = self.page(tr('Übertragungen'))
        box.addWidget(text(tr('Alles, was unterwegs ist.'), 'heading'))
        box.addWidget(text(tr('Kopien, Verschiebungen und Downloads aus Lumen · auch zum NAS. Browser-Downloads bleiben in deinem Browser.'), 'muted'))
        self.transfers = table([tr('Datei / Vorgang'), tr('Fortschritt'), tr('Status')]); box.addWidget(self.transfers, 1)
        self.transfer_detail = text(''); box.addWidget(self.transfer_detail)
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
        if not value:
            self.transfer_detail.setText(tr('Wähle eine Übertragung für Details.') if getattr(self, 'transfer_values', [])
                                         else tr('Noch keine Übertragungen. Kopien, Verschiebungen und Downloads erscheinen hier.'))
            return
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
        self.history_detail.setText(str(value.get('target') or '') if value else '' if getattr(self, 'history_values', [])
                                    else tr('Noch keine Änderungen. Dateiaktionen und geänderte Einstellungen erscheinen hier.'))

    def undo(self):
        identity = chosen(self.history)
        if not identity or self.busy: return
        self.undo_button.setEnabled(False); self.status.setText(tr('Änderung wird geprüft und zurückgenommen …'))
        def complete(_, error):
            self.status.setText(error or tr('Änderung zurückgenommen.')); self.refresh_activity()
            value = next((v for v in self.history_values if v['id'] == identity), None)
            if self.files_provider and not error and value and value['kind'] == 'preferences':
                window = self.guard(lambda: self.files())
                if window:
                    keys = list(value['after'])
                    window.reload_settings(value['target'], keys)
                    chat = window.spaces.chat()
                    if chat: chat.reload_settings(value['target'], keys)
        self.job('undo', {'id': identity}, complete, mutating=True)

    def refresh_activity(self):
        if not self.isVisible() and hasattr(self, 'transfer_values'): return
        try:
            self.transfer_values = transfers.tickets(self.store)
            action_names = {'copy': tr('Kopieren'), 'move': tr('Verschieben'), 'rename': tr('Umbenennen'), 'mkdir': tr('Neuer Ordner'), 'trash': tr('Papierkorb'), 'download': tr('Download')}
            fill(self.transfers, [(v['id'], [action_names.get(v['action'], v['action']) + ' · ' + (Path(v['target']).name if v['action'] == 'download' else v['current'] or Path(v['sources'][0]).name),
                (size_text(v['bytes']) + (' / ' + size_text(v['total']) if v['total'] else '') if v['action'] == 'download'
                 else f"{len(v['done'])} / {len(v['sources'])}" + (' · ' + size_text(v['bytes']) if v['bytes'] else '')),
                tr('Wird angehalten') if v.get('cancel') and v['status'] in transfers.ACTIVE else transfers.LABELS[v['status']]]) for v in self.transfer_values[:200]])
            self.transfer_details()
            self.history_values = history.entries(self.store)
            fill(self.history, [(v['id'], [v['title'], date(v['created']), tr('Verfügbar') if history.can_undo(v) else tr('Zurückgenommen') if v['status'] == 'undone' else tr('Nur Verlauf')]) for v in self.history_values])
            self.history_details()
        except Exception as error: self.status.setText(str(error))

    def can_close(self):
        return not self.busy

    def shutdown(self):
        self.timer.stop(); self.generation += 1
        for job in self.jobs[:]: job.kill(); job.waitForFinished(1000)


if __name__ == '__main__':
    try:
        store = Store(); action = sys.argv[1]; value = json.load(sys.stdin)
        if action == 'undo': history.undo_record(store, value['id']); result = True
        else: raise ValueError(tr('Unbekannte Aktion.'))
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
