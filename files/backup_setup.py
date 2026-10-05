"""Guided backup inventory, destination checks and encrypted Vault snapshots."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
import uuid

from lumen_i18n import tr


def vault_root():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'lumen-vault-lab'


def inventory():
    from PySide6.QtCore import QStandardPaths as Paths
    from interop_vault import discover_sources
    import vault_data
    files = []
    for label, location in [('Dokumente', Paths.DocumentsLocation), ('Bilder', Paths.PicturesLocation),
                            ('Musik', Paths.MusicLocation), ('Videos', Paths.MoviesLocation), ('Schreibtisch', Paths.DesktopLocation)]:
        path = Paths.writableLocation(location)
        if path and Path(path).is_dir() and Path(path).resolve() != Path.home().resolve():
            files.append(dict(label=tr(label), path=path))
    apps = [r for r in discover_sources() if r.get('kind') != 'native-vault']
    config = vault_data.config_sources()
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    for relative in ('color-schemes', 'aurorae/themes', 'plasma/desktoptheme', 'wallpapers'):
        if (data/relative).is_dir(): config.append(str(data/relative))
    return dict(files=files, lumen=[dict(label=r['title'], path=r['path']) for r in apps] +
                [dict(label=Path(p).name, path=p) for p in config],
                vault=[dict(label=tr('Verschlüsselter Passwort-Tresor'), path=str(vault_root()))] if (vault_root()/'vault.kdbx').is_file() else [])


def encrypted_copy(source, destination, job):
    """Pin the private directory and each saved inode; never read an unlock key."""
    root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        meta = os.fstat(root)
        if meta.st_uid != os.getuid() or meta.st_mode & 0o077: raise ValueError(tr('Tresor-Verzeichnis ist nicht privat.'))
        destination.mkdir(parents=True, mode=0o700)
        for name in ('vault.kdbx', 'previous.kdbx'):
            try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=root)
            except FileNotFoundError:
                if name == 'previous.kdbx': continue
                raise
            with os.fdopen(fd, 'rb') as src:
                before = os.fstat(src.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_nlink != 1 or not 12 <= before.st_size <= 64*1024**2:
                    raise ValueError(tr('Ungültige verschlüsselte Tresordatei.'))
                if src.read(8) != bytes.fromhex('03d9a29a67fb4bb5'): raise ValueError(tr('Keine KDBX-Tresordatei.'))
                src.seek(0)
                with (destination/name).open('xb') as dst:
                    os.chmod(destination/name, 0o600)
                    copied = 0
                    while chunk := src.read(1024*1024):
                        job.check(); copied += len(chunk)
                        if copied > 64*1024**2: raise ValueError(tr('Tresordatei wurde verändert.'))
                        dst.write(chunk)
                after = os.fstat(src.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError(tr('Tresordatei wurde während der Kopie verändert.'))
    finally: os.close(root)


def network(request, job):
    from backup_network import call, address
    from tools_secrets import secret
    from PySide6.QtCore import QSettings
    op = request.get('action', 'browse')
    uri = address(request.get('uri', 'smb://'))
    args = dict(op='mount' if op in ('test', 'resolve') else 'discover' if op == 'discover' else 'browse', uri=uri)
    for key in ('username', 'password', 'domain'):
        args[key] = request.get(key, '')
    identity = request.get('network_id', '')
    if identity and not args['password']:
        stored = json.loads(secret('backup-network', identity))
        # Credentials are scoped to this server; never forward to a new host.
        from urllib.parse import urlsplit
        if urlsplit(stored['uri']).netloc != urlsplit(uri).netloc: raise ValueError(tr('Netzwerkzugang gehört zu einem anderen Server.'))
        args.update({k: stored[k] for k in ('username', 'password', 'domain')})
    result = call(args, job)
    if op == 'discover':
        existing = []
        for value in QSettings('Lumen', 'Files').value('network_servers', [], type=list):
            try: existing.append(dict(label=value, uri=address(value)))
            except ValueError: continue
        result['items'] = list({r['uri']: r for r in existing + result.get('items', [])}.values())
        return result
    if result.get('error'):
        messages = {'auth_required': tr('Bitte Benutzername und Passwort prüfen. Anmeldung erforderlich.'),
                    'path_unavailable': tr('Netzwerkfreigabe hat keinen lokalen Zugriff. GVfs/FUSE vorbereiten.'),
                    'unavailable': tr('Netzwerkerkennung fehlt. Netzwerk-Unterstützung in Lumen einrichten.')}
        raise ValueError(messages.get(result['error'], tr('Freigabe nicht erreichbar. Verbindung und Berechtigungen prüfen.')))
    if op in ('test', 'resolve'):
        if op == 'test': result.update(probe(result['path']))
        if request.get('remember') and args['password']:
            identity = identity or uuid.uuid4().hex
            secret('backup-network', identity, json.dumps(dict(uri=uri, **{k: args[k] for k in ('username', 'password', 'domain')})))
        result['network_id'] = identity
    return result


def probe(path):
    parent = Path(path).expanduser().resolve(strict=True)
    if not parent.is_dir(): raise ValueError(tr('Sicherungsziel ist kein Ordner.'))
    if (parent/'config').is_file():
        return dict(path=str(parent), free=shutil.disk_usage(parent).free, existing=True, tested=True)
    content = secrets.token_bytes(64)
    fd, name = tempfile.mkstemp(prefix='.lumen-verbindungstest-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as file: file.write(content); file.flush(); os.fsync(file.fileno())
        if Path(name).read_bytes() != content: raise ValueError(tr('Schreib-/Lesetest fehlgeschlagen.'))
    finally: Path(name).unlink(missing_ok=True)
    return dict(path=str(parent), free=shutil.disk_usage(parent).free,
                existing=(parent/'config').is_file(), tested=True)


def resolve_plan(plan, job, *, sources=True):
    """Resolve the URI afresh; never create a shadow directory at an old mount."""
    plan = dict(plan)
    if plan.get('network_uri'):
        reply = network(dict(action='resolve', uri=plan['network_uri'], network_id=plan.get('network_id', '')), job)
        plan['repository'] = reply['path']
    mapping = {}
    for source in (plan.get('remote_sources', []) if sources else []):
        reply = network(dict(action='resolve', uri=source['uri'], network_id=source.get('network_id', '')), job)
        mapping[source['path']] = reply['path']
    if mapping:
        plan['sources'] = [mapping.get(p, p) for p in plan['sources']]
        plan['groups'] = {g: [mapping.get(p, p) for p in rows] for g, rows in plan.get('groups', {}).items()}
        plan['remote_sources'] = [dict(row, path=mapping[row['path']]) for row in plan['remote_sources']]
    return plan


def configure(library, request, job):
    import vault_data as vault
    from interop_vault import discover_sources
    target = request['repository']
    if request.get('network_uri'):
        target = resolve_plan(dict(repository=target, **{k: request.get(k, '') for k in ('network_uri', 'network_id')}), job)['repository']
    if request.get('adopt'):
        if not (Path(target)/'config').is_file(): raise ValueError(tr('Hier liegt keine bestehende Sicherung.'))
        identity = vault.create(library, request['title'], target, [], request['password'], job)
        library.update(identity, **{k: request.get(k, '') for k in ('network_uri', 'network_id')}, adopted=True)
        return dict(id=identity, restored_connection=True)
    probe(target)
    if not request.get('recovery_confirmed'): raise ValueError(tr('Wiederherstellungsschlüssel zuerst unabhängig aufbewahren.'))
    selected = request.get('groups', {})
    if not isinstance(selected, dict) or set(selected) - {'files', 'lumen', 'vault'}: raise ValueError(tr('Ungültige Quellenauswahl.'))
    sources = []
    current = inventory()
    for group, values in selected.items():
        if not isinstance(values, list) or len(values) > 100: raise ValueError(tr('Zu viele Sicherungsquellen.'))
        if any(not isinstance(v, str) for v in values): raise ValueError(tr('Ungültige Quelle.'))
        allowed = {r['path'] for r in current[group]}
        if group != 'files' and any(v not in allowed for v in values): raise ValueError(tr('Lumen-Quellen wurden geändert. Auswahl neu laden.'))
        selected[group] = list(dict.fromkeys(str(Path(v).expanduser().resolve(strict=True)) for v in values))
        sources.extend(selected[group])
    sources = list(dict.fromkeys(sources))
    if not sources: raise ValueError(tr('Mindestens eine Quelle auswählen.'))
    remotes = request.get('remote_sources', [])
    if not isinstance(remotes, list) or len(remotes) > 100: raise ValueError(tr('Ungültige Netzwerkquellen.'))
    for row in remotes:
        if isinstance(row, dict) and isinstance(row.get('path'), str): row['path'] = str(Path(row['path']).expanduser().resolve())
        if not isinstance(row, dict) or set(row) - {'path', 'uri', 'network_id'} or row.get('path') not in sources:
            raise ValueError(tr('Ungültige Netzwerkquelle.'))
        from backup_network import address
        address(row['uri'])
    if request.get('interval', 86400) not in (0, 86400, 604800): raise ValueError(tr('Ungültiger Zeitplan.'))
    # Exclusive fresh directory. Never initialize or overwrite existing content.
    parent = Path(target); child = 'Lumen-Sicherung-' + uuid.uuid4().hex[:8]
    repository = parent/child; repository.mkdir(mode=0o700)
    apps = [r for r in discover_sources() if r['path'] in sources]
    try:
        identity = vault.create(library, request['title'], str(repository), sources, request['password'], job, app_sources=apps)
    except BaseException:
        if not any(repository.iterdir()): repository.rmdir()
        raise
    uri = request.get('network_uri', '')
    if uri:
        from urllib.parse import quote
        uri = uri.rstrip('/') + '/' + quote(child)
    library.update(identity, groups=selected, network_uri=uri, network_id=request.get('network_id', ''), remote_sources=remotes,
                   setup_pending=True, intended_interval=request.get('interval', 86400))
    return dict(id=identity, prepared=True)


def finish_setup(library, identity, job):
    import vault_data as vault
    if not library.get(identity).get('setup_pending'): raise ValueError(tr('Einrichtung ist bereits abgeschlossen.'))
    try:
        summary = vault.run(library, identity, 'backup', job)
        plan = library.get(identity)
        vault.schedule(library, identity, plan.get('intended_interval', 86400), job)
        library.update(identity, setup_pending=False)
        return dict(id=identity, verified=True, snapshot=summary['snapshot_id'])
    except BaseException:
        library.update(identity, setup_pending=True, last_error=tr('Einrichtung unvollständig. Erste Sicherung und Prüfung erneut starten.'))
        raise


@contextmanager
def verification_source(enabled):
    if not enabled:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix='lumen-backup-check-') as directory:
        path = Path(directory)/'Wiederherstellungsprobe.txt'
        path.write_text('Lumen backup verification\n'+secrets.token_hex(32), encoding='utf-8')
        yield path
