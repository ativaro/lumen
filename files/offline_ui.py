"""Native offline folders and conflict choices; all NAS I/O runs in a process."""
import json
import os
from pathlib import Path
import sys
from PyQt5.QtCore import QObject, QProcess, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout
from lumen_store import Store
from lumen_offline import folders, pin, PREFIX
from network import Network


class Offline(QObject):
    changed = pyqtSignal()
    catalogChanged = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window; self.store = Store(); self.network = Network(self)
        self.proc = None; self.active = None; self.roots = {}; self.queue = []; self.message = ''
        self.network.connected.connect(self.connected)
        self.network.failed.connect(self.failed)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(60000)
        self.deadline = QTimer(self); self.deadline.setSingleShot(True); self.deadline.timeout.connect(self.timeout)
        QTimer.singleShot(3000, self.refresh)

    def add(self, address):
        try:
            item = pin(self.store, address); self.catalogChanged.emit(); self.changed.emit(); self.show(); self.start(item, manual=True)
        except (ValueError, OSError) as error: self.window.error(str(error))

    def refresh(self):
        if self.active: return
        self.queue = folders(self.store); self.next()

    def next(self):
        if self.queue: self.start(self.queue.pop(0))

    def start(self, item, manual=False, choices=None):
        if self.active: return
        self.active = item; self.choices = choices or {}; self.message = 'Verbinde ' + item['name'] + ' …'
        self.changed.emit(); self.deadline.start(120000)
        (self.network.mount if manual else self.network.mount_url)(item['remote'])

    def connected(self, address, path):
        if not self.active: return
        self.roots[self.active['id']] = path
        self.message = 'Gleiche Dateien ab …'; self.changed.emit()
        proc = QProcess(self); self.proc = proc; self.buffer = b''; self.received = False
        from PyQt5.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment(); env.insert('LUMEN_DATA', str(self.store.directory)); proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self.read)
        proc.finished.connect(self.finished)
        proc.errorOccurred.connect(lambda e: self.failed('Abgleich konnte nicht starten.') if e == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__).with_name('lumen_offline.py'))])
        proc.write((json.dumps(dict(id=self.active['id'], root=path, choices=self.choices)) + '\n').encode()); proc.closeWriteChannel()

    def read(self):
        if not self.proc: return
        self.buffer += bytes(self.proc.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: event = json.loads(line)
            except ValueError: continue
            self.deadline.start(120000)
            if 'progress' in event: self.message = 'Abgleich · ' + event['progress']
            if 'error' in event: self.message = event['error']; self.received = True
            if 'result' in event: self.message = event['result']['status']; self.received = True
            self.changed.emit()

    def finished(self, code):
        if not self.proc: return
        self.read(); self.proc.deleteLater(); self.proc = None
        if code or not self.received: self.failed(self.message if self.received else 'Abgleich unterbrochen. Erneut versuchen.'); return
        self.active = None; self.deadline.stop(); self.changed.emit(); self.next()

    def failed(self, message):
        if self.proc:
            proc, self.proc = self.proc, None; proc.kill(); proc.waitForFinished(1000); proc.deleteLater()
        if self.active:
            item = self.store.setting(PREFIX + self.active['id']); item['status'] = 'Offline · lokale Kopie verfügbar' if item['synced'] else 'Noch nicht vollständig geladen'
            self.store.set_setting(PREFIX + item['id'], item)
        self.active = None; self.deadline.stop(); self.message = message; self.changed.emit(); self.next()

    def timeout(self):
        self.network.cancel(); self.failed('Server antwortet nicht. Die lokale Kopie bleibt verfügbar.')

    def show(self):
        if not hasattr(self, 'dialog'): self.dialog = OfflineDialog(self)
        self.dialog.reload(); self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def close(self):
        self.queue = []; self.timer.stop(); self.deadline.stop(); self.network.close()
        if self.proc:
            proc, self.proc = self.proc, None; proc.kill(); proc.waitForFinished(1000); proc.deleteLater()


class OfflineDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner.window); self.owner = owner
        self.setWindowTitle('Offline verfügbare Ordner'); self.resize(900, 650)
        layout = QVBoxLayout(self)
        hint = QLabel('Arbeite in der lokalen Kopie. Solange Lumen Files geöffnet ist, wird jede Minute abgeglichen.\n'
                      'Konflikte bleiben erhalten. Ersetzte und gelöschte Inhalte liegen in der Sicherung.'); hint.setWordWrap(True); layout.addWidget(hint)
        self.list = QListWidget(); layout.addWidget(self.list)
        self.list.currentItemChanged.connect(self.selected)
        row = QHBoxLayout(); layout.addLayout(row)
        for text, callback in [('Lokale Kopie öffnen', self.open_local), ('Jetzt abgleichen', self.sync), ('Sicherung öffnen', self.backups), ('Nicht mehr abgleichen', self.remove)]:
            button = QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
        self.conflicts = QTreeWidget(); self.conflicts.setHeaderLabels(['Datei', 'Dieser PC', 'NAS']); layout.addWidget(self.conflicts)
        row = QHBoxLayout(); layout.addLayout(row)
        for text, callback in [('PC-Fassung ansehen', lambda: self.open_conflict(True)), ('NAS-Fassung ansehen', lambda: self.open_conflict(False)), ('PC-Fassung verwenden', lambda: self.resolve('local')), ('NAS-Fassung verwenden', lambda: self.resolve('remote'))]:
            button = QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.owner.changed.connect(self.reload)

    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def reload(self):
        identity = (self.current() or {}).get('id'); self.list.blockSignals(True); self.list.clear()
        for folder in folders(self.owner.store):
            item = QListWidgetItem(folder['name'] + '  ·  ' + folder['status']); item.setData(Qt.UserRole, folder); self.list.addItem(item)
            item.setToolTip(folder['remote'] + '\n' + folder['local'])
            if folder['id'] == identity: self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count(): self.list.setCurrentRow(0)
        self.list.blockSignals(False); self.selected(); self.status.setText(self.owner.message)

    def selected(self, *_):
        self.conflicts.clear()
        for conflict in (self.current() or {}).get('conflicts', []):
            item = QTreeWidgetItem([conflict['path'], 'Vorhanden' if conflict['local'] else 'Gelöscht', 'Vorhanden' if conflict['remote'] else 'Gelöscht'])
            item.setData(0, Qt.UserRole, conflict); self.conflicts.addTopLevelItem(item)
        self.conflicts.resizeColumnToContents(0)

    def open_local(self):
        if self.current(): self.owner.window.navigate(self.current()['local']); self.hide()

    def sync(self):
        if self.current(): self.owner.start(self.current(), manual=True)

    def backups(self):
        if self.current():
            path = self.owner.store.directory / 'offline' / self.current()['id'] / 'replaced'; path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def remove(self):
        if self.current() and not self.owner.active:
            # Remove registration only: local edits and archives are never discarded.
            with self.owner.store.connect() as db: db.execute('DELETE FROM settings WHERE key=?', (PREFIX + self.current()['id'],))
            self.owner.catalogChanged.emit(); self.owner.changed.emit()

    def open_conflict(self, local):
        item, conflict = self.current(), self.conflicts.currentItem()
        if not item or not conflict: return
        root = item['local'] if local else self.owner.roots.get(item['id'])
        value = conflict.data(0, Qt.UserRole)
        if root and value['local' if local else 'remote']: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(root) / value['path'])))
        else: self.status.setText('Diese Fassung ist gelöscht oder der Server ist noch nicht verbunden.')

    def resolve(self, use):
        item, conflict = self.current(), self.conflicts.currentItem()
        if item and conflict:
            value = conflict.data(0, Qt.UserRole)
            self.owner.start(item, manual=True, choices={value['path']: dict(value, use=use)})
