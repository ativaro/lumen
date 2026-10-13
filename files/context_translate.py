"""Translate a captured passage beside its source using the existing text workbench."""
import uuid
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout
from lumen_i18n import tr
from tools_ui import button, label


class TranslationDialog(QDialog):
    def __init__(self, source, record, root=None):
        super().__init__(source)
        from tools_translate import Translate
        self.setWindowTitle(tr('Lumen · Text übersetzen')); self.resize(1050, 780)
        layout = QVBoxLayout(self)
        layout.addWidget(label(tr('Übersetzung als eigener Text. Das Original bleibt unverändert.')))
        self.view = Translate(root); self.view.setWindowFlags(Qt.Widget)
        self.view.sidebar.hide(); self.view.setMinimumSize(0, 0)
        header = self.view.centralWidget().layout().itemAt(0).layout()
        for i in range(header.count()):
            if header.itemAt(i).widget(): header.itemAt(i).widget().hide()
        self.view.focus_record(record['id']); layout.addWidget(self.view, 1)
        layout.addWidget(button(tr('Zurück zur Quelle'), self.reject, 'go-previous'))

    def reject(self):
        event = QCloseEvent(); self.view.closeEvent(event)
        if event.isAccepted(): super().reject()


def open_translation(window, payload=None):
    from interop_ui import capture, root_for, with_saved
    from interop_targets import apply
    from translate_data import text_segments
    def prepare():
        value = payload or capture(window); text_segments(value.get('text', ''))
        root = root_for(window); result = []
        def show():
            if not result: return
            dialog = TranslationDialog(window, result[0], root)
            try: dialog.exec()
            finally: dialog.deleteLater()
        window.work(tr('Text für die Übersetzung vorbereiten …'),
                    lambda job: apply('translate.import', value,
                                      dict(mode='copy', token=uuid.uuid4().hex), job, root),
                    result.append, finished=show)
    with_saved(window, prepare)
