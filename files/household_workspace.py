"""Room relationships over the existing household records; no content copies."""
from PySide6.QtCore import Qt, QLockFile, Signal
from PySide6.QtWidgets import QComboBox, QInputDialog, QFormLayout
from lumen_i18n import tr
from tools_household import Household


class HouseholdRoom(Household):
    revealRequested = Signal()

    def __init__(self, root=None):
        from tools_data import Library
        lock = QLockFile(str(Library('household', root).root/'window.lock'))
        if not lock.tryLock(0):
            raise ValueError(tr('Der Haushalt ist bereits in einem anderen Fenster geöffnet. Bitte dort weiterarbeiten oder das Fenster schließen.'))
        self.room_id = ''; self.rooms = []
        super().__init__(root)
        self.library_lock = lock
        self.setWindowFlags(Qt.Widget); self.setMinimumSize(0, 0)
        shell = self.centralWidget().layout()
        shell.setContentsMargins(0, 12, 0, 0)
        header = shell.itemAt(0).layout()
        for i in range(header.count()):
            if header.itemAt(i).widget(): header.itemAt(i).widget().hide()
        self.scope = QComboBox()
        for title, value in [('Dieses Projekt','room'), ('Ohne Projektzuordnung','unassigned'), ('Alle Einträge','all')]:
            self.scope.addItem(tr(title), value)
        self.scope.setAccessibleName(tr('Haushalt anzeigen'))
        self.sidebar.layout().insertWidget(0, self.scope)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.assignment = QComboBox(); self.assignment.setAccessibleName(tr('Projekt zuordnen'))
        form = QFormLayout(); form.addRow(tr('Projekt'), self.assignment)
        self.content.insertLayout(1, form)
        self.assignment.activated.connect(lambda _: self.safe(self.assign))
        from tools_app import listen_window
        self.activation_server = listen_window(self, self.activate)

    def activate(self, request):
        if not isinstance(request, dict): raise ValueError(tr('Ungültige App-Anfrage.'))
        if request:
            from interop_ui import controller
            self.scope.setCurrentIndex(2)
            controller(self).enqueue(request)
        self.revealRequested.emit()
        from lumen_activation import present
        present(self.window())

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            self.activation_server.close(); self.library_lock.unlock()

    def set_room(self, identity, rooms):
        if self.job: raise ValueError(tr('Bitte den laufenden Belegimport zuerst abschließen.'))
        self.save(); self.current = ''; self.body.setEnabled(False)
        self.room_id, self.rooms = identity, list(rooms)
        self.scope.model().item(0).setEnabled(bool(identity))
        self.scope.setCurrentIndex(0 if identity else 2)
        self.refresh()

    def refresh(self, *_):
        super().refresh()
        if not hasattr(self, 'scope'): return
        known = {r['id'] for r in self.rooms}; mode = self.scope.currentData()
        for i in range(self.entries.count()):
            item = self.entries.item(i)
            room = self.library.get(item.data(Qt.UserRole)).get('room_id', '')
            item.setHidden(mode == 'room' and room != self.room_id or mode == 'unassigned' and room in known)

    def load(self, record):
        super().load(record)
        self.assignment.clear(); self.assignment.addItem(tr('Ohne Projektzuordnung'), '')
        for room in self.rooms: self.assignment.addItem(room['name'], room['id'])
        identity = record.get('room_id', '')
        if identity and self.assignment.findData(identity) < 0:
            self.assignment.addItem(tr('Projekt nicht mehr vorhanden'), identity)
        self.assignment.setCurrentIndex(max(0, self.assignment.findData(identity)))

    def assign(self):
        if not self.current or self.loading or self.job: return
        self.save()
        self.library.update(self.current, room_id=self.assignment.currentData())
        self.refresh()

    def create(self):
        title, ok = QInputDialog.getText(self, tr('Neuer Eintrag'), tr('Name des Geräts oder Vertrags'))
        if ok and title.strip():
            self.save()
            self.focus_record(self.library.create(title, kind='Gerät', attachments=[], notes='', room_id=self.room_id))

    def can_close(self):
        if self.job:
            self.status.setText(tr('Bitte den laufenden Belegimport zuerst abschließen.'))
            return False
        self.save()
        return True
