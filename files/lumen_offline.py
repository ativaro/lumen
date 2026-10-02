"""Private offline working copies. Three-way reconciliation never guesses a conflict winner."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
import uuid
from lumen_store import Store

PREFIX = 'offline/'


def folders(store):
    return [json.loads(r['value']) for r in store.rows('SELECT value FROM settings WHERE key LIKE ?', (PREFIX + '%',))]


def pin(store, remote):
    from network import normalize_url, server_label
    remote = normalize_url(remote)
    for item in folders(store):
        if item['remote'] == remote: return item
    identity = uuid.uuid4().hex
    local = store.directory / 'offline' / identity / 'files'
    local.mkdir(parents=True, mode=0o700)
    item = dict(id=identity, name=server_label(remote), remote=remote, local=str(local), base={},
                conflicts=[], status='Noch nicht geladen', synced=0)
    store.set_setting(PREFIX + identity, item)
    return item


def digest(path, progress=lambda _: None):
    try:
        info = path.lstat()
    except FileNotFoundError: return None
    if not stat.S_ISREG(info.st_mode): raise ValueError('Keine reguläre Datei: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): h.update(chunk); progress(path.name)
        after = os.fstat(stream.fileno())
    if (info.st_size, info.st_mtime_ns, info.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Datei wurde während des Lesens verändert: ' + str(path))
    return h.hexdigest()


def scan(root, progress=lambda _: None, directories=None):
    if root.is_symlink() or not root.is_dir(): raise ValueError('Ordner nicht verfügbar: ' + str(root))
    result = {}
    def failed(error): raise error
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=failed):
        for name in dirs:
            if directories is not None: directories.add((Path(directory) / name).relative_to(root).as_posix())
            if (Path(directory) / name).is_symlink(): raise ValueError('Symbolische Ordner werden nicht synchronisiert.')
        for name in names:
            if name.startswith('.lumen-sync-'): continue
            path = Path(directory) / name
            result[path.relative_to(root).as_posix()] = digest(path, progress)
            if len(result) > 50000: raise ValueError('Mehr als 50.000 Dateien. Bitte kleinere Ordner auswählen.')
    return result


def safe_path(root, relative):
    part = Path(relative)
    if part.is_absolute() or not part.parts or '..' in part.parts: raise ValueError('Ungültiger Dateipfad.')
    path = root / part
    for ancestor in [root, *path.parents, path]:
        if ancestor.is_symlink(): raise ValueError('Symbolische Verknüpfung wurde verändert: ' + str(ancestor))
    return path


def replace_file(source, target, expected_source, expected_target, archive, progress=lambda _: None, portable=False):
    """Stage first; preserve overwritten content; recheck both sides before committing."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if digest(target, progress) != expected_target: raise ValueError('Zieldatei inzwischen verändert: ' + target.name)
    staged = None
    try:
        if expected_source is not None:
            if digest(source, progress) != expected_source: raise ValueError('Quelldatei inzwischen verändert: ' + source.name)
            with tempfile.NamedTemporaryFile(prefix='.lumen-sync-', dir=target.parent, delete=False) as output:
                staged = Path(output.name)
                with source.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024): output.write(chunk); progress(source.name)
                output.flush(); os.fsync(output.fileno())
            if digest(staged, progress) != expected_source: raise ValueError('Quelldatei während Kopieren verändert.')
            if not portable: shutil.copystat(source, staged)
        if expected_target is not None and archive is not None:
            archive.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = archive / (str(time.time_ns()) + '-' + target.name.encode()[:160].decode(errors='ignore'))
            shutil.copy2(target, backup)
            if digest(backup, progress) != expected_target: raise ValueError('Zieldatei während Sicherung verändert.')
        if digest(source, progress) != expected_source: raise ValueError('Quelldatei inzwischen verändert.')
        if digest(target, progress) != expected_target: raise ValueError('Zieldatei inzwischen verändert.')
        if staged: os.replace(staged, target); staged = None
        elif expected_target is not None: target.unlink()
    finally:
        if staged: staged.unlink(missing_ok=True)


def sync(store, identity, remote_root, choices=None, progress=lambda _: None):
    lease = store.acquire('offline-' + identity)
    try:
        item = store.setting(PREFIX + identity)
        local, remote = Path(item['local']), Path(remote_root)
        def root_ids():
            try:
                infos = [p.stat() for p in (local, remote)]
                if not all(stat.S_ISDIR(info.st_mode) for info in infos): raise ValueError('Ordner nicht verfügbar.')
                return [(info.st_dev, info.st_ino) for info in infos]
            except OSError as error: raise ValueError('Ordner nicht verfügbar: ' + str(error)) from error
        root_signatures = root_ids()
        def check_roots():
            if root_ids() != root_signatures:
                raise ValueError('Ein Ordner wurde während des Abgleichs getrennt oder ersetzt.')
        # Complete both scans before deriving deletions; an unavailable share is never empty.
        local_dirs, remote_dirs = set(), set()
        ours, theirs = scan(local, progress, local_dirs), scan(remote, progress, remote_dirs)
        base = item['base']; conflicts = []
        for name in sorted(set(base) | set(ours) | set(theirs)):
            check_roots()
            left, right, old = ours.get(name), theirs.get(name), base.get(name)
            progress(name)
            if left == right: winner = left
            else:
                choice = (choices or {}).get(name)
                if choice and choice.get('local') == left and choice.get('remote') == right:
                    use_local = choice['use'] == 'local'
                elif left == old: use_local = False
                elif right == old: use_local = True
                else:
                    from datetime import datetime
                    def detail(root, checksum):
                        if checksum is None: return 'Gelöscht'
                        info = safe_path(root,name).stat()
                        return f'{info.st_size:,} Bytes · ' + datetime.fromtimestamp(info.st_mtime).strftime('%d.%m.%Y %H:%M')
                    conflicts.append(dict(path=name, local=left, remote=right, localInfo=detail(local,left), remoteInfo=detail(remote,right))); continue
                src, dst = (local, remote) if use_local else (remote, local)
                winner, previous = (left, right) if use_local else (right, left)
                replace_file(safe_path(src, name), safe_path(dst, name), winner, previous,
                             store.directory / 'offline' / identity / 'replaced', progress, portable=use_local)
            check_roots()
            if winner is None: base.pop(name, None)
            else: base[name] = winner
            # Crash-safe checkpoint after every committed file.
            store.set_setting(PREFIX + identity, item)
        # Mirror empty folders as well; only remove directories that are still empty.
        kept = local_dirs | remote_dirs
        for name in sorted(kept, key=lambda n: len(Path(n).parts), reverse=True):
            check_roots()
            removed = name in item.get('directories', []) and (name not in local_dirs or name not in remote_dirs)
            if removed:
                for root in (local, remote):
                    folder = safe_path(root, name)
                    try: folder.rmdir()
                    except FileNotFoundError: pass
                    except OSError:
                        if folder.is_dir() and any(folder.iterdir()): removed = False
                        else: raise
                if removed: kept.discard(name)
            if not removed:
                for root in (local, remote): safe_path(root, name).mkdir(parents=True, exist_ok=True)
        item['directories'] = sorted(kept)
        item.update(conflicts=conflicts, status=f'{len(conflicts)} Konflikte' if conflicts else 'Aktuell', synced=time.time())
        store.set_setting(PREFIX + identity, item)
        return item
    finally: os.close(lease)


if __name__ == '__main__':
    store = Store(); last = [0.0]
    def progress(name):
        if time.monotonic() - last[0] > .5:
            print(json.dumps({'progress': name}), flush=True); last[0] = time.monotonic()
    try:
        request = json.loads(sys.stdin.readline())
        result = sync(store, request['id'], request['root'], request.get('choices'), progress)
        print(json.dumps({'result': result}), flush=True)
    except Exception as error:
        print(json.dumps({'error': str(error)}), flush=True); sys.exit(1)
