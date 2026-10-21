"""Compose host with a private synthetic text pilot; no renderer-to-OS bridge."""
from pathlib import Path
from dataclasses import dataclass, replace
import os
import stat
import tempfile
import threading
import hashlib
import json
import time
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, QDateTime, QFileSystemWatcher, Signal, QLockFile, Slot
from PySide6.QtNetwork import QNetworkCookie, QSslCertificate
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QStackedWidget, QMessageBox
from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
from studio_design import font
from lumen_qt import is_deleted
from server_app_session import AppSession, SessionError, APPS, Binding, origin
import lumen_connect

try:
    from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineProfileBuilder,
        QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE = True
except ImportError:
    WEBENGINE = False


# Isolated world, main frame only; it exposes no native objects or credentials.
DRAFT_SCRIPT = '''(() => {
 const capture=event=>{const input=document.querySelector('#translation-text');
   if(event && event.target!==input)return;
   if(!event && typeof window.__lumenComposeDraft==='string')return;
   if(input && typeof input.value==='string' && input.value.length<=1048576)
     window.__lumenComposeDraft=input.value;};
 document.addEventListener('input',capture,true);
 document.addEventListener('change',capture,true);
 new MutationObserver(()=>capture()).observe(document,{childList:true,subtree:true});
 capture();
})()'''
DRAFT_READ = "window.__lumenComposeDraft ?? ''"
NOTES_DRAFT_SCRIPT = '''(() => {
 const capture=()=>{
   const note=document.querySelector('.knowledge-editor');
   if(!note)return;
   const warning=new Event('beforeunload',{cancelable:true});
   if(window.dispatchEvent(warning)){window.__lumenNotesDraft='';return;}
   const text=(note.querySelector('.title-input')?.value ?? '')+'\\n\\n'+
     (note.querySelector('.note-rich-text')?.innerText ?? '');
   window.__lumenNotesDraft=new TextEncoder().encode(text).length<=1048576 ? text :
     text.slice(0,262000)+'\\n\\n[Textkopie gekürzt]';
 };
 window.__lumenCaptureNotesDraft=capture;
 document.addEventListener('input',()=>setTimeout(capture,0),true);
 document.addEventListener('change',()=>setTimeout(capture,0),true);
 new MutationObserver(capture).observe(document,{childList:true,subtree:true,characterData:true,
   attributes:true,attributeFilter:['disabled']});
 capture();
})()'''
NOTES_DRAFT_READ = "window.__lumenCaptureNotesDraft?.(); window.__lumenNotesDraft ?? ''"


def _desktop_theme():
    value=QApplication.instance().property('lumenDesign')
    return value if type(value) is str and value in ('glass','graphite','atelier','midnight') else None


def _theme_source(value):
    assignment='delete window.__lumenDesktopTheme' if value is None else 'window.__lumenDesktopTheme='+json.dumps(value)
    return assignment+";window.dispatchEvent(new Event('lumen-desktop-theme'));true"


def _connection():
    """A scope is not a generation: retain the actual private file identity too."""
    try:
        path=lumen_connect.CONFIG
        if not path.is_absolute() or path.resolve()!=path:raise ValueError
        def stamp():
            s=path.lstat();parent=path.parent.stat()
            if (not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode & 0o077
                    or s.st_size>65536 or parent.st_uid!=os.getuid() or parent.st_mode & 0o022):raise ValueError
            return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,parent.st_dev,parent.st_ino)
        before=stamp();config=lumen_connect.read_config()
        if stamp()!=before:raise ValueError
        return config,(str(path),before,lumen_connect.connection_scope(config),config.get('ca_file'))
    except (OSError,ValueError,KeyError,TypeError):raise SessionError('connection') from None


@dataclass(frozen=True)
class ImportLease:
    window: object
    binding: object
    permissions_revision: int
    session: object
    generation: int
    connection: tuple
    cancelled: object
    destroyed: object
    gui_thread: int
    page: object
    profile: object

    def check(self):
        # Worker checks must never call Qt, including page/profile identity helpers.
        try:
            if (self.cancelled.is_set() or self.destroyed.is_set() or self.session.binding!=self.binding
                    or self.session._generation!=self.generation or not self.session.usable
                    or _connection()[1]!=self.connection or not self.session.usable
                    or self.session._generation!=self.generation
                    or self.cancelled.is_set()):raise SessionError('context')
        except SessionError:
            self.cancelled.set();raise

    def native_revision(self,job):
        job.check();self.check();config,_=_connection()
        me=lumen_connect.request(config,'/bridge/me',timeout=10)
        job.check();self.check()
        revision=me.get('permissions_revision')
        if (me.get('id')!=self.binding.account or me.get('device_id')!=self.binding.device
                or type(revision) is not int or revision<0
                or self.permissions_revision>=0 and revision!=self.permissions_revision
                or not isinstance(me.get('capabilities'),list)
                or not {'drive',APPS[self.binding.app][1]}<=set(me['capabilities'])):raise SessionError('identity')
        return revision

    def accept_import(self,reference,resolved):
        if threading.get_ident()!=self.gui_thread:raise SessionError('thread')
        self.window._accept_import(self,reference,resolved)


class Call(QThread):
    def __init__(self, function, parent):
        super().__init__(parent); self.function = function; self.ok = False

    def run(self):
        try:self.function(); self.ok = True
        except Exception:pass  # Only fixed native status text crosses the UI boundary.


def text_pilot_context(profile,job):
    if lumen_connect.CONFIG!=profile/'config/lumen-server/connection.json':raise SessionError('profile')
    job.check();config,stamp=_connection()
    if urlsplit(origin(config['server'])).hostname not in ('127.0.0.1','localhost','::1'):raise SessionError('origin')
    me=lumen_connect.request(config,'/bridge/me',timeout=10)
    job.check()
    if (_connection()[1]!=stamp or me.get('device_id')!=config.get('device_id')
            or me.get('capabilities')!=['translate'] or type(me.get('permissions_revision')) is not int
            or me['permissions_revision']<0):raise SessionError('identity')
    binding=Binding(config['server'],me.get('id'),me.get('device_id'),'compose')
    return config,binding,stamp


def run_text_pilot(app,profile):
    from interop_dialogs import run_job
    from tools_app import forward_window,listen_window
    from lumen_activation import present
    app.setApplicationName('lumen-translate');app.setDesktopFileName('lumen-translate')
    app.setQuitOnLastWindowClosed(False)
    try:
        context=run_job(None,'Lumen Compose · Private App-Sitzung wird geprüft …',lambda job:text_pilot_context(profile,job))
        if context is None:return 1
        config,binding,stamp=context
        identity=json.dumps([binding.origin,binding.account,binding.device,binding.app])
        root=profile/'runtime'/('compose-'+hashlib.sha256(identity.encode()).hexdigest()[:24])
        if root.is_symlink() or root.resolve()!=root:raise SessionError('profile')
        root.mkdir(mode=0o700,exist_ok=True)
        if root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:raise SessionError('profile')
        if forward_window(root,{},private=True):return 0
        lock=QLockFile(str(root/'window.lock'))
        if not lock.tryLock(0):
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if forward_window(root,{},private=True):return 0
                time.sleep(.05)
            raise SessionError('busy')
        try:
            window=ServerAppWindow(AppSession(config,binding),root,pilot_connection=stamp)
            server=listen_window(window,lambda _:present(window),root=root)
            app.setApplicationDisplayName('Lumen Compose');app.setQuitOnLastWindowClosed(True)
            window.show()
            try:return app.exec()
            finally:server.close()
        finally:lock.unlock()
    except (OSError,ValueError):
        QMessageBox.warning(None,'Lumen Compose','Die private App-Sitzung ist nicht verfügbar. Kein lokaler Ersatz wurde geöffnet.')
        return 1


if WEBENGINE:
    class OriginRequests(QWebEngineUrlRequestInterceptor):
        def __init__(self, window, parent):
            super().__init__(parent); self.window = window

        def interceptRequest(self, info):
            w = self.window
            if not w._live or not w.session.usable or not w.session.binding.resource(info.requestUrl().toString()):
                info.block(True); return
            info.setHttpHeader(b'Authorization', b'')
            method=bytes(info.requestMethod())
            # This endpoint only transforms draft strings; it persists no note.
            draft_tags=(w._binding.app=='notes' and method==b'POST'
                        and info.requestUrl().path()=='/api/note-drafts/tags')
            if method not in (b'GET', b'HEAD', b'OPTIONS') and not draft_tags:
                w.session.observe_write()

    class BoundPage(QWebEnginePage):
        def __init__(self, profile, window):
            super().__init__(profile, window); self.window = window

        def acceptNavigationRequest(self, url, kind, main):
            return bool(main and self.window._live and self.window.session.usable
                        and self.window.session.binding.navigation(url.toString()))

        def createWindow(self, kind):return None
        def chooseFiles(self, mode, old, types):return []


class ServerAppWindow(QMainWindow):
    import_reference_ready=Signal(object,object)

    def __init__(self, session, profile_root, parent=None, *, pilot_connection=None):
        super().__init__(parent)
        if not isinstance(session, AppSession) or session.binding.app not in ('compose','notes'):raise SessionError('identity')
        self.session = session
        self._app_title = 'Lumen Notes' if session.binding.app=='notes' else 'Lumen Compose'
        self._binding=session.binding;self._bound_profile=None;self._profile_cookie=None
        self._live = self._loaded = self._disposed = self._closing = False
        self._generation = 0; self._worker = None; self._temporary = None
        self._gui_thread=threading.get_ident();self._import_destroyed=threading.Event()
        self.destroyed.connect(self._import_destroyed.set)
        self._import_lease=self._import_reference=self._import_error=None
        self._import_running=self._import_accepting=self._import_close=False
        self._connection_watcher=None
        self._pilot_connection=pilot_connection;self._pilot_invalid=False
        self._theme_serial=0;self._theme_reveal=False;self._theme_script=None;self._theme_watcher=None
        self._theme_timer=QTimer(self);self._theme_timer.setSingleShot(True)
        self._theme_timer.timeout.connect(self._send_theme)
        self.profile = self.page = self.view = None
        self.setWindowTitle(self._app_title); self.resize(1000, 720); self.setFont(font(14))
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.status_page = QWidget(); layout = QVBoxLayout(self.status_page)
        layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
        layout.addWidget(AppHeader(self._app_title))
        self.status = QLabel('App-Sitzung wird geprüft.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.retry = QPushButton('Erneut prüfen');self.retry.clicked.connect(lambda:self.verify(reconnect=True));layout.addWidget(self.retry,0,Qt.AlignLeft)
        self.copy = QPushButton('Entwurf kopieren');self.copy.clicked.connect(self.copy_draft);self.copy.setEnabled(False);layout.addWidget(self.copy,0,Qt.AlignLeft)
        if session.binding.app=='notes':self.copy.setText('Textkopie der ungespeicherten Notiz')
        if pilot_connection is not None and session.binding.app!='notes':self.copy.hide()
        layout.addStretch();self.stack.addWidget(self.status_page)
        self.timer = QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.verify)
        if not WEBENGINE:
            self.status.setText('Qt WebEngine fehlt. Diese Serveransicht ist nicht verfügbar.')
            self.retry.setEnabled(False);return
        self._profile(profile_root)
        self._theme_watcher=getattr(QApplication.instance(),'theme_watcher',None)
        if self._theme_watcher is not None:
            self._theme_watcher.fileChanged.connect(self._theme_changed)
            self._theme_watcher.directoryChanged.connect(self._theme_changed)
        if pilot_connection is not None:
            if not self._pilot_current():raise SessionError('connection')
            self._watch_connection()
        QTimer.singleShot(0,lambda:self.verify(reconnect=True))

    def _profile(self, profile_root):
        root = Path(profile_root)
        if (not root.is_absolute() or root.resolve()!=root or not root.is_dir()
                or root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o022):raise SessionError('profile')
        self._temporary = tempfile.TemporaryDirectory(prefix='lumen-app-',dir=root)
        builder = QWebEngineProfileBuilder()
        builder.setPersistentStoragePath(self._temporary.name)
        builder.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        builder.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        ca = self.session._config.get('ca_file')
        if ca:
            data = Path(ca).read_bytes()
            if len(data)>1024*1024 or b'PRIVATE KEY' in data:raise SessionError('tls')
            certs = QSslCertificate.fromData(data)
            if not certs:raise SessionError('tls')
            builder.setAdditionalTrustedCertificates(certs)
        # An empty name is off-the-record; the builder retains the explicit CA.
        self.profile = builder.createProfile('',self)
        if self.profile is None:raise SessionError('profile')
        self._bound_profile=self.profile
        temporary = self._temporary
        def cleanup(attempt=0):
            try:temporary.cleanup()
            except OSError:
                if attempt>=3:raise
                QTimer.singleShot(100,lambda:cleanup(attempt+1))
                return
            if not is_deleted(self) and self._closing:self._finish_close()
        # Chromium's final filesystem work can outlive QObject.destroyed.
        self.profile.destroyed.connect(lambda *_:QTimer.singleShot(0,cleanup))
        self.interceptor = OriginRequests(self,self.profile);self.profile.setUrlRequestInterceptor(self.interceptor)
        self.profile.downloadRequested.connect(lambda request:request.cancel())
        self.profile.cookieStore().setCookieFilter(lambda request:not request.thirdParty)
        self.view = QWebEngineView();self.page = BoundPage(self.profile,self);self.view.setPage(self.page)
        settings = self.page.settings()
        for name in ('LocalContentCanAccessRemoteUrls','LocalContentCanAccessFileUrls','JavascriptCanOpenWindows',
                     'JavascriptCanAccessClipboard','JavascriptCanPaste','PluginsEnabled','HyperlinkAuditingEnabled',
                     'DnsPrefetchEnabled','ScreenCaptureEnabled'):
            settings.setAttribute(getattr(QWebEngineSettings.WebAttribute,name),False)
        settings.setUnknownUrlSchemePolicy(QWebEngineSettings.UnknownUrlSchemePolicy.DisallowUnknownUrlSchemes)
        self.page.permissionRequested.connect(lambda permission:permission.deny())
        self.page.fileSystemAccessRequested.connect(lambda request:request.reject())
        self.page.certificateError.connect(self._certificate)
        self.page.renderProcessTerminated.connect(lambda *_:self.block('renderer'))
        self.page.loadFinished.connect(self._loaded_page)
        self.profile.cookieStore().cookieAdded.connect(lambda c,p=self.profile:self._cookie_added(p,c))
        self.profile.cookieStore().cookieRemoved.connect(lambda c,p=self.profile:self._cookie_removed(p,c))
        script = QWebEngineScript();script.setName(self._app_title+' draft')
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(NOTES_DRAFT_SCRIPT if self.session.binding.app=='notes' else DRAFT_SCRIPT)
        self.page.scripts().insert(script)
        self._theme_script=QWebEngineScript();self._theme_script.setName('Lumen desktop theme')
        self._theme_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._theme_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        self._theme_script.setRunsOnSubFrames(False)
        self._theme_script.setSourceCode(_theme_source(_desktop_theme()));self.page.scripts().insert(self._theme_script)
        self.stack.addWidget(self.view)

    @Slot(str)
    def _theme_changed(self, _path):
        self._queue_theme()

    def _queue_theme(self, *, reveal=False):
        if self._disposed:return
        self._theme_serial+=1;self._theme_reveal|=reveal
        if (not self._closing and self.page is not None and not is_deleted(self.page)
                and self.profile is self._bound_profile and self.profile is not None and not is_deleted(self.profile)
                and self.view is not None and not is_deleted(self.view) and self.view.page() is self.page
                and self.page.profile() is self._bound_profile and self._theme_script is not None):
            scripts=self.page.scripts();scripts.remove(self._theme_script)
            self._theme_script.setSourceCode(_theme_source(_desktop_theme()));scripts.insert(self._theme_script)
        # Reuse the existing native watcher after its QSettings/palette update.
        if not self._closing:self._theme_timer.start(0)

    def _theme_current(self, context):
        page,profile,view,session,binding,generation,session_generation,serial,theme=context
        if (is_deleted(self) or self._disposed or self._closing or not self._live or not self._loaded
                or page is not self.page or profile is not self.profile or view is not self.view
                or session is not self.session or binding!=self._binding or binding!=session.binding
                or generation!=self._generation or session_generation!=session._generation
                or serial!=self._theme_serial or theme!=_desktop_theme() or not session.usable
                or not self._pilot_current()):return False
        return bool(all(obj is not None and not is_deleted(obj) for obj in (page,profile,view))
                    and view.page() is page and self._cookie_valid())

    def _send_theme(self):
        context=(self.page,self.profile,self.view,self.session,self._binding,self._generation,
                 self.session._generation,self._theme_serial,_desktop_theme())
        if not self._theme_current(context):return
        page=context[0]
        def applied(value):
            # Qt may invoke this callback while destroying the old page.
            if value is not True or not self._theme_current(context):return
            if self._theme_reveal:
                self._theme_reveal=False;self.stack.setCurrentWidget(context[2])
        page.runJavaScript(_theme_source(context[-1]),QWebEngineScript.ScriptWorldId.MainWorld,applied)

    def _cancel_theme(self):
        self._theme_timer.stop();self._theme_serial+=1;self._theme_reveal=False

    def verify(self, *, reconnect=False, ready=None):
        if self._disposed or self._closing or not WEBENGINE or self.page is None or self._worker is not None:return
        if not self._pilot_current():self._invalidate_pilot();return
        if self.session.state=='identity':self.retry.setEnabled(False);return
        if reconnect and self._loaded and not self.session.has_cookie:
            self.block(self.session.state)
            self.status.setText('Sitzung beendet. Entwurf kopieren und die App erneut öffnen.')
            self.retry.setEnabled(False);return
        generation = self._generation
        self.retry.setEnabled(False)
        connection=self._pilot_connection
        def check():
            if connection is not None and _connection()[1]!=connection:raise SessionError('connection')
            if reconnect and not self.session.has_cookie:self.session.connect()
            else:self.session.check()
            if connection is not None and _connection()[1]!=connection:raise SessionError('connection')
        worker = Call(check,self);self._worker = worker
        worker.finished.connect(lambda:self._verified(worker,generation,ready));worker.start()

    def _verified(self, worker, generation, ready=None):
        self._worker = None;worker.deleteLater()
        if self._disposed:return
        if self._closing:self._closing=False;self.close();return
        if generation!=self._generation:return
        if not self._pilot_current():self._invalidate_pilot();return
        self.retry.setEnabled(True)
        if not worker.ok or not self.session.usable:self.block(self.session.state);return
        if self._loaded:
            if not self._cookie_valid():self.block('cookie');return
            self._live=True;self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self._queue_theme(reveal=True);self.timer.start()
            if ready is not None:ready()
            return
        self.timer.start()
        if self._live:return
        cookies = QNetworkCookie.parseCookies(self.session.web_cookie())
        if len(cookies)!=1 or cookies[0].sameSitePolicy()!=QNetworkCookie.SameSite.Strict:self.block('cookie');return
        self._live = True
        # Initialize Chromium's blank page before waiting for its cookie signal.
        self.page.runJavaScript('void 0',QWebEngineScript.ScriptWorldId.ApplicationWorld)
        self.profile.cookieStore().loadAllCookies()
        self.profile.cookieStore().setCookie(cookies[0],QUrl(self.session.binding.origin))

    def _cookie_valid(self):
        cookie=self._profile_cookie
        # Qt 6.12's signal omits SameSite; native exchange/insertion enforce Strict.
        return bool(cookie is not None and self.session.binding==self._binding
            and self.profile is self._bound_profile and not is_deleted(self.profile)
            and self.page is not None and self.page.profile() is self._bound_profile
            and self.session.has_cookie and bytes(cookie.value())==self.session._cookie
            and cookie.domain()==QUrl(self._binding.origin).host() and cookie.path()=='/'
            and cookie.isHttpOnly() and cookie.isSecure()
            and (cookie.isSessionCookie() or cookie.expirationDate()>QDateTime.currentDateTimeUtc()))

    def _cookie_added(self, profile, cookie):
        if self._disposed or self._closing or bytes(cookie.name())!=b'lumen_session':return
        self._profile_cookie=QNetworkCookie(cookie) if profile is self._bound_profile else None
        if not self._cookie_valid():
            self._profile_cookie=None;profile.cookieStore().deleteCookie(cookie)
            self.session.close('identity');self.block('identity');return
        if not self._live or not self.session.usable:return
        if not self._loaded:self.view.load(QUrl(self.session.url))
        else:
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self._queue_theme(reveal=True)

    def _cookie_removed(self, profile, cookie):
        if self._disposed or self._closing or profile is not self._bound_profile or bytes(cookie.name())!=b'lumen_session':return
        self._profile_cookie=None
        self.block(self.session.state if self.session.state in ('identity','revoked','expired') else 'cookie')

    def _loaded_page(self, ok):
        if self._disposed or not self._live or not self.session.usable:return
        if not ok:self.block('load');return
        self._loaded = True;self._queue_theme(reveal=True)

    def _certificate(self, error):
        error.rejectCertificate();self.block('tls')

    def _invalidate_import(self,reason,lease=None):
        if lease is not None and self._import_lease is not lease:
            lease.cancelled.set();return
        if self._import_lease is not None:self._import_lease.cancelled.set()
        self._import_lease=None;self._import_accepting=False;self._import_reference=None
        self._import_error=reason

    def _watch_connection(self):
        if self._connection_watcher is None:
            self._connection_watcher=QFileSystemWatcher(self)
            self._connection_watcher.fileChanged.connect(lambda *_:self._connection_changed(True))
            self._connection_watcher.directoryChanged.connect(lambda *_:self._connection_changed(False))
        path=lumen_connect.CONFIG;watcher=self._connection_watcher
        missing={str(path),str(path.parent)}-set(watcher.files())-set(watcher.directories())
        if missing and watcher.addPaths(sorted(missing)):raise SessionError('connection')

    def _connection_changed(self,file_event):
        lease=self._import_lease
        try:
            current=_connection()[1]
            changed=(file_event or lease is not None and current!=lease.connection
                     or self._pilot_connection is not None and current!=self._pilot_connection)
            self._watch_connection()
        except SessionError:changed=True
        if changed:
            if self._pilot_connection is not None:self._invalidate_pilot();return
            if lease is not None:self._generation+=1
            self._invalidate_import('connection')

    def _pilot_current(self):
        if self._pilot_connection is None:return True
        try:return not self._pilot_invalid and _connection()[1]==self._pilot_connection
        except SessionError:return False

    def _invalidate_pilot(self):
        self._pilot_invalid=True;self.session.close('identity');self._profile_cookie=None
        if not self._disposed and not self._closing:
            self.block('identity');self.retry.setEnabled(False)

    def _import_gui(self,lease):
        if threading.get_ident()!=self._gui_thread:raise SessionError('thread')
        lease.check()
        if (self._disposed or self._closing or self._import_close or not self._live or not self._loaded
                or self._import_lease is not lease or self.session is not lease.session
                or self.page is not lease.page or self.profile is not lease.profile
                or self.view is None or is_deleted(self.view) or is_deleted(self.page)
                or not self._cookie_valid() or self.view.page() is not self.page):raise SessionError('identity')

    def _fresh_import(self,lease,callback):
        try:self._import_gui(lease)
        except SessionError:
            self._invalidate_import('context',lease);return
        if self._worker is not None:
            QTimer.singleShot(20,lambda:self._fresh_import(lease,callback));return
        def ready():
            try:self._import_gui(lease);callback()
            except Exception:self._invalidate_import('unavailable',lease)
        self.verify(ready=ready)

    def _lumen_file_import(self,token=None):
        """Native-only entry point; no renderer object, menu or launcher registration."""
        if self.session.binding.app!='compose':raise SessionError('identity')
        if threading.get_ident()!=self._gui_thread:raise SessionError('thread')
        if self._import_lease is not None or self._import_running:raise SessionError('busy')
        self._invalidate_import(None)
        try:
            config,connection=_connection()
            if (lumen_connect.connection_scope(config)!=lumen_connect.connection_scope(self.session._config)
                    or config.get('ca_file')!=self.session._config.get('ca_file')):raise SessionError('connection')
            self._watch_connection()
            lease=ImportLease(self,self._binding,-1,self.session,self.session._generation,connection,
                threading.Event(),self._import_destroyed,self._gui_thread,self.page,self.profile)
            self._import_lease=lease;self._import_gui(lease)
            self._fresh_import(lease,lambda:self._run_import(lease,token))
        except SessionError:
            self._invalidate_import('context');raise

    def _run_import(self,lease,token):
        from interop_dialogs import run_job
        from server_file_import_ui import start_import
        self._import_running=True
        try:
            revision=run_job(self,'Lumen Drive · App-Freigabe wird geprüft …',lease.native_revision)
            if revision is None:return
            self._import_gui(lease)
            lease=replace(lease,permissions_revision=revision);self._import_lease=lease
            start_import(self,lease,token)
        except Exception:self._invalidate_import('unavailable')
        finally:
            self._import_running=False
            if not self._import_accepting and self._import_lease is lease:self._invalidate_import('cancelled')
            if self._import_close:self._import_close=False;self.close()

    def _accept_import(self,lease,reference,resolved):
        from server_file_import_ui import _filtered
        self._import_gui(lease)
        if self._import_accepting:raise SessionError('busy')
        result=_filtered(reference,resolved,lease.binding)
        self._import_accepting=True
        # Leave the coordinator's stack before another fresh native/app proof.
        QTimer.singleShot(0,lambda:self._fresh_import(lease,lambda:self._publish_import(lease,result)))

    def _publish_import(self,lease,result):
        from interop_dialogs import run_job
        self._import_running=True
        try:
            revision=run_job(self,'Lumen Drive · Ergebnisfreigabe wird geprüft …',lease.native_revision)
            if revision is None:return
            self._import_gui(lease)
            self._import_reference=result
            lease.cancelled.set();self._import_lease=None;self._import_accepting=False
            self.import_reference_ready.emit(result['reference'],result['resolved'])
        finally:
            self._import_running=False
            if self._import_lease is lease:self._invalidate_import('cancelled')
            if self._import_close:self._import_close=False;self.close()

    def _capture(self, callback):
        if (self.page is None or not self._loaded
                or self.page.lifecycleState()==QWebEnginePage.LifecycleState.Frozen):callback();return
        generation = self._generation
        def captured(value):
            if self._disposed or generation!=self._generation:return
            if isinstance(value,str):self.session.remember_draft(value)
            self.copy.setEnabled(bool(self.session.draft(self.session.binding)) and self._copy_allowed())
            callback()
        self.page.runJavaScript(NOTES_DRAFT_READ if self.session.binding.app=='notes' else DRAFT_READ,
            QWebEngineScript.ScriptWorldId.ApplicationWorld,captured)

    def block(self, reason='offline'):
        if self._disposed or self._closing:return
        self._cancel_theme()
        self._invalidate_import('session')
        self._generation += 1;self._live = False;self.timer.stop();self.session.suspend(reason)
        self.stack.setCurrentWidget(self.status_page);self.retry.setEnabled(True)
        self.status.setText('Schreibbestätigung unklar. Kein erneutes Senden; Auftrag zuerst auf dem Server prüfen.'
                            if self.session.uncertain else 'App-Sitzung nicht verfügbar. Eingaben werden nicht erneut gesendet.')
        def freeze():
            if self.page is not None:self.page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        self._capture(freeze)

    def _copy_allowed(self):
        return (not self._disposed and self.session.binding==self._binding and self.session.state!='identity'
                and (self._pilot_connection is None or self._binding.app=='notes' and self._pilot_current()))

    def copy_draft(self):
        if not self._copy_allowed():return
        QApplication.clipboard().setText(self.session.draft(self._binding))

    def closeEvent(self, event):
        if self._disposed:event.accept();return
        self._cancel_theme()
        event.ignore()
        self._invalidate_import('closed')
        if self._import_running:
            self._import_close=True;self._generation+=1;self.timer.stop()
            dialog=QApplication.activeModalWidget()
            if dialog is not None and self.isAncestorOf(dialog):dialog.reject()
            return
        if self._worker is not None:
            self._closing=True;return
        if self._closing:return
        self._closing=True
        def finish():
            draft=self.session.draft(self.session.binding)
            prompt=('Ungespeicherte Notizänderungen verwerfen und schließen? Bereits gespeicherte Inhalte bleiben auf dem Server.'
                if self.session.binding.app=='notes' else
                'Ungesendete Eingaben verwerfen und schließen? Ein Serverauftrag kann weiterlaufen.')
            if (draft or self.session.uncertain) and QMessageBox.question(self,self._app_title,prompt,
                    QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:
                self._closing=False
                if not self._pilot_current():self._invalidate_pilot()
                elif not self.session.usable:self.block(self.session.state)
                else:self._queue_theme(reveal=self._live and self._loaded)
                return
            self.timer.stop();self._live=False;self._generation+=1
            self._profile_cookie=None;self.session.remember_draft('');self.session.close()
            if self.page is not None:
                page,profile,view=self.page,self.profile,self.view
                self.page=self.profile=self.view=None;self._loaded=False
                view.deleteLater();page.destroyed.connect(profile.deleteLater);page.deleteLater()
            else:self._finish_close()
        self._capture(finish)

    def _finish_close(self):
        self._cancel_theme()
        if self._theme_watcher is not None and not is_deleted(self._theme_watcher):
            self._theme_watcher.fileChanged.disconnect(self._theme_changed)
            self._theme_watcher.directoryChanged.disconnect(self._theme_changed)
            self._theme_watcher=None
        self._disposed=True;self.close()
