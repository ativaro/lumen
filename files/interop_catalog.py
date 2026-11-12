"""Bounded, read-only discovery of saved Lumen objects for shared local search."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import unquote, urlsplit
import uuid
from lumen_i18n import tr

MAX_OBJECTS = 5000
MAX_TEXT = 120000
MAX_BYTES = 64*1024*1024
MAX_RECORD = 2*1024*1024
APPS = ('translate', 'reader', 'workbench', 'household', 'meetings', 'radio', 'inbox', 'sound')
URL = re.compile(r'lumen://object/[a-f0-9]{32}(?:\?[^\s\)\]>\"\']+)?')


def _plain(value, limit=MAX_TEXT):
    return value.replace('\0', '')[:limit] if isinstance(value, str) else ''


def _safe_path(path):
    path = Path(path).absolute()
    return not any(item.is_symlink() for item in (path, *path.parents))


def _file_uri(value):
    if not isinstance(value, str): return ''
    parsed = urlsplit(value)
    if parsed.scheme == 'file' and parsed.netloc in ('', 'localhost'):
        path = unquote(parsed.path)
        if Path(path).is_absolute() and '\0' not in path: return path
    return value if not parsed.scheme and Path(value).is_absolute() and '\0' not in value else ''


def _record_text(app, record):
    fields = {
        'translate': ('source', 'result', 'document_name'),
        'reader': ('author', 'subject', 'notes'),
        'workbench': ('notes', 'questions', 'question_draft', 'resources'),
        'household': ('notes', 'manufacturer', 'model', 'serial', 'seller', 'attachments'),
        'meetings': ('summary', 'agenda', 'segments', 'results', 'decisions', 'actions'),
        'radio': ('script', 'sources', 'edition_sources'),
        'sound': ('mode', 'rules'),
    }.get(app, ())
    parts = []
    def add(value):
        if isinstance(value, str): parts.append(value)
        elif isinstance(value, list):
            for item in value[:5000]: add(item)
        elif isinstance(value, dict):
            # Only human-facing fields; never flatten credentials/configuration.
            for key in ('text', 'title', 'name', 'description', 'summary', 'label'):
                if isinstance(value.get(key), str): parts.append(value[key])
    for field in fields: add(record.get(field))
    return _plain('\n'.join(parts))


def _items(record, key):
    value = record.get(key, [])
    return [row for row in value[:100] if isinstance(row, dict)] if isinstance(value, list) else []


class _Limit(Exception):
    pass


class _Index:
    def __init__(self, registry, job):
        self.registry = registry; self.job = job
        self.root = registry.library.root.parent
        self.counts = dict(objects=0, links=0, skipped=0, unresolved=0, limited=False)
        self.bytes = 0; self.seen = set(); self.pending = []; self.run = uuid.uuid4().hex
        with registry.library.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS catalog_objects(url TEXT PRIMARY KEY, run TEXT NOT NULL)')

    def check(self):
        if self.job: self.job.check()
        if self.counts['objects'] >= MAX_OBJECTS or self.bytes >= MAX_BYTES:
            self.counts['limited'] = True; raise _Limit()

    def emit(self, ref, text=''):
        self.check()
        try:
            text = _plain(text)
            size = len(text.encode('utf-8'))
            if self.bytes+size > MAX_BYTES: self.counts['limited'] = True; raise _Limit()
            ref['title'] = _plain(ref.get('title'), 1000) or tr('(Ohne Titel)')
            url = self.registry.register(ref)
            if url not in self.seen:
                self.seen.add(url); self.counts['objects'] += 1
            self.bytes += size
            self.registry.index_text(url, text)
            with self.registry.library.connect() as db:
                db.execute('INSERT OR REPLACE INTO catalog_objects VALUES (?,?)', (url, self.run))
            return url
        except (ValueError, TypeError):
            self.counts['skipped'] += 1; return ''

    def file(self, path, title=''):
        path = _file_uri(str(path))
        if not path or not _safe_path(path): return ''
        return self.emit(dict(app='files', kind='file', id=path, path=path, title=title or Path(path).name))

    def links(self, source, target, relation='reference'):
        if source and target: self.pending.append((source, target, relation))

    def provenance(self, target, value):
        if isinstance(value, str):
            for source in URL.findall(value)[:100]: self.links(source, target)
        elif isinstance(value, list):
            for source in value[:100]: self.provenance(target, source)

    def app(self, app):
        path = self.root/app/'library.sqlite'
        if not path.is_file() or not _safe_path(path): return
        with closing(sqlite3.connect(path.absolute().as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            if app == 'inbox': self.inbox(db); return
            rows = db.execute('SELECT id,title,substr(data,1,?),length(data) AS size FROM records WHERE archived=0 ORDER BY updated DESC LIMIT ?', (MAX_RECORD, MAX_OBJECTS))
            for row in rows:
                self.check()
                if row['size'] > MAX_RECORD: self.counts['skipped'] += 1; continue
                size = len(row[2].encode('utf-8'))
                if self.bytes+size > MAX_BYTES: self.counts['limited'] = True; raise _Limit()
                self.bytes += size
                try:
                    record = json.loads(row[2])
                    if not isinstance(record, dict): raise ValueError('Invalid record')
                except (ValueError, TypeError): self.counts['skipped'] += 1; continue
                ref = dict(app=app, kind='record', id=row['id'], title=row['title'])
                if app == 'reader' and isinstance(record.get('asset'), str) and Path(record['asset']).name == record['asset']:
                    asset = self.root/app/'assets'/record['asset']
                    if _safe_path(asset): ref['path'] = str(asset.absolute())
                url = self.emit(ref, _record_text(app, record))
                self.provenance(url, record.get('interop_sources', []))
                if app == 'workbench':
                    for resource in _items(record, 'resources'):
                        if resource.get('kind') == 'file': self.links(url, self.file(resource.get('target', ''), resource.get('title', '')), 'resource')
                        elif resource.get('kind') == 'lumen': self.links(url, resource.get('target', ''), 'resource')
                elif app == 'reader':
                    original = _file_uri(record.get('source', ''))
                    if original: self.links(url, self.file(original), 'source')
                elif app == 'household':
                    for attachment in _items(record, 'attachments'):
                        if isinstance(attachment.get('asset'), str) and Path(attachment['asset']).name == attachment['asset']:
                            self.links(url, self.file(self.root/app/'assets'/attachment['asset'], attachment.get('name', '')), 'attachment')

    def inbox(self, db):
        # Account records, raw RFC822 bytes, ICS and tokens are deliberately not
        # selected. Cached body/subject and explicitly visible draft fields suffice.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'messages' in tables:
            for row in db.execute('SELECT account,folder,validity,uid,substr(subject,1,1000) AS subject,substr(body,1,?) AS body FROM messages LIMIT ?', (MAX_TEXT, MAX_OBJECTS)):
                locator = {key: str(row[key]) for key in ('account','folder','validity','uid')}
                identity = hashlib.sha256(json.dumps(locator, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
                self.emit(dict(app='inbox', kind='message', id=identity, title=row['subject'], locator=locator), row['body'])
        if 'tasks' in tables:
            detail="COALESCE((SELECT body FROM interop_task_details WHERE task=tasks.id),'')" if 'interop_task_details' in tables else "''"
            for row in db.execute('SELECT id,substr(title,1,1000) AS title,substr(source,1,4000) AS source,substr('+detail+',1,?) AS body FROM tasks LIMIT ?', (MAX_TEXT, MAX_OBJECTS)):
                url = self.emit(dict(app='inbox', kind='task', id=row['id'], title=row['title']), _plain(row['title'])+'\n'+_plain(row['body']))
                self.provenance(url, row['source'])
        if 'drafts' in tables:
            for row in db.execute("SELECT id,account,substr(json_extract(data,'$.subject'),1,1000) AS title,substr(json_extract(data,'$.body'),1,?) AS body,substr(json_extract(data,'$.interop_sources'),1,12000) AS sources FROM drafts WHERE json_valid(data) LIMIT ?", (MAX_TEXT, MAX_OBJECTS)):
                url = self.emit(dict(app='inbox', kind='draft', id=row['id'], title=row['title'],locator=dict(account=row['account'])), row['body'])
                self.provenance(url, row['sources'])
        if 'calendar_cache' in tables:
            for row in db.execute("SELECT account,uid,json_extract(data,'$.start') AS start,substr(json_extract(data,'$.title'),1,1000) AS title,substr(json_extract(data,'$.description'),1,?) AS description FROM calendar_cache WHERE json_valid(data) LIMIT ?", (MAX_TEXT, MAX_OBJECTS)):
                self.emit(dict(app='inbox', kind='event', id=row['uid']+'|'+(row['start'] or ''), title=row['title'], locator=dict(account=row['account'])), row['description'])

    def notebook(self, root):
        from wissen_data import parse, resolve_link
        root = Path(root).expanduser().absolute()
        if not root.is_dir() or not _safe_path(root): return
        notes = {}; urls = {}; scanned = 0
        for base, dirs, files in os.walk(root, followlinks=False):
            self.check()
            dirs[:] = sorted(name for name in dirs if not name.startswith('.') and name != 'attachments' and not (Path(base)/name).is_symlink())
            for name in sorted(files):
                scanned += 1
                if scanned > 20000: self.counts['limited'] = True; raise _Limit()
                path = Path(base)/name
                if name.startswith('.') or path.suffix.lower() != '.md' or path.is_symlink() or not path.is_file(): continue
                if path.stat().st_size > 1024*1024: self.counts['skipped'] += 1; continue
                try:
                    with path.open('rb') as source: raw = source.read(1024*1024+1)
                    if len(raw) > 1024*1024: self.counts['skipped'] += 1; continue
                    relative = str(path.relative_to(root)); note = parse(relative, raw)
                    if self.bytes+len(raw) > MAX_BYTES: self.counts['limited'] = True; raise _Limit()
                    self.bytes += len(raw)
                    url = self.emit(dict(app='wissen', kind='note', id=relative, title=note['title'], path=str(path), locator=dict(root=str(root),area='lumen')), note['text'])
                    urls[relative] = url; notes[relative] = note
                    self.provenance(url, note['source']); self.provenance(url, note['text'])
                except (OSError, ValueError, UnicodeError): self.counts['skipped'] += 1
        for relative, note in notes.items():
            for target in note['links'][:100]:
                resolved = resolve_link(relative, target, notes)
                if resolved and resolved in urls: self.links(urls[relative], urls[resolved], 'reference')

    def finish(self):
        if self.counts['objects'] >= MAX_OBJECTS: self.counts['limited'] = True
        for source, target, relation in self.pending:
            if self.job: self.job.check()
            try:
                self.registry.link(source, target, relation); self.counts['links'] += 1
            except ValueError: self.counts['unresolved'] += 1
        if not self.counts['limited'] and not self.counts['skipped']:
            with self.registry.library.connect() as db:
                old = [row[0] for row in db.execute('SELECT url FROM catalog_objects WHERE run<>?', (self.run,))]
            for url in old:
                self.registry.index_text(url, '')
            with self.registry.library.connect() as db:
                db.execute('DELETE FROM catalog_objects WHERE run<>?', (self.run,))
        return self.counts


def index_local(registry, store=None, job=None):
    """Index only saved local state; no app creation, account access or network."""
    index = _Index(registry, job)
    try:
        for app in APPS:
            try: index.app(app)
            except (sqlite3.Error, ValueError, OSError): index.counts['skipped'] += 1
        from lumen_store import state_path
        try: index.notebook((store.directory if store is not None else state_path())/'lumen-memory')
        except (sqlite3.Error, ValueError, OSError): index.counts['skipped'] += 1
    except _Limit: pass
    return index.finish()


def related_payload_refs(registry, payload):
    """Resolve existing relationships for a captured object, without indexing."""
    url = payload.get('source_url') or registry.register(payload['source'])
    return registry.related(url)
