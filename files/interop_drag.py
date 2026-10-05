"""A native object drag carries only a validated Lumen URL; imports stay reviewed."""
import json
import time

from PySide6.QtCore import Qt, QObject, QEvent, QMimeData, QTimer
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget, QTreeWidget, QWidget
from lumen_i18n import tr
from interop_data import Registry, validate_payload


def make_mime(payload, registry):
    payload = validate_payload(payload)
    if not payload.get('source'): raise ValueError(tr('Für diese Auswahl fehlt ein Lumen-Verweis.'))
    payload['source_url'] = registry.register(payload['source'])
    with registry.library.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS drag_payloads (url TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL NOT NULL)')
        db.execute('INSERT OR REPLACE INTO drag_payloads VALUES (?,?,?)', (payload['source_url'], json.dumps(payload), time.time()))
        db.execute('DELETE FROM drag_payloads WHERE url NOT IN (SELECT url FROM drag_payloads ORDER BY updated DESC LIMIT 100)')
    mime = QMimeData(); mime.setText(payload['source_url']); return mime


def payload_from_mime(mime, registry):
    if not mime.hasText(): raise ValueError(tr('Kein Lumen-Verweis in dieser Auswahl.'))
    url = mime.text().strip(); ref = registry.resolve(url)
    with registry.library.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drag_payloads'").fetchone()
        row = db.execute('SELECT data FROM drag_payloads WHERE url=?', (url,)).fetchone() if exists else None
    if row is None: raise ValueError(tr('Diese Ziehauswahl ist nicht mehr verfügbar. Den Inhalt erneut aus seiner Lumen-App ziehen.'))
    payload = validate_payload(json.loads(row['data']))
    if payload.get('source_url') != url or any(payload['source'].get(key) != ref.get(key) for key in ('app', 'kind', 'id')):
        raise ValueError(tr('Die Herkunft der Ziehauswahl stimmt nicht mehr überein.'))
    return payload


class EntryList(QListWidget):
    """Drag the selected library item, using the same saved source as its menu."""
    def __init__(self, window):
        super().__init__(window); self.owner = window; self.setDragEnabled(True)

    def startDrag(self, supported):
        from interop_ui import with_saved, capture, error, root_for
        if not self.currentItem() or getattr(self.owner, 'job', None): return
        def drag():
            try:
                self.owner._interop_focus = self
                payload = capture(self.owner); transfer = QDrag(self)
                transfer.setMimeData(make_mime(payload, Registry(root_for(self.owner))))
                transfer.exec(Qt.CopyAction | Qt.LinkAction, Qt.LinkAction)
            except Exception as exc: error(self.owner, exc)
        try: with_saved(self.owner, drag)
        except Exception as exc: error(self.owner, exc)


class EntryTree(QTreeWidget):
    def __init__(self, window):
        super().__init__(window); self.owner=window; self.setDragEnabled(True)

    startDrag=EntryList.startDrag


class DropFilter(QObject):
    def __init__(self, window, callback):
        super().__init__(window); self.window = window; self.callback = callback
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.scan)
        self.scan()

    def scan(self):
        for widget in [self.window, *self.window.findChildren(QWidget)]:
            widget.setAcceptDrops(True); widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.ChildAdded:
            self.timer.start(0); return False
        if event.type() not in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop): return False
        mime = event.mimeData()
        if not mime.hasText() or not mime.text().strip().startswith('lumen://object/'): return False
        try:
            from interop_ui import root_for
            payload = payload_from_mime(mime, Registry(root_for(self.window)))
        except (ValueError, TypeError, OSError):
            event.ignore(); return True
        event.setDropAction(Qt.CopyAction); event.accept()
        if event.type() == QEvent.Drop:
            def receive():
                from interop_ui import error
                try: self.callback(payload)
                except Exception as exc: error(self.window, exc)
            timer=QTimer(self);timer.setSingleShot(True)
            timer.timeout.connect(receive);timer.timeout.connect(timer.deleteLater);timer.start(0)
        return True


def install_drop_filter(window, callback):
    if not hasattr(window, 'lumen_drop_filter'): window.lumen_drop_filter = DropFilter(window, callback)
    return window.lumen_drop_filter
