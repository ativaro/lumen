"""Gallery chrome and a bounded, visible-only thumbnail strip."""
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListView,
                             QListWidget, QListWidgetItem, QPushButton, QShortcut,
                             QSizePolicy, QVBoxLayout, QWidget)
from preview import label


class Filmstrip(QListWidget):
    chosen = pyqtSignal(int)

    def __init__(self, loader, parent=None):
        super().__init__(parent)
        self.loader, self.paths, self.visible_rows = loader, [], set()
        self.setObjectName('filmstrip')
        self.setAccessibleName('Bildauswahl im Filmstreifen')
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight); self.setWrapping(False)
        self.setMovement(QListView.Static); self.setUniformItemSizes(True)
        self.setGridSize(QSize(128, 86)); self.setIconSize(QSize(112, 72))
        self.setFixedHeight(104)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(30)
        self.timer.timeout.connect(self.load_visible)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.timer.start())
        self.itemClicked.connect(lambda item: self.chosen.emit(self.row(item)))
        self.itemActivated.connect(lambda item: self.chosen.emit(self.row(item)))
        self.loader.ready.connect(self.ready)

    def select(self, paths, index):
        if self.paths != paths:
            self.loader.cancel(); self.loader.pending.clear(); self.clear()
            self.paths = list(paths); self.visible_rows.clear()
            for path in paths:
                item = QListWidgetItem(self)
                item.setSizeHint(self.gridSize())
                item.setToolTip(Path(path).name)
                item.setData(Qt.AccessibleTextRole, Path(path).name)
        self.setCurrentRow(index)
        if index >= 0: self.scrollToItem(self.item(index), QAbstractItemView.PositionAtCenter)
        self.timer.start()

    def load_visible(self):
        if not self.paths or not self.isVisible(): return
        start = max(0, self.horizontalScrollBar().value() // self.gridSize().width() - 1)
        end = min(len(self.paths), start + self.viewport().width() // self.gridSize().width() + 4)
        rows = set(range(start, end))
        for row in self.visible_rows - rows: self.item(row).setIcon(QIcon())
        self.visible_rows = rows
        paths = [self.paths[row] for row in sorted(rows)]
        for path in paths:
            if path in self.loader.cache: self.ready(path, *self.loader.cache[path])
        if paths: self.loader.want(paths)

    def ready(self, path, pixmap, _data):
        for row in self.visible_rows:
            if self.paths[row] == path:
                self.item(row).setIcon(QIcon(pixmap)); break

    def invalidate(self, path):
        self.loader.cache.pop(path, None)
        self.timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'timer'): self.timer.start()

    def showEvent(self, event):
        super().showEvent(event); self.timer.start()

    def stop(self):
        self.timer.stop(); self.loader.pending.clear(); self.loader.cancel()


def build_gallery(window, canvas, thumbnails):
    """Keep the photo central; expose the existing safe editor only on demand."""
    window.setObjectName('gallery')
    layout = QVBoxLayout(window); layout.setContentsMargins(18, 10, 18, 12); layout.setSpacing(10)
    header = QHBoxLayout(); header.setSpacing(12)
    header.addWidget(label('Lumen · Bilder', 'galleryBrand'))
    window.title = label('', 'galleryTitle'); window.title.setWordWrap(False)
    window.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    window.title.setAlignment(Qt.AlignCenter); header.addWidget(window.title, 1)
    window.source = label('', 'gallerySource'); window.source.setWordWrap(False)
    window.source.setMaximumWidth(240); header.addWidget(window.source)
    window.actions = []

    def action(row, text, callback, shortcut=None, tip=None):
        button = QPushButton(text)
        button.setAccessibleName(tip or text)
        button.setToolTip((tip or text) + (f' · {shortcut}' if shortcut else ''))
        if callback: button.clicked.connect(callback)
        row.addWidget(button)
        if shortcut: QShortcut(QKeySequence(shortcut), window, activated=callback)
        window.actions.append(button)
        return button

    window.editor_button = action(header, 'Bearbeiten', None, tip='Bildbearbeitung einblenden')
    window.editor_button.setCheckable(True)
    action(header, '⛶', window.fullscreen, 'F11', 'Vollbild').setFixedWidth(42)
    action(header, '×', window.reject, 'Space', 'Schließen').setFixedWidth(42)
    layout.addLayout(header)
    body = QHBoxLayout(); body.setSpacing(16)
    photos = QHBoxLayout(); photos.setSpacing(6)
    window.previous = action(photos, '‹', lambda: window.step(-1), 'Left', 'Vorheriges Bild')
    window.previous.setObjectName('galleryArrow'); window.previous.setFixedSize(40, 64)
    photos.setAlignment(window.previous, Qt.AlignVCenter)
    window.canvas = canvas; photos.addWidget(canvas, 1)
    window.next = action(photos, '›', lambda: window.step(1), 'Right', 'Nächstes Bild')
    window.next.setObjectName('galleryArrow'); window.next.setFixedSize(40, 64)
    photos.setAlignment(window.next, Qt.AlignVCenter)
    body.addLayout(photos, 1)
    window.editor = QFrame(); window.editor.setObjectName('galleryEditor'); window.editor.setFixedWidth(270)
    edit = QVBoxLayout(window.editor); edit.setContentsMargins(18, 14, 18, 14); edit.setSpacing(6)
    edit.addWidget(label('Bearbeiten', 'galleryTitle'))
    rotate = QHBoxLayout(); rotate.setSpacing(6); edit.addLayout(rotate)
    window.left = action(rotate, '↶  Links', lambda: window.edit('left'), 'Shift+R', 'Links drehen')
    window.right = action(rotate, '↷  Rechts', lambda: window.edit('right'), 'R', 'Rechts drehen')
    window.mirror = action(edit, '↔  Spiegeln', lambda: window.edit('mirror'), 'H')
    window.undo_button = action(edit, 'Rückgängig', window.undo, 'Ctrl+Z')
    window.save_button = action(edit, 'Änderungen speichern', lambda: window.save(), 'Ctrl+S')
    window.save_button.setObjectName('primary')
    edit.addWidget(label('Das Original wird beim Speichern gesichert.', 'galleryMuted'))
    edit.addStretch()
    window.trash_button = action(edit, 'In den Papierkorb', window.trash, 'Delete')
    window.trash_button.setObjectName('galleryTrash')
    body.addWidget(window.editor); window.editor.hide()
    window.editor_button.toggled.connect(window.editor.setVisible)
    layout.addLayout(body, 1)
    toolbar = QHBoxLayout(); toolbar.setSpacing(8)
    window.counter = label('', 'galleryMuted'); toolbar.addWidget(window.counter)
    toolbar.addStretch()
    action(toolbar, '−', lambda: canvas.zoom(1 / 1.2), '-', 'Verkleinern')
    action(toolbar, '+', lambda: canvas.zoom(1.2), '+', 'Vergrößern')
    action(toolbar, '100 %', canvas.actual_size, tip='100 % der geladenen Vorschau')
    action(toolbar, 'Einpassen', canvas.fit, '0')
    toolbar.addStretch()
    window.dimensions = label('', 'galleryMuted'); toolbar.addWidget(window.dimensions)
    layout.addLayout(toolbar)
    window.filmstrip = Filmstrip(thumbnails, window)
    window.filmstrip.chosen.connect(window.jump)
    layout.addWidget(window.filmstrip)
    window.status = label('', 'galleryMuted'); window.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(window.status)
