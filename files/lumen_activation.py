"""Explicit relaunch activation shared by native Lumen windows."""
import json
import os
from pathlib import Path
import re
from subprocess import SubprocessError
import tempfile
from types import SimpleNamespace
import uuid

from PySide6.QtCore import QObject, Qt, QTimer, ClassInfo, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBus

from lumen_controls import run
from lumen_i18n import tr


def window_script(store, body):
    """KWin replies over a private D-Bus object; no log scraping or shell."""
    from PySide6.QtCore import QObject, QCoreApplication, QEventLoop, QTimer, ClassInfo, Slot
    from PySide6.QtDBus import QDBusConnection
    app = QCoreApplication.instance() or QCoreApplication([])
    loop = QEventLoop()
    @ClassInfo(**{'D-Bus Interface': 'org.lumen.WindowReply'})
    class Reply(QObject):
        result = None
        @Slot(str)
        def receive(self, value):
            self.result = json.loads(value); loop.quit()
    receiver = Reply()
    bus = QDBusConnection.sessionBus()
    service = 'org.lumen.Layout.p' + uuid.uuid4().hex
    if not bus.registerService(service) or not bus.registerObject('/Reply', receiver, QDBusConnection.ExportAllSlots):
        raise RuntimeError(tr('KWin-Verbindung ist nicht verfügbar.'))
    script = store.directory / ('windows-' + uuid.uuid4().hex + '.js')
    script.write_text('try { const value = (() => {' + body + '})(); callDBus(' + json.dumps(service) +
                      ', "/Reply", "org.lumen.WindowReply", "receive", JSON.stringify({value})); } catch(e) { callDBus(' +
                      json.dumps(service) + ', "/Reply", "org.lumen.WindowReply", "receive", JSON.stringify({error:String(e)})); }')
    try:
        number = run(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.loadScript', str(script), script.stem])
        if not number.isdigit(): raise RuntimeError(tr('KWin hat die Fensteraktion nicht geladen.'))
        run(['qdbus6', 'org.kde.KWin', '/Scripting/Script' + number, 'org.kde.kwin.Script.run'])
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit); timer.start(2500)
        if receiver.result is None: loop.exec()
        timer.stop()
        if receiver.result is None: raise RuntimeError(tr('KWin hat nicht rechtzeitig geantwortet.'))
        if 'error' in receiver.result: raise RuntimeError(receiver.result['error'])
        return receiver.result['value']
    finally:
        try: run(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.unloadScript', script.stem])
        finally:
            script.unlink(missing_ok=True); bus.unregisterObject('/Reply'); bus.unregisterService(service)


def activate_process(pid, app_id, title=None):
    """KWin fallback, restricted to the owning process and Lumen application."""
    if type(pid) is not int or pid <= 0 or not isinstance(app_id, str) or not re.fullmatch(r'lumen(?:-[a-z0-9]+)*', app_id):
        return False
    interface = QDBusConnection.sessionBus().interface()
    if interface is None or not interface.isServiceRegistered('org.kde.KWin').value():
        return False
    script = '''const windows = workspace.windowList().filter(w =>
        Number(w.pid) === PID && (String(w.resourceClass).toLowerCase() === APP ||
                                 String(w.desktopFileName).toLowerCase() === APP));
        let target = windows.find(w => w.caption === TITLE) || windows.find(w => w.normalWindow);
        if (!target) return false;
        let modal;
        while ((modal = windows.find(w => w.modal && w.transientFor === target))) target = modal;
        if (!target.onAllDesktops && target.desktops.length &&
            !target.desktops.includes(workspace.currentDesktop))
            workspace.currentDesktop = target.desktops[0];
        target.minimized = false;
        workspace.activeWindow = target;
        return workspace.activeWindow === target;'''
    script = script.replace('PID', str(pid)).replace('APP', json.dumps(app_id)).replace('TITLE', json.dumps(title))
    try:
        with tempfile.TemporaryDirectory(prefix='lumen-focus-') as root:
            return bool(window_script(SimpleNamespace(directory=Path(root)), script))
    except (OSError, RuntimeError, SubprocessError):
        return False  # Other desktops retain Qt's normal activation path.


def present(window):
    """Restore the existing window, preserving maximization and modal dialogs."""
    from PySide6.QtWidgets import QApplication, QWidget
    widget = isinstance(window, QWidget)
    if widget:
        window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
    elif window.windowState() == Qt.WindowMinimized:
        window.showNormal()
    window.show()
    target = (QApplication.activeModalWidget() if widget else QGuiApplication.modalWindow()) or window
    target.raise_()
    if widget:
        target.activateWindow()
        handle = target.windowHandle()
        if handle: handle.requestActivate()
    else:
        target.requestActivate()
    app = QGuiApplication.instance()
    title = target.windowTitle() if widget else target.title()
    app_id = app.desktopFileName() or app.applicationName().lower()
    # Map/show requests must reach the compositor before its fallback runs.
    QTimer.singleShot(0, lambda: activate_process(os.getpid(), app_id, title))


@ClassInfo(**{'D-Bus Interface': 'org.lumen.Application'})
class SingleWindow(QObject):
    """Reserve an app before constructing it; queue relaunches during startup."""
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.handler = None
        self.pending = []
        self.bus = QDBusConnection.sessionBus()
        self.running = self.bus.isConnected() and not self.bus.registerService(service)
        if self.bus.isConnected() and not self.running:
            if not self.bus.registerObject('/Application', self, QDBusConnection.ExportAllSlots):
                raise RuntimeError('Lumen: Fensteraktivierung konnte nicht registriert werden.')

    def forward(self, request=None):
        message = QDBusMessage.createMethodCall(self.service, '/Application', 'org.lumen.Application', 'Open')
        message.setArguments([json.dumps(request or {})])
        reply = self.bus.call(message, QDBus.Block, 5000)
        return 0 if reply.type() != QDBusMessage.ErrorMessage and reply.arguments() == [True] else 1

    @Slot(str, result=bool)
    def Open(self, value):
        if len(value) > 65536: return False
        try:
            request = json.loads(value)
            if not isinstance(request, dict): return False
            if self.handler is None:
                if len(self.pending) >= 32: return False
                self.pending.append(request)
            else:
                self.handler(request)
            return True
        except (ValueError, TypeError):
            return False

    def bind(self, handler):
        self.handler = handler
        pending, self.pending = self.pending, []
        for request in pending:
            QTimer.singleShot(0, lambda request=request: self.Open(json.dumps(request)))


if __name__ == '__main__':
    import argparse
    from PySide6.QtCore import QCoreApplication
    parser = argparse.ArgumentParser(description='Lumen window activation')
    parser.add_argument('pid', type=int)
    parser.add_argument('app_id')
    args = parser.parse_args()
    app = QCoreApplication([])
    raise SystemExit(0 if activate_process(args.pid, args.app_id) else 1)
