"""Retain Files underneath the existing Reader, including its private reading copy."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from lumen_i18n import tr
from tools_ui import button, row


class ReadingWorkspace(QStackedWidget):
    def __init__(self, window, root=None):
        super().__init__(window)
        from tools_reader import Reader
        self.window = window
        self.root = root
        self.translation = None
        self.file_controls = window.findChildren(QAction) + window.findChildren(QShortcut)
        self.control_state = None
        self.files = window.takeCentralWidget(); self.addWidget(self.files)
        self.reader = Reader(root); self.reader.setWindowFlags(Qt.Widget)
        self.reader.setMinimumSize(0, 0); self.reader.sidebar.hide()
        self.reader.app_header.hide()
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(row(button(tr('Zurück zu den Dateien'), self.back, 'go-previous'),
                             button(tr('Lesebibliothek'), lambda: self.reader.sidebar.setVisible(self.reader.sidebar.isHidden()), 'view-list-details'),
                             button(tr('Leseeinstellungen'), self.reader.open_settings, 'configure')))
        layout.addWidget(self.reader, 1); self.addWidget(page)
        window.setCentralWidget(self)

    def open_file(self, path):
        path = Path(path).expanduser().resolve(strict=True)
        if not path.is_file(): raise ValueError(tr('Bitte eine lesbare Datei auswählen.'))
        if self.reader.job: raise ValueError(tr('Bitte den laufenden Vorgang abwarten.'))
        self.reader.save()
        self.show_page(1)
        existing = next((r for r in self.reader.library.all() if r.get('source') == path.as_uri()), None)
        if existing: self.reader.focus_record(existing['id'])
        else: self.reader.open_file(str(path))

    def show_page(self, index):
        if self.control_state is None:
            self.control_state = [(control, control.isEnabled()) for control in self.file_controls]
            for control in self.file_controls: control.setEnabled(False)
        self.setCurrentIndex(index)

    def open_library(self):
        self.reader.sidebar.show()
        self.show_page(1)
        self.reader.search.setFocus()

    def open_translation(self):
        if self.translation is None:
            from tools_translate import Translate
            self.translation = Translate(self.root)
            self.translation.setWindowFlags(Qt.Widget)
            self.translation.setMinimumSize(0, 0)
            self.translation.app_header.hide()
            page = QWidget(); layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(row(button(tr('Zurück zu den Dateien'), self.back, 'go-previous'),
                                 button(tr('Übersetzungseinstellungen'), self.translation.open_settings, 'configure')))
            layout.addWidget(self.translation, 1); self.addWidget(page)
        self.show_page(2)
        self.translation.input.setFocus()

    def back(self):
        view = self.translation if self.currentIndex() == 2 else self.reader
        if view.job:
            view.status.setText(tr('Bitte den laufenden Vorgang abwarten.')); return
        try: view.save()
        except Exception as error: view.error(str(error)); return
        self.reader.player.stop(); self.setCurrentIndex(0)
        for control, enabled in self.control_state or []: control.setEnabled(enabled)
        self.control_state = None

    def can_close(self):
        from PySide6.QtGui import QCloseEvent
        for view in (self.reader, self.translation):
            if view is not None:
                event = QCloseEvent(); view.closeEvent(event)
                if not event.isAccepted(): return False
        return True
