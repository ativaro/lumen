"""Encrypted restic backups, explicit sources and non-overwriting restores."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import time
from tools_data import Library
from tools_secrets import secret


def binary():
    local = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'lumen/vault/restic-0.19.1'
    return str(local) if local.is_file() else shutil.which('restic') or ''


def config_sources():
    root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))
    return [str(p) for p in [root/'Lumen', root/'plasma-org.kde.plasma.desktop-appletsrc', root/'plasmarc',
                            root/'kwinrc', root/'kglobalshortcutsrc', root/'kdeglobals'] if p.exists()]


def paths(repository, sources):
    if not str(repository).strip():raise ValueError('Einen Sicherungszielordner auswählen.')
    repo = Path(repository).expanduser().resolve()
    if not repo.is_dir(): raise ValueError('Zielordner nicht erreichbar. USB/NAS verbinden.')
    if not sources: raise ValueError('Mindestens eine Quelle auswählen.')
    checked = []
    for value in sources:
        path = Path(value).expanduser().resolve(strict=True)
        if not (path.is_dir() or path.is_file()): raise ValueError('Nur Dateien und Ordner sind zulässig.')
        if repo == path or repo.is_relative_to(path) or path.is_relative_to(repo):
            raise ValueError('Sicherung und Quellen müssen getrennt liegen.')
        checked.append(str(path))
    return str(repo), list(dict.fromkeys(checked))


@contextmanager
def lease(library, identity):
    if not re.fullmatch('[a-f0-9]{32}', identity): raise ValueError('Ungültiger Sicherungsplan.')
    fd = os.open(library.root/(identity+'.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Dieser Sicherungsplan arbeitet bereits.') from None
        yield
    finally: os.close(fd)


def command(plan, password, args, job, timeout=3600):
    program = binary()
    if not program: raise ValueError('Restic fehlt. Vault über die Einrichtung vorbereiten.')
    if not password or '\n' in password: raise ValueError('Sicherungspasswort fehlt.')
    if not Path(plan['repository']).is_dir(): raise ValueError('Sicherungsziel nicht erreichbar. USB/NAS verbinden.')
    output = job.command([program, '--quiet', '--repo', plan['repository'], '--password-file', '/dev/stdin',
                          '--json', *args], data=(password+'\n').encode(), timeout=timeout,max_output=32*1024**2)
    return output.decode('utf-8')


def verify(plan, password, job):
    data = json.loads(command(plan, password, ['cat','config'], job, 30))
    if data.get('id') != plan.get('repository_id'):
        raise ValueError('Am Ziel liegt eine andere Sicherung. Den richtigen Datenträger verbinden.')


def create(library, title, repository, sources, password, job):
    if not title.strip():raise ValueError('Bitte einen Namen angeben.')
    existing = (Path(repository).expanduser()/'config').is_file()
    if existing and not sources: repository, sources = str(Path(repository).expanduser().resolve(strict=True)), []
    else: repository, sources = paths(repository, sources)
    if not existing and len(password) < 12: raise ValueError('Bitte mindestens 12 Zeichen für das Sicherungspasswort verwenden.')
    plan = dict(repository=repository, sources=sources, interval=0, next_run=0)
    # An existing restic repository is adopted, never reset. A new one must be empty.
    if not (Path(repository)/'config').is_file():
        if any(Path(repository).iterdir()): raise ValueError('Für eine neue Sicherung einen leeren Zielordner wählen.')
        command(plan,password,['init'],job,60)
    data = json.loads(command(plan,password,['cat','config'],job,30))
    identity = library.create(title,**plan,repository_id=data['id'])
    try: secret('vault',identity,password)
    except BaseException:
        with library.connect() as db: db.execute('DELETE FROM records WHERE id=?',(identity,))
        raise
    return identity


def run(library, identity, action, job, snapshot='', selected='', destination='', full=False):
    with lease(library,identity):
        job.check()
        plan = library.get(identity); password = secret('vault',identity)
        verify(plan,password,job)
        if action in ('backup','preview'):
            _, sources = paths(plan['repository'], plan['sources'])
            args=['backup','--tag','lumen-vault','--exclude-caches']
            if action == 'preview': args.append('--dry-run')
            text=command(plan,password,[*args,'--',*sources],job,86400)
            events=[json.loads(line) for line in text.splitlines() if line.strip()]
            result=next((e for e in reversed(events) if e.get('message_type')=='summary'),None)
            if not result: raise ValueError('Restic meldet keinen abgeschlossenen Sicherungslauf.')
            if action=='backup':
                if not result.get('snapshot_id'): raise ValueError('Kein neuer Sicherungsstand bestätigt.')
                library.update(identity,last_backup=time.time(),last_error='',next_run=time.time()+plan.get('interval',0),summary=result)
            return result
        if action=='snapshots': return json.loads(command(plan,password,['snapshots'],job,60)) or []
        if action=='check':
            command(plan,password,['check',*(['--read-data'] if full else [])],job,86400)
            library.update(identity,last_check=time.time(),check_full=full); return 'Sicherungsdaten vollständig geprüft.' if full else 'Sicherungsstruktur geprüft.'
        if not re.fullmatch('[a-f0-9]{64}',snapshot): raise ValueError('Einen konkreten Sicherungsstand auswählen.')
        if action=='files':
            output=command(plan,password,['ls',snapshot],job,120)
            return [v for line in output.splitlines() if (v:=json.loads(line)).get('struct_type')=='node']
        if action=='restore':
            parent=Path(destination).expanduser().resolve(strict=True)
            if not parent.is_dir() or parent.is_relative_to(Path(plan['repository']).resolve()):
                raise ValueError('Wiederherstellungsordner außerhalb der Sicherung auswählen.')
            args=['restore',snapshot,'--verify']
            if selected:
                path=PurePosixPath(selected)
                if not path.is_absolute() or '..' in path.parts or any(c in selected for c in '\0\r\n*?['):
                    raise ValueError('Dieser Pfad kann nicht einzeln wiederhergestellt werden. Gesamten Stand wählen.')
                args+=['--include',selected]
            import tempfile
            target=Path(tempfile.mkdtemp(prefix='Lumen-Wiederherstellung-',dir=parent))
            try: command(plan,password,[*args,'--target',str(target)],job,86400)
            except BaseException:
                # Preserve completed files after cancellation; do not traverse/delete restored symlinks.
                library.update(identity,restore_path=str(target),last_error='Wiederherstellung unvollständig; Ziel prüfen.')
                raise
            library.update(identity,restore_path=str(target),last_restore=time.time()); return str(target)
        raise ValueError('Unbekannte Sicherungsaktion.')


def schedule(library, identity, interval, job):
    if interval not in (0,86400,604800): raise ValueError('Ungültiger Zeitplan.')
    config=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'systemd/user'
    config.mkdir(parents=True,exist_ok=True)
    script=str(Path(__file__).resolve())
    if any(c in script for c in '\n\r%"\\'): raise ValueError('Installationspfad nicht für Zeitpläne geeignet.')
    unit='[Unit]\nDescription=Lumen Vault Sicherungsplaene\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 "'+script+'" --tick\nNice=10\n'
    (config/'lumen-vault.service').write_text(unit)
    (config/'lumen-vault.timer').write_text('[Unit]\nDescription=Lumen Vault Zeitplan\n[Timer]\nOnCalendar=*:0/15\nPersistent=true\n[Install]\nWantedBy=timers.target\n')
    job.command(['systemctl','--user','daemon-reload'],timeout=20)
    if interval: job.command(['systemctl','--user','enable','--now','lumen-vault.timer'],timeout=20)
    library.update(identity,interval=interval,next_run=time.time()+interval)
    if not any(p.get('interval') for p in library.all()):job.command(['systemctl','--user','disable','--now','lumen-vault.timer'],timeout=20)


def tick():
    from tools_secrets import unlocked
    from tools_ui import Job
    from lumen_hardware import background_reason
    from lumen_store import Store
    library=Library('vault')
    for plan in library.all():
        if not plan.get('interval') or plan.get('next_run',0)>time.time(): continue
        try:
            reason=background_reason(Store())
            if reason: raise ValueError(reason)
            if not unlocked(): raise ValueError('Schlüsselbund gesperrt. Sicherung wartet auf die nächste Anmeldung.')
            run(library,plan['id'],'backup',Job(lambda _:None))
        except Exception as error: library.update(plan['id'],last_error=str(error)[:1000])


if __name__=='__main__' and sys.argv[1:]==['--tick']: tick()
