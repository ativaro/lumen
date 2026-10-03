"""Persistent file references and bounded listings for libraries, shelf and rooms."""
from lumen_i18n import tr
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

from PyQt5.QtCore import QStandardPaths, QUrl
from lumen_store import Store
from network import is_network_address, normalize_url

PREFIX = 'files/spaces/'
LIBRARY = 'lumen:library/'
SHELF = 'lumen:shelf'
DEFAULTS = [('documents', tr('Dokumente'), QStandardPaths.DocumentsLocation, 'folder-documents'),
            ('pictures', tr('Bilder'), QStandardPaths.PicturesLocation, 'folder-pictures'),
            ('music', tr('Musik'), QStandardPaths.MusicLocation, 'folder-music'),
            ('videos', tr('Videos'), QStandardPaths.MoviesLocation, 'folder-videos')]


def virtual(location):
    return isinstance(location, str) and (location.startswith(LIBRARY) or location == SHELF)


def canonical(location):
    if not isinstance(location, str) or not location.strip() or '\x00' in location:
        raise ValueError(tr('Bitte einen gültigen Ordnerpfad oder eine Netzwerkadresse angeben.'))
    if virtual(location):
        return location
    if is_network_address(location):
        return normalize_url(location).rstrip('/') + ('/' if QUrl(normalize_url(location)).path() == '/' else '')
    if location.startswith('file:'):
        url = QUrl(location)
        if not url.isLocalFile() or url.host():
            raise ValueError(tr('Bitte einen lokalen Pfad oder eine Serveradresse verwenden.'))
        location = url.toLocalFile()
    if not os.path.isabs(os.path.expanduser(location)):
        raise ValueError(tr('Bitte einen absoluten Ordnerpfad angeben.'))
    return os.path.abspath(os.path.expanduser(location))


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError(tr('Bitte einen Namen mit 1 bis 120 Zeichen angeben.'))
    return value.strip()


class Catalog:
    def __init__(self, store=None):
        self.store = store or Store()
        self.shelf_kind = 'shelf'

    def objects(self, kind):
        return [json.loads(row['value']) for row in self.store.rows(
            'SELECT value FROM settings WHERE key LIKE ? ORDER BY key', (PREFIX + kind + '/%',))]

    def put(self, kind, value, previous=None):
        key = PREFIX + kind + '/' + value['id']
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            default = kind == 'library' and value['id'] in {item[0] for item in DEFAULTS}
            if previous is not None and ((row and json.loads(row[0]) != previous) or (not row and not default)):
                raise ValueError(tr('Dieser Eintrag wurde in einem anderen Fenster geändert. Bitte erneut öffnen.'))
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
        return value

    def remove(self, kind, identity, previous=None):
        key = PREFIX + kind + '/' + identity
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            if previous is not None and (not row or json.loads(row[0]) != previous):
                raise ValueError(tr('Dieser Eintrag wurde in einem anderen Fenster geändert. Bitte erneut öffnen.'))
            db.execute('DELETE FROM settings WHERE key=?', (key,))

    def libraries(self):
        values = {item['id']: item for item in self.objects('library')}
        result = []
        for identity, name, location, icon in DEFAULTS:
            default = {'id': identity, 'name': name, 'icon': icon, 'sources': [
                {'label': tr('Dieser PC'), 'location': QStandardPaths.writableLocation(location)}]}
            result.append(values.pop(identity, default))
        return result + list(values.values())

    def library(self, identity):
        if identity.startswith('project-'):
            room = next((r for r in self.rooms() if r['id'] == identity[8:] and r.get('project')), None)
            if room: return dict(id=identity, name=room['name'], sources=room['sources'], project=room['id'])
        return next((item for item in self.libraries() if item['id'] == identity), None)

    def save_library(self, previous, name, sources):
        if len(sources) > 24:
            raise ValueError(tr('Bis zu 24 Quellen je Bibliothek sind möglich.'))
        checked, seen = [], set()
        for source in sources:
            location = canonical(source['location'])
            if virtual(location):
                raise ValueError(tr('Eine Quelle muss ein echter Ordner sein.'))
            if location in seen:
                raise ValueError(tr('Dieser Ordner ist bereits als Quelle eingetragen.'))
            seen.add(location)
            checked.append({'label': title(source['label']), 'location': location})
        return self.put('library', {'id': previous['id'] if previous else uuid.uuid4().hex,
            'name': title(name), 'icon': previous.get('icon', 'folder') if previous else 'folder',
            'sources': checked}, previous)

    def shelf(self):
        return [item['location'] for item in sorted(self.objects(self.shelf_kind), key=lambda item: item['added'])]

    def use_room_shelf(self, identity=None, snapshot=()):
        """Each room has its own references; reopen never overwrites another window."""
        if identity == 'previous': identity = None
        kind = 'room-shelf/' + identity if identity else 'shelf'
        checked = [canonical(item) for item in snapshot]
        if any(virtual(item) for item in checked): raise ValueError(tr('Ungültige Sammelfläche.'))
        if identity:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                marker = PREFIX + kind
                if not db.execute('SELECT 1 FROM settings WHERE key=?', (marker,)).fetchone():
                    for location in checked:
                        key = PREFIX + kind + '/' + hashlib.sha256(location.encode()).hexdigest()
                        db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',
                                   (key, json.dumps({'location': location, 'added': time.time()})))
                    db.execute('INSERT INTO settings VALUES (?,?)', (marker, 'true'))
        self.shelf_kind = kind

    def add_shelf(self, locations):
        checked = [canonical(item) for item in locations]
        if any(virtual(item) for item in checked):
            raise ValueError(tr('Bitte einzelne Dateien oder Ordner sammeln.'))
        with self.store.connect() as db:
            for location in checked:
                identity = hashlib.sha256(location.encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (PREFIX + self.shelf_kind + '/' + identity,
                    json.dumps({'location': location, 'added': time.time()})))

    def remove_shelf(self, locations):
        for location in locations:
            self.remove(self.shelf_kind, hashlib.sha256(canonical(location).encode()).hexdigest())

    def rooms(self):
        return sorted(self.objects('room'), key=lambda item: item['name'].casefold())

    def save_room(self, previous, name, state):
        return self.put('room', {**(previous or {}), 'id': previous['id'] if previous else uuid.uuid4().hex,
            'name': title(name), 'state': state}, previous)

    def replace_shelf(self, locations):
        checked = [canonical(item) for item in locations]
        if any(virtual(item) for item in checked):
            raise ValueError(tr('Ungültige Sammelfläche.'))
        with self.store.connect() as db:
            db.execute('DELETE FROM settings WHERE key LIKE ?', (PREFIX + self.shelf_kind + '/%',))
            for i, location in enumerate(dict.fromkeys(checked)):
                identity = hashlib.sha256(location.encode()).hexdigest()
                db.execute('INSERT INTO settings VALUES (?,?)', (PREFIX + self.shelf_kind + '/' + identity,
                    json.dumps({'location': location, 'added': time.time() + i / 1000})))


def scan_source(root, query, hidden, limit, single=False, names=None):
    """Executed in a killable process: offline FUSE calls cannot block the GUI."""
    terms = query.casefold().split()
    queue, visited, count = [root], 0, 0
    while queue:
        folder = queue.pop(0)
        try:
            explicit = single or names is not None
            entries = [Path(folder)] if single else [Path(folder) / name for name in names] if names is not None else os.scandir(folder)
            try:
                for entry in entries:
                    name, path = entry.name, str(entry) if explicit else entry.path
                    if not hidden and name.startswith('.') and not single:
                        continue
                    visited += 1
                    try:
                        info = entry.stat(follow_symlinks=False)
                        directory = stat.S_ISDIR(info.st_mode)
                        if query and directory and not explicit:
                            queue.append(path)
                        if all(term in name.casefold() for term in terms):
                            yield {'path': path, 'name': name, 'directory': directory,
                                   'size': info.st_size, 'modified': info.st_mtime}
                            count += 1
                    except OSError as error:
                        yield {'error': str(error)}
                    if count >= limit or visited >= 100000:
                        yield {'limited': True}
                        return
            finally:
                if not explicit:
                    entries.close()
        except OSError as error:
            yield {'error': str(error)}


if __name__ == '__main__':
    request = json.loads(sys.stdin.readline())
    for entry in scan_source(**request):
        print(json.dumps(entry), flush=True)
