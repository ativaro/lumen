"""Shared Lumen transfer tickets and bounded, independently supervised workers."""
from lumen_i18n import worker_environment, tr
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import threading
import urllib.request
from urllib.parse import urlsplit
import uuid

from lumen_store import Store

PREFIX = 'workplace/transfer/'
ACTIVE = ('queued', 'running', 'cancelling')
LABELS = {'queued': tr('Wartet'), 'running': tr('Läuft'), 'cancelling': tr('Wird angehalten'),
          'paused': tr('Angehalten'), 'failed': tr('Fehlgeschlagen'), 'completed': tr('Fertig'), 'cancelled': tr('Abgebrochen')}


def tickets(store):
    values = [json.loads(row['value']) for row in store.rows(
        'SELECT value FROM settings WHERE key LIKE ?', (PREFIX + '%',))]
    for value in values:
        if value['status'] in ACTIVE and time.time() - value['updated'] > 5:
            try: lease = store.acquire('transfer-' + value['id'])
            except BlockingIOError: continue
            try:
                value.update(update(store, value['id'], status='paused', errors=[tr('Transferprozess wurde unterbrochen. Ziel vor erneutem Versuch prüfen.')]))
            finally: os.close(lease)
    return sorted(values, key=lambda v: v['created'], reverse=True)


def update(store, identity, **fields):
    # Merge individual fields under a write lock: cancellation cannot be lost to progress.
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM settings WHERE key=?', (PREFIX + identity,)).fetchone()
        if not row: raise ValueError(tr('Transfer nicht gefunden.'))
        value = json.loads(row[0]); value.update(fields, updated=time.time())
        follow = value.get('followup', {})
        retired = (follow.get('enabled') or follow.get('pending_notice') or follow.get('state') == 'review') and (value['status'] not in ('paused', 'failed') or value.get('discard'))
        if retired:
            value['followup'] = dict(follow, enabled=False, state='off', revision=follow['revision'] + 1,
                                     archive_pending=bool(follow.get('notification_id')), pending_notice=False)
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(value), PREFIX + identity))
    if retired:
        from transfer_followup import clear_notice
        clear_notice(value)
    return value


def web_url(url):
    value = urlsplit(url)
    if value.scheme not in ('http', 'https') or not value.hostname or value.username or value.password or any(ord(c) < 32 for c in url):
        raise ValueError(tr('Bitte eine HTTP(S)-Adresse ohne Zugangsdaten eingeben.'))
    return url


def create(store, action, sources, target=None, portable=False, expected=None, drive=None):
    if action not in ('copy', 'move', 'rename', 'mkdir', 'trash', 'download', 'drive-upload', 'drive-download', 'drive-copy') or not sources:
        raise ValueError(tr('Ungültiger Dateivorgang.'))
    if action == 'download':
        if len(sources) != 1: raise ValueError(tr('Ein Download benötigt genau eine Adresse.'))
        web_url(sources[0])
    elif action in ('drive-download', 'drive-copy'):
        if any(not p.startswith('lumen-drive://') for p in sources): raise ValueError(tr('Ungültige Drive-Adresse.'))
    elif any(not os.path.isabs(p) or '\x00' in p for p in sources):
        raise ValueError(tr('Absolute Dateipfade sind erforderlich.'))
    if action in ('copy', 'move', 'rename', 'download', 'drive-download') and (not target or not os.path.isabs(target) or '\x00' in target):
        raise ValueError(tr('Ein absoluter Zielpfad ist erforderlich.'))
    value = dict(id=uuid.uuid4().hex, action=action, sources=sources, target=target,
                 portable=portable, status='queued', created=time.time(), updated=time.time(),
                 done=[], errors=[], current='', bytes=0, total=0, cancel=False, expected=expected, drive=drive)
    if action.startswith('drive-') and not drive: raise ValueError(tr('Drive-Verbindung fehlt.'))
    store.set_setting(PREFIX + value['id'], value)
    return value


def start(store, value):
    env = worker_environment(LUMEN_DATA=str(store.directory))
    process = subprocess.Popen([sys.executable, str(Path(__file__)), '--supervise', value['id']],
                            env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=process.wait, daemon=True).start()
    return process


def pause(store, identity):
    value = store.setting(PREFIX + identity)
    if value and value['status'] in ACTIVE: return update(store, identity, cancel=True)


def cancel(store, identity):
    value = store.setting(PREFIX + identity)
    if not value or value['status'] in ('completed', 'cancelled'): return
    active = value['status'] in ACTIVE
    value = update(store, identity, cancel=True, discard=True, status=value['status'] if active else 'queued')
    if not active: start(store, value)


def cleanup(store, value):
    import shutil
    import drive_local as local
    if value.get('moving'):
        from transfer_copy import restore_source
        items = {item['source']: item for item in value['copy_plan']['items']}
        for source, quarantine in value['moving'].items():
            restore_source(items[source], quarantine)
    if value.get('upload_plan'):
        import drive_sync as sync
        import drive_transport as transport
        import lumen_connect
        config = lumen_connect.read_config()
        if sync.scope(config) != value['drive']['scope']: raise ValueError(tr('Zum Aufräumen die ursprüngliche Serververbindung wiederherstellen.'))
        from urllib.error import HTTPError
        from drive_transfers import require_current
        require_current(value)
        for item in value['upload_plan']['files']:
            if item['request'] in value.get('upload_done', []): continue
            try:
                transport.request(config, '/uploads/' + item['request'], method='DELETE')
            except HTTPError as error:
                if error.code != 404: raise
    for plan_name in ('copy_plan', 'download_plan'):
        plan = value.get(plan_name)
        if not plan: continue
        root, stage = plan['root'], plan['stage']
        if value['action'] == 'drive-copy' and not Path(root['path']).exists(): continue
        with local.directory(root): pass
        try:
            with local.directory(root, Path(stage).parent) as parent:
                try:
                    info = os.stat(Path(stage).name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError: continue
                expected = plan.get('stage_root', {}).get('identity') or value.get('stage_identity')
                if expected and [info.st_dev, info.st_ino] != expected: raise ValueError(tr('Zwischenablage der Kopie wurde ersetzt.'))
                shutil.rmtree(Path(stage).name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            continue
    if value['action'] == 'download':
        part = Path(value['target']).with_name('.lumen-download-' + value['id'] + '.part')
        if part.parent.resolve() != part.parent: raise ValueError(tr('Zielordner wurde ersetzt.'))
        part.unlink(missing_ok=True)
    if value['action'] == 'drive-copy' and value.get('download_plan'):
        temporary = store.directory / ('drive-copy-' + value['id'])
        if temporary.exists():
            with local.directory(value['download_plan']['root']):
                shutil.rmtree(temporary)


def retry(store, identity):
    value = store.setting(PREFIX + identity)
    if not value or value['status'] in ACTIVE or value['status'] in ('completed', 'cancelled'):
        raise ValueError(tr('Dieser Transfer kann gerade nicht fortgesetzt werden.'))
    # Only the supervisor holding this lease may transition the job to running.
    value = update(store, identity, status='queued', cancel=bool(value.get('discard')), errors=[])
    start(store, value)


def download(store, value):
    target = Path(value['target'])
    if os.path.lexists(target): raise FileExistsError(tr('Das Ziel existiert bereits. Nichts überschrieben.'))
    if target.parent.resolve() != target.parent:
        raise ValueError(tr('Das Downloadziel darf nicht durch einen symbolischen Ordner verweisen.'))
    part = target.with_name('.lumen-download-' + value['id'] + '.part')
    validator = value.get('validator', '')
    offset = 0
    if part.exists():
        from lumen_history import fingerprint
        if value.get('partial') != fingerprint(part):
            raise ValueError(tr('Die unvollständige Datei wurde verändert. Bitte einen neuen Download starten.'))
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
                raise ValueError(tr('Der Server bestätigt die Fortsetzung nicht. Download wurde angehalten.'))
            total = int(match[3])
        elif response.status == 200:
            offset = 0
            total = int(response.headers.get('Content-Length', '0'))
        else: raise ValueError(tr('Unerwartete Antwort des Downloadservers.'))
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
        if total and offset != total: raise ValueError(tr('Download unvollständig; Fortsetzen ist möglich.'))
    from core import move_entry
    move_entry(part, target, atomic=True)
    update(store, value['id'], bytes=offset, done=value['sources'])
    from lumen_history import file_change
    file_change(store, 'copy', str(target), str(target))


def execute(store, identity):
    value = store.setting(PREFIX + identity)
    if value.get('transfer_done'): return
    if value['action'] == 'download':
        download(store, value)
        return
    from core import copy_entry, move_entry
    from gi.repository import Gio, GLib
    from lumen_history import file_change
    done, errors = list(value['done']), []
    count, last = value.get('bytes', 0), 0
    def progress(amount, total=None, *_):
        nonlocal count, last
        count = amount if total is not None else count + amount
        if time.monotonic() - last > .3:
            update(store, identity, bytes=count, total=total or 0)
            last = time.monotonic()
    if value['action'] == 'copy':
        from transfer_copy import execute as copy
        copy(store, value, progress)
        return
    if value['action'] == 'move' and value.get('copy_plan'):
        from transfer_copy import execute as copy
        copy(store, value, progress)
        return
    if value['action'].startswith('drive-'):
        from drive_transfers import execute as drive
        drive(store, value, progress)
        return
    for source in value['sources']:
        if source in done: continue
        path, destination = Path(source), None
        update(store, identity, current=path.name)
        try:
            action = value['action']
            if value.get('expected') is not None:
                from image_edit import file_stamp
                if path.resolve() != path or file_stamp(path.lstat()) != value['expected'].get(source):
                    raise ValueError(tr('Datei seit der Vorschau verändert. Bitte erneut prüfen.'))
            if action == 'copy': destination = copy_entry(path, value['target'], value['portable'], progress)
            elif action in ('move', 'rename'):
                destination = Path(value['target']) / path.name if action == 'move' else Path(value['target'])
                move_entry(path, destination, atomic=(action == 'move'), progress=progress)
            elif action == 'mkdir': path.mkdir()
            elif action == 'trash': Gio.File.new_for_path(source).trash(None)
            done.append(source)
            update(store, identity, done=done)
            file_change(store, action, source, str(destination) if destination else None)
        except Exception as error:
            if (value['action'] == 'move' and isinstance(error, GLib.Error) and
                    error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_SUPPORTED)):
                from transfer_copy import execute as copy
                copy(store, store.setting(PREFIX + identity), progress)
                return
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
            if value.get('discard'): cleanup(store, value)
            update(store, identity, status='cancelled' if value.get('discard') else 'paused', errors=[])
            return
        update(store, identity, status='running')
        child = subprocess.Popen([sys.executable, str(Path(__file__)), '--execute', identity],
                                 env=worker_environment(LUMEN_DATA=str(store.directory)),
                                 pass_fds=(lease,),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        interrupted = ''
        while child.poll() is None:
            value = store.setting(PREFIX + identity)
            if value['cancel'] or time.time() - value['updated'] > 120:
                interrupted = tr('Angehalten.') if value['cancel'] else tr('Keine Antwort seit zwei Minuten. Verbindung prüfen und erneut versuchen.')
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
        elif child.returncode and not errors: errors = [tr('Übertragung wurde unterbrochen. Vor erneutem Versuch das Ziel prüfen.')]
        if value.get('discard'):
            cleanup(store, value)
            update(store, identity, status='cancelled', errors=[], **fields)
        else:
            if not errors and value['action'].startswith('drive-'): cleanup(store, value)
            update(store, identity, status='paused' if interrupted else 'failed' if errors else 'completed', errors=errors, **fields)
    except Exception as error:
        update(store, identity, status='failed', errors=[str(error)])
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
        try:
            execute(store, identity)
            update(store, identity, transfer_done=True)
        except Exception as error:
            update(store, identity, errors=[str(error)]); sys.exit(1)
