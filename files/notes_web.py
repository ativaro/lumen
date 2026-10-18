"""Local Server Notes presentation; the existing native notebook owns every write."""
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QUrl, Qt
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget, QVBoxLayout, QPushButton
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo
from PySide6.QtGui import QPalette
from lumen_i18n import tr, language
from note_tags import tags

ASSETS = Path(__file__).with_name('notes_web')


class Offline(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        allowed = (url.scheme() == 'file' and Path(url.toLocalFile()) in {ASSETS / n for n in ('index.html', 'notes.js', 'notes.css')})
        allowed |= url.toString() == 'qrc:///qtwebchannel/qwebchannel.js'
        allowed |= url.scheme() == 'data' and info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeFontResource
        info.block(not allowed)


class Page(QWebEnginePage):
    def acceptNavigationRequest(self, url, kind, main):
        return main and url == QUrl.fromLocalFile(str(ASSETS / 'index.html'))

    def createWindow(self, kind): return None
    def chooseFiles(self, mode, old, types): return []


class Bridge(QObject):
    changed = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.epoch = 0
        self.ack = 0
        self.identity = None
        self.limit = 100
        self.previous = None
        self.stamp = None

    def document(self, note, selected=False):
        from notes_structure import document_parts
        w = self.window
        return dict(id=note['path'], title=w.title.text() if selected else note['title'],
                    body=w.editor.toPlainText() if selected else document_parts(note['text'][:2000],note['title'])[3],
                    tags=tags(w.document_text()) if selected else note['tags'],
                    updated=note.get('modified', 0), shared=w.share_note.isChecked() if selected else False)

    @Slot(result=str)
    def snapshot(self):
        w = self.window
        # A styled widget's Base role may be its painted window background.
        palette = QApplication.palette()
        appearance = {key: palette.color(role).name() for key, role in {
            'window': QPalette.Window, 'surface': QPalette.Base, 'soft': QPalette.AlternateBase,
            'text': QPalette.Text, 'button': QPalette.Button, 'line': QPalette.Mid,
            'muted': QPalette.PlaceholderText, 'accent': QPalette.Highlight,
            'on-accent': QPalette.HighlightedText,
        }.items()}
        from desktop_design import WEB_TOKENS
        appearance.update(WEB_TOKENS)
        from appearance_tokens import RADII
        family = w.font().family()
        appearance['font-family'] = json.dumps('DM Sans' if family == 'DM Sans 9pt' else family)
        appearance['radius'] = str(RADII.get(QApplication.instance().property('lumenDesign'), 8)) + 'px'
        appearance['color-scheme'] = 'light' if palette.color(QPalette.Window).lightness() > 128 else 'dark'
        identity = (str(w.book.root) if w.book else '', w.area, w.doc['path'] if w.doc else '')
        if identity != self.identity:
            self.identity = identity; self.epoch += 1; self.ack = 0; self.limit = 100
        rows = [w.entries.item(i).data(Qt.UserRole) for i in range(w.entries.count())]
        collections = [dict(id=w.collections.item(i).data(Qt.UserRole), title=w.collections.item(i).text(), name=w.collections.item(i).text().rsplit('  ', 1)[0]) for i in range(w.collections.count())]
        return json.dumps(dict(epoch=self.epoch, ack=self.ack, doc=self.document(w.doc, True) if w.doc else None,
            notes=[self.document(w.notes[p]) for p in rows[:self.limit] if p in w.notes], more=len(rows)>self.limit,
            collections=collections, collection=w.collection, q=w.search.text(), status=w.status.text(),
            banner=w.banner.text() if not w.banner.isHidden() else '', conflict=w.conflict, dirty=w.dirty,
            busy=bool((w.job and not w.writing) or (w.engine and w.engine.busy)), ready=bool(w.book), language=language(), appearance=appearance), ensure_ascii=False)

    def publish(self):
        w = self.window
        stamp = (id(w.notes), id(getattr(w,'note_items',None)), w.editor.document().revision(), w.title.text(), w.heading_prefix,
                 w.doc.get('hash') if w.doc else None, str(w.book.root) if w.book else '', w.area, w.collection,
                 w.search.text(), w.status.text(), w.banner.text(), w.banner.isHidden(), w.conflict, w.dirty,
                 bool(w.job), bool(w.writing), w.tabs.currentIndex(), w.share_note.isChecked(), w.palette().cacheKey(), self.ack, self.limit)
        if stamp == self.stamp: return
        self.stamp = stamp
        value = self.snapshot()
        if value != self.previous:
            self.previous = value; self.changed.emit(value)

    @Slot(str)
    def command(self, raw):
        w = self.window
        try:
            if len(raw) > 8 * 1024**2: raise ValueError(tr('Notiz größer als 1 MiB. Bitte aufteilen.'))
            value = json.loads(raw)
            if not isinstance(value, dict): raise ValueError('Invalid Notes command')
            action = value.get('action')
            self.snapshot()  # Validate against the current notebook/selection, not a stale web snapshot.
            if action in ('edit', 'tag', 'share'):
                if not w.doc or value.get('id') != w.doc['path'] or value.get('epoch') != self.epoch: return
                if w.area != 'user' or not w.editor.isEnabled(): return
            if action == 'edit':
                title, body, sequence = value.get('title'), value.get('body'), value.get('sequence')
                if not isinstance(title,str) or len(title)>300 or not isinstance(body,str) or len(body.encode())>1024**2 or type(sequence) is not int: raise ValueError('Invalid note text')
                if sequence <= self.ack: return
                w.loading = True
                try:
                    w.title.setText(title)
                    blocked=w.editor.blockSignals(True)
                    try: w.editor.setPlainText(body)
                    finally: w.editor.blockSignals(blocked)
                finally: w.loading = False
                self.ack = sequence; w.edited()
            elif action == 'tag':
                if type(value.get('checked')) is not bool: raise ValueError('Invalid tag action')
                w.note_tags.change(value.get('tag'), value['checked'])
            elif action == 'share': w.share_note.toggle()
            elif action == 'search':
                if not isinstance(value.get('value'),str) or len(value['value'])>200: raise ValueError('Invalid query')
                self.limit=100; w.search.setText(value['value'])
            elif action == 'collection':
                key=value.get('id')
                if key not in {w.collections.item(i).data(Qt.UserRole) for i in range(w.collections.count())}: return
                if w.dirty: w.save_note(lambda:w.set_collection(key))
                else: w.set_collection(key)
                self.limit=100
            elif action == 'open':
                if value.get('id') in w.notes: w.open_note(value['id'])
            elif action == 'more_notes': self.limit += 100
            elif action in ('settings', 'more'):
                menu=w.notebook_menu if action=='settings' else w.more_button.menu()
                w.rich_editor.load_source()
                menu.popup(w.notes_web.mapToGlobal(w.notes_web.rect().center()))
            elif action == 'daily':
                from notes_capture import open_daily
                open_daily(w)
            elif action == 'template':
                from notes_capture import choose_template
                choose_template(w)
            elif action in ('save','create','create_collection','history','archive','reload','copy'):
                getattr(w,dict(save='save_note',reload='reload_external',copy='save_copy').get(action,action))()
        except (ValueError, TypeError, OSError) as error:
            w.status.setText(str(error)); w.banner.setText(str(error)); w.banner.show()
        self.publish()


def install(window):
    w = window
    if not all((ASSETS/name).is_file() for name in ('index.html','notes.js','notes.css')): return
    original = w.takeCentralWidget()
    stack = QStackedWidget(w); w.setCentralWidget(stack)
    native = QWidget(); layout = QVBoxLayout(native); layout.setContentsMargins(0,0,0,0)
    back = QPushButton(tr('Lumen Notes')); layout.addWidget(back); layout.addWidget(original)
    view = QWebEngineView(); w.notes_web = view
    profile = QWebEngineProfile(w); interceptor = Offline(profile); profile.setUrlRequestInterceptor(interceptor)
    profile.downloadRequested.connect(lambda download: download.cancel())
    page = Page(profile, view); view.setPage(page)
    settings = page.settings()
    for name in ('LocalContentCanAccessRemoteUrls','LocalStorageEnabled','JavascriptCanOpenWindows','JavascriptCanAccessClipboard','JavascriptCanPaste','PluginsEnabled','HyperlinkAuditingEnabled','DnsPrefetchEnabled','ScreenCaptureEnabled'):
        settings.setAttribute(getattr(QWebEngineSettings.WebAttribute,name),False)
    settings.setUnknownUrlSchemePolicy(QWebEngineSettings.DisallowUnknownUrlSchemes)
    page.permissionRequested.connect(lambda permission:permission.deny())
    page.fileSystemAccessRequested.connect(lambda request:request.reject())
    bridge = Bridge(w); channel = QWebChannel(page); channel.registerObject('notes', bridge); page.setWebChannel(channel)
    stack.addWidget(view); stack.addWidget(native)
    def unavailable(*_):
        w.rich_editor.load_source(); stack.setCurrentWidget(native)
        w.status.setText(tr('Die Schreibansicht wurde beendet. Deine gesicherten Eingaben sind in der nativen Ansicht verfügbar.'))
    page.renderProcessTerminated.connect(unavailable)
    page.loadFinished.connect(lambda ok: unavailable() if not ok else None)
    back.clicked.connect(lambda:(w.tabs.setCurrentIndex(0),w.switch_area('user'),stack.setCurrentWidget(view)))
    def section(index):
        stack.setCurrentWidget(view if index==0 and w.area=='user' else native)
    w.tabs.currentChanged.connect(section)
    for menu in (w.notebook_menu,w.more_button.menu()):
        menu.triggered.connect(lambda *_: (w.rich_editor.load_source(),stack.setCurrentWidget(native)))
    timer = QTimer(w); timer.setInterval(150); timer.timeout.connect(bridge.publish); timer.start()
    # Keep every QObject alive for the page's lifetime; profile must outlive the page.
    w.notes_web_objects = (bridge, channel, profile, interceptor, page, stack, timer)
    page.load(QUrl.fromLocalFile(str(ASSETS / 'index.html')))


def flush_close(w, event):
    """Read the last browser keystroke before native close/save can run."""
    if not hasattr(w, 'notes_web_objects'): return False
    if getattr(w, '_notes_close_ready', False):
        w._notes_close_ready = False
        return False
    event.ignore()
    if getattr(w, '_notes_flush_pending', False): return True
    w._notes_flush_pending = True
    def received(value):
        w._notes_flush_pending = False
        if isinstance(value, str): w.notes_web_objects[0].command(value)
        w._notes_close_ready = True
        QTimer.singleShot(0, w.close)
    w.notes_web.page().runJavaScript('window.lumenNotes?.flush() ?? null', received)
    return True
