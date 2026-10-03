"""Bounded previews: decoding happens in killable child processes."""
import json
import os
import stat
import sys
from pathlib import Path

from lumen_i18n import worker_process, tr

from PyQt5.QtCore import QProcess, QSize, Qt, QTemporaryDir, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFontDatabase, QIcon, QImageReader, QPixmap
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                             QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)
from core import file_kind, size_text


def label(text='', name=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


class Preview(QWidget):
    openImage = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('preview')
        self.setMinimumWidth(270)
        self.path = None
        self.proc = None
        self.temp = QTemporaryDir()
        self.page, self.pages = 1, 1
        self.pixmap = QPixmap()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(22, 24, 22, 20)
        self.layout.setSpacing(14)
        self.layout.addWidget(label(tr('Vorschau'), 'eyebrow'))
        self.title = label(tr('Keine Auswahl'), 'previewTitle')
        self.layout.addWidget(self.title)
        self.detail = label(tr('Wähle eine Datei für die Vorschau.'), 'muted')
        self.layout.addWidget(self.detail)
        self.stack = QStackedWidget()
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(100, 160)
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setObjectName('previewCanvas')
        self.message = label(tr('Bilder, PDFs, Text und Medien'), 'previewMessage')
        self.message.setAlignment(Qt.AlignCenter)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.NoWrap)
        for widget in [self.message, self.image, self.text]:
            self.stack.addWidget(widget)
        self.layout.addWidget(self.stack, 1)
        self.pagebar = QWidget()
        row = QHBoxLayout(self.pagebar)
        row.setContentsMargins(0, 0, 0, 0)
        self.previous = QPushButton('←')
        self.previous.setAccessibleName(tr('Vorherige PDF-Seite'))
        self.previous.clicked.connect(lambda: self.change_page(-1))
        self.page_label = label()
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next = QPushButton('→')
        self.next.setAccessibleName(tr('Nächste PDF-Seite'))
        self.next.clicked.connect(lambda: self.change_page(1))
        row.addWidget(self.previous)
        row.addWidget(self.page_label, 1)
        row.addWidget(self.next)
        self.layout.addWidget(self.pagebar)
        self.pagebar.hide()
        self.note = label(tr('Leertaste für die große Vorschau'), 'muted')
        self.layout.addWidget(self.note)
        self.location = label('', 'fileLocation')
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(self.location)
        self.open_button = QPushButton(tr('Mit Standard-App öffnen  ↗'))
        self.open_button.clicked.connect(self.open_file)
        self.open_button.setEnabled(False)
        self.layout.addWidget(self.open_button)
        self.edit_button = QPushButton(tr('Bild bearbeiten'))
        self.edit_button.clicked.connect(lambda: self.openImage.emit(str(self.path), True) if self.path else None)
        self.layout.addWidget(self.edit_button)
        self.photo_layout(False)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def open_file(self):
        if self.path:
            if self.photo and self.receivers(self.openImage):
                self.openImage.emit(str(self.path), False)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def photo_layout(self, enabled):
        self.photo = enabled
        self.layout.removeWidget(self.stack)
        self.layout.insertWidget(1 if enabled else 3, self.stack, 1)
        native = enabled and self.receivers(self.openImage) > 0
        self.open_button.setText(tr('Groß öffnen') if native else tr('Mit Standard-App öffnen  ↗'))
        self.open_button.setObjectName('primary' if native else '')
        self.open_button.style().unpolish(self.open_button)
        self.open_button.style().polish(self.open_button)
        self.edit_button.setVisible(native)
        self.edit_button.setEnabled(False)

    def cancel(self):
        self.timer.stop()
        if self.proc:
            proc, self.proc = self.proc, None
            proc.kill()
            proc.waitForFinished(1000)
            proc.deleteLater()

    def timeout(self):
        self.cancel()
        self.show_message(tr('Die Vorschau hat zu lange gedauert.\nDu kannst die Datei mit ihrer Standard-App öffnen.'))

    def show_message(self, text):
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def clear(self):
        self.cancel()
        self.photo_layout(False)
        self.path = None
        self.title.setText(tr('Keine Auswahl'))
        self.detail.setText(tr('Wähle eine Datei für die Vorschau.'))
        self.location.clear()
        self.pagebar.hide()
        self.open_button.setEnabled(False)
        self.show_message(tr('Bilder, PDFs, Text und Medien'))

    def show_path(self, path, location=None, page=1):
        self.cancel()
        self.photo_layout(False)
        self.path = Path(path)
        self.title.setText(self.path.name or '/')
        self.location.setText(location or str(self.path.parent))
        self.location.setToolTip(location or str(self.path.parent))
        self.pagebar.hide()
        self.page, self.pages = max(1, page), 1
        self.note.setText(tr('Leertaste für die große Vorschau'))
        self.open_button.setEnabled(True)
        self.detail.setText(tr('Dateiinformationen laden …'))
        self.show_message(tr('Vorschau wird geladen …'))
        self.start(sys.executable, [str(Path(__file__).resolve()), '--info', str(self.path)], self.info_ready)

    def info_ready(self, proc):
        info = json.loads(bytes(proc.readAllStandardOutput()))
        if info['directory']:
            self.detail.setText(tr('Ordner'))
            self.pixmap = QIcon.fromTheme('folder').pixmap(128, 128)
            self.stack.setCurrentWidget(self.image)
            self.fit_image()
            self.note.setText(tr('Doppelklick öffnet den Ordner'))
            return
        self.detail.setText(size_text(info['size']))
        if not info['regular']:
            self.show_message(tr('Für diesen Dateityp gibt es keine Vorschau.'))
            return
        kind = file_kind(self.path)
        if kind == 'image':
            self.photo_layout(True)
            remote = QUrl(self.location.toolTip())
            self.location.setText(('NAS · ' if remote.scheme() == 'smb' else tr('Netzwerk · ')) + remote.host()
                                  if remote.host() else tr('Dieser PC · ') + self.path.parent.name)
        if kind == 'pdf':
            self.start('pdfinfo', [str(self.path)], self.pdf_info)
        elif kind in {'video', 'audio'}:
            self.start('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe',
                       '-show_entries', 'format=duration:stream=width,height', '-of', 'json',
                       str(self.path)], lambda proc: self.media_info(proc, kind))
        else:
            output = str(Path(self.temp.path()) / 'image.png')
            self.start(sys.executable, [str(Path(__file__).resolve()), '--data', str(self.path), output],
                       self.data_ready)

    def start(self, command, args, callback):
        self.cancel()
        proc = worker_process(self)
        self.proc = proc
        proc.setProgram(command)
        proc.setArguments(args)
        def finished(code, _status):
            if self.proc is not proc:
                return
            self.timer.stop()
            self.proc = None
            if code:
                self.show_message(tr('Keine Vorschau verfügbar.\nDie Datei ist beschädigt, geschützt oder nicht unterstützt.'))
            else:
                try:
                    callback(proc)
                except (ValueError, OSError, KeyError) as exc:
                    self.show_message(tr('Vorschau nicht verfügbar.\n{0}', exc))
            proc.deleteLater()
        proc.finished.connect(finished)
        def failed(error):
            if error == QProcess.FailedToStart and self.proc is proc:
                self.timer.stop()
                self.proc = None
                self.show_message(tr('Für diese Vorschau fehlt {0}.', command))
                proc.deleteLater()
        proc.errorOccurred.connect(failed)
        proc.start()
        self.timer.start(12000)

    def data_ready(self, proc):
        data = json.loads(bytes(proc.readAllStandardOutput()))
        if data['kind'] == 'image':
            self.display_image(data['output'])
            self.detail.setText(self.detail.text() + f"  ·  {data['width']} × {data['height']} px")
            self.edit_button.setEnabled(not self.pixmap.isNull())
        elif data['kind'] == 'text':
            self.text.setPlainText(data['text'])
            self.stack.setCurrentWidget(self.text)
            self.note.setText(tr('Auszug: erste 128 KB') if data['truncated'] else tr('Textvorschau · schreibgeschützt'))
        else:
            self.show_message(data['message'])

    def pdf_info(self, proc):
        lines = bytes(proc.readAllStandardOutput()).decode(errors='replace').splitlines()
        self.pages = next((int(line.split(':', 1)[1]) for line in lines if line.startswith('Pages:')), 1)
        self.page = min(self.page, self.pages)
        self.render_pdf()

    def render_pdf(self):
        self.pagebar.show()
        self.page_label.setText(tr('Seite {0} / {1}', self.page, self.pages))
        self.previous.setEnabled(self.page > 1)
        self.next.setEnabled(self.page < self.pages)
        self.note.setText(tr('PDF-Vorschau · Leertaste zum Vergrößern'))
        self.show_message(tr('Seite wird geladen …'))
        output = str(Path(self.temp.path()) / 'pdf')
        self.start('pdftoppm', ['-f', str(self.page), '-l', str(self.page), '-scale-to', '1500',
                   '-singlefile', '-png', str(self.path), output],
                   lambda _proc: self.display_image(output + '.png'))

    def change_page(self, delta):
        self.page = max(1, min(self.pages, self.page + delta))
        self.render_pdf()

    def media_info(self, proc, kind):
        data = json.loads(bytes(proc.readAllStandardOutput()))
        duration = float(data.get('format', {}).get('duration', 0))
        self.detail.setText(self.detail.text() + f'  ·  {int(duration // 60)}:{int(duration % 60):02d} min')
        output = str(Path(self.temp.path()) / 'media.png')
        args = ['-nostdin', '-v', 'error', '-threads', '1', '-protocol_whitelist', 'file,pipe',
                '-i', str(self.path)]
        if kind == 'video':
            args += ['-vf', 'scale=1200:800:force_original_aspect_ratio=decrease', '-frames:v', '1']
            self.note.setText(tr('Video-Standbild · Öffnen zum Abspielen'))
        else:
            args += ['-filter_complex', 'atrim=duration=30,showwavespic=s=1000x280:colors=0x89d5c4',
                     '-frames:v', '1']
            self.note.setText(tr('Wellenform: erste 30 s · Öffnen zum Abspielen'))
        self.start('ffmpeg', args + ['-update', '1', '-y', output],
                   lambda _proc: self.display_image(output))

    def display_image(self, filename):
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(Path(filename).read_bytes())
        if self.pixmap.isNull():
            self.show_message(tr('Dieses Bild konnte nicht gelesen werden.'))
        else:
            self.stack.setCurrentWidget(self.image)
            self.fit_image()

    def fit_image(self):
        if not self.pixmap.isNull():
            self.image.setPixmap(self.pixmap.scaled(self.image.size() - QSize(12, 12),
                                                   Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_image()


def preview_data(path, output, max_side=1600):
    """Executed outside the UI. Never render HTML or open non-regular streams."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            return {'kind': 'other', 'message': tr('Keine Vorschau für Spezialdateien.')}
        if file_kind(path) == 'image':
            from image_edit import file_stamp
            import image_cache
            max_side = max(1, min(max_side, 4096))
            stamp = file_stamp(info)
            try:
                cached = image_cache.read(path, stamp, max_side, output)
                if cached and stamp == file_stamp(path.stat()): return cached
            except OSError: pass
            if info.st_size > 128 * 1024 * 1024:
                return {'kind': 'other', 'message': tr('Bild größer als 128 MB. Bitte extern öffnen.')}
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            original = reader.size()
            if original.width() * original.height() > 80_000_000:
                return {'kind': 'other', 'message': tr('Bild größer als 80 Megapixel. Bitte extern öffnen.')}
            max_side = max(1, min(max_side, 4096))
            target = original.scaled(min(max_side, original.width()), min(max_side, original.height()), Qt.KeepAspectRatio)
            target.setWidth(max(1, target.width()))
            target.setHeight(max(1, target.height()))
            reader.setScaledSize(target)
            image = reader.read()
            if image.width() > max_side or image.height() > max_side:
                image = image.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if image.isNull() or not image.save(output, 'PNG'):
                return {'kind': 'other', 'message': tr('Bildformat nicht unterstützt oder Datei beschädigt.')}
            from image_edit import file_stamp
            if file_stamp(info) != file_stamp(path.stat()):
                return {'kind': 'other', 'message': tr('Die Datei wurde während des Ladens geändert.')}
            data = {'kind': 'image', 'output': output, 'width': original.width(), 'height': original.height(),
                    'stamp': stamp, 'format': bytes(reader.format()).decode('ascii', errors='replace')}
            try:
                image_cache.write(path, stamp, max_side, Path(output).read_bytes(), data)
                if max_side > 640:
                    from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
                    for side in (192, 640):
                        encoded = QByteArray(); buffer = QBuffer(encoded); buffer.open(QIODevice.WriteOnly)
                        image.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(buffer, 'PNG')
                        image_cache.write(path, stamp, side, bytes(encoded), data)
            except OSError: pass  # A full/read-only cache must not break viewing.
            return data
        data = stream.read(128 * 1024 + 1)
        if b'\0' in data or (data and sum(b < 9 or 13 < b < 32 for b in data) / len(data) > .03):
            return {'kind': 'other', 'message': tr('Keine integrierte Vorschau für dieses Dateiformat.\nMit der Standard-App öffnen.')}
        return {'kind': 'text', 'text': data[:128 * 1024].decode('utf-8', errors='replace'),
                'truncated': len(data) > 128 * 1024}


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--info':
    info = Path(sys.argv[2]).stat()
    print(json.dumps({'directory': stat.S_ISDIR(info.st_mode), 'regular': stat.S_ISREG(info.st_mode),
                      'size': info.st_size}))
elif __name__ == '__main__' and len(sys.argv) in {4, 5} and sys.argv[1] == '--data':
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5.QtCore import QThreadPool
    from PyQt5.QtGui import QGuiApplication
    application = QGuiApplication(sys.argv)
    # Qt image scaling otherwise creates a CPU-sized pool whose stacks/arenas can
    # exhaust RLIMIT_AS and stall large photos. Each image already has its own process.
    QThreadPool.globalInstance().setMaxThreadCount(1)
    print(json.dumps(preview_data(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) == 5 else 1600)))
