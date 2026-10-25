"""Thin Desktop adapters: user-selected folders and a separate application profile."""
import hashlib
import json
from pathlib import Path
from uuid import UUID
from PySide6.QtCore import QFile, QIODevice, QObject, QUrl, Slot, QLockFile
from PySide6.QtNetwork import QSslCertificate
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineProfileBuilder, QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout
from interop_dialogs import run_job
from lumen_qt import is_deleted
import lumen_connect
from server_app_session import SessionError
from server_code_transport import Preview, import_folder


class Host(QObject):
    def __init__(self, window, root):
        super().__init__(window)
        self.window, self.root, self.previews = window, Path(root), {}
        window.destroyed.connect(lambda *_: self.close())

    def context(self):
        from server_app_window import _connection
        w = self.window
        config, stamp = _connection()
        frozen = (w.page, w.profile, w.session, w._generation, w.session._generation)
        def check():
            current, current_stamp = _connection()
            if (w._disposed or w._closing or not w._live or not w._loaded or not w.session.usable
                    or frozen != (w.page, w.profile, w.session, w._generation, w.session._generation)
                    or stamp != current_stamp or w._binding.app != 'code'
                    or any(current.get(k) != w.session._config.get(k) for k in ('server', 'device_id', 'token', 'ca_file'))):
                raise SessionError('context')
        check()
        return config, check

    def emit(self, identity, status, error=None):
        try:
            self.context()
            value = json.dumps(dict(entry=identity, status=status, error=error))
            self.window.page.runJavaScript("window.dispatchEvent(new CustomEvent('lumen-code-host',{detail:" + value + '}))')
        except SessionError:
            pass

    @Slot(str)
    def importFolder(self, identity):
        try:
            identity = str(UUID(identity)); config, check = self.context()
            folder = QFileDialog.getExistingDirectory(self.window, 'Projektordner für Lumen Code öffnen')
            if not folder: return
            check()
            def transfer(job):
                def current(): job.check(); check()
                current()
                entry = lumen_connect.request(config, '/bridge/code-library/' + identity + '/runtime/info')
                current()
                return import_folder(config, identity, entry['revision'], folder, current)
            result = run_job(self.window, 'Lumen Code · Ganzen Projektordner importieren …', transfer)
            check()
            if result is not None: self.emit(identity, 'imported')
        except Exception as error:
            self.emit(identity, '', str(error))

    @Slot(str)
    def openPreview(self, identity):
        try:
            identity = str(UUID(identity)); config, check = self.context()
            if identity in self.previews:
                dialog = self.previews[identity]; dialog.show(); dialog.raise_(); dialog.activateWindow(); return
            result = run_job(self.window, 'Lumen Code · App-Vorschau öffnen …',
                lambda job: (job.check(), check(), lumen_connect.request(config,
                    '/bridge/code-library/' + identity + '/runtime/info'))[-1])
            if result is None: return
            check()
            scope = hashlib.sha256(json.dumps([config['server'], self.window._binding.account, config['device_id'], identity]).encode()).hexdigest()
            root = self.root / 'code-previews'; root.mkdir(mode=0o700, exist_ok=True)
            storage = root / scope; storage.mkdir(mode=0o700, exist_ok=True)
            if root.is_symlink() or storage.is_symlink(): raise SessionError('profile')
            lock = QLockFile(str(storage / 'preview.lock'))
            if not lock.tryLock(0): raise ValueError('Diese App-Vorschau ist bereits in einem anderen Fenster geöffnet.')
            port_file = storage / 'port'
            if port_file.is_symlink(): lock.unlock(); raise SessionError('profile')
            try:
                proxy = Preview(config, identity, check, port=int(port_file.read_text()) if port_file.exists() else 0)
                port_file.write_text(str(proxy.server.server_port))
            except BaseException:
                lock.unlock(); raise
            dialog = QDialog(self.window); dialog.setWindowTitle(result['title'] + ' · App-Vorschau'); dialog.resize(1280, 900)
            layout = QVBoxLayout(dialog); bar = QHBoxLayout()
            address = QLineEdit('/'); address.setAccessibleName('Pfad in der App')
            reload = QPushButton('Aktualisieren'); close = QPushButton('Schließen')
            bar.addWidget(address, 1); bar.addWidget(reload); bar.addWidget(close); layout.addLayout(bar)
            builder = QWebEngineProfileBuilder(); builder.setPersistentStoragePath(str(storage))
            builder.setCachePath(str(storage / 'cache'))
            builder.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            if config.get('ca_file'): builder.setAdditionalTrustedCertificates(QSslCertificate.fromData(Path(config['ca_file']).read_bytes()))
            profile = builder.createProfile('code-' + scope, dialog)
            class Requests(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, info):
                    try: check()
                    except Exception: info.block(True); return
                    url = info.requestUrl()
                    if url.toString().startswith(proxy.origin + '/'):
                        info.setHttpHeader(b'X-Lumen-Preview', proxy.secret.encode())
                    elif url.scheme() not in ('https', 'data', 'blob'):
                        info.block(True)
            class Page(QWebEnginePage):
                def acceptNavigationRequest(self, url, kind, main):
                    try: check()
                    except Exception: return False
                    return url.toString().startswith(proxy.origin + '/')
                def createWindow(self, kind): return None
            interceptor = Requests(profile); profile.setUrlRequestInterceptor(interceptor)
            view = QWebEngineView(dialog); page = Page(profile, view); view.setPage(page)
            page.permissionRequested.connect(lambda permission: permission.deny())
            page.fileSystemAccessRequested.connect(lambda request: request.reject())
            page.certificateError.connect(lambda error: error.rejectCertificate())
            for name in ('LocalContentCanAccessRemoteUrls', 'LocalContentCanAccessFileUrls', 'JavascriptCanOpenWindows', 'JavascriptCanAccessClipboard', 'JavascriptCanPaste'):
                page.settings().setAttribute(getattr(QWebEngineSettings.WebAttribute, name), False)
            script = QWebEngineScript(); script.setName('Lumen Code preview websocket')
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld); script.setRunsOnSubFrames(True)
            script.setSourceCode("(()=>{const Native=window.WebSocket;window.WebSocket=class extends Native{constructor(url,protocols){const target=new URL(url,location.href);let p=protocols===undefined?[]:typeof protocols==='string'?[protocols]:Array.from(protocols);if(target.host===location.host)p.push(" + json.dumps('lumen-preview.' + proxy.secret) + ");super(url,p)}}})()")
            page.scripts().insert(script); layout.addWidget(view, 1)
            def navigate():
                path = address.text()
                if path.startswith('/') and not path.startswith('//'): view.setUrl(QUrl(proxy.origin + path))
            address.returnPressed.connect(navigate)
            view.urlChanged.connect(lambda url: address.setText(url.path() + ('?' + url.query() if url.query() else '')))
            reload.clicked.connect(view.reload); close.clicked.connect(dialog.close)
            dialog.finished.connect(lambda *_: self.previews.pop(identity, None))
            dialog.finished.connect(lambda *_: (page.deleteLater(), proxy.close(), lock.unlock(), dialog.deleteLater()))
            dialog._code_preview = (proxy, profile, interceptor, page, view, lock)
            self.previews[identity] = dialog; view.setUrl(QUrl(proxy.origin + '/')); dialog.show()
        except Exception as error:
            self.emit(identity, '', str(error))

    def close(self):
        for dialog in list(self.previews.values()):
            if not is_deleted(dialog): dialog.close()


def install(window, root):
    channel = QWebChannel(window.page); host = Host(window, root); channel.registerObject('codeHost', host)
    window.page.setWebChannel(channel)
    source = QFile(':/qtwebchannel/qwebchannel.js')
    if not source.open(QIODevice.OpenModeFlag.ReadOnly): raise SessionError('code-host')
    javascript = bytes(source.readAll()).decode(); source.close()
    script = QWebEngineScript(); script.setName('Lumen Code native host')
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld); script.setRunsOnSubFrames(False)
    script.setSourceCode(javascript + "\nnew QWebChannel(qt.webChannelTransport,c=>{window.lumenCodeHost={importFolder:id=>c.objects.codeHost.importFolder(id),openPreview:id=>c.objects.codeHost.openPreview(id)};window.dispatchEvent(new Event('lumen-code-host-ready'))});")
    window.page.scripts().insert(script); window._code_host, window._code_channel = host, channel
