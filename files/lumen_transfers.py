"""Shared Lumen transfer tickets and bounded, independently supervised workers."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit
import uuid

from lumen_store import Store

PREFIX = 'workplace/transfer/'
ACTIVE = ('queued', 'running', 'cancelling')
LABELS = {'queued': 'Wartet', 'running': 'Läuft', 'cancelling': 'Wird angehalten',
          'paused': 'Angehalten', 'failed': 'Fehlgeschlagen', 'completed': 'Fertig'}


def tickets(store):
    values = [json.loads(row['value']) for row in store.rows(
        'SELECT value FROM settings WHERE key LIKE ?', (PREFIX + '%',))]
    for value in values:
        if value['status'] in ACTIVE and time.time() - value['updated'] > 5:
            try: lease = store.acquire('transfer-' + value['id'])
            except BlockingIOError: continue
            try:
                value.update(update(store, value['id'], status='paused', errors=['Transferprozess wurde unterbrochen. Ziel vor erneutem Versuch prüfen.']))
            finally: os.close(lease)
    return sorted(values, key=lambda v: v['created'], reverse=True)


def update(store, identity, **fields):
    # Merge individual fields under a write lock: cancellation cannot be lost to progress.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE key=?', (PREFIX + identity,)).fetchone()
        if not row: raise ValueError('Transfer nicht gefunden.')
        value = json.loads(row[0]); value.update(fields, updated=time.time())
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), PREFIX + identity))
    return value


def web_url(url):
    value = urlsplit(url)
    if value.scheme not in ('http', 'https') or not value.hostname or value.username or value.password or any(ord(c) < 32 for c in url):
        raise ValueError('Bitte eine HTTP(S)-Adresse ohne Zugangsdaten eingeben.')
    return url


def create(store, action, sources, target=None, portable=False, expected=None):
    if action not in ('copy', 'move', 'rename', 'mkdir', 'trash', 'download') or not sources:
        raise ValueError('Ungültiger Dateivorgang.')
    if action == 'download':
        if len(sources) != 1: raise ValueError('Ein Download benötigt genau eine Adresse.')
        web_url(sources[0])
    elif any(not os.path.isabs(p) or '\x00' in p for p in sources):
        raise ValueError('Absolute Dateipfade sind erforderlich.')
    if action in ('copy', 'move', 'rename', 'download') and (not target or not os.path.isabs(target) or '\x00' in target):
        raise ValueError('Ein absoluter Zielpfad ist erforderlich.')
    value = dict(id=uuid.uuid4().hex, action=action, sources=sources, target=target,
                 portable=portable, status='queued', created=time.time(), updated=time.time(),
                 done=[], errors=[], current='', bytes=0, total=0, cancel=False, expected=expected)
    store.set_setting(PREFIX + value['id'], value)
    return value


def start(store, value):
    env = dict(os.environ, LUMEN_DATA=str(store.directory))
    return subprocess.Popen([sys.executable, str(Path(__file__)), '--supervise', value['id']],
                            env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pause(store, identity):
    return update(store, identity, cancel=True)


def retry(store, identity):
    value = store.setting(PREFIX + identity)
    if not value or value['status'] in ACTIVE or value['status'] == 'completed':
        raise ValueError('Dieser Transfer kann gerade nicht fortgesetzt werden.')
    # Only the supervisor holding this lease may transition the job to running.
    value = update(store, identity, status='queued', cancel=False, errors=[])
    start(store, value)


def download(store, value):
    target = Path(value['target'])
    if os.path.lexists(target): raise FileExistsError('Das Ziel existiert bereits. Nichts überschrieben.')
    if target.parent.resolve() != target.parent:
        raise ValueError('Das Downloadziel darf nicht durch einen symbolischen Ordner verweisen.')
    part = target.with_name('.lumen-download-' + value['id'] + '.part')
    validator = value.get('validator', '')
    offset = 0
    if part.exists():
        from lumen_history import fingerprint
        if value.get('partial') != fingerprint(part):
            raise ValueError('Die unvollständige Datei wurde verändert. Bitte einen neuen Download starten.')
        offset = part.stat().st_size if validator else 0
    headers = {'Accept-Encoding': 'identity', 'User-Agent': 'Lumen/1.2'}
    if offset: headers.update(Range=f'bytes={offset}-', **{'If-Range': validator})
    request = urllib.request.Request(web_url(value['sources'][0]), headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        web_url(response.url)
        etag = response.headers.get('ETag', '')
        new_validator = etag if etag and not etag.startswith('W/') else response.headers.get('Last-Modified', '')
        if offset and response.status == 206:
            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
            if not match or int(match[1]) != offset or new_validator != validator:
                raise ValueError('Der Server bestätigt die Fortsetzung nicht. Download wurde angehalten.')
            total = int(match[3])
        elif response.status == 200:
            offset = 0
            total = int(response.headers.get('Content-Length', '0'))
        else: raise ValueError('Unerwartete Antwort des Downloadservers.')
        flags = os.O_WRONLY | os.O_NOFOLLOW | (os.O_APPEND if offset else os.O_TRUNC)
        flags |= 0 if part.exists() else os.O_CREAT | os.O_EXCL
        fd = os.open(part, flags, 0o600)
        update(store, value['id'], validator=new_validator, bytes=offset, total=total)
        last = 0
        with os.fdopen(fd, 'ab' if offset else 'wb') as stream:
            while chunk := response.read(1024 * 256):
                stream.write(chunk); offset += len(chunk)
                if time.monotonic() - last > .3:
                    stream.flush()
                    update(store, value['id'], bytes=offset)
                    last = time.monotonic()
            stream.flush(); os.fsync(stream.fileno())
        if total and offset != total: raise ValueError('Download unvollständig; Fortsetzen ist möglich.')
    from core import move_entry
    move_entry(part, target, atomic=True)
    update(store, value['id'], bytes=offset, done=value['sources'])
    from lumen_history import file_change
    file_change(store, 'copy', str(target), str(target))


def execute(store, identity):
    value = store.setting(PREFIX + identity)
    if value['action'] == 'download':
        download(store, value)
        return
    from core import copy_entry, move_entry
    from gi.repository import Gio
    from lumen_history import file_change
    done, errors = list(value['done']), []
    count, last = value.get('bytes', 0), 0
    def progress(amount, total=None, *_):
        nonlocal count, last
        count = amount if total is not None else count + amount
        if time.monotonic() - last > .3:
            update(store, identity, bytes=count, total=total or 0)
            last = time.monotonic()
    for source in value['sources']:
        if source in done: continue
        path, destination = Path(source), None
        update(store, identity, current=path.name)
        try:
            action = value['action']
            if value.get('expected') is not None:
                from image_edit import file_stamp
                if path.resolve() != path or file_stamp(path.lstat()) != value['expected'].get(source):
                    raise ValueError('Datei seit der Vorschau verändert. Bitte erneut prüfen.')
            if action == 'copy': destination = copy_entry(path, value['target'], value['portable'], progress)
            elif action in ('move', 'rename'):
                destination = Path(value['target']) / path.name if action == 'move' else Path(value['target'])
                move_entry(path, destination, progress=progress)
            elif action == 'mkdir': path.mkdir()
            elif action == 'trash': Gio.File.new_for_path(source).trash(None)
            done.append(source)
            update(store, identity, done=done)
            file_change(store, action, source, str(destination) if destination else None)
        except Exception as error:
            errors.append(path.name + ': ' + str(error))
            update(store, identity, errors=errors)


def supervise(store, identity):
    try: lease = store.acquire('transfer-' + identity)
    except BlockingIOError: return
    child = None
    try:
        value = store.setting(PREFIX + identity)
        if not value or value['status'] not in ACTIVE: return
        if value['cancel']:
            update(store, identity, status='paused', errors=['Angehalten.'])
            return
        update(store, identity, status='running')
        child = subprocess.Popen([sys.executable, str(Path(__file__)), '--execute', identity],
                                 env=dict(os.environ, LUMEN_DATA=str(store.directory)),
                                 pass_fds=(lease,),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        interrupted = ''
        while child.poll() is None:
            value = store.setting(PREFIX + identity)
            if value['cancel'] or time.time() - value['updated'] > 120:
                interrupted = 'Angehalten.' if value['cancel'] else 'Keine Antwort seit zwei Minuten. Verbindung prüfen und erneut versuchen.'
                child.kill(); child.wait(timeout=3)
                break
            time.sleep(.25)
        value = store.setting(PREFIX + identity)
        fields = {}
        if value['action'] == 'download':
            part = Path(value['target']).with_name('.lumen-download-' + identity + '.part')
            # A separate bounded process captures metadata even on a stalled NAS.
            try:
                result = subprocess.run([sys.executable, str(Path(__file__)), '--partial', str(part)],
                                        capture_output=True, timeout=3, text=True)
                fields['partial'] = json.loads(result.stdout) if result.returncode == 0 else None
            except (subprocess.TimeoutExpired, ValueError): fields['partial'] = None
        errors = value['errors']
        if interrupted: errors = [interrupted]
        elif child.returncode and not errors: errors = ['Übertragung wurde unterbrochen. Vor erneutem Versuch das Ziel prüfen.']
        update(store, identity, status='paused' if interrupted else 'failed' if errors else 'completed', errors=errors, **fields)
    finally:
        if child and child.poll() is None: child.kill(); child.wait(timeout=3)
        os.close(lease)


if __name__ == '__main__':
    store = Store()
    mode, identity = sys.argv[1:]
    if mode == '--supervise': supervise(store, identity)
    elif mode == '--partial':
        from lumen_history import fingerprint
        print(json.dumps(fingerprint(identity)))
    elif mode == '--execute':
        try: execute(store, identity)
        except Exception as error:
            update(store, identity, errors=[str(error)]); sys.exit(1)
