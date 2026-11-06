"""Shared native entry: server apps own content, this process owns presentation."""
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QUrl
from PySide6.QtWidgets import QMessageBox
from lumen_i18n import tr
from lumen_activation import present
from server_app_session import AppSession, Binding, SessionError, APPS, APP_NAMES, origin
from server_app_window import ServerAppWindow, _connection
import lumen_connect


def context(job, kind='notes'):
    if kind not in APP_NAMES:raise SessionError('identity')
    job.check()
    config, stamp = _connection()
    me = lumen_connect.request(config, '/bridge/me', timeout=10)
    job.check()
    if (_connection()[1] != stamp or me.get('device_id') != config.get('device_id')
            or not isinstance(me.get('capabilities'), list)
            or type(me.get('permissions_revision')) is not int or me['permissions_revision'] < 0):
        raise SessionError('identity')
    binding = Binding(config['server'], me.get('id'), me.get('device_id'), kind)
    if APPS[kind][1] not in me['capabilities']:
        raise SessionError('permission')
    return config, binding, stamp, me['permissions_revision']


def verify_context(kind='notes'):
    from interop_dialogs import run_job
    def check(job):
        try:return context(job, kind)
        # Job.failed preserves only text; retain the category for actionable recovery.
        except SessionError as error:return error
    while True:
        try:
            result = run_job(None, tr(APP_NAMES[kind][0])+' · '+tr('Serververbindung wird geprüft …'), check)
            if isinstance(result, SessionError):raise result
            return result
        except (OSError, ValueError, RuntimeError) as error:
            if not recover(kind, error):return None


def open_device_permissions():
    from PySide6.QtGui import QDesktopServices
    config, stamp = _connection()
    server = origin(config['server'])
    device = str(UUID(config['device_id']))
    if device != config['device_id'] or _connection()[1] != stamp:raise SessionError('connection')
    return QDesktopServices.openUrl(QUrl(server+'/?app=devices&device='+device))


def runtime_root(binding, stamp):
    runtime = Path(QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation))
    def private(path):
        if (not path.is_absolute() or path.resolve() != path or not path.is_dir()
                or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077):
            raise SessionError('profile')
    private(runtime)
    # Preserve old unsaved windows while new launchers need task refs and Code previews.
    receiver = 'code-preview-1' if binding.app=='code' else 'app-links-1'
    identity = json.dumps([binding.origin, binding.account, binding.device, stamp, receiver])
    root = runtime / ('lumen-' + binding.app + '-' + hashlib.sha256(identity.encode()).hexdigest()[:24])
    if root.is_symlink():
        raise SessionError('profile')
    root.mkdir(mode=0o700, exist_ok=True)
    private(root)
    return root


def recover(kind='notes', error=None):
    title=APP_NAMES[kind][0]
    permission = isinstance(error, SessionError) and error.kind == 'permission'
    message = (tr('Für dieses Gerät fehlt die Freigabe für {app}. Öffne auf deinem Lumen Server '
                  'Geräte → dieses Gerät → Serverdaten und aktiviere {app}. '
                  'Danach „Erneut prüfen“ wählen.').format(app=tr(title)) if permission else
               tr('Diese Lumen-App benötigt eine gültige Serververbindung und ihre Gerätefreigabe. '
                  'Server, Konto und Gerätefreigabe prüfen und anschließend erneut öffnen.'))
    dialog = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.NoButton)
    dialog.setTextFormat(Qt.PlainText)
    connect = dialog.addButton(tr('Gerätefreigabe öffnen') if permission else tr('Serververbindung öffnen'), QMessageBox.ActionRole)
    retry = dialog.addButton(tr('Erneut prüfen'), QMessageBox.AcceptRole)
    close = dialog.addButton(tr('Schließen'), QMessageBox.RejectRole)
    dialog.setDefaultButton(retry)
    dialog.setEscapeButton(close)
    while True:
        dialog.exec()
        selected = dialog.clickedButton()
        if selected is not connect:return selected is retry
        if permission:
            try:
                if not open_device_permissions():raise SessionError('connection')
            except (OSError, ValueError, RuntimeError):
                QMessageBox.warning(dialog, title, tr('Die Gerätefreigabe konnte nicht geöffnet werden. '
                    'Öffne deinen Lumen Server im Browser und wähle Geräte → dieses Gerät → Serverdaten.'))
            continue
        from lumen_connect_gui import ConnectionDialog
        settings = ConnectionDialog()
        settings.exec()
        settings.deleteLater()
        return True


def run(app, activation=None, *, kind='notes'):
    if kind not in APP_NAMES:raise SessionError('identity')
    title,desktop=APP_NAMES[kind]
    from tools_app import forward_window, listen_window
    app.setApplicationName(desktop)
    app.setDesktopFileName(desktop)
    app.setApplicationDisplayName(title)
    app.setQuitOnLastWindowClosed(False)
    while True:
        lock = server = window = None
        try:
            verified = verify_context(kind)
            if verified is None:
                return 1
            config, binding, stamp, revision = verified
            root = runtime_root(binding, stamp)
            if forward_window(root, activation or {}, private=True):
                return 0
            lock = QLockFile(str(root / 'window.lock'))
            if not lock.tryLock(0):
                if forward_window(root, activation or {}, private=True):
                    return 0
                raise SessionError('busy')
            if _connection()[1] != stamp:
                raise SessionError('connection')
            window = ServerAppWindow(AppSession(config, binding), root, pilot_connection=stamp)
            from server_notes_handoffs import Requests
            requests=Requests(window)
            def activate(value):
                try:requests.activate(value)
                except (ValueError,OSError) as error:QMessageBox.warning(window,title,str(error))
            server = listen_window(window, activate, root=root, request_keys=('reference','save_task') if kind=='code' else ('reference','mode','handoff') if kind=='audio' else ('reference','handoff'))
            window.show()
            if activation:activate(activation)
            app.setQuitOnLastWindowClosed(True)
            return app.exec()
        except (OSError, ValueError, RuntimeError) as error:
            if window is not None:
                window.close()
            if not recover(kind, error):
                return 1
        finally:
            if server is not None:
                server.close()
            if lock is not None:
                lock.unlock()
