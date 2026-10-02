"""A native page workbench; edits are a recipe until exported to a new PDF."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from PyQt5.QtCore import QProcess, QTimer, Qt, QRectF
from PyQt5.QtGui import QColor, QPen, QPixmap
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSplitter, QVBoxLayout, QWidget)


class PageCanvas(QGraphicsView):
    def __init__(self, parent):
        super().__init__(parent); self.owner = parent; self.setScene(QGraphicsScene(self)); self.page = None; self.origin = None; self.rubber = None
        self.setAccessibleName('PDF-Seitenvorschau · Schwärzungsbereiche mit der Maus aufziehen')

    def display(self, path, item):
        self.scene().clear(); self.page = item; self.rubber = None; self.origin = None
        pixmap = QPixmap(path); self.scene().addPixmap(pixmap); self.area = QRectF(pixmap.rect()); self.scene().setSceneRect(self.area)
        self.draw_boxes(); self.fitInView(self.area, Qt.KeepAspectRatio)

    def draw_boxes(self):
        for box in self.page.data(Qt.UserRole)['boxes']:
            x0,y0,x1,y1 = box
            self.scene().addRect(QRectF(x0*self.area.width(),y0*self.area.height(),(x1-x0)*self.area.width(),(y1-y0)*self.area.height()), QPen(QColor('#111111')), QColor(0,0,0,225))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.page: self.fitInView(self.area, Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            scale = 1.2 if event.angleDelta().y() > 0 else 1/1.2; self.scale(scale, scale); event.accept()
        else: super().wheelEvent(event)

    def mousePressEvent(self, event):
        if self.page and self.owner.redact.isChecked() and event.button() == Qt.LeftButton:
            point = self.mapToScene(event.pos())
            if self.area.contains(point):
                self.origin = point; self.rubber = self.scene().addRect(QRectF(point,point), QPen(QColor('#ef6262'),2), QColor(0,0,0,120)); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.rubber.setRect(QRectF(self.origin,self.mapToScene(event.pos())).normalized().intersected(self.area)); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.origin is not None:
            rect = self.rubber.rect(); self.origin = None
            if rect.width() > 3 and rect.height() > 3:
                value = self.page.data(Qt.UserRole); value['boxes'].append([rect.left()/self.area.width(),rect.top()/self.area.height(),rect.right()/self.area.width(),rect.bottom()/self.area.height()]); self.page.setData(Qt.UserRole,value)
                self.rubber.setBrush(QColor(0,0,0,225)); self.rubber.setPen(QPen(QColor('#111111')))
                self.owner.status.setText('Bereich markiert. Erst der PDF-Export entfernt den Inhalt dauerhaft.')
            else: self.scene().removeItem(self.rubber)
            self.rubber = None; return
        super().mouseReleaseEvent(event)


class DocumentWorkshop(QDialog):
    def __init__(self, paths=(), parent=None):
        super().__init__(parent); self.proc = None; self.temp = tempfile.TemporaryDirectory(prefix='lumen-workshop-')
        self.setWindowTitle('Dokumentenwerkstatt'); self.resize(1150,850)
        layout = QVBoxLayout(self); row = QHBoxLayout(); layout.addLayout(row)
        self.controls = []
        for title, callback in [('PDFs hinzufügen …', self.add), ('Seite entfernen', self.remove), ('Drehen', self.rotate), ('Markierungen löschen', self.clear_boxes)]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button); self.controls.append(button)
        self.redact = QCheckBox('Schwärzen'); row.addWidget(self.redact); self.controls.append(self.redact)
        splitter = QSplitter(); layout.addWidget(splitter,1)
        self.pages = QListWidget(); self.pages.setSelectionMode(QAbstractItemView.ExtendedSelection); self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setAccessibleName('PDF-Seiten · ziehen zum Umordnen · mehrere markieren zum Extrahieren'); splitter.addWidget(self.pages)
        self.canvas = PageCanvas(self); splitter.addWidget(self.canvas); splitter.setSizes([290,850])
        self.pages.currentItemChanged.connect(self.preview)
        row = QHBoxLayout(); layout.addLayout(row)
        self.ocr = QCheckBox('Scans durchsuchbar machen · lokal'); row.addWidget(self.ocr)
        self.dpi = QComboBox(); self.dpi.addItems(['150 dpi','200 dpi','300 dpi']); self.dpi.setCurrentIndex(1); self.dpi.setAccessibleName('Qualität für Schwärzungen und Texterkennung'); row.addWidget(self.dpi)
        for title, callback in [('Auswahl als PDF …', lambda: self.save(True)), ('Alles als PDF …', lambda: self.save(False))]:
            button = QPushButton(title); button.clicked.connect(callback); row.addWidget(button); self.controls.append(button)
        self.cancel = QPushButton('Abbrechen'); self.cancel.clicked.connect(self.cancel_process); self.cancel.hide(); row.addWidget(self.cancel)
        hint = QLabel('Seiten ziehen zum Ordnen · Strg+Mausrad zum Zoomen · Export immer als neue PDF.\n'
                      'Geschwärzte Seiten werden neu als Bild aufgebaut; mit Texterkennung erhalten sie eine neue Textebene.'); hint.setWordWrap(True); layout.addWidget(hint)
        self.status = QLabel('PDFs hinzufügen, um zu beginnen.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.timeout)
        if paths: QTimer.singleShot(0, lambda: self.load(list(paths)))

    def add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'PDFs hinzufügen', str(Path.home()), 'PDF (*.pdf)')
        if paths: self.load(paths)

    def load(self, paths):
        def loaded(pages):
            for page in pages:
                item = QListWidgetItem(Path(page['path']).name + f" · Seite {page['page'] + 1}"); item.setData(Qt.UserRole,page); item.setToolTip(page['path']); self.pages.addItem(item)
            self.status.setText(f'{self.pages.count()} Seiten · Originaldateien unverändert')
            if self.pages.currentRow() < 0: self.pages.setCurrentRow(0)
        self.run(dict(action='inspect', paths=paths), loaded)

    def run(self, request, callback):
        if self.proc: return
        proc = QProcess(self); self.proc = proc; self.buffer = b''; self.result = None; self.error = ''
        for widget in self.controls + [self.pages, self.ocr, self.dpi]: widget.setEnabled(False)
        self.cancel.show(); self.canvas.setEnabled(False); self.status.setText('PDF wird verarbeitet …')
        def read():
            self.buffer += bytes(proc.readAllStandardOutput())
            while b'\n' in self.buffer:
                line,self.buffer = self.buffer.split(b'\n',1)
                try: event = json.loads(line)
                except ValueError: continue
                self.timer.start(180000)
                if 'progress' in event: self.status.setText(event['progress'])
                if 'result' in event: self.result = event['result']
                if 'error' in event: self.error = event['error']
        def done(code):
            if self.proc is not proc: return
            read(); self.proc = None; self.timer.stop(); self.cancel.hide(); self.canvas.setEnabled(True)
            for widget in self.controls + [self.pages, self.ocr, self.dpi]: widget.setEnabled(True)
            proc.deleteLater()
            if code or self.result is None: self.status.setText(self.error or 'Vorgang unterbrochen. Originale sind unverändert.')
            else: callback(self.result)
        proc.readyReadStandardOutput.connect(read); proc.finished.connect(done)
        proc.errorOccurred.connect(lambda e: done(1) if e == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(Path(__file__).with_name('document_workshop.py'))]); proc.write((json.dumps(request)+'\n').encode()); proc.closeWriteChannel(); self.timer.start(180000)

    def preview(self, item, *_):
        if not item or self.proc: return
        def rendered(path): self.canvas.display(path,item); self.status.setText(item.text())
        self.run(dict(action='render',page=item.data(Qt.UserRole),target=str(Path(self.temp.name)/'preview.png')), rendered)

    def remove(self):
        self.pages.blockSignals(True)
        for item in self.pages.selectedItems(): self.pages.takeItem(self.pages.row(item))
        self.pages.blockSignals(False); self.canvas.scene().clear(); self.canvas.page = None
        self.preview(self.pages.currentItem())

    def rotate(self):
        item = self.pages.currentItem()
        if not item: return
        value = item.data(Qt.UserRole); value['rotation'] = (value['rotation'] + 90) % 360
        value['boxes'] = [[1-b[3],b[0],1-b[1],b[2]] for b in value['boxes']]
        item.setData(Qt.UserRole,value); self.preview(item)

    def clear_boxes(self):
        item = self.pages.currentItem()
        if item:
            value = item.data(Qt.UserRole); value['boxes'] = []; item.setData(Qt.UserRole,value); self.preview(item)

    def save(self, selected):
        pages = [self.pages.item(i).data(Qt.UserRole) for i in range(self.pages.count()) if not selected or self.pages.item(i).isSelected()]
        if not pages: self.status.setText('Bitte mindestens eine Seite auswählen.'); return
        path, _ = QFileDialog.getSaveFileName(self, 'Neue PDF speichern', str(Path(pages[0]['path']).with_name('Bearbeitet.pdf')), 'PDF (*.pdf)')
        if not path: return
        if not path.lower().endswith('.pdf'): path += '.pdf'
        self.run(dict(action='export',pages=pages,target=path,ocr=self.ocr.isChecked(),dpi=int(self.dpi.currentText().split()[0])), lambda target: self.status.setText('Gespeichert und geprüft: ' + target))

    def cancel_process(self):
        if self.proc:
            pid = int(self.proc.processId())
            if pid:
                try: os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError: self.proc.kill()
            else: self.proc.kill()
            self.proc.waitForFinished(1000)

    def timeout(self): self.error = 'Zeitlimit erreicht. Originale bleiben unverändert.'; self.cancel_process()

    def done(self, result):
        self.cancel_process(); self.temp.cleanup(); super().done(result)


def open_workshop(parent, paths=()):
    from lumen_setup import executable
    if not executable('pymupdf'):
        from setup_dialog import open_setup
        open_setup(parent)
        if not executable('pymupdf'): return
    dialog = DocumentWorkshop(paths, parent); dialog.exec_(); dialog.deleteLater()
