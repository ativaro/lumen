"""Small durable journal; an inverse is available only with a checked postcondition."""
from lumen_i18n import tr
import json
import os
from pathlib import Path
import stat
import time
import uuid

from lumen_store import Store

PREFIX = 'history/'


def record(store, title, kind='activity', before=None, after=None, target=None):
    value = dict(id=uuid.uuid4().hex, title=title, kind=kind, before=before,
                 after=after, target=target, status='applied', created=time.time())
    store.set_setting(PREFIX + value['id'], value)
    return value['id']


def entries(store):
    values = [json.loads(row['value']) for row in store.rows(
        'SELECT value FROM settings WHERE key LIKE ?', (PREFIX + '%',))]
    values += [dict(id=c['id'], title=Path(c['path']).name, target=c['path'],
                    kind='task-file', status=c['status'], created=c['created'])
               for c in store.changes()]
    return sorted(values, key=lambda v: v['created'], reverse=True)[:300]


def fingerprint(path):
    """Bounded metadata tree; never follow symlinks, including parent directories."""
    path = Path(path).absolute()
    if path.parent.resolve() != path.parent:
        raise ValueError(tr('Ein übergeordneter Ordner ist ein symbolischer Link.'))
    pending, result = [path], []
    while pending:
        item = pending.pop()
        info = item.lstat()
        result.append([str(item.relative_to(path)), info.st_dev, info.st_ino,
                       info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                       os.readlink(item) if stat.S_ISLNK(info.st_mode) else None])
        if len(result) > 5000:
            raise ValueError(tr('Für diese große Ordnerstruktur ist Rückgängig nicht verfügbar.'))
        if stat.S_ISDIR(info.st_mode):
            pending.extend(sorted(item.iterdir(), reverse=True))
    return result


def file_change(store, action, source, destination=None, *, undoable=True):
    names = {'copy': tr('Kopiert'), 'move': tr('Verschoben'), 'rename': tr('Umbenannt'),
             'mkdir': tr('Ordner erstellt'), 'trash': tr('In den Papierkorb verschoben')}
    kind, after = 'activity', None
    if undoable and action in ('copy', 'move', 'rename', 'mkdir'):
        try:
            after = fingerprint(destination or source)
            kind = 'file-move' if action in ('move', 'rename') else 'file-create'
        except (ValueError, OSError):
            pass
    return record(store, names.get(action, action) + ': ' + Path(source).name,
                  kind, source if kind == 'file-move' else None, after, destination or source)


def can_undo(value):
    if value['kind'] == 'file-move':
        try:
            # The inverse is atomic; retain cross-device moves as history only.
            if Path(value['before']).parent.stat().st_dev != value['after'][0][1]:
                return False
        except (OSError, TypeError, IndexError, KeyError):
            return False
    return value['status'] in ('applied', 'pending') and value['kind'] in (
        'task-file', 'file-move', 'file-create', 'store-setting', 'preferences', 'panel', 'shortcut')


def undo_record(store, identity):
    value = next((v for v in entries(store) if v['id'] == identity), None)
    if value is None or not can_undo(value):
        raise ValueError(tr('Diese Änderung kann nicht zurückgenommen werden.'))
    if value['kind'] == 'task-file':
        from lumen_actions import undo
        undo(store, identity)
        return
    try: lease = store.acquire('history-' + identity)
    except BlockingIOError: raise ValueError(tr('Rückgängig läuft bereits in einem anderen Fenster.'))
    try:
        value = store.setting(PREFIX + identity)
        if not can_undo(value): raise ValueError(tr('Die Änderung wurde bereits zurückgenommen.'))
        kind, target, before, after = (value[k] for k in ('kind', 'target', 'before', 'after'))
        if kind == 'store-setting':
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT value FROM settings WHERE key=?', (target,)).fetchone()
                if (json.loads(row[0]) if row else None) != after:
                    raise ValueError(tr('Der Eintrag wurde inzwischen geändert.'))
                if before is None: db.execute('DELETE FROM settings WHERE key=?', (target,))
                else: db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (target, json.dumps(before)))
                value['status'] = 'undone'
                db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), PREFIX + identity))
            return
        if kind in ('file-move', 'file-create'):
            if fingerprint(target) != after:
                raise ValueError(tr('Dateien wurden inzwischen geändert. Rückgängig wurde nicht ausgeführt.'))
            if kind == 'file-move':
                from core import move_entry
                if Path(before).parent.resolve() != Path(before).parent:
                    raise ValueError(tr('Der ursprüngliche Ordner hat sich geändert.'))
                move_entry(target, before, atomic=True)
            else:
                from gi.repository import Gio
                Gio.File.new_for_path(target).trash(None)
        elif kind == 'preferences':
            from PySide6.QtCore import QSettings
            settings = QSettings(target, QSettings.IniFormat)
            settings.sync()
            for key, expected in after.items():
                current = settings.value(key)
                # INI values are textual in a fresh process; use the recorded type.
                if expected is not None: current = settings.value(key, type=type(expected))
                if current != expected: raise ValueError(tr('Einstellungen wurden inzwischen geändert.'))
            if 'appearance' in before and settings.fileName() == QSettings('Lumen', 'Assistant').fileName():
                from appearance import normalize_design
                from lumen_desktop_theme import apply
                apply({'design': normalize_design(before['appearance']),
                       'expected': 'org.lumen.' + normalize_design(after['appearance'])})
            for key, previous in before.items():
                if previous is None: settings.remove(key)
                else: settings.setValue(key, previous)
            settings.sync()
            if settings.status() != QSettings.NoError: raise OSError(tr('Einstellungen konnten nicht gespeichert werden.'))
        elif kind == 'panel':
            from desktop_settings import change_panel
            change_panel({'id': target, 'before': after, 'changes': before}, journal=False)
        elif kind == 'shortcut':
            from desktop_settings import set_shortcut
            set_shortcut({'component': target, 'before': after, 'key': before[0] if before else 0}, journal=False)
        value['status'] = 'undone'
        store.set_setting(PREFIX + identity, value)
    finally:
        os.close(lease)
