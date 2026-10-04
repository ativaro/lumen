"""Explicit application backup sources and recoverable, isolated app copies.

A backup captures committed SQLite transactions and saved files, never unsaved
editors. Each database is consistent independently; this is not a global app
transaction. All restore paths stay below Restic's newly created directory.
"""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from lumen_i18n import tr


APP_NAMES = {
    'translate': 'Lumen Translate',
    'wissen': 'Lumen Wissen', 'reader': 'Lumen Reader', 'inbox': 'Lumen Inbox',
    'meetings': 'Lumen Meeting-Werkstatt', 'household': 'Lumen Digitaler Haushalt',
    'workbench': 'Lumen Projekt-Werkbank', 'radio': 'Lumen Persönliches Radio',
    'sound': 'Lumen Sound', 'vault': 'Lumen Vault', 'interop': tr('Lumen Verknüpfungen'),
}
MANIFEST = 'lumen-app-backup.json'


def tools_root(root=None):
    return Path(root or os.environ.get('LUMEN_TOOLS_DATA') or
                Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'lumen-tools').resolve()


def discover_sources(root=None, store=None):
    """Discover existing local sources without creating libraries or reading secrets."""
    from lumen_store import state_path
    base = tools_root(root)
    state = Path(store.directory if store else state_path()).resolve()
    include_state = store is not None or root is None or base == tools_root()
    result = []
    for app, title in APP_NAMES.items():
        path = base/app
        if path.is_dir() and (path/'library.sqlite').is_file():
            result.append(dict(app=app, title=tr(title), path=str(path), slot='tools/'+app, kind='library'))
    if not include_state: return result
    notebook = store.setting('knowledge/notebook', '') if store else ''
    if store is None and (state/'lumen.sqlite3').is_file():
        with closing(sqlite3.connect((state/'lumen.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute("SELECT value FROM settings WHERE key='knowledge/notebook'").fetchone()
            if row: notebook = json.loads(row[0])
    if notebook and Path(notebook).is_dir():
        result.append(dict(app='wissen', title=tr('Lumen Wissen · Notizordner mit Bildern'),
                           path=str(Path(notebook).resolve()), slot='notebook', kind='notebook'))
    for relative, slot in [('lumen.sqlite3', 'state/lumen.sqlite3'), ('wissen-history', 'state/wissen-history'),
                           ('lumen-memory', 'state/lumen-memory')]:
        path = state/relative
        if path.exists():
            title = {'lumen.sqlite3': tr('Lumen · gemeinsame Einstellungen, Aufgaben und Verlauf'),
                     'wissen-history': tr('Lumen Wissen · Notizverlauf'), 'lumen-memory': tr('Lumen Wissen · Gedächtnis')}[relative]
            result.append(dict(app='wissen', title=title,
                               path=str(path), slot=slot, kind='state'))
    return result


def payload_sources(payload, root=None, store=None):
    """Back up whole app records with assets; Files retains the explicit selection."""
    source = payload.get('source', {})
    app = source.get('app')
    entries = [entry for entry in discover_sources(root, store) if entry['app'] == app] if app in APP_NAMES else []
    if app == 'wissen':
        notebook = source.get('locator', {}).get('notebook') or source.get('locator', {}).get('root')
        if notebook and source.get('id') == 'collection:' and payload.get('paths') == [notebook]:
            if not Path(notebook).is_dir():raise ValueError(tr('Notizordner nicht erreichbar.'))
            return [dict(app='wissen',title=tr('Lumen Wissen · Notizordner mit Bildern'),
                         path=str(Path(notebook).resolve()),slot='notebook',kind='notebook')]+[e for e in discover_sources(root,store) if e['app']=='interop']
        if notebook and Path(notebook).is_dir() and not any(e['path'] == str(Path(notebook).resolve()) for e in entries):
            entries.append(dict(app='wissen', title=tr('Lumen Wissen · Notizordner mit Bildern'),
                                path=str(Path(notebook).resolve()), slot='notebook', kind='notebook'))
    if entries:
        links = [e for e in discover_sources(root, store) if e['app'] == 'interop']
        entries += links
        if app == 'workbench' and source.get('id'):
            dbpath = tools_root(root)/'workbench/library.sqlite'
            with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro', uri=True)) as db:
                record = db.execute('SELECT data FROM records WHERE id=?', (source['id'],)).fetchone()
                if record:
                    for item in json.loads(record[0]).get('resources', []):
                        if item.get('kind') == 'file':
                            path = Path(item['target']).expanduser().resolve()
                            entries.append(dict(app='files', title=item.get('title', path.name), path=str(path),
                                                kind='file', missing=not path.exists()))
        for path in payload.get('paths', []):
            path = Path(path).expanduser().resolve()
            if not any(path == Path(row['path']) or path.is_relative_to(Path(row['path'])) for row in entries):
                entries.append(dict(app='files', title=path.name, path=str(path), kind='file', missing=not path.exists()))
        return list({row['path']: row for row in entries}.values())
    paths = list(payload.get('paths') or [])
    if source.get('path'): paths.append(source['path'])
    if not paths: raise ValueError(tr('Keine gespeicherten Dateien für Lumen Vault vorhanden.'))
    return [dict(app='files', title=Path(p).name, path=str(Path(p).expanduser().resolve(strict=True)),
                 kind='file') for p in dict.fromkeys(paths)]


def handoff_receipt(library, token, signature):
    """Recover a completed plan mutation even when the central receipt failed."""
    if not token: return None
    if not isinstance(token, str) or not 1 <= len(token) <= 128 or not isinstance(signature, str) or not 1 <= len(signature) <= 128:
        raise ValueError(tr('Ungültige Übergabe.'))
    with library.connect() as db:
        for row in db.execute('SELECT id,title,data,archived FROM records'):
            found = json.loads(row['data']).get('interop_handoffs', {}).get(token)
            if found is None: continue
            if found != signature: raise ValueError(tr('Diese Übergabe wurde bereits mit anderem Inhalt übernommen.'))
            if row['archived']: raise ValueError(tr('Der Sicherungsplan dieser Übergabe wurde archiviert.'))
            return dict(app='vault', id=row['id'], kind='record', title=row['title'])
    return None


def merge_sources(library, identity, sources, source_ref=None, token=None, signature=None, schedule_interval=None):
    """Merge explicitly reviewed source rows idempotently under the plan lease."""
    import vault_data
    rows = [dict(path=str(row)) if not isinstance(row, dict) else dict(row) for row in sources]
    if not rows or len(rows) > 100: raise ValueError(tr('Eine bis hundert Sicherungsquellen auswählen.'))
    with vault_data.lease(library, identity):
        plan = library.get(identity)
        _, paths = vault_data.paths(plan['repository'], plan.get('sources', [])+[row['path'] for row in rows])
        apps = {entry['path']: entry for entry in plan.get('app_sources', [])}
        for row in rows:
            canonical = str(Path(row['path']).expanduser().resolve(strict=True))
            if row.get('app') in APP_NAMES and row.get('slot'):
                _slot(row['slot'])
                apps[canonical] = dict(row, path=canonical)
        refs = list(plan.get('interop_sources', []))
        if source_ref and source_ref not in refs: refs.append(source_ref)
        receipts = dict(plan.get('interop_handoffs', {}))
        if token:
            previous = handoff_receipt(library, token, signature)
            if previous and previous['id'] != identity: raise ValueError(tr('Diese Übergabe gehört bereits zu einem anderen Sicherungsplan.'))
            receipts[token] = signature
        schedule = dict(schedule_pending=schedule_interval) if schedule_interval is not None else {}
        library.update(identity, sources=paths, app_sources=list(apps.values()), interop_sources=refs, interop_handoffs=receipts, **schedule)
    return library.get(identity)


def coverage(paths, root=None):
    """Offline plan coverage, not an assertion that a current file is backed up."""
    from tools_data import Library
    base = tools_root(root)
    plans = Library('vault', base).all() if (base/'vault/library.sqlite').is_file() else []
    result = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        candidates = []
        for plan in plans:
            included = lambda sources: any(path == Path(p) or path.is_relative_to(Path(p)) for p in sources)
            if not included(plan.get('sources', [])): continue
            saved = plan.get('backup_sources', [])
            last = plan.get('last_backup', 0) if included(saved) else 0
            changed = bool(last and path.exists() and path.stat().st_mtime > plan.get('backup_started', last))
            candidates.append(dict(id=plan['id'], title=plan['title'], last_backup=last, interval=plan.get('interval',0),
                                   changed=changed, state='changed' if changed else 'last_run' if last else 'planned'))
        result.append(dict(path=str(path), exists=path.exists(), plans=candidates))
    return result


def preflight(plan):
    """Find missing sources and unprotected external project material offline."""
    findings = []
    for path in plan.get('sources', []):
        if not Path(path).exists(): findings.append(dict(path=path, reason='missing'))
    for row in plan.get('app_sources', []):
        if row.get('app') != 'workbench' or not (Path(row['path'])/'library.sqlite').is_file(): continue
        with closing(sqlite3.connect((Path(row['path'])/'library.sqlite').as_uri()+'?mode=ro', uri=True)) as db:
            for title, data in db.execute('SELECT title,data FROM records'):
                for item in json.loads(data).get('resources', []):
                    if item.get('kind') != 'file': continue
                    path = Path(item['target']).expanduser().resolve()
                    reason = 'missing' if not path.exists() else 'uncovered' if not any(
                        path == Path(p) or path.is_relative_to(Path(p)) for p in plan['sources']) else ''
                    if reason: findings.append(dict(path=str(path), reason=reason, project=title))
    return findings


def _slot(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(tr('Ungültiger Pfad im Lumen-Sicherungspaket.'))
    return path


def _stamp(path):
    value = path.stat(follow_symlinks=False)
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _files(source):
    if source.is_symlink(): raise ValueError(tr('Lumen-Datenquellen dürfen keine symbolischen Links sein.'))
    if source.is_file(): return [source]
    found = []
    for base, dirs, files in os.walk(source, followlinks=False):
        for name in dirs+files:
            path = Path(base)/name
            if path.is_symlink(): raise ValueError(tr('Lumen-Daten enthalten einen symbolischen Link. Quelle bitte prüfen.'))
        found.extend(Path(base)/name for name in files if not name.endswith(('.lock', '-wal', '-shm', '-journal')))
    return sorted(found)


def _copy_source(source, target, job):
    paths = _files(source)
    before = {path: _stamp(path) for path in paths}
    databases = set()
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for base, dirs, _ in os.walk(source, followlinks=False):
            for name in dirs: (target/(Path(base)/name).relative_to(source)).mkdir(parents=True, exist_ok=True)
    for path in paths:
        job.check()
        dest = target/path.relative_to(source) if source.is_dir() else target
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise ValueError(tr('Nur reguläre Lumen-Datendateien können gesichert werden.'))
        with path.open('rb') as stream: header = stream.read(16)
        if header == b'SQLite format 3\0':
            databases.add(path)
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as original, closing(sqlite3.connect(dest)) as copy:
                original.backup(copy, pages=128, progress=lambda *_: job.check())
                if copy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError(tr('Lumen-Datenbank konnte nicht konsistent kopiert werden.'))
        else:
            with path.open('rb') as src, dest.open('xb') as dst:
                while chunk := src.read(1024*1024): job.check(); dst.write(chunk)
            shutil.copystat(path, dest)
        dest.chmod(0o600)
    after = _files(source)
    if set(after) != set(paths) or any(_stamp(path) != before[path] for path in paths if path not in databases):
        raise ValueError(tr('Lumen-Dateien wurden während der Vorbereitung geändert. Erneut sichern.'))


@contextmanager
def prepared_sources(plan, job, root=None):
    """Online SQLite copies and stable saved files; temporary plaintext is removed."""
    covered = lambda value: any(Path(value) == Path(p) or Path(value).is_relative_to(Path(p)) for p in plan['sources'])
    rows = {row['path']: row for row in plan.get('app_sources', []) if covered(row['path'])}
    if root is not None:
        for row in discover_sources(root):
            if covered(row['path']): rows.setdefault(row['path'], row)
    rows = list(rows.values())
    if not rows:
        yield plan['sources'], [], None
        return
    with tempfile.TemporaryDirectory(prefix='lumen-app-snapshot-') as temporary:
        bundle = Path(temporary)/'Lumen-Anwendungen'
        bundle.mkdir(mode=0o700)
        slots = set()
        for row in rows:
            slot = _slot(row['slot'])
            if str(slot) in slots: raise ValueError(tr('Mehrere Lumen-Quellen verwenden denselben Sicherungsplatz.'))
            slots.add(str(slot))
            if row.get('kind') == 'inbox-local':
                from interop_inbox_backup import export_package
                export_package(Path(row['path']), bundle/slot, job)
            else: _copy_source(Path(row['path']), bundle/slot, job)
        originals = [row['path'] for row in rows]
        ordinary = [path for path in plan['sources'] if path not in originals]
        manifest = dict(version=1, created=time.time(), consistency='committed-databases-and-saved-files', sources=rows, files=ordinary,
                        flushes=plan.get('flush_acknowledgements', []))
        (bundle/MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        yield [*ordinary, str(bundle)], originals, manifest


def restored_bundles(directory):
    """Inspect only bounded manifests below a newly restored directory."""
    root = Path(directory).resolve(strict=True)
    bundles = []
    examined = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(base)/name).is_symlink()]
        examined += len(dirs)+len(names)
        if examined > 100000: break
        if MANIFEST not in names: continue
        path = Path(base)/MANIFEST
        if path.is_symlink() or path.stat().st_size > 512*1024: continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('version') != 1 or not isinstance(value.get('sources'), list): continue
            rows = []
            for row in value['sources'][:100]:
                if row.get('app') not in APP_NAMES: continue
                relative = _slot(row['slot']); restored = Path(base)/relative
                if not restored.exists() or not restored.resolve().is_relative_to(Path(base).resolve()): continue
                if any(parent.is_symlink() for parent in [restored, *list(restored.parents)[:-1]]): continue
                rows.append(dict(row, restored=str(restored)))
            external = []
            for original in value.get('files', [])[:100]:
                original = Path(original)
                if not original.is_absolute() or '..' in original.parts: continue
                restored = root/str(original).lstrip('/')
                if restored.exists() and restored.resolve().is_relative_to(root):
                    external.append(dict(path=str(original), restored=str(restored)))
            if rows: bundles.append(dict(root=str(Path(base)), sources=rows, external=external, restore_root=str(root)))
        except (ValueError, KeyError, TypeError, OSError): continue
    return bundles


def open_restored(bundle, app):
    """Open the recovered workspace, never replace currently running app data."""
    import subprocess
    import sys
    if app not in APP_NAMES or app == 'interop': raise ValueError(tr('Diese Lumen-Daten haben kein eigenes Fenster.'))
    base = Path(bundle['root']).resolve(strict=True)
    # Re-read and validate the metadata at the moment of opening.
    matches = [entry for entry in restored_bundles(bundle.get('restore_root', base)) if entry['root'] == str(base)]
    if not matches or not any(r['app'] == app and r.get('kind') != 'inbox-local' for r in matches[0]['sources']):
        raise ValueError(tr('Keine geprüfte Anwendungskopie gefunden.'))
    relocate_restored(matches[0])
    if app == 'wissen':
        from lumen_store import Store
        state = Store(base/'state')
        notebook = base/'notebook'
        if notebook.is_dir():
            state.set_setting('knowledge/notebook', str(notebook))
            identity = notebook.stat(); state.set_setting('knowledge/identity', [identity.st_dev, identity.st_ino])
    if app == 'sound':
        from tools_data import Library
        library = Library('sound', base/'tools')
        for record in library.all():
            library.update(record['id'], mode='off', applied={}, overrides=[], heartbeat=0)
    environment = dict(os.environ, LUMEN_TOOLS_DATA=str(base/'tools'), LUMEN_DATA=str(base/'state'))
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name('tools_app.py')), app],
                            env=environment, start_new_session=True)


def relocate_restored(bundle):
    """Rebind only structured paths in copies; opaque Lumen object IDs survive."""
    import hashlib
    boundary = Path(bundle.get('restore_root', bundle['root'])).resolve(strict=True)
    mappings = []
    for row in bundle['sources']+bundle.get('external', []):
        original = Path(row['path']); restored = Path(row['restored'])
        if not original.is_absolute() or '..' in original.parts or not restored.is_absolute() or '..' in restored.parts:
            raise ValueError(tr('Ungültiger Pfad im Lumen-Sicherungspaket.'))
        if not restored.resolve().is_relative_to(boundary) or any(path.is_symlink() for path in (restored, *restored.parents)):
            raise ValueError(tr('Ungültiger Pfad im Lumen-Sicherungspaket.'))
        mappings.append((original, restored))
    mappings.sort(key=lambda pair: len(pair[0].parts), reverse=True)
    def moved(value):
        if not isinstance(value, str) or not Path(value).is_absolute(): return value
        normalized = Path(os.path.normpath(value))
        for original, restored in mappings:
            if normalized.is_relative_to(original): return str(restored/normalized.relative_to(original))
        return value
    for row in bundle['sources']:
        if row.get('kind') != 'library': continue
        dbpath = Path(row['restored'])/'library.sqlite'
        if not dbpath.is_file(): continue
        with closing(sqlite3.connect(dbpath)) as db, db:
            if row['app'] == 'workbench':
                for key, data in db.execute('SELECT id,data FROM records').fetchall():
                    record = json.loads(data)
                    for resource in record.get('resources', []):
                        if resource.get('kind') == 'file': resource['target'] = moved(resource.get('target'))
                    db.execute('UPDATE records SET data=? WHERE id=?', (json.dumps(record), key))
            elif row['app'] == 'interop':
                for key, data in db.execute('SELECT id,data FROM objects').fetchall():
                    ref = json.loads(data)
                    if ref.get('path'): ref['path'] = moved(ref['path'])
                    if ref.get('kind') == 'file': ref['id'] = moved(ref.get('id'))
                    if ref.get('locator', {}).get('root'): ref['locator']['root'] = moved(ref['locator']['root'])
                    identity = hashlib.sha256(json.dumps({k: ref.get(k) for k in ('app','kind','id','locator')}, sort_keys=True).encode()).hexdigest()
                    db.execute('UPDATE objects SET data=?,identity=? WHERE id=?', (json.dumps(ref), identity, key))


def show_restored(window, directory):
    """Called exclusively by the successful, verified native restore callback."""
    from PySide6.QtWidgets import QDialog, QFormLayout, QComboBox, QDialogButtonBox
    from tools_ui import label, button, open_path
    bundles = restored_bundles(directory)
    if not bundles: open_path(directory); return
    dialog = QDialog(window); dialog.setWindowTitle(tr('Lumen-Anwendungen wiederhergestellt'))
    form = QFormLayout(dialog)
    form.addRow(label(tr('Die geprüften Kopien liegen im neuen Wiederherstellungsordner. Du kannst sie getrennt öffnen und vergleichen. Deine bisherigen Daten bleiben erhalten.')))
    applications = QComboBox()
    for bundle in bundles:
        for app in sorted({row['app'] for row in bundle['sources'] if row.get('kind') != 'inbox-local'} - {'interop'}):
            applications.addItem(tr(APP_NAMES[app]), (bundle, app))
    form.addRow(tr('Wiederhergestellte Anwendung'), applications)
    def launch():
        bundle, app = applications.currentData()
        window.safe(open_restored, bundle, app)
    opener=button(tr('Wiederhergestellte Kopie öffnen'), launch); opener.setEnabled(applications.count()>0); form.addRow(opener)
    if any(row.get('kind') == 'notebook' for bundle in bundles for row in bundle['sources']):
        form.addRow(button(tr('Notiz vergleichen und übernehmen'), lambda: window.safe(show_note_comparison, window, directory)))
    if any(row.get('kind') == 'inbox-local' for bundle in bundles for row in bundle['sources']):
        from interop_inbox_backup import show_restore
        form.addRow(button(tr('Lokale Aufgaben und Entwürfe übernehmen'), lambda: window.safe(show_restore, window, directory)))
    form.addRow(button(tr('Wiederherstellungsordner öffnen'), lambda: open_path(directory)))
    form.addRow(label(tr('Gesichert sind gespeicherte Dateien und bestätigte Datenbankänderungen. Verweise auf externe Originaldateien können eine erneute Zuordnung benötigen. Audioregeln starten ausgeschaltet.')))
    buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, dialog.exec)


def receive_sources(window, payload, root=None, store=None, done=None, entries=None, token=None):
    """Review in the activated Vault window. False=cancel, True=accepted.

    done(ref) reports durable success; done(None) reports asynchronous failure.
    Creating a new plan retains the existing native password/target flow.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QFormLayout, QComboBox, QListWidget, QListWidgetItem, QDialogButtonBox, QCheckBox
    from tools_ui import label
    root = root or window.library.root.parent
    if window.job: raise ValueError(tr('Lumen Vault arbeitet bereits. Übergabe anschließend erneut öffnen.'))
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    def finished(identity):
        if done:
            done(dict(app='vault', id=identity, kind='record', title=window.library.get(identity)['title']) if identity else None)
    def activate(identity):
        import vault_data
        window.focus_record(identity)
        interval=window.library.get(identity).get('schedule_pending')
        if interval is None:finished(identity);return True
        def complete(_):
            window.focus_record(identity);finished(identity)
        return window.work(tr('Zeitplan wird eingerichtet …'),lambda job:vault_data.schedule(window.library,identity,interval,job),complete,
                           failed=lambda _:finished(None))
    recovered = handoff_receipt(window.library, token, signature)
    if recovered:
        return activate(recovered['id'])
    rows = entries if entries is not None else payload_sources(payload, root, store)
    dialog = QDialog(window); dialog.setWindowTitle(tr('Sicherung einrichten')); dialog.resize(680, 480)
    form = QFormLayout(dialog)
    form.addRow(label(tr('Wähle die gespeicherten Daten, die ein Sicherungsplan künftig erfassen soll. Dadurch wird noch keine Sicherung gestartet.')))
    listing = QListWidget(); listing.setAccessibleName(tr('Lumen-Daten für den Sicherungsplan'))
    for entry in rows:
        item = QListWidgetItem(entry['title']+'\n'+entry['path']+(tr(' · Datei fehlt') if entry.get('missing') else '')); item.setData(Qt.UserRole, entry)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Unchecked if entry.get('missing') else Qt.Checked)
        if entry.get('missing'): item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
        listing.addItem(item)
    form.addRow(listing)
    local_inbox = QCheckBox(tr('Lumen Inbox: nur lokale Aufgaben und ungesendete Entwürfe mit Anhängen sichern'))
    local_inbox.setChecked(payload.get('source', {}).get('app') == 'inbox' and payload.get('source', {}).get('kind') in ('task', 'draft'))
    if any(row.get('app') == 'inbox' for row in rows): form.addRow(local_inbox)
    plans = QComboBox()
    plans.addItem(tr('Neuen Sicherungsplan einrichten'), '')
    for plan in window.library.all(): plans.addItem(plan['title'], plan['id'])
    if window.current and plans.findData(window.current) >= 0: plans.setCurrentIndex(plans.findData(window.current))
    form.addRow(tr('Sicherungsplan'), plans)
    interval=QComboBox();interval.setAccessibleName(tr('Sicherungsrhythmus'))
    for caption,value in [(tr('Nur manuell'),0),(tr('Täglich'),86400),(tr('Wöchentlich'),604800)]:interval.addItem(caption,value)
    form.addRow(tr('Zeitplan'),interval)
    def update_interval():
        identity=plans.currentData();interval.setEnabled(bool(identity))
        interval.setCurrentIndex(interval.findData(window.library.get(identity).get('interval',0)) if identity else 0)
        interval.setToolTip('' if identity else tr('Den Zeitplan wählst du zusammen mit dem Sicherungsziel im nächsten Schritt.'))
    plans.currentIndexChanged.connect(update_interval);update_interval()
    form.addRow(label(tr('Lumen Vault kopiert geöffnete Datenbanken konsistent. Ungespeicherte Änderungen in anderen Fenstern sind noch nicht enthalten.')))
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
    if dialog.exec() != QDialog.Accepted: return False
    chosen = [listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked]
    if not chosen: raise ValueError(tr('Mindestens eine Quelle auswählen.'))
    if local_inbox.isChecked():
        chosen = [dict(row, kind='inbox-local', slot='inbox-local', title=tr('Lumen Inbox · lokale Aufgaben und Entwürfe')) if row.get('app') == 'inbox' else row for row in chosen]
    identity = plans.currentData()
    if identity:
        rhythm=interval.currentData()
        changed=rhythm if rhythm!=window.library.get(identity).get('interval',0) else None
        merge_sources(window.library, identity, chosen, payload.get('source_url'), token, signature, schedule_interval=changed)
        window.status.setText(tr('Quellen im Sicherungsplan ergänzt. Zum Sichern „Jetzt sichern“ wählen.'))
        return activate(identity)
    return bool(window.create(prefill_sources=chosen, on_done=finished, source_ref=payload.get('source_url'),
                              handoff={token: signature} if token else None))


send_to_vault = receive_sources


def note_comparison(restored_note, restored_notebook, store):
    """Read both saved versions for a review; the returned hash guards later import."""
    from wissen_data import Notebook, parse, MAX_NOTE
    root = Path(restored_notebook).absolute(); path = Path(restored_note).absolute()
    if not path.is_relative_to(root) or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError(tr('Notiz außerhalb der wiederhergestellten Kopie.'))
    relative = str(path.relative_to(root)); book = Notebook(store)
    book.relative(relative)
    with path.open('rb') as source: raw = source.read(MAX_NOTE+1)
    if len(raw) > MAX_NOTE: raise ValueError(tr('Notiz größer als 1 MiB.'))
    recovered = parse(relative, raw)
    try: current = book.read(relative)
    except FileNotFoundError: current = dict(text='', hash='', title=recovered['title'])
    return dict(path=relative, current=current, recovered=recovered, notebook=str(book.root), restored_root=str(root), restored_path=str(path))


def import_restored_note(comparison, store, expected, job):
    """Import the reviewed text/images with Notebook's compare-and-write guard."""
    import re
    from urllib.parse import unquote, urlsplit
    from wissen_data import Notebook, digest
    book = Notebook(store)
    if str(book.root) != comparison['notebook']:
        raise ValueError(tr('Der aktive Notizordner hat sich geändert. Vergleich erneut öffnen.'))
    fresh = note_comparison(comparison['restored_path'], comparison['restored_root'], store)
    if fresh['recovered']['hash'] != comparison['recovered']['hash']:
        raise ValueError(tr('Die wiederhergestellte Notiz wurde geändert. Vergleich erneut öffnen.'))
    recovered = fresh['recovered']; relative = fresh['path']; root = Path(fresh['restored_root'])
    expression = re.compile(r'!\[[^\]\n]*\]\(([^)\n]+)\)')
    targets = list(dict.fromkeys(expression.findall(recovered['text'])))
    if len(targets) > 32: raise ValueError(tr('Notiz enthält mehr als 32 Bilder. Bitte einzeln übernehmen.'))
    created = []; replacements = {}
    try:
        # Fail before image work if the comparison is already obsolete.
        try: current_hash = digest(book.raw(relative))
        except FileNotFoundError: current_hash = ''
        if current_hash != expected:
            raise ValueError(tr('Die aktuelle Notiz wurde seit dem Vergleich geändert. Vergleich erneut öffnen.'))
        for target in targets:
            job.check(); parsed = urlsplit(target)
            if parsed.scheme in ('http', 'https'): continue
            if parsed.scheme or parsed.netloc:
                raise ValueError(tr('Notizbild liegt außerhalb des wiederhergestellten Notizordners.'))
            local = root/os.path.normpath(str(Path(relative).parent/unquote(target)))
            if not local.is_relative_to(root) or '..' in local.parts or any(p.is_symlink() for p in (local, *local.parents)):
                raise ValueError(tr('Notizbild liegt außerhalb des wiederhergestellten Notizordners.'))
            copied = book.add_image(local); created.append(copied)
            replacements[target] = os.path.relpath(copied, str(Path(relative).parent))
        text = expression.sub(lambda match: match.group(0).replace('('+match[1]+')', '('+replacements.get(match[1], match[1])+')'), recovered['text'])
        job.check()
        result = book.write(relative, text, expected, source=recovered.get('source', ''), legacy=recovered.get('legacy', ''), created=recovered.get('created', 0))
        return dict(app='wissen', kind='note', id=relative, title=result['title'], path=str(book.root/relative), locator=dict(root=str(book.root)))
    except BaseException:
        for relative in created:
            path = Path(relative)
            with book.directory(path.parent) as parent:
                try: os.unlink(path.name, dir_fd=parent)
                except FileNotFoundError: pass
        raise


def show_note_comparison(parent, directory, store=None):
    from lumen_store import Store
    from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QDialogButtonBox, QFileDialog,
        QMessageBox)
    from tools_ui import label, button
    notebooks = [row['restored'] for bundle in restored_bundles(directory) for row in bundle['sources'] if row.get('kind') == 'notebook']
    if not notebooks: raise ValueError(tr('Keine wiederhergestellten Lumen-Notizen gefunden.'))
    path, _ = QFileDialog.getOpenFileName(parent, tr('Wiederhergestellte Notiz vergleichen'), notebooks[0], tr('Markdown-Notizen (*.md)'))
    if not path: return
    notebook = next((root for root in notebooks if Path(path).absolute().is_relative_to(Path(root))), None)
    if not notebook: raise ValueError(tr('Notiz außerhalb der wiederhergestellten Kopie.'))
    store = store or Store(); comparison = note_comparison(path, notebook, store)
    dialog = QDialog(parent); dialog.setWindowTitle(tr('Lumen Wissen · Notizvergleich')); dialog.resize(1080, 650)
    layout = QVBoxLayout(dialog); layout.addWidget(label(comparison['path']))
    columns = QHBoxLayout()
    for title, text in ((tr('Aktuell gespeichert'), comparison['current']['text']), (tr('Wiederhergestellte Fassung'), comparison['recovered']['text'])):
        column = QVBoxLayout(); column.addWidget(label(title)); editor = QPlainTextEdit(); editor.setReadOnly(True); editor.setPlainText(text); editor.setAccessibleName(title); column.addWidget(editor); columns.addLayout(column)
    layout.addLayout(columns)
    layout.addWidget(label(tr('Beim Übernehmen werden lokale Bilder kopiert. Eine inzwischen geänderte Notiz wird nicht überschrieben; die bisherige Fassung bleibt im Lumen-Wissen-Verlauf.')))
    def apply():
        def done(_):
            QMessageBox.information(dialog, tr('Lumen Wissen'), tr('Die geprüfte Notizfassung wurde übernommen.')); dialog.accept()
        _run_job(dialog, tr('Notiz und Bilder werden übernommen …'),
                 lambda job: import_restored_note(comparison, store, comparison['current']['hash'], job), done)
    layout.addWidget(button(tr('Geprüfte Fassung übernehmen'), apply))
    buttons = QDialogButtonBox(QDialogButtonBox.Cancel); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    dialog.exec()


def file_versions(library, identity, path, job, offset=0, limit=20):
    """Inspect actual snapshot nodes and capsule mappings in a verified repository."""
    import vault_data
    path = Path(path).expanduser().resolve()
    if offset < 0 or not 1 <= limit <= 50: raise ValueError(tr('Ungültiger Bereich für Sicherungsstände.'))
    snapshots = list(reversed(vault_data.run(library, identity, 'snapshots', job)))
    result = []
    for snapshot in snapshots[offset:offset+limit]:
        job.check()
        job.progress.emit(tr('Dateiversion wird geprüft: {0}', snapshot['time'][:19]))
        nodes = vault_data.run(library, identity, 'files', job, snapshot=snapshot['id'])
        by_path = {node['path']: node for node in nodes if node.get('type') == 'file'}
        candidates = {str(path)}
        for name in by_path:
            if Path(name).name != MANIFEST or Path(name).parent.name != 'Lumen-Anwendungen': continue
            try: manifest = vault_data.run(library, identity, 'manifest', job, snapshot=snapshot['id'], selected=name)
            except json.JSONDecodeError: continue
            if not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(manifest.get('sources'), list): continue
            for source in manifest.get('sources', [])[:100]:
                try:
                    original = Path(source['path']); slot = _slot(source['slot'])
                    if original.is_absolute() and path.is_relative_to(original):
                        relative = path.relative_to(original)
                        if source.get('kind') == 'inbox-local':
                            if len(relative.parts) == 2 and relative.parts[0] == 'assets':
                                candidates.add(str(Path(name).parent/slot/'attachments'/relative.name))
                        else: candidates.add(str(Path(name).parent/slot/relative))
                except (TypeError, ValueError, KeyError): continue
        for saved in sorted(candidates & by_path.keys()):
            result.append(dict(snapshot=snapshot['id'], time=snapshot['time'], path=saved,
                               plan=identity, size=by_path[saved].get('size', 0)))
    return dict(versions=result, total=len(snapshots), scanned=min(limit, max(0, len(snapshots)-offset)),
                next_offset=offset+limit if offset+limit < len(snapshots) else None)


def _run_job(parent, title, function, done):
    """A modal cancellable job also usable from Files, which has no ToolWindow.work."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QProgressDialog, QMessageBox
    from tools_ui import Job
    dialog = QProgressDialog(title, tr('Abbrechen'), 0, 0, parent)
    dialog.setWindowTitle(tr('Lumen Vault')); dialog.setWindowModality(Qt.WindowModal); dialog.setMinimumDuration(0)
    job = Job(function, dialog); result = {}
    dialog.canceled.connect(job.cancelled.set); job.progress.connect(dialog.setLabelText)
    job.result.connect(lambda value: result.update(value=value)); job.failed.connect(lambda error: result.update(error=error))
    def finished():
        dialog.close(); job.deleteLater()
        def complete():
            if 'error' in result:
                if result['error'] != 'Abgebrochen': QMessageBox.warning(parent, tr('Lumen Vault'), result['error'])
            else: done(result.get('value'))
            dialog.deleteLater()
        QTimer.singleShot(0, complete)
    job.finished.connect(finished); dialog.show(); job.start()
    return job


def show_file_versions(parent, path, root=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QDialog, QFormLayout, QComboBox, QListWidget, QListWidgetItem, QDialogButtonBox,
        QFileDialog, QMessageBox)
    from tools_data import Library
    from tools_ui import label, button
    base = tools_root(root or (parent.library.root.parent if hasattr(parent, 'library') else None))
    if not (base/'vault/library.sqlite').is_file():
        QMessageBox.information(parent, tr('Lumen Vault'), tr('Noch kein Sicherungsplan vorhanden.')); return
    library = Library('vault', base)
    dialog = QDialog(parent); dialog.setWindowTitle(tr('Dateiversionen in Lumen Vault')); dialog.resize(760, 520)
    form = QFormLayout(dialog); form.addRow(label(str(path)))
    plans = QComboBox()
    selected_path = Path(path).expanduser().resolve()
    def relevance(plan):
        return not any(selected_path == Path(value) or selected_path.is_relative_to(Path(value))
                       for value in plan.get('sources', [])+plan.get('backup_sources', []))
    for plan in sorted(library.all(), key=relevance): plans.addItem(plan['title'], plan['id'])
    form.addRow(tr('Sicherungsplan'), plans)
    listing = QListWidget(); listing.setAccessibleName(tr('Geprüfte Sicherungsversionen der Datei')); form.addRow(listing)
    status = label(tr('Der Sicherungsdatenträger wird erst beim Laden geöffnet.')); form.addRow(status)
    cursor = dict(offset=0, plan='')
    def load():
        identity = plans.currentData()
        if not identity: return
        if cursor['plan'] != identity: cursor.update(offset=0, plan=identity); listing.clear()
        if cursor['offset'] is None: return
        def loaded(value):
            for version in value['versions']:
                item = QListWidgetItem(version['time'][:19].replace('T', ' ')+' · '+str(version['size'])+' B')
                item.setData(Qt.UserRole, version); listing.addItem(item)
            cursor['offset'] = value['next_offset']
            status.setText(tr('{0} passende Dateiversionen gefunden.', listing.count()))
            more.setEnabled(value['next_offset'] is not None)
        _run_job(dialog, tr('Sicherungsstände werden nach dieser Datei durchsucht …'),
                 lambda job: file_versions(library, identity, path, job, offset=cursor['offset']), loaded)
    more = button(tr('Weitere Sicherungsstände laden'), load)
    plans.currentIndexChanged.connect(lambda _: more.setEnabled(True))
    form.addRow(more)
    def restore():
        item = listing.currentItem()
        if not item: return
        selected = item.data(Qt.UserRole)
        target = QFileDialog.getExistingDirectory(dialog, tr('Wiederherstellung: übergeordneten Zielordner wählen'), str(Path.home()))
        if not target: return
        import vault_data
        _run_job(dialog, tr('Daten werden in einen neuen Ordner wiederhergestellt …'),
                 lambda job: vault_data.run(library, selected['plan'], 'restore', job, snapshot=selected['snapshot'],
                                           selected=selected['path'], destination=target), lambda restored: show_restored(parent, restored))
    form.addRow(button(tr('Gewählte Dateiversion wiederherstellen'), restore))
    buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
    dialog.exec()
