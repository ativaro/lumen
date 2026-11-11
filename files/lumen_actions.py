"""Reviewed native actions; explicit argv, checked paths and conflict-safe undo."""
from lumen_i18n import tr
from contextlib import contextmanager
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from urllib.parse import urlsplit

from content_search import folder_fd
from lumen_store import identifier

ACTIONS = {
    'open': (tr('Datei, Ordner oder Webseite öffnen'), ('path',)),
    'launch': (tr('Anwendung starten'), ('desktop',)),
    'layout': (tr('Fenster nebeneinander anordnen'), ()),
    'write': (tr('Textdatei erstellen oder ersetzen'), ('path', 'text')),
    'copy': (tr('Datei kopieren'), ('source', 'path')),
    'diagnose': (tr('Systemzustand messen'), ()),
    'restart_service': (tr('Dienst neu starten und prüfen'), ('unit', 'scope')),
    'install_packages': (tr('Pakete installieren und prüfen'), ('packages',)),
    'snapshot': (tr('System-Snapshot anlegen'), ()),
}


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError(tr('Ein Auftrag benötigt 1 bis 100 Schritte.'))
    for step in steps:
        if not isinstance(step, dict) or step.get('action') not in ACTIONS:
            raise ValueError(tr('Unbekannte Aktion.'))
        required = ACTIONS[step['action']][1]
        if set(step) != {'action', *required} or any(not isinstance(step[k], str) for k in required):
            raise ValueError(tr('Ungültige Felder für ') + step['action'])
        if any(len(step[k]) > 1000000 for k in required): raise ValueError(tr('Aktionsdaten zu groß.'))
        if step['action'] == 'restart_service':
            unit = step['unit']
            if (step['scope'] not in ('user', 'system') or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@:-]*\.service', unit)
                    or any(x in unit.lower() for x in ('dbus', 'systemd', 'display-manager', 'sddm', 'gdm', 'plasmalogin'))):
                raise ValueError(tr('Dieser Dienst kann hier nicht neu gestartet werden.'))
        if step['action'] == 'install_packages':
            packages = step['packages'].split()
            if not 1 <= len(packages) <= 30 or any(not re.fullmatch(r'[a-z0-9][a-z0-9@._+\-]*', p) for p in packages):
                raise ValueError(tr('Bitte gültige Paketnamen angeben.'))


@contextmanager
def target_fd(path, roots):
    target = Path(os.path.abspath(os.path.expanduser(path)))
    match = next((Path(r) for r in roots if target.is_relative_to(Path(r)) and target != Path(r)), None)
    if match is None or match.resolve() != match:
        raise PermissionError(tr('Der Zielpfad liegt außerhalb der freigegebenen Ordner.'))
    root_fd = os.open(match, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent = None
    try:
        parent = folder_fd(root_fd, target.relative_to(match).parent)
        yield parent, target.name, target
    finally:
        if parent is not None: os.close(parent)
        os.close(root_fd)


@contextmanager
def locked_target(store, path, roots):
    with target_fd(path, roots) as (parent, name, target):
        info = os.fstat(parent)
        key = hashlib.sha256(f'{info.st_dev}:{info.st_ino}:{name}'.encode()).hexdigest()
        fd = os.open(store.directory / ('target-' + key + '.lock'),
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            # Lock the directory entry, since atomic replacement changes the file inode.
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield parent, name, target
        finally: os.close(fd)


def read_at(parent, name):
    try: fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError: return None, 0o600
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024 * 1024:
            raise ValueError(tr('Nur reguläre Dateien bis 16 MiB werden geändert.'))
        return stream.read(), stat.S_IMODE(info.st_mode)


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else 'absent'


def atomic_write(parent, name, data, mode):
    temporary = '.lumen-' + identifier()
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try: os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError: pass


def command(argv, timeout=30):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode: raise RuntimeError((proc.stderr or proc.stdout or tr('{0} fehlgeschlagen', argv[0]))[-4000:])
    return proc.stdout.strip()[:20000]


def desktop_file(name):
    if not re.fullmatch(r'[A-Za-z0-9_.\-]+\.desktop', name): raise ValueError(tr('Ungültige Anwendung.'))
    bases = [Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))]
    bases += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')]
    for base in bases:
        path = base / 'applications' / name
        if path.is_file(): return path
    raise ValueError(tr('Anwendung ist nicht installiert: ') + name)


def execute(store, task_id, step):
    validate_steps([step]); task = store.task(task_id)
    if (not task['approved'] or task['status'] != 'running' or task['cursor'] >= len(task['steps'])
            or step != task['steps'][task['cursor']]):
        raise PermissionError(tr('Nur der freigegebene aktuelle Schritt eines laufenden Auftrags darf ausgeführt werden.'))
    action = step['action']; result = ''
    store.event(task_id, 'started', json.dumps(step, ensure_ascii=False) if action != 'write' else tr('Datei schreiben: ') + step['path'])
    if action in ('write', 'copy'):
        if action == 'copy':
            with target_fd(step['source'], task['roots']) as (parent, name, _): data, _mode = read_at(parent, name)
            if data is None: raise ValueError(tr('Quelldatei nicht gefunden.'))
        else: data = step['text'].encode('utf-8')
        with locked_target(store, step['path'], task['roots']) as (parent, name, target):
            before, mode = read_at(parent, name)
            change = identifier()
            # Save recovery data before touching the file; pending records survive a crash.
            with store.connect() as db:
                db.execute('INSERT INTO changes VALUES (?,?,?,?,?,?,?,?)',
                           (change, task_id, str(target), before, digest(data), mode, 'pending', time.time(),))
            if read_at(parent, name) != (before, mode): raise ValueError(tr('Datei wurde inzwischen geändert.'))
            atomic_write(parent, name, data, mode)
            if digest(read_at(parent, name)[0]) != digest(data): raise ValueError(tr('Geschriebene Datei konnte nicht geprüft werden.'))
            with store.connect() as db: db.execute("UPDATE changes SET status='applied' WHERE id=?", (change,))
            result = str(target)
    elif action == 'open':
        value = step['path']; url = urlsplit(value)
        if url.scheme in ('http', 'https'):
            if not url.hostname or url.username or url.password: raise ValueError(tr('Ungültige Webadresse.'))
        else:
            path = Path(value).expanduser().absolute()
            if not path.exists() or path.resolve() != path or not any(path.is_relative_to(Path(r)) for r in task['roots']):
                raise PermissionError(tr('Der Pfad ist nicht freigegeben.'))
            value = str(path)
        result = command(['xdg-open', value]) or tr('Öffnen angefordert: ') + value
    elif action == 'launch':
        result = command(['gio', 'launch', str(desktop_file(step['desktop']))]) or tr('Anwendung gestartet: ') + step['desktop']
    elif action == 'layout':
        script = store.directory / ('layout-' + identifier() + '.js')
        script.write_text('''const windows = workspace.windowList().filter(w => w.normalWindow && !w.minimized && w.onAllDesktops === false);
const groups = new Map();
for (const w of windows) { const key = w.output; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(w); }
for (const [output, list] of groups) { const area = workspace.clientArea(KWin.MaximizeArea, list[0]);
  const width = Math.floor(area.width / list.length);
  list.forEach((w,i) => { w.setMaximize(false, false); w.frameGeometry = {x: area.x + i*width, y: area.y, width: i === list.length-1 ? area.width-i*width : width, height: area.height}; }); }
''')
        number = None
        try:
            number = command(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.loadScript', str(script), script.stem])
            if not re.fullmatch(r'\d+', number): raise RuntimeError(tr('KWin hat das Layout nicht geladen.'))
            command(['qdbus6', 'org.kde.KWin', '/Scripting/Script' + number, 'org.kde.kwin.Script.run'])
            result = tr('Fensteranordnung bei KWin angefordert.')
        finally:
            if number is not None:
                try: command(['qdbus6', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.unloadScript', script.stem])
                except (RuntimeError, OSError): pass
            script.unlink(missing_ok=True)
    elif action == 'diagnose':
        results = []
        for argv in (['free', '-h'], ['df', '-h'], ['systemctl', '--user', '--failed', '--no-pager'], ['systemctl', '--failed', '--no-pager']):
            results.append(' '.join(argv) + '\n' + command(argv))
        result = '\n\n'.join(results)
    elif action == 'restart_service':
        base = ['systemctl'] + (['--user'] if step['scope'] == 'user' else [])
        command(([] if step['scope'] == 'user' else ['pkexec']) + base + ['restart', step['unit']])
        result = command(base + ['is-active', step['unit']])
        if result != 'active': raise RuntimeError(tr('Dienst ist nach dem Neustart nicht aktiv.'))
    elif action == 'install_packages':
        packages = step['packages'].split()
        command(['pkexec', 'pacman', '-S', '--needed', '--noconfirm', '--', *packages], 900)
        result = command(['pacman', '-Q', '--', *packages])
    elif action == 'snapshot':
        result = command(['pkexec', 'snapper', '-c', 'root', 'create', '--print-number', '--description', 'Lumen: ' + task['title']])
        if not result.isdigit(): raise RuntimeError(tr('Kein bestätigter Snapshot erhalten.'))
        result = tr('System-Snapshot ') + result + tr(' (Root-Konfiguration; persönliche Ordner sind nicht automatisch enthalten).')
    store.event(task_id, 'requested' if action in ('open', 'launch', 'layout') else 'verified', result)
    return result


def undo(store, change_id):
    rows = store.rows('SELECT * FROM changes WHERE id=?', (change_id,))
    if not rows: raise ValueError(tr('Änderung nicht gefunden.'))
    change = rows[0]
    task = store.task(change['task'])
    with locked_target(store, change['path'], task['roots']) as (parent, name, _):
        change = store.rows('SELECT * FROM changes WHERE id=?', (change_id,))[0]
        if change['status'] not in ('applied', 'pending'): raise ValueError(tr('Änderung wurde bereits zurückgenommen.'))
        current, _mode = read_at(parent, name)
        if digest(current) != change['after_hash'] or _mode != change['mode']:
            raise ValueError(tr('Die Datei wurde inzwischen geändert; Rückgängig würde fremde Änderungen überschreiben.'))
        if change['before'] is None: os.unlink(name, dir_fd=parent)
        else: atomic_write(parent, name, change['before'], change['mode'])
        with store.connect() as db: db.execute("UPDATE changes SET status='undone' WHERE id=?", (change_id,))
    store.event(change['task'], 'undone', change['path'])
