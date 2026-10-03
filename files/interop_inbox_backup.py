"""Selective local Inbox recovery packages: tasks, unsent drafts and attachments.

No accounts, raw messages, calendars or keyring data enter the package. Drafts
can only be imported after a local destination account has been reviewed.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from lumen_i18n import tr

PACKAGE = 'lumen-inbox-local.json'
MAX_ITEMS = 5000
MAX_PACKAGE = 32*1024*1024


def _text(value, limit=120000):
    if not isinstance(value, str) or len(value) > limit or '\0' in value:
        raise ValueError(tr('Ungültiger Text im lokalen Inbox-Sicherungspaket.'))
    return value


def _asset(directory, name):
    if not isinstance(name, str) or not name or Path(name).name != name or name in ('.', '..'):
        raise ValueError(tr('Ungültiger Anhang im lokalen Inbox-Sicherungspaket.'))
    path = Path(directory)/name
    if not path.is_file() or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError(tr('Ein Entwurfsanhang fehlt.'))
    return path


def export_package(source, target, job):
    """Read one committed transaction using explicit field projections only."""
    from interop_vault import _copy_source
    source = Path(source); target = Path(target); target.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (source/'library.sqlite').is_file() or any(p.is_symlink() for p in (source, source/'library.sqlite', *source.parents)):
        raise ValueError(tr('Lumen-Inbox-Datenbank nicht erreichbar.'))
    tasks = []; drafts = []; copied = {}; total_json = 0
    with closing(sqlite3.connect((source/'library.sqlite').absolute().as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row; db.execute('BEGIN')
        if db.execute("SELECT 1 FROM drafts WHERE status='draft' AND NOT json_valid(data) LIMIT 1").fetchone():
            raise ValueError(tr('Ein lokaler Entwurf ist beschädigt. Lumen Inbox vor der Sicherung prüfen.'))
        has_details=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='interop_task_details'").fetchone()
        detail="COALESCE((SELECT body FROM interop_task_details WHERE task=tasks.id),'')" if has_details else "''"
        for row in db.execute('SELECT substr(id,1,4097) AS id,substr(title,1,4097) AS title,substr(due,1,4097) AS due,substr(source,1,4097) AS source,done,substr('+detail+',1,120001) AS body FROM tasks LIMIT ?', (MAX_ITEMS+1,)):
            job.check(); tasks.append(dict(row)); total_json += len(json.dumps(dict(row)).encode())
            if total_json>MAX_PACKAGE:raise ValueError(tr('Lokales Inbox-Sicherungspaket ist zu groß.'))
        columns = ','.join("substr(json_extract(data,'$."+field+"'),1,"+('512001' if field in ('attachments','interop_sources') else '120001')+") AS "+field for field in ('to', 'subject', 'body', 'reply_to', 'attachments', 'interop_sources'))
        columns+=",json_extract(data,'$.formatted') AS formatted"
        # Quote the field named 'to', which is an SQL keyword.
        columns = columns.replace(' AS to,', ' AS "to",')
        for row in db.execute("SELECT id,"+columns+" FROM drafts WHERE status='draft' AND json_valid(data) LIMIT ?", (MAX_ITEMS+1,)):
            job.check()
            values = {key: row[key] or '' for key in ('to', 'subject', 'body', 'reply_to')}
            values['formatted']=row['formatted']==1
            attachments = json.loads(row['attachments'] or '[]')
            if not isinstance(attachments, list) or len(attachments) > 100: raise ValueError(tr('Ungültige Entwurfsanhänge.'))
            values['attachments'] = []; total = 0
            for item in attachments:
                path = _asset(source/'assets', item.get('asset')); total += path.stat().st_size
                if total > 12*1024**2: raise ValueError(tr('Anhänge zusammen größer als 12 MiB.'))
                if path.name not in copied:
                    _copy_source(path, target/'attachments'/path.name, job)
                    with (target/'attachments'/path.name).open('rb') as saved:copied[path.name]=hashlib.file_digest(saved,'sha256').hexdigest()
                values['attachments'].append(dict(asset=path.name, name=_text(item.get('name'), 1000), sha256=copied[path.name]))
            values['interop_sources'] = json.loads(row['interop_sources'] or '[]')
            draft=dict(id=row['id'], data=values);total_json+=len(json.dumps(draft).encode())
            if total_json>MAX_PACKAGE:raise ValueError(tr('Lokales Inbox-Sicherungspaket ist zu groß.'))
            drafts.append(draft)
    if len(tasks)+len(drafts) > MAX_ITEMS: raise ValueError(tr('Mehr als 5.000 lokale Inbox-Einträge. Sicherung bitte aufteilen.'))
    value = dict(version=1, created=time.time(), tasks=tasks, drafts=drafts)
    raw = json.dumps(value, ensure_ascii=False).encode()
    if len(raw) > MAX_PACKAGE: raise ValueError(tr('Lokales Inbox-Sicherungspaket ist zu groß.'))
    path = target/PACKAGE
    with path.open('xb') as output: os.chmod(path, 0o600); output.write(raw)
    read_package(target)
    return dict(tasks=len(tasks), drafts=len(drafts))


def read_package(directory):
    directory = Path(directory); path = _asset(directory, PACKAGE)
    if path.stat().st_size > MAX_PACKAGE: raise ValueError(tr('Lokales Inbox-Sicherungspaket ist zu groß.'))
    with path.open('rb') as source: raw = source.read(MAX_PACKAGE+1)
    if len(raw)>MAX_PACKAGE:raise ValueError(tr('Lokales Inbox-Sicherungspaket ist zu groß.'))
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('tasks'), list) or not isinstance(value.get('drafts'), list):
        raise ValueError(tr('Ungültiges lokales Inbox-Sicherungspaket.'))
    if len(value['tasks'])+len(value['drafts']) > MAX_ITEMS: raise ValueError(tr('Mehr als 5.000 lokale Inbox-Einträge. Sicherung bitte aufteilen.'))
    for row in value['tasks']:
        for field in ('id', 'title', 'due', 'source'): _text(row.get(field), 4096)
        _text(row.get('body',''))
        if row.get('done') not in (0, 1): raise ValueError(tr('Ungültiger Aufgabenstatus.'))
    for row in value['drafts']:
        _text(row.get('id'), 4096); data = row.get('data', {})
        for field in ('to', 'subject', 'body', 'reply_to'): _text(data.get(field))
        if type(data.get('formatted',False)) is not bool:raise ValueError(tr('Ungültiges Entwurfsformat im Sicherungspaket.'))
        attachments = data.get('attachments', [])
        if not isinstance(attachments, list) or len(attachments) > 100: raise ValueError(tr('Ungültige Entwurfsanhänge.'))
        total = 0
        for item in attachments:
            _text(item.get('name'), 1000); total += _asset(directory/'attachments', item.get('asset')).stat().st_size
            if not isinstance(item.get('sha256'),str) or len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):raise ValueError(tr('Ungültige Prüfsumme für einen Entwurfsanhang.'))
        if total > 12*1024**2: raise ValueError(tr('Anhänge zusammen größer als 12 MiB.'))
        if not isinstance(data.get('interop_sources', []), list) or any(not isinstance(v, str) or len(v)>4096 for v in data.get('interop_sources', [])):
            raise ValueError(tr('Ungültige Herkunftsangabe.'))
    return value, hashlib.sha256(raw).hexdigest()


def import_package(directory, library, account, job, include_tasks=True, include_drafts=True, expected=''):
    """Copy into reviewed live Inbox with new IDs; repeated imports are idempotent."""
    from inbox_data import draft_attachments
    value, digest = read_package(directory)
    if expected and digest != expected: raise ValueError(tr('Das Sicherungspaket wurde seit der Prüfung verändert. Erneut öffnen.'))
    created = []; refs = []; counts = dict(tasks=0, drafts=0)
    try:
        with library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if include_drafts and value['drafts']:
                row = db.execute("SELECT json_extract(data,'$.kind') FROM records WHERE id=? AND archived=0", (account,)).fetchone()
                if not row or row[0] not in ('imap', 'bridge'): raise ValueError(tr('Ein Zielkonto für die wiederhergestellten Entwürfe auswählen.'))
            db.execute('CREATE TABLE IF NOT EXISTS local_restore_receipts(package TEXT, kind TEXT, original TEXT, restored TEXT, PRIMARY KEY(package,kind,original))')
            db.execute('CREATE TABLE IF NOT EXISTS interop_task_details(task TEXT PRIMARY KEY,body TEXT NOT NULL)')
            for kind, rows in (('task', value['tasks'] if include_tasks else []), ('draft', value['drafts'] if include_drafts else [])):
                for item in rows:
                    job.check()
                    receipt = digest+(':'+account if kind=='draft' else '')
                    previous = db.execute('SELECT restored FROM local_restore_receipts WHERE package=? AND kind=? AND original=?', (receipt, kind, item['id'])).fetchone()
                    if previous and not db.execute('SELECT 1 FROM '+('tasks' if kind=='task' else 'drafts')+' WHERE id=?', (previous[0],)).fetchone():previous=None
                    key = previous[0] if previous else uuid.uuid4().hex
                    if not previous:
                        if kind == 'task':
                            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?)', (key, item['title'], item['due'], item['source'], item['done']))
                            if item.get('body'):db.execute('INSERT INTO interop_task_details VALUES (?,?)',(key,item['body']))
                        else:
                            data = {field: item['data'][field] for field in ('to','subject','body','reply_to')}
                            data['formatted']=item['data'].get('formatted',False)
                            data['interop_sources'] = item['data'].get('interop_sources', [])
                            data['attachments'] = []
                            for attachment in item['data']['attachments']:
                                saved = library.import_file(_asset(Path(directory)/'attachments', attachment['asset']), job, limit=12*1024**2)
                                copied=library.asset(saved['asset']);created.append(copied)
                                with copied.open('rb') as content:
                                    if hashlib.file_digest(content,'sha256').hexdigest()!=attachment['sha256']:raise ValueError(tr('Ein Entwurfsanhang wurde seit der Sicherung verändert.'))
                                saved['name'] = attachment['name']; data['attachments'].append(saved)
                            data['attachments'] = draft_attachments(library, data['attachments'])
                            db.execute('INSERT INTO drafts VALUES (?,?,?,?)', (key, account, json.dumps(data), 'draft'))
                        db.execute('INSERT OR REPLACE INTO local_restore_receipts VALUES (?,?,?,?)', (receipt, kind, item['id'], key))
                        counts['tasks' if kind == 'task' else 'drafts'] += 1
                    refs.append(dict(app='inbox', kind=kind, id=key, title=item['title'] if kind == 'task' else item['data']['subject']))
            job.check()
        return dict(counts, refs=refs)
    except BaseException:
        for path in created: path.unlink(missing_ok=True)
        raise


def show_restore(parent, directory, root=None):
    from PyQt5.QtWidgets import QDialog, QFormLayout, QComboBox, QCheckBox, QDialogButtonBox, QMessageBox, QInputDialog
    from interop_vault import restored_bundles, tools_root, _run_job
    from inbox_data import store
    from tools_ui import label, button
    packages = [row['restored'] for bundle in restored_bundles(directory) for row in bundle['sources'] if row.get('kind') == 'inbox-local']
    if not packages: raise ValueError(tr('Keine lokalen Inbox-Sicherungspakete gefunden.'))
    package = packages[0]
    if len(packages)>1:
        package,accepted=QInputDialog.getItem(parent,tr('Lokales Inbox-Sicherungspaket auswählen'),tr('Wiederhergestelltes Paket'),packages,0,False)
        if not accepted:return
    data, digest = read_package(package)
    base = tools_root(root or (parent.library.root.parent if hasattr(parent, 'library') else None))
    library = store(base)
    dialog = QDialog(parent); dialog.setWindowTitle(tr('Lumen Inbox · lokale Daten wiederherstellen')); form = QFormLayout(dialog)
    form.addRow(label(tr('{0} Aufgaben und {1} ungesendete Entwürfe gefunden. Bestehende Einträge bleiben erhalten.', len(data['tasks']), len(data['drafts']))))
    tasks = QCheckBox(tr('Lokale Aufgaben übernehmen')); tasks.setChecked(bool(data['tasks'])); tasks.setEnabled(bool(data['tasks'])); form.addRow(tasks)
    drafts = QCheckBox(tr('Ungesendete Entwürfe und Anhänge übernehmen')); drafts.setChecked(bool(data['drafts'])); form.addRow(drafts)
    accounts = QComboBox(); accounts.addItem(tr('Zielkonto auswählen'), '')
    with library.connect() as db:
        for identity, title in db.execute("SELECT id,title FROM records WHERE archived=0 AND json_extract(data,'$.kind') IN ('imap','bridge')"):
            accounts.addItem(title, identity)
    form.addRow(tr('Zielkonto für Entwürfe'), accounts)
    form.addRow(label(tr('Das Paket enthält keine Konten, Zugangsdaten oder Nachrichten. Entwürfe werden dem gewählten vorhandenen Konto zugeordnet und bleiben ungesendet.')))
    if accounts.count()==1:
        drafts.setChecked(False); drafts.setEnabled(False)
        form.addRow(label(tr('Zum Übernehmen von Entwürfen zuerst ein Mailkonto in Lumen Inbox einrichten.')))
    def apply():
        if not tasks.isChecked() and not drafts.isChecked():return
        if drafts.isChecked() and not accounts.currentData():
            QMessageBox.warning(dialog,tr('Lumen Inbox'),tr('Ein Zielkonto für die wiederhergestellten Entwürfe auswählen.'));return
        selected_account=accounts.currentData(); include_tasks=tasks.isChecked(); include_drafts=drafts.isChecked()
        def done(result):
            QMessageBox.information(dialog,tr('Lumen Inbox'),tr('{0} Aufgaben und {1} Entwürfe übernommen.',result['tasks'],result['drafts']))
            dialog.accept()
            if result['refs']:
                from interop_data import Registry
                from interop_ui import launch
                ref=Registry(base).register(result['refs'][0]);launch('inbox',['--ref',ref],base)
        _run_job(dialog,tr('Lokale Inbox-Daten werden übernommen …'),
                 lambda job:import_package(package,library,selected_account,job,include_tasks,include_drafts,expected=digest),done)
    form.addRow(button(tr('Geprüfte Auswahl übernehmen'),apply))
    buttons=QDialogButtonBox(QDialogButtonBox.Cancel);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
    dialog.exec_()
