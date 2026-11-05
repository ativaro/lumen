"""Checked-revision updates using Lumen's existing installers; no work on import."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from lumen_i18n import tr, worker_environment

REMOTE = 'https://forge.example.invalid/ativaro/lumen.git'
SYSTEM_ROOT = Path('/usr/share/lumen')
PREVIOUS_OFFICIAL_REMOTE = 'https://github.com/ativaro/lumen.git'


def data_root():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'lumen'


def state_root():
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home()/'.local/state')/'lumen/updater'


def source_root():
    channel = hashlib.sha256(source_url().encode()).hexdigest()
    return Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'lumen/updater/sources'/channel


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError): return {}


def save_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        stage = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
            os.replace(stage, path)
        finally: stage.unlink(missing_ok=True)


def report(**data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def run(args, *, cwd=None, timeout=None, env=None):
    environment = worker_environment(GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='/bin/false', SSH_ASKPASS='/bin/false')
    if env: environment.update(env)
    # Package/build output may be large or contain local configuration. Only the
    # small stdout contracts (Git revision/log) are returned, never raw error text.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(args, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.DEVNULL, timeout=timeout)
        if result.returncode:
            raise RuntimeError(tr('Der Schritt ist fehlgeschlagen (Code {0}).', result.returncode))
        output.seek(0); return output.read(262144).decode(errors='replace').strip()


def installations():
    roots = [data_root(), SYSTEM_ROOT]
    own = Path(__file__).resolve().parent.parent
    if (own/'install.json').is_file() and own not in roots: roots.append(own)
    return [p for p in roots if (p/'files/app.py').is_file()]


def source_url():
    sources = set()
    for root in installations():
        value = read_json(root/'install.json').get('source_url')
        if value is None or value == PREVIOUS_OFFICIAL_REMOTE:
            sources.add(REMOTE)
            continue
        if not isinstance(value, str): raise ValueError(tr('Ungültige Lumen-Update-Quelle.'))
        try:
            url = urlsplit(value)
            valid = (url.scheme == 'https' and url.hostname and not url.username and
                     not url.password and not url.query and not url.fragment and
                     url.path.endswith('.git') and not any(c.isspace() for c in value))
            url.port
        except ValueError:
            valid = False
        if not valid: raise ValueError(tr('Ungültige Lumen-Update-Quelle.'))
        sources.add(value)
    if len(sources) > 1:
        raise ValueError(tr('Die installierten Lumen-Versionen stammen aus verschiedenen Quellen. Bitte getrennt aktualisieren.'))
    return next(iter(sources), REMOTE)


def prepare_source():
    remote = source_url()
    source = source_root(); source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        if not source.exists():
            with tempfile.TemporaryDirectory(dir=source.parent) as tmp:
                staged = Path(tmp)/'source'
                run(['git', 'clone', '--depth=50', '--single-branch', '--branch', 'main', remote, str(staged)], timeout=180)
                staged.rename(source)
        if run(['git','remote','get-url','origin'], cwd=source) != remote:
            raise ValueError(tr('Der Update-Ordner gehört zu einer anderen Quelle. Bitte den vorhandenen Update-Ordner sichern und entfernen.'))
        if run(['git','status','--porcelain'], cwd=source):
            raise ValueError(tr('Der Update-Ordner enthält eigene Änderungen. Diese zuerst sichern.'))
        run(['git','fetch','--no-tags','origin','main'], cwd=source, timeout=180)
        revision = run(['git','rev-parse','FETCH_HEAD'], cwd=source)
        if not re.fullmatch(r'[a-f0-9]{40}', revision): raise ValueError(tr('Ungültige Update-Version.'))
        run(['git','checkout','--detach', revision], cwd=source)
        return revision
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        raise RuntimeError(tr('Die Update-Quelle ist nicht erreichbar. Internet und Zugriff auf das private Lumen-Repository prüfen.')) from error


def component_definitions():
    root = data_root(); speech = root/'speech'
    return [
        ('qt', tr('Lumen-Oberfläche'), tr('Gemeinsame Qt-Laufzeit'), (root/'qt6-env/bin/python').is_file(), ['bin/lumen-python']),
        ('engine', tr('KI-Engine'), tr('Die für Lumen geprüfte OpenCode-Version'),
         bool(shutil.which('opencode') or (Path.home()/'.opencode/bin/opencode').is_file() or list((root/'engine').glob('*/opencode'))), ['files/lumen_setup.py','files/assistant_backend.py']),
        ('dictation', tr('Diktieren'), tr('Spracherkennung und Sprechpausen'), bool(list(speech.glob('whisper-*'))), ['files/lumen_setup.py']),
        ('dictation-quality', tr('Genauere Spracherkennung'), tr('Bereits installiertes großes Sprachmodell'), bool(list(speech.glob('ggml-large*'))), ['files/lumen_setup.py']),
        ('voice', tr('Sprachausgabe'), tr('Lokale Piper-Stimme'), (speech/'piper-env/bin/python').is_file(), ['files/lumen_setup.py']),
        ('voice-multilingual', tr('Mehrsprachige Stimme'), tr('Lokale Qwen-Laufzeit und Modell'), (speech/'qwen-env/bin/python').is_file(), ['files/lumen_setup.py','files/speech_model.py']),
        ('image-search', tr('Bildsuche'), tr('Lokale Motivsuche und Modelle'), (root/'vision/env-v1/bin/python').is_file(), ['files/lumen_setup.py','files/photo_tools.py']),
        ('inbox', tr('Kalenderanbindung'), tr('Inbox und CalDAV'), (root/'inbox-env-v1/bin/python').is_file(), ['files/lumen_setup.py']),
        ('vault', tr('Datensicherung'), tr('Lokale Restic-Laufzeit'), bool(list((root/'vault').glob('restic-*'))), ['files/lumen_setup.py']),
        ('native-vault', tr('Tresor'), tr('Bereits installierter nativer Passwort-Tresor'), (root/'vault-lab/bin/lumen-vault-lab').is_file(), ['native/vault-ui','native/vault-core']),
    ]


def fingerprint(source, paths):
    # ponytail: installer-file granularity can recheck an unchanged dependency;
    # split the installer modules if this becomes a measurable update cost.
    digest = hashlib.sha256()
    for rel in paths:
        path = source/rel
        files = [path] if path.is_file() else [source/p for p in run(['git','ls-files',rel], cwd=source).splitlines()]
        for file in files:
            digest.update(str(file.relative_to(source)).encode()); digest.update(file.read_bytes())
    return digest.hexdigest()


def check():
    report(message=tr('Nach Lumen-Updates suchen …'))
    revision = prepare_source(); source = source_root()
    saved = read_json(state_root()/'components.json')
    roots = installations()
    bundle_current = bool(roots) and all(read_json(p/'install.json').get('revision') == revision for p in roots)
    rows = [dict(id='lumen', title=tr('Lumen und alle Apps'), detail=tr('Files, Suche, Panels, Themes und Integrationen'),
                 pending=not bundle_current, fingerprint=revision, optional=False)]
    for key, title, detail, installed, paths in component_definitions():
        if not installed: continue
        stamp = fingerprint(source, paths)
        rows.append(dict(id=key, title=title, detail=detail, pending=saved.get(key)!=stamp,
                         fingerprint=stamp, optional=False))
    if shutil.which('pacman'):
        rows.append(dict(id='system', title=tr('Linux-System'), detail=tr('Alle Systempakete über die Paketverwaltung'), pending=True, optional=True))
    if shutil.which('flatpak'):
        rows.append(dict(id='flatpak', title=tr('Flatpak-Apps'), detail=tr('Installierte Apps und Laufzeiten'), pending=True, optional=True))
    notes = run(['git','log','-6','--format=%s',revision], cwd=source)
    plan = dict(revision=revision, source_url=source_url(), rows=rows, notes=notes)
    save_json(state_root()/'plan.json', plan); report(plan=plan)
    return plan


def install_bundle(source, revision):
    roots = installations()
    if not roots: roots = [data_root()]
    if any((root/'files/server_notes_app.py').is_file() for root in roots):
        required = ('files/server_notes_app.py','files/server_app_session.py','files/server_app_window.py','files/tools_app.py')
        if any(not (source/name).is_file() for name in required) or (source/'files/tools_inbox.py').exists():
            raise ValueError(tr('Dieses Update würde die Server-Apps Inbox oder Notes durch ältere Desktop-Apps ersetzen.'))
    if any((root/'files/topbar_data.py').is_file() for root in roots):
        required = ('files/topbar_data.py','files/topbar_activity.py','files/topbar_system.py',
                    'files/topbar_context.py','files/topbar_conversation.py','native/topbar/CMakeLists.txt','bin/lumen-panel')
        if any(not (source/name).is_file() for name in required):
            raise ValueError(tr('Dieses Update enthält keine passende Lumen-Topbar. Die Installation bleibt unverändert.'))
        help_text = run([str(source/'bin/lumen-panel'),'--help'], cwd=source, timeout=15)
        if any(flag not in help_text for flag in ('--bar-snapshot','--system-topic','--conversation','--topbar-note')):
            raise ValueError(tr('Der Topbar-Helfer dieses Updates ist unvollständig. Die Installation bleibt unverändert.'))
    # Update every installed runtime; a newer user launcher must not mask an old
    # system copy. Existing installers preserve data and desktop preferences.
    if SYSTEM_ROOT in roots:
        run(['bash',str(source/'packaging/arch/build-package.sh')], cwd=source)
        packages = [Path(p) for p in run(['makepkg','--packagelist'], cwd=source/'packaging/arch', env={'LOCALSRC':'1'}).splitlines()]
        if len(packages)!=1: raise ValueError(tr('Das Update-Paket konnte nicht eindeutig bestimmt werden.'))
        run(['pkexec','pacman','-U','--noconfirm',str(packages[0])])
        # Execute the new helper, even while this updater still runs the old code.
        run([str(source/'bin/lumen-desktop-setup'),'--refresh-decoration'], cwd=source)
    for root in roots:
        if root == SYSTEM_ROOT: continue
        run(['bash',str(source/'install.sh'),'--no-mcp'], cwd=source,
            env={'PREFIX':str(root), 'LUMEN_SOURCE_REVISION':revision, 'LUMEN_SOURCE_URL':source_url()})


def apply(revision, selected):
    plan = read_json(state_root()/'plan.json'); source = source_root()
    if (not re.fullmatch(r'[a-f0-9]{40}', revision) or plan.get('revision')!=revision or
            plan.get('source_url') != source_url() or
            run(['git','remote','get-url','origin'], cwd=source) != plan.get('source_url') or
            run(['git','rev-parse','HEAD'], cwd=source)!=revision or
            run(['git','status','--porcelain'], cwd=source)):
        raise ValueError(tr('Die Update-Auswahl ist veraltet. Bitte erneut prüfen.'))
    rows = {row['id']:row for row in plan['rows']}
    if not selected or not set(selected)<=rows.keys(): raise ValueError(tr('Keine gültigen Updates ausgewählt.'))
    if rows['lumen']['pending'] and 'lumen' not in selected and any(not rows[key]['optional'] for key in selected):
        raise ValueError(tr('Bitte Lumen zusammen mit seinen Komponenten aktualisieren.'))
    saved = read_json(state_root()/'components.json'); failures = []
    from PySide6.QtCore import QSettings
    model = QSettings('Lumen','Assistant').value('speechModel','')
    python = str(source/'bin/lumen-python')
    ordered = [key for key in ['system', *rows, 'flatpak'] if key in selected]
    ordered = list(dict.fromkeys(ordered))
    for index, key in enumerate(ordered):
        report(component=key, state='running', message=tr('{0} wird aktualisiert …', rows[key]['title']), progress=int(index*100/len(ordered)))
        try:
            if key == 'lumen': install_bundle(source, revision)
            elif key == 'system': run(['pkexec','pacman','-Syu','--ignore','lumen','--noconfirm'])
            elif key == 'flatpak': run(['flatpak','update','--noninteractive','--assumeyes'])
            elif key == 'qt': run([python,'--install-runtime'])
            elif key == 'native-vault':
                development = data_root().parent/'lumen-dev'
                environment = {'PATH':str(Path.home()/'.cargo/bin')+os.pathsep+os.environ.get('PATH','')}
                if (development/'cargo/bin/cargo').is_file():
                    environment.update(CARGO_HOME=str(development/'cargo'), RUSTUP_HOME=str(development/'rustup'),
                                       PATH=str(development/'cargo/bin')+os.pathsep+environment['PATH'])
                if not shutil.which('cargo', path=environment['PATH']):
                    raise RuntimeError(tr('Für den nativen Tresor fehlt die Rust-Bauumgebung. Bitte die Tresor-Einrichtung vervollständigen.'))
                run(['bash',str(source/'native/vault-ui/install-laboratory.sh')], cwd=source,
                    env=environment)
            else:
                arguments = [python,str(source/'files/lumen_setup.py'),key]
                if key in ('dictation','voice') and model and Path(model).is_file(): arguments += ['--existing-model',model]
                run(arguments)
            if 'fingerprint' in rows[key]:
                saved[key] = rows[key]['fingerprint']; save_json(state_root()/'components.json',saved)
            report(component=key, state='done', message=tr('{0} ist aktualisiert.',rows[key]['title']))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            failures.append(key); report(component=key,state='failed',message=tr('{0} konnte nicht aktualisiert werden.',rows[key]['title'])+' '+str(error))
            if key == 'lumen': break  # Dependency revisions must not outrun the apps.
    report(finished=True, success=not failures, progress=100,
           message=tr('Aktualisiert. Geöffnete Apps übernehmen Änderungen beim nächsten Start; Panels bei der nächsten Anmeldung.') if not failures else
                   tr('Nicht alles wurde aktualisiert. Fehlgeschlagene Schritte nach einer erneuten Prüfung wiederholen.'))
    from lumen_notifications import announce
    announce('Lumen Updater',revision,tr('Aktualisierung abgeschlossen') if not failures else tr('Aktualisierung braucht deine Aufmerksamkeit'),
             target='app:updater',attention=bool(failures),revision=time.time_ns())
    return not failures


def main():
    import argparse
    from PySide6.QtCore import QCoreApplication, QLockFile
    app = QCoreApplication(sys.argv)
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['check','apply'])
    parser.add_argument('--revision',default=''); parser.add_argument('--components',nargs='*',default=[])
    args=parser.parse_args()
    state_root().mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=QLockFile(str(state_root()/'worker.lock')); lock.setStaleLockTime(0)
    if not lock.tryLock(0): report(error=tr('Eine Update-Prüfung oder Installation läuft bereits.')); return 1
    try:
        if args.action=='check': check(); return 0
        return 0 if apply(args.revision,args.components) else 1
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report(error=str(error)); return 1
    finally: lock.unlock()


if __name__=='__main__': raise SystemExit(main())
