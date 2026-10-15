"""Keyboard-first note navigation; the caller still owns saving the active draft."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout
from lumen_i18n import tr


class NoteSwitcher(QDialog):
    def __init__(self, notes, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Lumen Notes · Notiz öffnen'))
        self.resize(560, 400)
        self.path = None
        self.notes = sorted(notes, key=lambda note: (note['title'].casefold(), note['path']))
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Titel oder Pfad suchen …'))
        self.search.setAccessibleName(tr('Notiz suchen'))
        self.rows = QListWidget(); self.rows.setAccessibleName(tr('Gefundene Notizen'))
        layout.addWidget(self.search); layout.addWidget(self.rows)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        self.rows.itemActivated.connect(lambda _: self.choose())
        self.refresh('')

    def refresh(self, query):
        self.rows.clear()
        terms = query.casefold().split()
        for note in self.notes:
            if not all(term in (note['title']+' '+note['path']).casefold() for term in terms): continue
            row = QListWidgetItem(note['title']+' · '+note['path'])
            row.setData(Qt.UserRole, note['path']); self.rows.addItem(row)
            if self.rows.count() == 100: break
        if self.rows.count(): self.rows.setCurrentRow(0)

    def choose(self):
        if self.rows.currentItem():
            self.path = self.rows.currentItem().data(Qt.UserRole)
            self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_Up):
            delta = 1 if event.key() == Qt.Key_Down else -1
            self.rows.setCurrentRow(max(0, min(self.rows.count()-1, self.rows.currentRow()+delta)))
            return
        super().keyPressEvent(event)
