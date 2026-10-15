"""Open and organize saved conversations/tasks without resuming execution."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QInputDialog
from lumen_i18n import tr
from tools_ui import label, row, button
from projects_references import change, identity, open_reference


class ReferencesPane(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        box = QVBoxLayout(self); box.setContentsMargins(0, 12, 0, 0)
        box.addWidget(label(tr('Gespräche und Aufträge verknüpfen. Beim Öffnen startet keine neue Ausführung.'), 'muted'))
        self.items = QListWidget(); self.items.setAccessibleName(tr('Projektverweise'))
        self.items.itemDoubleClicked.connect(lambda _: window.safe(self.open))
        box.addWidget(self.items, 1)
        self.add_task = button(tr('Auftrag zuordnen'), lambda: window.safe(self.pick, 'task'))
        self.add_chat = button(tr('Gespräch zuordnen'), lambda: window.safe(self.pick, 'chat'))
        self.remove = button(tr('Zuordnung entfernen'), lambda: window.safe(self.unlink))
        box.addWidget(row(self.add_task, self.add_chat, button(tr('Öffnen'), lambda: window.safe(self.open)), self.remove))

    def load(self, record, readonly=False):
        self.items.clear()
        for ref in record.get('references', []):
            item = QListWidgetItem(ref['title'] + '\n' + tr('Gespräch' if ref['kind'] == 'chat' else 'Auftrag'))
            item.setData(Qt.UserRole, ref); self.items.addItem(item)
        for control in (self.add_task, self.add_chat, self.remove): control.setEnabled(not readonly)

    def pick(self, kind):
        from lumen_store import Store
        choices = []
        for task in Store().tasks(include_dismissed=False):
            if kind == 'task': ref = dict(kind=kind, title=task['title'], id=task['id'])
            elif task.get('session'): ref = dict(kind=kind, title=task['title'], chat=dict(directory=task['directory'], session=task['session']))
            else: continue
            if not any(identity(old) == identity(ref) for old in choices): choices.append(ref)
        if not choices: raise ValueError(tr('Noch keine gespeicherten Gespräche oder Aufträge vorhanden.'))
        labels = [f"{index + 1}. {ref['title']}" for index, ref in enumerate(choices)]
        selected, ok = QInputDialog.getItem(self, tr('Lumen Projekte · Inhalt zuordnen'), tr('Gespeicherter Inhalt'), labels, 0, False)
        if ok: self.apply(choices[labels.index(selected)])

    def apply(self, reference, remove=False):
        window = self.window
        if window.scope: raise ValueError(tr('Zuerst das Projekt auswählen.'))
        window.save()
        change(window.library, window.current, window.loaded_updated, reference, remove)
        window.loading = True
        try: window.load_fields(window.library.get(window.current))
        finally: window.loading = False

    def unlink(self):
        if self.items.currentItem(): self.apply(self.items.currentItem().data(Qt.UserRole), True)

    def open(self):
        if self.items.currentItem():
            from lumen_store import Store
            open_reference(self.items.currentItem().data(Qt.UserRole), Store())
