"""Folder retention controls, file history, comparison and guarded restore."""
import json
import os
from pathlib import Path
import sys
import tempfile
from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSpinBox, QSplitter, QPlainTextEdit, QVBoxLayout, QWidget)
from lumen_versions import Versions, start
from preview import Preview


class VersionsDialog(QDialog):
    def __init__(self, parent=None, path=None):
        super().__init__(parent); self.versions = Versions(); self.path = path; self.proc = None; self.expected = None; self.compared = None
        self.temp = tempfile.TemporaryDirectory(prefix='lumen-versions-')
        self.setWindowTitle('Dateiversionen'); self.resize(1100, 800)
        layout = QVBoxLayout(self)
        hint = QLabel('Versionen entstehen ab dem Aktivieren, auch bei Änderungen durch andere Programme.\n'
                      'Kurze Zwischenstände zwischen zwei Prüfungen können fehlen. Die Sicherungen liegen auf diesem PC.'); hint.setWordWrap(True); layout.addWidget(hint)
        controls = QHBoxLayout(); layout.addLayout(controls)
        for title, callback in [('Ordner sichern …', self.add_root), ('Überwachte Ordner …', self.configure), ('Aktualisieren', self.refresh), ('Alle Dateien', self.all_files)]:
            button = QPushButton(title); button.clicked.connect(callback); controls.addWidget(button)
        splitter = QSplitter(); layout.addWidget(splitter, 1)
        self.list = QListWidget(); self.list.currentItemChanged.connect(self.compare); splitter.addWidget(self.list)
        detail = QWidget(); box = QVBoxLayout(detail); splitter.addWidget(detail); splitter.setSizes([450,650])
        self.diff = QPlainTextEdit(); self.diff.setReadOnly(True); self.diff.setAccessibleName('Unterschiede zwischen gespeicherter und aktueller Fassung'); box.addWidget(self.diff)
        self.preview = Preview(); box.addWidget(self.preview, 1)
        self.restore_button = QPushButton('Diese Fassung wiederherstellen'); self.restore_button.clicked.connect(self.restore); self.restore_button.setEnabled(False); layout.addWidget(self.restore_button)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.refresh()

    def all_files(self): self.path = None; self.refresh()

    def refresh(self):
        if self.proc: return
        self.list.clear()
        from datetime import datetime
        for version in self.versions.history(self.path):
            item = QListWidgetItem(Path(version['path']).name + ' · ' + datetime.fromtimestamp(version['created']).strftime('%d.%m.%Y %H:%M:%S') + (' · Gelöscht' if not version['hash'] else f" · {version['size']:,} Bytes"))
            item.setData(Qt.UserRole, version); item.setToolTip(version['path']); self.list.addItem(item)
        statuses = [Path(root).name + ': ' + self.versions.store.setting('versions/status/' + root, {}).get('status','Erste Sicherung steht aus') for root in self.versions.config()['roots']]
        self.status.setText(f'{self.list.count()} gespeicherte Fassungen · ' + str(self.versions.objects.parent) + '\n' + '\n'.join(statuses))

    def add_root(self):
        path = QFileDialog.getExistingDirectory(self, 'Versionen für Ordner aktivieren', str(Path(self.path).parent) if self.path else str(Path.home()))
        if not path: return
        try:
            config = self.versions.config()
            self.versions.configure(config['roots'] + [path], config['interval'], config['copies'], config['days'], config['bytes'] // 1024**3)
            start(self.versions.store); self.status.setText('Sicherung aktiviert. Die erste Fassung wird im Hintergrund erstellt.')
        except (ValueError, OSError) as error: self.status.setText(str(error))

    def configure(self):
        config = self.versions.config(); dialog = QDialog(self); dialog.setWindowTitle('Versionen aufbewahren'); dialog.resize(650, 400)
        layout = QVBoxLayout(dialog); roots = QListWidget(); roots.addItems(config['roots']); layout.addWidget(roots)
        remove = QPushButton('Ausgewählten Ordner nicht mehr sichern'); remove.clicked.connect(lambda: roots.takeItem(roots.currentRow())); layout.addWidget(remove)
        form = QFormLayout(); layout.addLayout(form); fields = []
        for title, key, low, high, factor in [('Prüfen alle (Sekunden)', 'interval',10,3600,1), ('Fassungen pro Datei','copies',2,1000,1), ('Aufbewahrung (Tage)','days',1,3650,1), ('Speichergrenze (GiB)','bytes',1,1000,1024**3)]:
            field = QSpinBox(); field.setRange(low,high); field.setValue(config[key] // factor); form.addRow(title,field); fields.append(field)
        error = QLabel(); layout.addWidget(error)
        def save():
            try:
                self.versions.configure([roots.item(i).text() for i in range(roots.count())], *(f.value() for f in fields))
                start(self.versions.store); dialog.accept()
            except (ValueError, OSError) as exc: error.setText(str(exc))
        button = QPushButton('Speichern'); button.clicked.connect(save); layout.addWidget(button); dialog.exec_()

    def run(self, args, callback):
        if self.proc: return
        proc = QProcess(self); self.proc = proc; self.restore_button.setEnabled(False); self.list.setEnabled(False)
        from PyQt5.QtCore import QProcessEnvironment, QTimer
        env = QProcessEnvironment.systemEnvironment(); env.insert('LUMEN_DATA', str(self.versions.store.directory)); proc.setProcessEnvironment(env)
        timer = QTimer(proc); timer.setSingleShot(True); timer.timeout.connect(proc.kill)
        def finished(code):
            if self.proc is not proc: return
            self.proc = None; timer.stop(); self.list.setEnabled(True)
            try:
                result = json.loads(bytes(proc.readAllStandardOutput()))
                if code or result.get('error'): raise ValueError(result.get('error', 'Vorgang fehlgeschlagen.'))
                callback(result)
            except (ValueError, OSError) as error: self.status.setText(str(error))
            proc.deleteLater()
        proc.finished.connect(finished); proc.errorOccurred.connect(lambda e: finished(1) if e == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__).with_name('lumen_versions.py')), *args]); timer.start(300000)

    def compare(self, item, *_):
        self.restore_button.setEnabled(False); self.compared = None
        if not item: return
        version = item.data(Qt.UserRole); self.status.setText('Fassungen vergleichen …')
        def ready(result):
            self.expected = result['expected']; self.compared = version['id']; self.diff.setPlainText(result['detail'])
            if result.get('preview'): self.preview.show_path(result['preview'])
            else: self.preview.clear()
            self.restore_button.setEnabled(bool(version['hash'])); self.status.setText(version['path'])
        self.run(['--compare', str(version['id']), self.temp.name], ready)

    def restore(self):
        if not self.compared: return
        self.status.setText('Wiederherstellen · aktuelle Fassung wird zuvor gesichert …')
        def ready(result):
            self.refresh(); self.status.setText('Wiederhergestellt: ' + result['path'])
        self.run(['--restore', str(self.compared), json.dumps(self.expected)], ready)

    def done(self, result):
        if self.proc:
            self.status.setText('Bitte den laufenden Vergleich oder die Wiederherstellung abschließen lassen.'); return
        self.preview.cancel(); self.temp.cleanup(); super().done(result)
