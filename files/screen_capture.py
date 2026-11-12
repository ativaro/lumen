"""Selected-window capture worker. No desktop fallback, text extraction or disk images."""
import base64
import json
import re
import subprocess
import sys
import time
import uuid

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage
from lumen_i18n import tr


def window_info(bus, identity=None):
    import dbus
    kwin = dbus.Interface(bus.get_object('org.kde.KWin', '/KWin'), 'org.kde.KWin')
    row = kwin.getWindowInfo(identity, timeout=5) if identity else kwin.queryWindowInfo(timeout=90)
    if not row or row.get('minimized') or row.get('excludeFromCapture'):
        raise ValueError(tr('Das Fenster ist geschlossen, minimiert oder vor Aufnahmen geschützt.'))
    identity = str(row.get('uuid', ''))
    uuid.UUID(identity.strip('{}'))
    if int(row.get('type', -1)) not in (0, 5):
        raise ValueError(tr('Bitte ein Anwendungsfenster auswählen.'))
    return dict(uuid=identity, pid=int(row.get('pid', 0)), caption=str(row.get('caption', '')),
                app=str(row.get('resourceClass', '')))


def accessibility_state(target):
    """Role/state only, never editable text. Unknown always requires image review.

    ponytail: bounded tree walk; apps without a complete matching AT-SPI window
    use manual review instead of a second accessibility implementation.
    """
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        Atspi.set_timeout(150, 150)
        desktop = Atspi.get_desktop(0)
        deadline = time.monotonic() + 1.5
        windows = []
        for i in range(min(desktop.get_child_count(), 100)):
            app = desktop.get_child_at_index(i)
            if app.get_process_id() != target['pid']: continue
            for j in range(min(app.get_child_count(), 100)):
                window = app.get_child_at_index(j)
                if window.get_name() == target['caption']: windows.append(window)
        if len(windows) != 1: return 'unknown'
        queue = windows[:]; visited = 0
        while queue:
            if time.monotonic() > deadline or visited >= 400: return 'unknown'
            node = queue.pop(); visited += 1
            states = node.get_state_set()
            if states.contains(Atspi.StateType.DEFUNCT): return 'unknown'
            if not states.contains(Atspi.StateType.SHOWING): continue
            if node.get_role() == Atspi.Role.PASSWORD_TEXT: return 'password'
            count = node.get_child_count()
            if count > 400 - visited: return 'unknown'
            queue.extend(node.get_child_at_index(i) for i in range(count))
        return 'clear' if visited > 1 else 'unknown'
    except Exception:
        return 'unknown'


def capture(bus, target, automatic=False):
    current = window_info(bus, target['uuid'])
    if current['pid'] != target['pid'] or current['app'] != target['app']:
        raise ValueError(tr('Das ausgewählte Fenster hat sich geändert. Bitte neu auswählen.'))
    state = accessibility_state(current)
    if state == 'password': return dict(protection=state)
    if automatic and state != 'clear': return dict(protection='unknown')
    from lumen_launch import executable
    result = subprocess.run([executable('lumen-window-capture'), target['uuid']], capture_output=True, timeout=10)
    if result.returncode:
        code = result.stderr.decode(errors='replace').strip()
        if not re.fullmatch(r'org\.[A-Za-z0-9_.]{1,150}', code): code = str(result.returncode)
        raise ValueError(tr('KDE hat die Aufnahme nicht freigegeben. Bitte Lumen neu installieren und erneut anmelden.') + ' (' + code + ')')
    meta = json.loads(result.stderr)
    width, height, stride = (int(meta[key]) for key in ('width', 'height', 'stride'))
    if meta.get('type') != 'raw' or not (0 < width <= 16384 and 0 < height <= 16384
            and width <= stride <= width * 16 and stride * height <= 128 * 1024**2):
        raise ValueError(tr('Ungültige Fensteraufnahme.'))
    if len(result.stdout) != stride * height:
        raise ValueError(tr('Unvollständige Fensteraufnahme.'))
    image = QImage(result.stdout, width, height, stride, QImage.Format(int(meta['format']))).copy()
    if image.isNull(): raise ValueError(tr('Ungültige Fensteraufnahme.'))
    after = window_info(bus, target['uuid'])
    after_state = accessibility_state(after)
    if after_state == 'password': return dict(protection='password')
    state = 'clear' if state == after_state == 'clear' and current == after else 'unknown'
    if automatic and state != 'clear': return dict(protection='unknown')
    image = image.scaled(1600, 1200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buffer = QBuffer(); buffer.open(QIODevice.WriteOnly); image.save(buffer, 'PNG')
    return dict(protection=state, png=base64.b64encode(bytes(buffer.data())).decode())


def main():
    # A killable worker bounds native accessibility calls and window selection.
    import dbus
    try:
        bus = dbus.SessionBus(private=True)
        try:
            if sys.argv[1] == 'select': result = window_info(bus)
            else:
                target = json.loads(sys.stdin.read(8192))
                result = capture(bus, target, automatic=sys.argv[1] == 'automatic')
        finally:
            bus.close()
        print(json.dumps(result))
    except Exception as error:
        # No raw DBus errors (which may contain private window titles).
        text = str(error) if isinstance(error, (ValueError, TimeoutError)) else tr('Fensterzugriff nicht möglich. KDE Plasma und Bildschirmfreigabe prüfen.')
        if isinstance(error, dbus.DBusException): text += ' (' + error.get_dbus_name() + ')'
        else: text += ' (' + type(error).__name__ + ')'
        print(json.dumps(dict(error=text))); sys.exit(1)


if __name__ == '__main__': main()
