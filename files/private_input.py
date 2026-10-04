"""Editors that do not import password-manager clipboard content into AI tools."""
from PySide6.QtWidgets import QPlainTextEdit


class AssistantInput(QPlainTextEdit):
    def insertFromMimeData(self, source):
        if source and source.data('x-kde-passwordManagerHint') == b'secret':
            return
        super().insertFromMimeData(source)
