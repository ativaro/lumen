"""Direct Notes entry through the existing private server-app host."""
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, Qt
from PySide6.QtWidgets import QMessageBox
from lumen_i18n import tr
from lumen_activation import present
from server_app_session import AppSession, Binding, SessionError
from server_app_window import ServerAppWindow, _connection
import lumen_connect


def context(job):
    job.check()
    config, stamp = _connection()
    me = lumen_connect.request(config, '/bridge/me', timeout=10)
    job.check()
    if (_connection()[1] != stamp or me.get('device_id') != config.get('device_id')
            or not isinstance(me.get('capabilities'), list) or 'notes' not in me['capabilities']
            or type(me.get('permissions_revision')) is not int or me['permissions_revision'] < 0):
        raise SessionError('identity')
    return config, Binding(config['server'], me.get('id'), me.get('device_id'), 'notes'), stamp


def runtime_root(binding, stamp):
    runtime = Path(QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation))
    def private(path):
        if (not path.is_absolute() or path.resolve() != path or not path.is_dir()
                or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077):
            raise SessionError('profile')
    private(runtime)
    identity = json.dumps([binding.origin, binding.account, binding.device, stamp])
    root = runtime / ('lumen-notes-' + hashlib.sha256(identity.encode()).hexdigest()[:24])
    if root.is_symlink():
        raise SessionError('profile')
    root.mkdir(mode=0o700, exist_ok=True)
    private(root)
    return root


def recover():
    dialog = QMessageBox(QMessageBox.Warning, 'Lumen Notes',
        tr('Lumen Notes benötigt eine gültige Serververbindung und die Freigabe für Notizen. '
           'Server, Konto und Gerätefreigabe prüfen und anschließend erneut öffnen.'),
        QMessageBox.NoButton)
    dialog.setTextFormat(Qt.PlainText)
    connect = dialog.addButton(tr('Serververbindung öffnen'), QMessageBox.ActionRole)
    retry = dialog.addButton(tr('Erneut prüfen'), QMessageBox.AcceptRole)
    close = dialog.addButton(tr('Schließen'), QMessageBox.RejectRole)
    dialog.setDefaultButton(retry)
    dialog.setEscapeButton(close)
    dialog.exec()
    selected = dialog.clickedButton()
    if selected is connect:
        from lumen_connect_gui import ConnectionDialog
        settings = ConnectionDialog()
        settings.exec()
        settings.deleteLater()
        return True
    return selected is retry


def run(app):
    from interop_dialogs import run_job
    from tools_app import forward_window, listen_window
    app.setApplicationName('lumen-wissen')
    app.setDesktopFileName('lumen-wissen')
    app.setApplicationDisplayName('Lumen Notes')
    app.setQuitOnLastWindowClosed(False)
    while True:
        lock = server = window = None
        try:
            verified = run_job(None, tr('Lumen Notes · Serververbindung wird geprüft …'), context)
            if verified is None:
                return 1
            config, binding, stamp = verified
            root = runtime_root(binding, stamp)
            if forward_window(root, {}, private=True):
                return 0
            lock = QLockFile(str(root / 'window.lock'))
            if not lock.tryLock(0):
                if forward_window(root, {}, private=True):
                    return 0
                raise SessionError('busy')
            if _connection()[1] != stamp:
                raise SessionError('connection')
            window = ServerAppWindow(AppSession(config, binding), root, pilot_connection=stamp)
            server = listen_window(window, lambda _: present(window), root=root)
            window.show()
            app.setQuitOnLastWindowClosed(True)
            return app.exec()
        except (OSError, ValueError, RuntimeError):
            if window is not None:
                window.close()
            if not recover():
                return 1
        finally:
            if server is not None:
                server.close()
            if lock is not None:
                lock.unlock()
