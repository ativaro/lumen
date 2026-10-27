"""Inspect the latest submitted context through the existing knowledge editor."""
import json
from PySide6.QtWidgets import QPushButton, QMenu, QMessageBox
from lumen_i18n import tr
from lumen_memory import Memory
from lumen_store import Store
from wissen_data import Notebook


def local_source(store, source):
    memory = Memory(store)
    kind = source.get('source_kind')
    if kind not in ('memory', 'note'):
        raise ValueError(tr('Diese Quelle gehört zum Lumen Server.'))
    book = memory.book if kind == 'memory' else Notebook(store)
    note = book.read(source['path'])
    identity = memory.record(note)['id'] if kind == 'memory' else memory.identity('notebook:'+json.dumps(book.identity)+':'+note['path'])
    if identity != source['id'] or identity in store.setting('memory/tombstones', {}):
        raise ValueError(tr('Diese Quelle ist nicht mehr verfügbar.'))
    return book, note


class MemorySources(QPushButton):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.snapshot = {}
        self.setObjectName('toolButton')
        self.setToolTip(tr('Für diese Anfrage bereitgestellte Quellen. Dies belegt nicht, welche davon die Antwort tatsächlich verwendet.'))
        self.menu = QMenu(self)
        self.setMenu(self.menu)
        self.menu.aboutToShow.connect(self.populate)
        backend.memoryContextChanged.connect(self.receive)
        backend.sessionChanged.connect(lambda _: self.receive({}))
        self.hide()

    def receive(self, snapshot):
        self.snapshot = snapshot if snapshot.get('phase') == 'submitted' else {}
        count = len(self.snapshot.get('sources', []))
        self.setText(tr('{0} Kontextquellen', count))
        self.setAccessibleName(self.text())
        self.setVisible(bool(count))

    def populate(self):
        self.menu.clear()
        for source in self.snapshot.get('sources', [])[:10]:
            title = source.get('title', '')[:120].replace('&', '&&')
            item = self.menu.addMenu(title)
            item.addAction(source.get('origin', '')).setEnabled(False)
            item.addAction(tr('Öffnen / korrigieren'), lambda s=source: self.open_source(s))
            if source.get('source_kind') == 'memory':
                item.addAction(tr('Vergessen …'), lambda s=source: self.forget(s))

    def error(self, message):
        QMessageBox.warning(self, tr('Lumen · Kontextquelle'), message)

    def open_source(self, source):
        try:
            if source.get('source_kind') in ('server_memory','server_note'):
                from lumen_connect import memory_stamp, read_config, connection_scope
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                config=read_config()
                bound=self.snapshot.get('server_connection')
                if (bound and bound!=connection_scope(config)) or (not bound and self.snapshot.get('server_stamp') != memory_stamp()):
                    raise ValueError(tr('Die Serverquelle wurde geändert. Bitte erneut fragen.'))
                from uuid import UUID
                identity = str(UUID(source['id'].removeprefix('server:').removeprefix('server-note:')))
                app='memory' if source.get('source_kind')=='server_memory' else 'note'
                QDesktopServices.openUrl(QUrl(config['server']+'/?app='+app+'&document='+identity))
                return
            book, note = local_source(Store(), source)
            from interop_open import launch
            launch('wissen', [str(book.root/note['path']), '--area', 'lumen'] if source.get('source_kind')=='memory' else [str(book.root/note['path'])])
        except (OSError, ValueError, KeyError) as error:
            self.error(str(error))

    def forget(self, source):
        try:
            _, note = local_source(Store(), source)
            if note['hash'] != source['revision']:
                raise ValueError(tr('Diese Erinnerung wurde inzwischen geändert. Bitte die aktuelle Fassung in den Gedächtniseinstellungen prüfen.'))
            if QMessageBox.question(self, tr('Lumen · Erinnerung vergessen'),
                    tr('„{0}“ dauerhaft vergessen? Bei aktiviertem Abgleich gilt dies auch auf verbundenen Geräten.', note['title']),
                    QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
                return
            from memory_bridge import MemoryBridge
            if self.backend.memory is None or self.backend.memory.closed:
                self.backend.memory = MemoryBridge(self.backend)
            def done(_):
                updated = dict(self.snapshot, sources=[s for s in self.snapshot.get('sources', []) if s['id'] != source['id']])
                self.receive(updated)
                self.backend.memoryStatus.emit(tr('Erinnerung vergessen. Die bestehende Antwort bleibt unverändert.'))
            self.backend.memory.job('forget', done, self.error, path=note['path'], expected=note['hash'])
        except (OSError, ValueError, KeyError) as error:
            self.error(str(error))
