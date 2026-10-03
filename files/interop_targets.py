"""Local, reviewed Lumen transfers. A transfer never sends mail or calls a model."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import time
import uuid
from urllib.parse import quote

from lumen_i18n import tr
from tools_data import Library, document_text, media_duration, web_url


ACTIONS = {
    'wissen.import': dict(target='wissen', label=tr('Als Notiz speichern …'), modes=['copy', 'link'], description=tr('In Lumen Wissen speichern. Die Originaldatei bleibt unverändert.')),
    'workbench.add': dict(target='workbench', label=tr('Zu einem Projekt hinzufügen …'), modes=['copy', 'link','live'], description=tr('Material und Notizen einem neuen oder vorhandenen Projekt zuordnen.')),
    'workbench.question': dict(target='workbench', label=tr('Als offene Projektfrage übernehmen'), modes=['copy'], description=tr('Ausgewählten Text als offene Frage mit Herkunft speichern.')),
    'household.add': dict(target='household', label=tr('Zu einem Gerät oder Vertrag hinzufügen …'), modes=['copy','link','live'], description=tr('Belege, Handbücher und Notizen einem Gerät oder Vertrag zuordnen.')),
    'radio.add': dict(target='radio', label=tr('Für eine Radioausgabe sammeln …'), modes=['copy'], description=tr('Lokalen Text für eine neue oder vorhandene Radioausgabe sammeln.')),
    'reader.import': dict(target='reader', label=tr('In Lumen Reader öffnen'), modes=['copy'], description=tr('Eine private Lesekopie mit Herkunft anlegen.')),
    'meetings.import': dict(target='meetings', label=tr('Aufnahme in Lumen Meeting-Werkstatt öffnen'), modes=['copy'], description=tr('Audio lokal importieren; Transkription separat starten.')),
    'meetings.agenda': dict(target='meetings', label=tr('Als Meeting-Agenda übernehmen'), modes=['copy'], description=tr('Text als Agenda einer neuen oder vorhandenen Besprechung hinzufügen.')),
    'inbox.draft': dict(target='inbox', label=tr('Mailentwurf in Lumen Inbox vorbereiten'), modes=['copy'], description=tr('Text und Dateikopien als lokalen, ungesendeten Entwurf speichern.')),
    'inbox.task': dict(target='inbox', label=tr('Aufgabe in Lumen Inbox anlegen'), modes=['copy'], description=tr('Eine lokale Aufgabe mit Fälligkeit und Herkunft erstellen.')),
    'inbox.event': dict(target='inbox', label=tr('Termin in Lumen Inbox vorbereiten'), modes=['copy'], description=tr('Einen lokalen Terminvorschlag zur Prüfung im Kalendereditor vorbereiten.')),
}
for _action in ('inbox.draft', 'inbox.event'): ACTIONS[_action]['requires_choice'] = True
TEXT_SUFFIXES = {'.pdf', '.txt', '.md', '.csv', '.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'}
READER_SUFFIXES = {'.pdf', '.epub', '.txt', '.md', '.html', '.htm'}
AUDIO_SUFFIXES = {'.wav', '.mp3', '.m4a', '.ogg', '.flac', '.opus', '.mp4', '.mkv', '.webm'}


def available(payload):
    paths = payload.get('paths', []); text = bool(payload.get('text', '').strip())
    result = ['wissen.import', 'workbench.add', 'household.add', 'inbox.draft', 'inbox.task', 'inbox.event']
    if text: result += ['workbench.question', 'meetings.agenda']
    if text or (paths and all(Path(p).suffix.lower() in TEXT_SUFFIXES for p in paths)): result.append('radio.add')
    if text or (len(paths) == 1 and Path(paths[0]).suffix.lower() in READER_SUFFIXES): result.append('reader.import')
    if len(paths) == 1 and Path(paths[0]).suffix.lower() in AUDIO_SUFFIXES: result.append('meetings.import')
    return [action for action in ACTIONS if action in result]


def choices(action, root=None, store=None):
    target = ACTIONS[action]['target']
    if action == 'wissen.import':
        from lumen_store import Store
        from wissen_data import Notebook
        book = Notebook(store or Store())
        return [dict(id='.', title=tr('Notizordner'))] + [dict(id=p, title=p) for p in book.scan()['folders']]
    if action in ('reader.import', 'meetings.import', 'inbox.task'): return []
    records = Library(target, root).all()
    if target == 'inbox':
        kinds = ('imap', 'bridge') if action == 'inbox.draft' else ('caldav',)
        records = [record for record in records if record.get('kind') in kinds]
    return [dict(id=record['id'], title=record['title']) for record in records]


def _validate(action, payload, choice):
    if action not in ACTIONS or choice.get('mode', 'copy') not in ACTIONS[action]['modes']:
        raise ValueError(tr('Diese Übergabeart wird nicht unterstützt.'))
    if choice.get('mode')=='live' and not (payload.get('source',{}).get('app')=='wissen' and payload['source'].get('kind') in ('note','collection')):
        raise ValueError(tr('Live-Verknüpfungen benötigen eine Notiz oder Sammlung aus Lumen Wissen.'))
    if not isinstance(payload.get('title'), str) or not payload['title'].strip() or len(payload['title']) > 1000:
        raise ValueError(tr('Die Übergabe benötigt einen Titel.'))
    text = payload.get('text', '')
    if not isinstance(text, str) or len(text) > 120000: raise ValueError(tr('Übergabetext größer als 120.000 Zeichen.'))
    paths = payload.get('paths', [])
    if not isinstance(paths, list) or len(paths) > 100 or any(not isinstance(p, str) or not Path(p).is_absolute() or '\0' in p for p in paths):
        raise ValueError(tr('Nur bis zu 100 absolute lokale Dateipfade übergeben.'))
    if not re.fullmatch(r'lumen://object/[0-9a-f]{32}(?:\?[^\s]*)?', payload.get('source_url', '')):
        raise ValueError(tr('Die Herkunft der Übergabe fehlt oder ist ungültig.'))
    token = choice.get('token', '')
    if not isinstance(token, str) or not 1 <= len(token) <= 200: raise ValueError(tr('Die Übergabekennung fehlt.'))
    if choice.get('due'): date.fromisoformat(choice['due'])
    if payload.get('url'): web_url(payload['url'])
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 512*1024: raise ValueError(tr('Übergabe größer als 512 KiB.'))
    if action not in available(payload): raise ValueError(tr('Dieser Inhalt passt nicht zum gewählten Ziel.'))


@contextmanager
def _lock(library, job):
    fd = os.open(library.root/'interop.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        while True:
            job.check()
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError: time.sleep(.05)
        yield
    finally: os.close(fd)


def _receipt(db, token, signature):
    db.execute('CREATE TABLE IF NOT EXISTS interop_receipts (token TEXT PRIMARY KEY, signature TEXT NOT NULL, result TEXT NOT NULL)')
    row = db.execute('SELECT signature,result FROM interop_receipts WHERE token=?', (token,)).fetchone()
    if row:
        if row['signature'] != signature: raise ValueError(tr('Diese Übergabekennung gehört zu einem anderen Inhalt.'))
        return json.loads(row['result'])


def _remember(db, token, signature, result):
    db.execute('INSERT INTO interop_receipts VALUES (?,?,?)', (token, signature, json.dumps(result)))


def _body(payload, mode='copy'):
    content = payload.get('text', '').strip() if mode == 'copy' else ''
    from interop_sources import source_title
    title=source_title(payload.get('source',{})).replace('\\','\\\\').replace('[','\\[').replace(']','\\]')
    return (content+'\n\n' if content else '') + tr('Quelle: ') + '['+title+']('+payload['source_url']+')'


def _copy(library, path, job, created, limit=128*1024**2):
    asset = library.import_file(path, job, limit=limit)
    created.append(library.asset(asset['asset']))
    return asset


def _filename(payload, path):
    item = next((item for item in payload.get('items', []) if item.get('path') == str(path) and item.get('title')), {})
    return Path(item.get('title', Path(path).name).replace('\\', '/')).name


def _record(db, library, action, payload, choice, values, extend=()):
    key = choice.get('id') or uuid.uuid4().hex
    existing = db.execute('SELECT * FROM records WHERE id=?', (key,)).fetchone() if choice.get('id') else None
    if choice.get('id') and not existing: raise ValueError(tr('Das gewählte Ziel ist nicht mehr vorhanden.'))
    previous = json.loads(existing['data']) if existing else {}
    if not existing:
        if action.startswith('workbench.'):
            from interop_paths import revision
            previous.update(notes='', questions=[], resources=[],interop_path_revision=revision(library.root.parent))
        if action == 'household.add': previous.update(kind='Gerät', notes='', attachments=[])
        if action == 'radio.add': previous.update(sources=[], script='', minutes=5)
        if action.startswith('meetings.'): previous.update(recording=None, duration=0, segments=[], summary='', results=[], agenda='')
    for field in extend:
        if field not in values: continue
        before = previous.get(field)
        if before: values[field] = before + ('\n\n' if isinstance(before, str) else []) + values[field]
    previous.update(values)
    previous['interop_sources'] = list(dict.fromkeys(previous.get('interop_sources', []) + [payload['source_url']]))
    previous['interop_token'] = choice['token']
    title = existing['title'] if existing else (choice.get('title') or payload['title']).strip()[:300]
    if not title: raise ValueError(tr('Bitte einen Titel eingeben.'))
    if existing:
        db.execute('UPDATE records SET data=?,updated=? WHERE id=?', (json.dumps(previous), time.time(), key))
    else:
        db.execute('INSERT INTO records VALUES (?,?,?,?,?)', (key, title, json.dumps(previous), 0, time.time()))
    return dict(app=ACTIONS[action]['target'], kind='record', id=key, title=title)


def _wissen(library, payload, choice, job, store, created):
    from lumen_store import Store
    from wissen_data import Notebook
    book = Notebook(store or Store()); folder = choice.get('id') or '.'
    name = 'Lumen-'+hashlib.sha256(choice['token'].encode()).hexdigest()[:24]+'.md'
    relative = str(Path(folder)/name); marker = 'interop:'+choice['token']
    try:
        note = book.read(relative)
        if note.get('legacy') != marker: raise ValueError(tr('Am Übergabeziel liegt bereits eine andere Notiz.'))
    except FileNotFoundError:
        # The notebook stores the source in portable metadata and displays it
        # as a named link outside the editable text.
        text = payload.get('text','').strip() if choice.get('mode','copy')=='copy' else ''; links = []
        if choice.get('mode', 'copy') == 'copy' and not payload.get('text', '').strip():
            imported = [document_text(p, job) for p in payload.get('paths', []) if Path(p).suffix.lower() in ('.md', '.txt')]
            if sum(map(len, imported)) > 120000: raise ValueError(tr('Übergabetext größer als 120.000 Zeichen.'))
            if imported: text = '\n\n'.join(imported)+'\n\n'+text
        for path in dict.fromkeys(payload.get('paths', [])):
            job.check(); path = Path(path)
            if choice.get('mode') == 'link':
                links.append('['+path.name.replace(']', '\\]')+']('+path.as_uri()+')'); continue
            with book.directory() as root:
                try: os.mkdir('attachments', 0o700, dir_fd=root)
                except FileExistsError: pass
            copied = _copy(library, path, job, created)
            # The notebook API verifies every directory component, including attachments.
            target = 'attachments/'+copied['asset']
            with book.directory('attachments') as directory:
                fd = os.open(copied['asset'], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=directory)
                created.append(book.root/target)
                with os.fdopen(fd, 'wb') as output, library.asset(copied['asset']).open('rb') as source:
                    while chunk := source.read(1024*1024): job.check(); output.write(chunk)
                    output.flush(); os.fsync(output.fileno())
            library.asset(copied['asset']).unlink()
            link = os.path.relpath(target, folder)
            links.append('['+_filename(payload, path).replace(']', '\\]')+']('+quote(link)+')')
        if links: text += '\n\n'+'\n'.join('- '+link for link in links)
        job.check()
        note = book.write(relative, '# '+(choice.get('title') or payload['title'])+'\n\n'+text, '', payload['source_url'], marker)
        # A crash after this atomic write is replayable from its deterministic name.
    return dict(app='wissen', kind='note', id=relative, title=note['title'], path=str(book.root/relative), locator=dict(root=str(book.root)))


def apply(action, payload, choice, job, root=None, store=None):
    from interop_undo import snapshot,remember
    _validate(action, payload, choice)
    if ACTIONS[action]['target'] == 'inbox':
        from inbox_data import store as inbox_store
        library = inbox_store(root)
    else: library = Library(ACTIONS[action]['target'], root)
    signature = hashlib.sha256(json.dumps([action, payload, choice], sort_keys=True).encode()).hexdigest()
    created = []
    with _lock(library, job):
        with library.connect() as db:
            result = _receipt(db, choice['token'], signature)
        if result: return result
        try:
            if action == 'wissen.import':
                result = _wissen(library, payload, choice, job, store, created)
                created.clear()  # The notebook is durable; replay recovers it even if receipt persistence fails.
                from wissen_data import Notebook
                from lumen_store import Store
                note=Notebook(store or Store(),root=result['locator']['root']).read(result['id'])
                with library.connect() as db:
                    _remember(db, choice['token'], signature, result)
                    remember(db,choice['token'],result,None,dict(hash=note['hash']))
                return result
            values, extend = _prepare(library, action, payload, choice, job, created)
            job.check()
            with library.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                kind='event' if action=='inbox.event' else 'record'
                key=values.get('proposal_id') if kind=='event' else choice.get('id')
                before=snapshot(db,kind,key) if key and not action.startswith(('inbox.draft','inbox.task')) else None
                result = (_inbox(db, library, action, payload, choice, values) if action.startswith('inbox.') else
                          _record(db, library, action, payload, choice, values, extend))
                _remember(db, choice['token'], signature, result)
                remember(db,choice['token'],result,before,snapshot(db,result['kind'],result['id']))
            return result
        except BaseException:
            for path in created: path.unlink(missing_ok=True)
            raise


def _prepare(library, action, payload, choice, job, created):
    mode = choice.get('mode', 'copy'); paths = list(dict.fromkeys(payload.get('paths', [])))
    if action.startswith('workbench.'):
        if action == 'workbench.question':
            return dict(questions=[dict(text=_body(payload), done=False)], notes='', resources=[]), ('questions', 'notes', 'resources')
        if mode=='live':return dict(notes='',resources=[dict(kind='lumen',target=payload['source_url'],title=payload['title'],live=True)],questions=[]),('resources',)
        resources = []
        for path in paths:
            job.check()
            if not Path(path).exists(): raise ValueError(tr('Die Quelldatei ist nicht mehr vorhanden.'))
            target = path if mode == 'link' else str(library.asset(_copy(library, path, job, created)['asset']))
            resources.append(dict(kind='file', target=target, title=_filename(payload, path)))
        if payload.get('url'): resources.append(dict(kind='url', target=payload['url'], title=payload['title']))
        if mode == 'link' and not resources: resources.append(dict(kind='lumen', target=payload['source_url'], title=payload['title']))
        questions = []
        if mode == 'copy':
            for item in payload.get('items', []):
                if item.get('kind') not in ('task', 'question') or not item.get('text', item.get('title', '')).strip(): continue
                text = item.get('text') or item['title']
                if item.get('due'): text += ' · '+item['due']
                questions.append(dict(text=text+'\n'+payload['source_url'], done=bool(item.get('done', False))))
        return dict(notes=_body(payload, mode), resources=resources, questions=questions), ('notes', 'resources', 'questions')
    if action == 'household.add':
        if mode=='live':return dict(live_sources=[payload['source_url']]),('live_sources',)
        if mode=='link':return dict(notes=_body(payload,mode),linked_paths=[dict(path=path,title=_filename(payload,path)) for path in paths]),('notes','linked_paths')
        attachments = [dict(_copy(library, path, job, created), name=_filename(payload, path)) for path in paths]
        return dict(notes=_body(payload), attachments=attachments), ('notes', 'attachments')
    if action == 'radio.add':
        sources = []
        for item in payload.get('items', []):
            if item.get('kind') == 'source' and item.get('text', '').strip():
                url = web_url(item['url']) if item.get('url', '').startswith(('http://', 'https://')) else payload['source_url']
                if item.get('url','').startswith('lumen://'):
                    from interop_data import Registry
                    Registry(library.root.parent).resolve(item['url']);url=item['url']
                sources.append(dict(title=item.get('title') or payload['title'], text=item['text'], url=url, selected=True))
        if not sources and payload.get('text', '').strip(): sources.append(dict(title=payload['title'], text=payload['text'], url=payload['source_url'], selected=True))
        else:
            for path in paths:
                text = document_text(path, job)
                sources.append(dict(title=Path(path).name, text=text, url=payload['source_url'], selected=True))
        return dict(sources=sources), ('sources',)
    if action == 'reader.import': return _reader(library, payload, choice, job, created), ()
    if action == 'meetings.import':
        if choice.get('id'): raise ValueError(tr('Aufnahmen werden als neue Besprechung importiert.'))
        duration = media_duration(paths[0], job)
        return dict(recording=_copy(library, paths[0], job, created, limit=2*1024**3), duration=duration), ()
    if action == 'meetings.agenda': return dict(agenda=_body(payload)), ('agenda',)
    if action.startswith('inbox.'):
        values = dict(title=(choice.get('title') or payload['title']).strip()[:300], source=payload['source_url'])
        if action != 'inbox.task':
            account = library.get(choice.get('id', ''))
            if account.get('kind') not in (('imap', 'bridge') if action == 'inbox.draft' else ('caldav',)):
                raise ValueError(tr('Bitte ein passendes Lumen-Inbox-Konto auswählen.'))
            values['account'] = account['id']
        if action == 'inbox.draft':
            values.update(to='', subject=values['title'], body=_body(payload), reply_to='', attachments=[])
            values['formatted']=payload.get('source',{}).get('app')=='wissen'
            total = 0
            for path in paths:
                asset = dict(_copy(library, path, job, created, limit=12*1024**2), name=_filename(payload, path))
                total += library.asset(asset['asset']).stat().st_size
                if total > 12*1024**2: raise ValueError(tr('Anhänge zusammen größer als 12 MiB.'))
                values['attachments'].append(asset)
            from inbox_data import draft_attachments
            values['attachments'] = draft_attachments(library, values['attachments'])
        elif action == 'inbox.task':
            task=next((i for i in payload.get('items',[]) if i.get('kind')=='task'),{})
            values['due'] = choice.get('due',task.get('due',''))
            if values['due']:date.fromisoformat(values['due'])
        else:
            start = datetime.combine(date.fromisoformat(choice['due']) if choice.get('due') else date.today(), datetime.min.time()).replace(hour=9).astimezone()
            values.update(start=start.isoformat(), end=(start+timedelta(hours=1)).isoformat(), description=_body(payload), location='')
            event = next((i for i in payload.get('items', []) if i.get('kind') == 'event'), {})
            if event.get('start') and event.get('end'):
                begin, end = datetime.fromisoformat(event['start']), datetime.fromisoformat(event['end'])
                if end <= begin: raise ValueError(tr('Das Terminende muss nach dem Beginn liegen.'))
                values.update(start=begin.isoformat(), end=end.isoformat(), location=event.get('location', ''))
            from interop_workflows import prepare_event_update
            values=prepare_event_update(library,values,event)
        return values, ()
    raise ValueError(tr('Diese Übergabe ist noch nicht verfügbar.'))


def _reader(library, payload, choice, job, created):
    from reader_data import worker, MAX_FILE
    from tools_data import ArticleParser
    if choice.get('id'): raise ValueError(tr('Lesekopien werden als neues Dokument importiert.'))
    paths = payload.get('paths', []); text = payload.get('text', '')
    if not text and len(paths) == 1 and Path(paths[0]).suffix.lower() not in ('.html', '.htm'):
        asset = _copy(library, paths[0], job, created, limit=MAX_FILE)['asset']
    else:
        if not text and len(paths) == 1:
            path = Path(paths[0])
            if path.stat().st_size > 2*1024**2: raise ValueError(tr('HTML-Artikel größer als 2 MiB.'))
            parser = ArticleParser(); parser.feed(path.read_text(errors='replace')); text = parser.text()
        if not text.strip() or len(text) > 120000: raise ValueError(tr('Artikel muss 1 bis 120.000 Zeichen enthalten.'))
        asset = uuid.uuid4().hex+'.html'; path = library.asset(asset); created.append(path)
        body = '<html><head><meta charset="utf-8"></head><body><h1>'+html.escape(choice.get('title') or payload['title'])+'</h1>'
        body += ''.join('<p>'+html.escape(line)+'</p>' for line in text.splitlines() if line.strip())+'</body></html>'
        with path.open('x') as stream: path.chmod(0o600); stream.write(body)
    path = library.asset(asset); metadata = worker(job, 'metadata', path); metadata.pop('title', None)
    values = dict(asset=asset, source=payload['source_url'], page=0, scroll=0, notes=[], stamp=[path.stat().st_size, path.stat().st_mtime_ns], **metadata)
    if not payload.get('text') and len(paths) == 1: values['original_path'] = paths[0]
    return values


def _inbox(db, library, action, payload, choice, values):
    key = uuid.uuid4().hex; title = values.pop('title')
    values.update(interop_sources=[payload['source_url']], interop_token=choice['token'])
    if action == 'inbox.draft':
        account = values.pop('account')
        db.execute('INSERT INTO drafts VALUES (?,?,?,?)', (key, account, json.dumps(values), 'draft'))
        return dict(app='inbox', kind='draft', id=key, title=title, locator=dict(account=account))
    if action == 'inbox.task':
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,0)', (key, title, values['due'], payload['source_url']))
        db.execute('INSERT INTO interop_task_details VALUES (?,?)',(key,_body(payload)))
        return dict(app='inbox', kind='task', id=key, title=title)
    values['title'] = title
    db.execute('CREATE TABLE IF NOT EXISTS interop_event_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    key=values.pop('proposal_id',None) or key
    db.execute('INSERT INTO interop_event_proposals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (key, json.dumps(values)))
    return dict(app='inbox', kind='event', id=key, title=title, locator=dict(account=values['account']))


def event_proposal(library, key):
    """Read a local proposal for the existing reviewed calendar editor."""
    with library.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS interop_event_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        row = db.execute('SELECT data FROM interop_event_proposals WHERE id=?', (key,)).fetchone()
    return json.loads(row['data']) if row else None
