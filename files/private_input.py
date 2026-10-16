"""Editors that do not import password-manager clipboard content into AI tools."""
from PySide6.QtWidgets import QPlainTextEdit
from clipboard_image import has_image


class AssistantInput(QPlainTextEdit):
    image_handler = None

    def canInsertFromMimeData(self, source):
        if source and source.data('x-kde-passwordManagerHint') == b'secret': return False
        return bool(source and has_image(source) and self.image_handler) or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source and source.data('x-kde-passwordManagerHint') == b'secret':
            return
        if source and has_image(source) and self.image_handler:
            self.image_handler(source)
            return
        super().insertFromMimeData(source)
