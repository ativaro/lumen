"""Bring the backup window forward after an explicit Vault navigation click."""
import tempfile
from subprocess import SubprocessError
from pathlib import Path
from types import SimpleNamespace


def activate_backup(pid):
    """Use KWin's existing window API, scoped to the locked backup process."""
    if type(pid) is not int or pid <= 0:
        return False
    from PySide6.QtDBus import QDBusConnection
    bus = QDBusConnection.sessionBus()
    interface = bus.interface()
    if interface is None or not interface.isServiceRegistered('org.kde.KWin').value():
        return False
    from lumen_modes import window_script
    script = '''const target = workspace.windowList().find(w =>
        Number(w.pid) === PID && w.normalWindow &&
        String(w.resourceClass).toLowerCase() === "lumen-vault");
        if (!target) return false;
        if (!target.onAllDesktops && target.desktops.length &&
            !target.desktops.includes(workspace.currentDesktop))
            workspace.currentDesktop = target.desktops[0];
        target.minimized = false;
        workspace.activeWindow = target;
        return workspace.activeWindow === target;'''.replace('PID', str(pid))
    try:
        with tempfile.TemporaryDirectory(prefix='lumen-vault-focus-') as root:
            return bool(window_script(SimpleNamespace(directory=Path(root)), script))
    except (OSError, RuntimeError, SubprocessError):
        # Other desktops retain Qt's normal show/raise/activate path.
        return False


def activate_existing_backup(root):
    from PySide6.QtCore import QLockFile
    pid, _, _ = QLockFile(str(Path(root) / 'window.lock')).getLockInfo()
    return activate_backup(pid)
