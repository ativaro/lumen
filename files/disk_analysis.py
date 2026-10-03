"""TreeSize-style, read-only analysis using GNU du in a cancellable process."""
import heapq
import os
from pathlib import Path

from lumen_i18n import worker_process, tr

from PySide6.QtCore import QFileInfo, QProcess, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
                             QMessageBox, QPushButton, QStyledItemDelegate, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout)
from core import size_text
from preview import label

PATH, LOADED = Qt.UserRole, Qt.UserRole + 1


class SizeItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        if column in (1, 2):
            return (self.data(column, Qt.UserRole) or 0) < (other.data(column, Qt.UserRole) or 0)
        return self.text(column).casefold() < other.text(column).casefold()


class SizeBar(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        fraction = index.data(Qt.UserRole) or 0
        rect = QRectF(option.rect.adjusted(64, 12, -12, -12))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#2e3b49'))
        painter.drawRoundedRect(rect, 3, 3)
        rect.setWidth(rect.width() * min(fraction, 1))
        painter.setBrush(QColor('#7bc3ae'))
        painter.drawRoundedRect(rect, 3, 3)
        painter.restore()


class DiskAnalysis(QDialog):
    openPath = Signal(str)
    sizesReady = Signal(object)

    def __init__(self, path, parent=None, apparent=False):
        super().__init__(parent)
        self.proc = None
        self.queue = []
        self.errors = ''
        self.path = os.path.abspath(path)
        self.resize(1000, 740)
        self.setMinimumSize(720, 480)
        self.setWindowTitle(tr('Lumen · Speicheranalyse'))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        heading = QHBoxLayout()
        heading.addWidget(label(tr('Was braucht Platz?'), 'heading'), 1)
        choose = QPushButton(tr('Ordner wählen'))
        choose.clicked.connect(self.choose)
        heading.addWidget(choose)
        self.refresh_button = QPushButton(tr('Neu analysieren'))
        self.refresh_button.clicked.connect(self.restart)
        heading.addWidget(self.refresh_button)
        self.stop_button = QPushButton(tr('Stoppen'))
        self.stop_button.clicked.connect(self.stop)
        heading.addWidget(self.stop_button)
        layout.addLayout(heading)
        self.location = label(self.path, 'fileLocation')
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.location)
        self.apparent = QCheckBox(tr('Dateigröße statt belegtem Speicher'))
        self.apparent.setChecked(apparent)
        self.apparent.toggled.connect(self.restart)
        layout.addWidget(self.apparent)
        layout.addWidget(label(tr('Ordner aufklappen für Details · Anteil am jeweiligen Elternordner · Größte Einträge zuerst'), 'muted'))
        self.tree = QTreeWidget()
        self.tree.setObjectName('diskTree')
        self.tree.setHeaderLabels([tr('Ordner / Datei'), tr('Belegt'), tr('Anteil')])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnWidth(0, 480)
        self.tree.setColumnWidth(1, 135)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(2, 220)
        self.tree.setItemDelegateForColumn(2, SizeBar(self.tree))
        self.tree.setSortingEnabled(True)
        self.tree.sortItems(1, Qt.DescendingOrder)
        self.tree.itemExpanded.connect(self.expand)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self.open_item(item))
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.status = label('', 'muted')
        row.addWidget(self.status, 1)
        self.error_button = QPushButton(tr('Fehler ansehen'))
        self.error_button.clicked.connect(self.show_errors)
        self.error_button.hide()
        row.addWidget(self.error_button)
        open_button = QPushButton(tr('Ordner öffnen'))
        open_button.clicked.connect(lambda: self.open_item(self.tree.currentItem()))
        row.addWidget(open_button)
        layout.addLayout(row)
        layout.addWidget(label(tr('Versteckte Dateien sind enthalten. Verknüpfungen und andere Dateisysteme werden nicht durchlaufen. Komprimierung und gemeinsam genutzte Datenblöcke können die tatsächliche Belegung abweichen lassen.'), 'muted'))
        self.finished.connect(self.stop)
        self.restart()

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, tr('Speicher analysieren'), self.path)
        if path:
            self.path = path
            self.restart()

    def restart(self):
        self.stop()
        self.tree.clear()
        self.location.setText(self.path)
        self.tree.setHeaderLabels([tr('Ordner / Datei'), tr('Dateigröße') if self.apparent.isChecked() else tr('Belegt'), tr('Anteil')])
        self.root_item = SizeItem(self.tree, [Path(self.path).name or '/', '…', ''])
        self.root_item.setData(0, PATH, self.path)
        self.root_item.setIcon(0, QIcon.fromTheme('folder'))
        self.root_item.setExpanded(True)
        self.tree.setCurrentItem(self.root_item)
        if self.proc is None:
            self.scan(self.root_item)

    def expand(self, item):
        if item.data(0, LOADED) or item is getattr(self, 'scanning', None):
            return
        if self.proc:
            if item not in self.queue:
                self.queue.append(item)
        else:
            self.scan(item)

    def scan(self, item):
        # ponytail: du rescans an expanded subtree; cache a full walk if repeated drilling is too slow.
        self.scanning = item
        item.setData(0, LOADED, False)
        self.scan_path = item.data(0, PATH)
        self.buffer = b''
        self.entries = []
        self.entry_count = 0
        self.total = None
        self.errors = ''
        self.error_button.hide()
        self.status.setText(tr('Analysiere ') + self.scan_path + ' …')
        self.stop_button.setEnabled(True)
        proc = worker_process(self)
        self.proc = proc
        proc.readyReadStandardOutput.connect(self.read_output)
        proc.readyReadStandardError.connect(self.read_errors)
        proc.finished.connect(lambda code, _status: self.complete(proc, code))
        proc.errorOccurred.connect(lambda error: self.complete(proc, 1) if error == QProcess.FailedToStart else None)
        args = ['--all', '--max-depth=1', '--null', '--block-size=1', '--one-file-system']
        if self.apparent.isChecked():
            args.append('--apparent-size')
        proc.start('du', args + ['--', self.scan_path])

    def read_output(self):
        if self.proc is None:
            return
        self.buffer += bytes(self.proc.readAllStandardOutput())
        records = self.buffer.split(b'\0')
        self.buffer = records.pop()
        for record in records:
            size, path = record.split(b'\t', 1)
            path, size = os.fsdecode(path), int(size)
            if path == self.scan_path:
                self.total = size
            else:
                self.entry_count += 1
                entry = (size, self.entry_count, path)
                if len(self.entries) < 5000:
                    heapq.heappush(self.entries, entry)
                else:
                    heapq.heappushpop(self.entries, entry)
        self.status.setText(tr('Analysiere … {0:,} direkte Einträge gefunden', self.entry_count))

    def read_errors(self):
        if self.proc:
            data = bytes(self.proc.readAllStandardError()).decode(errors='replace')
            self.errors = (self.errors + data)[:12000]

    def complete(self, proc, code):
        if self.proc is not proc:
            return
        self.read_output()
        self.read_errors()
        self.result_code = code
        self.directories = set()
        if self.entries:
            # Metadata on a network mount can block too: keep even type checks off the UI.
            self.visible_paths = {entry[2] for entry in self.entries}
            self.buffer = b''
            types = worker_process(self)
            self.proc = types
            types.readyReadStandardOutput.connect(self.read_types)
            types.readyReadStandardError.connect(self.read_errors)
            types.finished.connect(lambda result, _status: self.render(types, result))
            types.errorOccurred.connect(lambda error: self.render(types, 1) if error == QProcess.FailedToStart else None)
            types.start('find', [self.scan_path, '-mindepth', '1', '-maxdepth', '1', '-type', 'd', '-print0'])
            proc.deleteLater()
        else:
            self.render(proc, code)

    def read_types(self):
        if self.proc:
            self.buffer += bytes(self.proc.readAllStandardOutput())
            paths = self.buffer.split(b'\0')
            self.buffer = paths.pop()
            self.directories.update(os.fsdecode(path) for path in paths if os.fsdecode(path) in self.visible_paths)

    def render(self, proc, code):
        if self.proc is not proc:
            return
        if self.entries:
            self.read_types()
        self.read_errors()
        code = code or self.result_code
        self.proc = None
        parent = self.scanning
        self.scanning = None
        self.tree.setSortingEnabled(False)
        parent.takeChildren()
        if self.total is not None:
            parent.setText(1, size_text(self.total))
            parent.setData(1, Qt.UserRole, self.total)
        for size, _order, path in sorted(self.entries, reverse=True):
            fraction = size / self.total if self.total else 0
            child = SizeItem(parent, [Path(path).name, size_text(size), f'{fraction:.1%}'])
            child.setData(0, PATH, path)
            child.setData(1, Qt.UserRole, size)
            child.setData(2, Qt.UserRole, fraction)
            child.setToolTip(0, path)
            directory = path in self.directories
            child.setIcon(0, QIcon.fromTheme('folder' if directory else 'text-x-generic'))
            if directory:
                child.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            else:
                child.setData(0, LOADED, True)
        parent.setData(0, LOADED, not code)
        if not parent.childCount():
            parent.setChildIndicatorPolicy(QTreeWidgetItem.DontShowIndicatorWhenChildless)
        self.tree.setSortingEnabled(True)
        self.stop_button.setEnabled(False)
        if code:
            self.errors = self.errors or proc.errorString()
            self.status.setText(tr('Unvollständig: Einige Einträge konnten nicht gelesen werden. Neu analysieren versucht es erneut.'))
            self.error_button.show()
            self.queue.clear()
        else:
            note = tr(' · nur die größten 5.000 von {0:,} Einträgen angezeigt', self.entry_count) if self.entry_count > 5000 else ''
            self.status.setText(tr('{0} · {1:,} direkte Einträge', size_text(self.total or 0), self.entry_count) + note)
            if self.apparent.isChecked() and self.total is not None:
                self.sizesReady.emit({self.scan_path: self.total, **{
                    path: size for size, _order, path in self.entries if path in self.directories}})
        proc.deleteLater()
        if self.queue:
            self.scan(self.queue.pop(0))

    def stop(self):
        self.queue.clear()
        if self.proc:
            proc, self.proc = self.proc, None
            proc.kill()
            proc.waitForFinished(1000)
            proc.deleteLater()
            self.scanning = None
            self.status.setText(tr('Analyse abgebrochen. Angezeigte Werte können unvollständig sein.'))
        self.stop_button.setEnabled(False)

    def open_item(self, item):
        if item:
            path = item.data(0, PATH)
            folder = path if QFileInfo(path).isDir() else str(Path(path).parent)
            self.openPath.emit(folder)
            self.accept()

    def show_errors(self):
        box = QMessageBox(QMessageBox.Warning, tr('Analyse unvollständig'),
                          tr('Nicht alle Daten konnten gelesen werden.'), QMessageBox.Ok, self)
        box.setDetailedText(self.errors)
        box.exec()
