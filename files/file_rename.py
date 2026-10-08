"""Native inline editors, committing through Lumen's existing file operations."""
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate
from core import valid_name


class RenameEditor(QLineEdit):
    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            event.accept()
            return True
        return super().event(event)


class RenameDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        window = self.parent().main_window
        if index.column() != 0 or window.file_job or len(window.selected_paths()) != 1:
            return None
        return RenameEditor(parent)

    def setEditorData(self, editor, index):
        path = Path(index.model().path(index))
        editor.setText(path.name)
        length = len(path.name) if index.model().directory(index) else len(path.stem)
        # The view selects all on focus; select the stem once it has focused us.
        QTimer.singleShot(0, editor, lambda: editor.setSelection(0, length))

    def setModelData(self, editor, model, index):
        path = Path(model.path(index))
        if editor.text() == path.name: return
        window = self.parent().main_window
        try: target = path.with_name(valid_name(editor.text()))
        except ValueError as error:
            window.error(str(error)); return
        window.run_operation('rename', [str(path)], str(target))
