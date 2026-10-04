"""Lumen's explicit results alongside the conversation, using Files workers."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QComboBox, QSplitter
from core import file_kind
from gallery import Gallery, ImageLoader
from gallery_widgets import Filmstrip
from lumen_i18n import tr
from preview import Preview, label
from studio_chat import icon_button


class StudioPreview(Preview):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout.setContentsMargins(20, 8, 20, 20)
        self.layout.itemAt(0).widget().hide()
        self.note.hide()
        self.filmstrip = Filmstrip(ImageLoader(self, max_side=192, cache_limit=16), self)
        self.filmstrip.chosen.connect(self.choose_image)
        self.layout.insertWidget(2, self.filmstrip); self.filmstrip.hide()
        self.openImage.connect(self.open_gallery)
        actions = QHBoxLayout()
        for control in (self.open_button, self.edit_button):
            self.layout.removeWidget(control); actions.addWidget(control)
        self.layout.addLayout(actions)

    def photo_layout(self, enabled):
        super().photo_layout(enabled)
        if hasattr(self, 'filmstrip'):
            self.layout.removeWidget(self.filmstrip); self.layout.insertWidget(2, self.filmstrip)
            self.filmstrip.setVisible(enabled and len(self.filmstrip.paths) > 1)

    def choose_image(self, index):
        self.show_path(self.filmstrip.paths[index])

    def open_gallery(self, path, edit):
        paths = self.filmstrip.paths or [path]
        gallery = Gallery(paths, path, self)
        if edit: gallery.editor_button.setChecked(True)
        gallery.exec(); gallery.deleteLater()
        self.filmstrip.invalidate(path)
        self.show_path(path)

    def shutdown(self):
        self.cancel(); self.filmstrip.stop()


class StudioSurface(QWidget):
    def __init__(self, chat, parent=None):
        super().__init__(parent)
        self.chat = chat; self.paths = []; self.preview_wanted = False; self.narrow_preview = False
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.split = QSplitter(Qt.Horizontal); self.split.setChildrenCollapsible(False); self.split.setHandleWidth(1)
        root.addWidget(self.split); self.split.addWidget(chat)
        self.pane = QWidget(); self.pane.setObjectName('studioPreviewPane')
        layout = QVBoxLayout(self.pane); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        top = QHBoxLayout(); top.setContentsMargins(20, 22, 16, 0)
        self.heading = label(tr('Vorschau'), 'heading'); self.heading.setWordWrap(True)
        top.addWidget(self.heading, 1)
        self.close_preview = icon_button(tr('Vorschau schließen'), 'window-close', self.close_pane); top.addWidget(self.close_preview)
        layout.addLayout(top)
        self.choice = QComboBox(); self.choice.setAccessibleName(tr('Datei in der Vorschau'))
        self.choice.setMinimumContentsLength(10); self.choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.choice.activated.connect(self.choose); layout.addWidget(self.choice)
        self.preview = StudioPreview(); layout.addWidget(self.preview, 1)
        self.split.addWidget(self.pane); self.split.setSizes([560, 540]); self.pane.hide()
        self.preview.filmstrip.chosen.connect(lambda i: self.choice.setCurrentIndex(
            self.choice.findData(self.preview.filmstrip.paths[i])))
        chat.resultChanged.connect(self.set_result); chat.previewRequested.connect(self.toggle_preview)
        self.set_result(chat.presentation)

    def set_result(self, result):
        paths = result['paths'] if result else []
        self.heading.setText(result['title'] if result and result['title'] else tr('Vorschau'))
        self.paths = paths; self.choice.clear()
        for path in paths: self.choice.addItem(Path(path).name or '/', path)
        images = [p for p in paths if file_kind(p) == 'image']
        self.preview.filmstrip.stop()
        self.preview.filmstrip.loader.cache.clear()
        self.preview.filmstrip.select([], -1)
        self.preview.filmstrip.select(images, 0 if images else -1)
        self.preview_wanted = bool(paths); self.narrow_preview = False
        self.preview.path = None
        self.update_visibility()
        if not paths:
            self.preview.clear(); self.preview.shutdown()
            self.preview.title.setText(tr('Ergebnisse von Lumen'))
            self.preview.detail.setText(tr('Hier zeigt Lumen gefundene und erstellte Dateien.'))
            self.preview.show_message(tr('Bitte Lumen, dir etwas zu zeigen.'))
        self.choice.setVisible(bool(paths))

    def choose(self, index):
        path = self.choice.itemData(index)
        if path:
            self.preview.show_path(path)
            images = self.preview.filmstrip.paths
            self.preview.filmstrip.select(images, images.index(path) if path in images else -1)

    def toggle_preview(self):
        self.preview_wanted = not self.pane.isVisible(); self.narrow_preview = self.preview_wanted
        self.update_visibility()

    def close_pane(self):
        self.preview_wanted = False; self.narrow_preview = False; self.update_visibility()
        self.preview.shutdown(); self.chat.composer.setFocus()

    def update_visibility(self):
        wide = self.width() >= 850
        show = self.preview_wanted and (wide or self.narrow_preview)
        was_visible = self.pane.isVisible()
        self.pane.setVisible(show); self.chat.setVisible(wide or not show)
        if show and (not was_visible or self.preview.path is None) and self.paths: self.choose(self.choice.currentIndex())
        if not show: self.preview.shutdown()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'pane'): self.update_visibility()
