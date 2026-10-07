"""Motif search and photo review in the existing Files visual language."""
import json
import sys
from pathlib import Path
from lumen_i18n import worker_process, tr

from PySide6.QtCore import Qt, QProcess, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QSplitter, QMessageBox)
from preview import Preview, label
from photo_tools import available, runtime
from gallery import Gallery
from core import FileWorker


class PhotoToolsDialog(QDialog):
    folderRequested = Signal(str)

    def __init__(self, directory, mode='search', query='', parent=None):
        super().__init__(parent)
        self.directory, self.mode = str(Path(directory).absolute()), mode
        if parent and hasattr(parent, 'network'): self.network = parent.network
        self.proc = None; self.worker = None; self.buffer = b''; self.completed = False; self.limited = False
        self.setWindowTitle((tr('Bilder nach Motiv suchen') if mode == 'search' else tr('Fotos aufräumen')) + ' — Lumen Files')
        self.resize(1140, 780); self.setMinimumSize(820, 550)
        layout = QVBoxLayout(self); layout.setContentsMargins(24, 22, 24, 20); layout.setSpacing(14)
        layout.addWidget(label(tr('Bilder nach Motiv suchen') if mode == 'search' else tr('Fotos in Ruhe sortieren'), 'heading'))
        layout.addWidget(label(self.directory + tr(' · einschließlich Unterordnern · lokal'), 'muted'))
        layout.addWidget(label(tr('Beschreibe ein Motiv, zum Beispiel „Berge am See“. Die Suche vergleicht Bildinhalte statt Dateinamen.')
            if mode == 'search' else tr('Ähnliche Bildserien, wenig Details und Screenshots prüfen. Du entscheidest, was bleibt.'), 'muted'))
        row = QHBoxLayout(); layout.addLayout(row)
        self.query = QLineEdit(query); self.query.setPlaceholderText(tr('Welches Bild suchst du?')); self.query.setMaxLength(500)
        self.query.setAccessibleName(tr('Gesuchtes Bildmotiv')); self.query.returnPressed.connect(self.start)
        if mode == 'search': row.addWidget(self.query, 1)
        self.start_button = QPushButton(tr('Motive suchen') if mode == 'search' else tr('Ordner prüfen')); self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start); row.addWidget(self.start_button)
        self.stop = QPushButton(tr('Anhalten')); self.stop.clicked.connect(self.cancel); self.stop.setEnabled(False); row.addWidget(self.stop)
        self.setup = QPushButton(tr('Lokale Bildsuche einrichten …')); self.setup.clicked.connect(self.setup_search)
        self.setup.setVisible(mode == 'search' and not available()); layout.addWidget(self.setup)
        self.override = QCheckBox(tr('Diese Analyse auch bei Spiel, Aufnahme oder hoher GPU-Auslastung ausführen'))
        self.override.setToolTip(tr('Gilt nur für den nächsten Start in diesem Fenster. Die allgemeine Hintergrundpause bleibt gespeichert.'))
        layout.addWidget(self.override)
        split = QSplitter(); layout.addWidget(split, 1)
        self.results = QTreeWidget(); self.results.setHeaderLabels([tr('Datei'), tr('Vorschlag') if mode == 'tidy' else tr('Motivähnlichkeit')])
        self.results.setRootIsDecorated(False); self.results.setColumnWidth(0, 220); self.results.setAccessibleName(tr('Bildergebnisse'))
        self.results.currentItemChanged.connect(self.selected); self.results.itemDoubleClicked.connect(self.open_image)
        split.addWidget(self.results)
        self.preview = Preview(); split.addWidget(self.preview); split.setSizes([600, 410])
        self.preview.openImage.connect(lambda path, editing: self.open_image(editing=editing))
        self.status = label(tr('Bereit. Es wird erst nach deinem Klick analysiert.'), 'muted'); layout.addWidget(self.status)
        row = QHBoxLayout(); layout.addLayout(row)
        self.open_button = QPushButton(tr('Groß ansehen')); self.open_button.clicked.connect(self.open_image); row.addWidget(self.open_button)
        self.folder = QPushButton(tr('Im Ordner zeigen')); self.folder.clicked.connect(self.open_folder); row.addWidget(self.folder)
        self.trash_button = QPushButton(tr('Auswahl in den Papierkorb')); self.trash_button.setObjectName('danger')
        self.trash_button.setVisible(mode == 'tidy'); self.trash_button.clicked.connect(self.trash); row.addWidget(self.trash_button)
        self.results.itemChanged.connect(self.buttons); row.addStretch()
        close = QPushButton(tr('Schließen')); close.clicked.connect(self.reject); row.addWidget(close)
        self.deadline = QTimer(self); self.deadline.setSingleShot(True); self.deadline.setInterval(180000)
        self.deadline.timeout.connect(lambda: self.cancel(tr('Keine Antwort seit drei Minuten. Angehalten; der bisherige Index bleibt erhalten.')))
        self.buttons()

    def buttons(self, *_):
        busy = self.proc is not None or self.worker is not None
        self.start_button.setEnabled(not busy); self.query.setEnabled(not busy); self.override.setEnabled(not busy)
        self.stop.setEnabled(self.proc is not None)
        self.open_button.setEnabled(self.results.currentItem() is not None and self.worker is None)
        self.folder.setEnabled(self.results.currentItem() is not None)
        self.trash_button.setEnabled(not busy and any(self.results.topLevelItem(i).checkState(0) == Qt.Checked for i in range(self.results.topLevelItemCount())))

    def setup_search(self):
        from setup_dialog import open_setup
        open_setup(self, page=0)
        self.setup.setVisible(not available())

    def start(self):
        if self.proc or self.worker: return
        if self.mode == 'search' and not available():
            self.status.setText(tr('Bitte die lokale Bildsuche einmalig einrichten. Danach werden keine Fotos übertragen.')); return
        if self.mode == 'search' and not self.query.text().strip(): self.query.setFocus(); return
        self.results.clear(); self.preview.clear(); self.buffer = b''; self.completed = self.limited = False
        self.proc = worker_process(self); proc = self.proc
        proc.readyReadStandardOutput.connect(self.read)
        proc.finished.connect(lambda code: self.finished_job(proc, code))
        proc.errorOccurred.connect(lambda error: self.finished_job(proc, 1) if error == QProcess.FailedToStart else None)
        python = str(runtime() / 'env-v1/bin/python') if self.mode == 'search' else sys.executable
        args = [str(Path(__file__).with_name('photo_tools.py')), self.mode, self.directory, '--query', self.query.text()]
        if self.override.isChecked(): args.append('--override')
        self.status.setText(tr('Bilder werden vorbereitet …')); self.buttons(); proc.start(python, args); self.deadline.start()

    def read(self):
        if not self.proc: return
        self.buffer += bytes(self.proc.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: event = json.loads(line)
            except ValueError: continue
            self.deadline.start()
            self.limited |= event.get('limited', False)
            if event.get('status'): self.status.setText(event['status'])
            if event.get('error'): self.status.setText(tr('Analyse fehlgeschlagen: ') + event['error'])
            self.completed |= event.get('done', False)
            if 'item' in event:
                result = event['item']; item = QTreeWidgetItem([Path(result['path']).name, result['group']])
                item.setData(0, Qt.UserRole, result); item.setToolTip(0, result['path']); item.setToolTip(1, result['reason'])
                if self.mode == 'tidy': item.setCheckState(0, Qt.Unchecked)
                self.results.addTopLevelItem(item)

    def finished_job(self, proc, code):
        if self.proc is not proc: return
        self.read(); self.proc = None; self.deadline.stop()
        if code and not self.status.text().startswith(tr('Analyse fehlgeschlagen')):
            self.status.setText(tr('Analyse beendet, bevor sie fertig war. Erneut versuchen oder Einrichtung prüfen.'))
        elif self.limited: self.status.setText(self.status.text() + tr(' · Teilanalyse: Dateigrenze erreicht'))
        proc.deleteLater(); self.buttons()

    def cancel(self, message=tr('Angehalten. Bereits indizierte Bilder bleiben für die nächste Suche verfügbar.')):
        if self.proc:
            proc, self.proc = self.proc, None; proc.kill(); proc.waitForFinished(1500); proc.deleteLater()
        self.deadline.stop(); self.status.setText(message if isinstance(message, str) else tr('Analyse angehalten.')); self.buttons()

    def selected(self, item, *_):
        if item:
            result = item.data(0, Qt.UserRole); self.preview.show_path(result['path'])
            self.preview.note.setText(result['reason'])
        self.buttons()

    def open_image(self, *_, editing=False):
        item = self.results.currentItem()
        if not item or self.worker: return
        paths = list(dict.fromkeys(self.results.topLevelItem(i).data(0, Qt.UserRole)['path'] for i in range(self.results.topLevelItemCount())))
        self.preview.cancel(); gallery = Gallery(paths, item.data(0, Qt.UserRole)['path'], self)
        gallery.editor_button.setChecked(editing)
        gallery.exec(); gallery.deleteLater()

    def open_folder(self):
        item = self.results.currentItem()
        if item: self.folderRequested.emit(str(Path(item.data(0, Qt.UserRole)['path']).parent))

    def trash(self):
        if self.proc or self.worker: return
        selected = {self.results.topLevelItem(i).data(0, Qt.UserRole)['path']: self.results.topLevelItem(i).data(0, Qt.UserRole)['stamp']
                    for i in range(self.results.topLevelItemCount()) if self.results.topLevelItem(i).checkState(0) == Qt.Checked}
        if not selected: return
        if QMessageBox.question(self, tr('Auswahl prüfen'), tr('{0} ausgewählte Bilder in den Papierkorb verschieben?\nBei Netzwerkordnern kann der Papierkorb fehlen; dann bleibt die Datei erhalten.', len(selected))) != QMessageBox.Yes: return
        self.preview.clear(); self.worker = FileWorker('trash', list(selected), expected=selected)
        worker = self.worker
        def complete(done, errors):
            for i in reversed(range(self.results.topLevelItemCount())):
                if self.results.topLevelItem(i).data(0, Qt.UserRole)['path'] in done: self.results.takeTopLevelItem(i)
            self.status.setText(tr('{0} Bilder im Papierkorb', len(done)) + (' · ' + '\n'.join(errors) if errors else ''))
        def finished(): self.worker = None; worker.deleteLater(); self.buttons()
        worker.completed.connect(complete); worker.finished.connect(finished); self.buttons(); worker.start()

    def done(self, result):
        if self.worker:
            self.status.setText(tr('Bitte den laufenden Papierkorb-Vorgang abwarten.')); return
        self.cancel(); self.preview.cancel(); super().done(result)
