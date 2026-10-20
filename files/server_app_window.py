"""Inactive Compose host. No launcher, local editor or renderer-to-OS bridge."""
from pathlib import Path
import os
import tempfile
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtNetwork import QNetworkCookie, QSslCertificate
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QStackedWidget, QMessageBox
from desktop_design import AppHeader, PAGE_MARGIN, PAGE_SPACING
from studio_design import font
from lumen_qt import is_deleted
from server_app_session import AppSession, SessionError

try:
    from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineProfileBuilder,
        QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE = True
except ImportError:
    WEBENGINE = False


# Isolated world, main frame only; it exposes no native objects or credentials.
DRAFT_SCRIPT = '''(() => {
 const capture=()=>{const input=document.querySelector('#translation-text');
   if(input && typeof input.value==='string' && input.value.length<=1048576)
     window.__lumenComposeDraft=input.value;};
 document.addEventListener('input',capture,true);
 document.addEventListener('change',capture,true);
 new MutationObserver(capture).observe(document,{childList:true,subtree:true});
 capture();
})()'''
DRAFT_READ = "window.__lumenComposeDraft ?? ''"


class Call(QThread):
    def __init__(self, function, parent):
        super().__init__(parent); self.function = function; self.ok = False

    def run(self):
        try:self.function(); self.ok = True
        except Exception:pass  # Only fixed native status text crosses the UI boundary.


if WEBENGINE:
    class OriginRequests(QWebEngineUrlRequestInterceptor):
        def __init__(self, window, parent):
            super().__init__(parent); self.window = window

        def interceptRequest(self, info):
            w = self.window
            if not w._live or not w.session.usable or not w.session.binding.resource(info.requestUrl().toString()):
                info.block(True); return
            info.setHttpHeader(b'Authorization', b'')
            if bytes(info.requestMethod()) not in (b'GET', b'HEAD', b'OPTIONS'):
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
    def __init__(self, session, profile_root, parent=None):
        super().__init__(parent)
        if not isinstance(session, AppSession) or session.binding.app != 'compose':raise SessionError('identity')
        self.session = session
        self._live = self._loaded = self._disposed = self._closing = False
        self._generation = 0; self._worker = None; self._temporary = None
        self.profile = self.page = self.view = None
        self.setWindowTitle('Lumen Compose'); self.resize(1000, 720); self.setFont(font(14))
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        self.status_page = QWidget(); layout = QVBoxLayout(self.status_page)
        layout.setContentsMargins(PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN,PAGE_MARGIN);layout.setSpacing(PAGE_SPACING)
        layout.addWidget(AppHeader('Lumen Compose'))
        self.status = QLabel('App-Sitzung wird geprüft.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.retry = QPushButton('Erneut prüfen');self.retry.clicked.connect(lambda:self.verify(reconnect=True));layout.addWidget(self.retry,0,Qt.AlignLeft)
        self.copy = QPushButton('Entwurf kopieren');self.copy.clicked.connect(self.copy_draft);self.copy.setEnabled(False);layout.addWidget(self.copy,0,Qt.AlignLeft)
        layout.addStretch();self.stack.addWidget(self.status_page)
        self.timer = QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.verify)
        if not WEBENGINE:
            self.status.setText('Qt WebEngine fehlt. Diese Serveransicht ist nicht verfügbar.')
            self.retry.setEnabled(False);return
        self._profile(profile_root)
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
        self.profile = builder.createProfile('lumen-app-'+uuid4().hex,self)
        if self.profile is None:raise SessionError('profile')
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
        self.profile.cookieStore().cookieAdded.connect(self._cookie_added)
        script = QWebEngineScript();script.setName('Lumen Compose draft')
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setRunsOnSubFrames(False);script.setSourceCode(DRAFT_SCRIPT);self.page.scripts().insert(script)
        self.stack.addWidget(self.view)

    def verify(self, *, reconnect=False):
        if self._disposed or self._closing or not WEBENGINE or self.page is None or self._worker is not None:return
        if reconnect and self._loaded and not self.session.has_cookie:
            self.block(self.session.state)
            self.status.setText('Sitzung beendet. Entwurf kopieren und die App erneut öffnen.')
            self.retry.setEnabled(False);return
        generation = self._generation
        self.retry.setEnabled(False)
        def check():
            if reconnect and not self.session.has_cookie:self.session.connect()
            else:self.session.check()
        worker = Call(check,self);self._worker = worker
        worker.finished.connect(lambda:self._verified(worker,generation));worker.start()

    def _verified(self, worker, generation):
        self._worker = None;worker.deleteLater()
        if self._disposed:return
        if self._closing:self._closing=False;self.close();return
        if generation!=self._generation:return
        self.retry.setEnabled(True)
        if not worker.ok or not self.session.usable:self.block(self.session.state);return
        self.timer.start()
        if self._live:return
        cookies = QNetworkCookie.parseCookies(self.session.web_cookie())
        if len(cookies)!=1:self.block('cookie');return
        self._live = True
        # Initialize Chromium's blank page before waiting for its cookie signal.
        self.page.runJavaScript('void 0',QWebEngineScript.ScriptWorldId.ApplicationWorld)
        self.profile.cookieStore().loadAllCookies()
        self.profile.cookieStore().setCookie(cookies[0],QUrl(self.session.binding.origin))

    def _cookie_added(self, cookie):
        if self._disposed or not self._live or not self.session.usable or bytes(cookie.name())!=b'lumen_session':return
        if bytes(cookie.value())!=self.session._cookie or not cookie.isHttpOnly() or not cookie.isSecure():
            self.profile.cookieStore().deleteCookie(cookie);self.session.close('identity');self.block('identity');return
        if not self._loaded:self.view.load(QUrl(self.session.url))
        else:
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self.stack.setCurrentWidget(self.view)

    def _loaded_page(self, ok):
        if self._disposed or not self._live or not self.session.usable:return
        if not ok:self.block('load');return
        self._loaded = True;self.stack.setCurrentWidget(self.view)

    def _certificate(self, error):
        error.rejectCertificate();self.block('tls')

    def _capture(self, callback):
        if (self.page is None or not self._loaded
                or self.page.lifecycleState()==QWebEnginePage.LifecycleState.Frozen):callback();return
        generation = self._generation
        def captured(value):
            if self._disposed or generation!=self._generation:return
            if isinstance(value,str):self.session.remember_draft(value)
            self.copy.setEnabled(bool(self.session.draft(self.session.binding)) and self.session.state!='identity')
            callback()
        self.page.runJavaScript(DRAFT_READ,QWebEngineScript.ScriptWorldId.ApplicationWorld,captured)

    def block(self, reason='offline'):
        if self._disposed or self._closing:return
        self._generation += 1;self._live = False;self.timer.stop();self.session.suspend(reason)
        self.stack.setCurrentWidget(self.status_page);self.retry.setEnabled(True)
        self.status.setText('Schreibbestätigung unklar. Kein erneutes Senden; Auftrag zuerst auf dem Server prüfen.'
                            if self.session.uncertain else 'App-Sitzung nicht verfügbar. Eingaben werden nicht erneut gesendet.')
        def freeze():
            if self.page is not None:self.page.setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        self._capture(freeze)

    def copy_draft(self):
        if self.session.state=='identity':return
        QApplication.clipboard().setText(self.session.draft(self.session.binding))

    def closeEvent(self, event):
        if self._disposed:event.accept();return
        event.ignore()
        if self._worker is not None:
            self._closing=True;self._generation+=1;self._live=False;self.timer.stop()
            self.stack.setCurrentWidget(self.status_page);self.session.close();return
        if self._closing:return
        self._closing=True
        def finish():
            draft=self.session.draft(self.session.binding)
            if (draft or self.session.uncertain) and QMessageBox.question(self,'Lumen Compose',
                    'Ungesendete Eingaben verwerfen und schließen? Ein Serverauftrag kann weiterlaufen.',
                    QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:
                self._closing=False;return
            self.timer.stop();self._live=False;self._generation+=1
            self.session.remember_draft('');self.session.close()
            if self.page is not None:
                page,profile,view=self.page,self.profile,self.view
                self.page=self.profile=self.view=None;self._loaded=False
                view.deleteLater();page.destroyed.connect(profile.deleteLater);page.deleteLater()
            else:self._finish_close()
        self._capture(finish)

    def _finish_close(self):
        self._disposed=True;self.close()
