"""Large image browsing with bounded prefetch and explicit, backed-up edits."""
import json
import sys
from collections import OrderedDict
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, Qt, QTemporaryDir, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPixmap, QTransform
from PyQt5.QtWidgets import QDialog, QGraphicsScene, QGraphicsView, QMessageBox
from core import FileWorker

ROOT = Path(__file__).resolve().parent


class ImageLoader(QObject):
    ready = pyqtSignal(str, object, object)
    failed = pyqtSignal(str, str)

    def __init__(self, parent=None, max_side=2560, cache_limit=3):
        super().__init__(parent)
        self.max_side, self.cache_limit = max_side, cache_limit
        self.cache = OrderedDict()
        self.pending = []
        self.proc = None
        self.loading = None
        self.temp = QTemporaryDir()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def cancel(self):
        self.timer.stop()
        if self.proc:
            proc, self.proc = self.proc, None
            proc.kill()
            proc.waitForFinished(1000)
            proc.deleteLater()
        self.loading = None

    def want(self, paths):
        self.pending = list(dict.fromkeys(paths))
        current = paths[0]
        if current in self.cache:
            self.cache.move_to_end(current)
            self.ready.emit(current, *self.cache[current])
        elif self.loading != current:
            self.cancel()
        self.advance()

    def advance(self):
        if self.proc:
            return
        self.pending = [path for path in self.pending if path not in self.cache]
        if not self.pending:
            return
        path = self.pending.pop(0)
        self.loading = path
        output = str(Path(self.temp.path()) / 'image.png')
        proc = QProcess(self)
        self.proc = proc

        def finished(code, _status):
            if self.proc is not proc:
                return
            self.timer.stop()
            self.proc = self.loading = None
            try:
                if code:
                    raise ValueError('Das Bild konnte nicht gelesen werden.')
                data = json.loads(bytes(proc.readAllStandardOutput()))
                pixmap = QPixmap()
                if data['kind'] == 'image':
                    # The worker reuses its output name; bypass Qt's filename cache.
                    pixmap.loadFromData(Path(output).read_bytes())
                if pixmap.isNull():
                    raise ValueError(data.get('message', 'Das Bild konnte nicht gelesen werden.'))
                self.cache[path] = (pixmap, data)
                # Bounded previews; the gallery keeps both neighbors, the grid small thumbnails.
                while len(self.cache) > self.cache_limit:
                    self.cache.popitem(last=False)
                self.ready.emit(path, pixmap, data)
            except (OSError, ValueError, KeyError) as exc:
                self.failed.emit(path, str(exc))
            proc.deleteLater()
            self.advance()

        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda err: self.fail_start(proc, path) if err == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(ROOT / 'preview.py'), '--data', path, output, str(self.max_side)])
        self.timer.start(12000)

    def fail_start(self, proc, path):
        if self.proc is proc:
            self.cancel()
            self.failed.emit(path, 'Der Bildprozess konnte nicht gestartet werden.')
            self.advance()

    def timeout(self):
        path = self.loading
        self.cancel()
        self.failed.emit(path, 'Das Laden hat zu lange gedauert. Du kannst zum nächsten Bild wechseln.')
        self.advance()


class ImageCanvas(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = self.scene().addPixmap(QPixmap())
        self.setBackgroundBrush(QColor('#13171c'))
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.fitted = True

    def display(self, pixmap):
        self.item.setPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        self.fit()

    def fit(self):
        self.fitted = True
        if not self.item.pixmap().isNull():
            self.fitInView(self.item, Qt.KeepAspectRatio)

    def actual_size(self):
        self.fitted = False
        self.resetTransform()

    def zoom(self, factor):
        scale = self.transform().m11() * factor
        if .01 < scale < 20:
            self.fitted = False
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit()


class Gallery(QDialog):
    def __init__(self, paths, current, parent=None):
        super().__init__(parent)
        self.paths = list(dict.fromkeys(map(str, paths)))
        self.index = self.paths.index(str(current))
        self.operations = []
        self.data = None
        self.original = QPixmap()
        self.busy = False
        self.save_proc = self.worker = None
        self.resize(1240, 850)
        self.setMinimumSize(900, 560)
        self.setWindowTitle('Lumen · Bilder')
        from gallery_widgets import build_gallery
        self.loader = ImageLoader(self)
        build_gallery(self, ImageCanvas(), ImageLoader(self, max_side=192, cache_limit=48))
        self.loader.ready.connect(self.loaded)
        self.loader.failed.connect(self.failed)
        self.finished.connect(self.loader.cancel)
        self.finished.connect(self.filmstrip.stop)
        QTimer.singleShot(0, self.load)

    @property
    def path(self):
        return self.paths[self.index] if self.paths else None

    def controls(self):
        for button in self.actions:
            button.setEnabled(not self.busy)
        self.filmstrip.setEnabled(not self.busy)
        self.previous.setEnabled(not self.busy and self.index > 0)
        self.next.setEnabled(not self.busy and self.index < len(self.paths) - 1)
        for button in (self.left, self.right, self.mirror):
            button.setEnabled(not self.busy and self.data is not None)
        for button in (self.undo_button, self.save_button):
            button.setEnabled(not self.busy and bool(self.operations))

    def load(self):
        self.data = None
        self.operations.clear()
        self.original = QPixmap()
        self.canvas.display(QPixmap())
        self.title.setText(Path(self.path).name)
        self.counter.setText(f'{self.index + 1} von {len(self.paths)}')
        self.filmstrip.select(self.paths, self.index)
        self.dimensions.clear()
        self.title.setToolTip(self.path)
        parent = self.parent()
        remote = parent.network.remote(self.path) if parent and hasattr(parent, 'network') else None
        self.source.setText(('NAS · ' if QUrl(remote).scheme() == 'smb' else 'Netzwerk · ') + QUrl(remote).host()
                            if remote else 'Dieser PC')
        self.source.setToolTip(remote or self.path)
        self.status.setText('Bild laden …')
        self.controls()
        neighbors = [self.path] + [self.paths[i] for i in (self.index + 1, self.index - 1)
                                   if 0 <= i < len(self.paths)]
        self.loader.want(neighbors)

    def loaded(self, path, pixmap, data):
        if path != self.path or self.data is not None:
            return
        self.original, self.data = pixmap, data
        self.dimensions.setText(f"{data['width']} × {data['height']} px")
        self.canvas.display(pixmap)
        self.status.setText(f"{data['width']} × {data['height']} px · Ansicht bis 2560 px · Pfeiltasten blättern · Mausrad zoomt")
        self.controls()

    def failed(self, path, message):
        if path == self.path:
            self.status.setText(message)

    def step(self, direction):
        self.jump(self.index + direction)

    def jump(self, destination):
        if self.busy or not 0 <= destination < len(self.paths) or destination == self.index:
            self.filmstrip.select(self.paths, self.index)
            return
        def change():
            self.index = destination
            self.load()
        self.leave_edits(change)
        self.filmstrip.select(self.paths, self.index)

    def edit(self, operation):
        if self.busy or self.data is None:
            return
        self.editor_button.setChecked(True)
        self.operations.append(operation)
        self.render_edits()

    def undo(self):
        if self.operations and not self.busy:
            self.operations.pop()
            self.render_edits()

    def render_edits(self):
        pixmap = self.original
        for operation in self.operations:
            transform = QTransform().scale(-1, 1) if operation == 'mirror' else QTransform().rotate(90 if operation == 'right' else -90)
            pixmap = pixmap.transformed(transform)
        self.canvas.display(pixmap)
        self.title.setText(Path(self.path).name + (' · Ungespeichert' if self.operations else ''))
        self.status.setText('Speichern: volle Auflösung + Original in .lumen-originals. JPEG wird neu komprimiert.'
                            if self.operations else 'Keine ungespeicherten Änderungen.')
        self.controls()

    def leave_edits(self, action):
        if self.operations:
            choice = QMessageBox.question(self, 'Änderungen speichern?',
                'Änderungen vor dem Verlassen dieses Bildes speichern?',
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.Save:
                self.save(action)
                return
        action()

    def save(self, after=None):
        if self.busy or not self.operations or not self.data:
            return
        self.busy = True
        self.controls()
        self.status.setText('Original sichern und Änderungen speichern …')
        proc = QProcess(self)
        self.save_proc = proc

        def finished(_code, _status):
            if self.save_proc is not proc:
                return
            self.save_proc = None
            self.busy = False
            try:
                result = json.loads(bytes(proc.readAllStandardOutput()))
                if 'error' in result:
                    raise ValueError(result['error'])
                self.loader.cache.pop(self.path, None)
                self.filmstrip.invalidate(self.path)
                self.load()
                if after:
                    after()
            except (ValueError, KeyError):
                message = result.get('error') if 'result' in locals() else 'Der Bildprozess wurde beendet. Bitte Original und Sicherung prüfen.'
                QMessageBox.warning(self, 'Speichern fehlgeschlagen', message)
            proc.deleteLater()
            self.controls()

        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda err: self.save_failed(proc) if err == QProcess.FailedToStart else None)
        proc.start(sys.executable, [str(ROOT / 'image_edit.py'), self.path,
                                   json.dumps(self.operations), json.dumps(self.data['stamp'])])

    def save_failed(self, proc):
        self.save_proc = None
        self.busy = False
        proc.deleteLater()
        self.controls()
        self.status.setText('Der Bildprozess konnte nicht gestartet werden. Änderungen sind nicht gespeichert.')

    def trash(self):
        if self.busy or not self.path:
            return
        box = QMessageBox(QMessageBox.Question, 'Bild in den Papierkorb', '',
                          QMessageBox.Yes | QMessageBox.Cancel, self)
        box.setTextFormat(Qt.PlainText)
        box.setText(f'„{Path(self.path).name}“ in den Papierkorb verschieben?\nUngespeicherte Änderungen werden verworfen.')
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec_() != QMessageBox.Yes:
            return
        self.busy = True
        self.controls()
        self.status.setText('In den Papierkorb verschieben …')
        self.loader.cancel()
        path = self.path
        worker = FileWorker('trash', [path])
        self.worker = worker
        result = [[], []]
        worker.completed.connect(lambda done, errors: result.__setitem__(slice(None), [done, errors]))

        def finished():
            self.worker = None
            self.busy = False
            if result[1]:
                QMessageBox.warning(self, 'Papierkorb nicht verfügbar', '\n'.join(result[1]))
            elif path in result[0]:
                self.loader.cache.pop(path, None)
                self.paths.remove(path)
                self.operations.clear()
                self.index = min(self.index, len(self.paths) - 1)
                if self.paths:
                    self.load()
                else:
                    self.reject()
            self.controls()
            worker.deleteLater()
        worker.finished.connect(finished)
        worker.start()

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def reject(self):
        if not self.busy:
            self.leave_edits(lambda: super(Gallery, self).reject())

    def closeEvent(self, event):
        event.ignore()
        self.reject()
