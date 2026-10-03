"""Concrete local household/project workflows built on reviewed Lumen transfers."""
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from lumen_i18n import tr
from interop_data import Registry, validate_payload


def _payload(library, record, title, text, paths=(), items=()):
    source = dict(app=library.root.name, kind='record', id=record['id'], title=record['title'])
    registry = Registry(library.root.parent)
    return validate_payload(dict(title=title, text=text, paths=list(paths), items=list(items), source=source, source_url=registry.register(source)))


def invoice_candidates(text):
    """Extract labeled candidates only; the native review dialog commits them."""
    result = {}
    for field, labels in [('provider', r'Händler|Verkäufer|Anbieter|Hersteller'), ('model', r'Modell|Vertragsnummer'), ('serial', r'Seriennummer|Kundennummer')]:
        found = re.search(r'(?im)^\s*(?:'+labels+r')\s*:\s*(.{1,200})$', text)
        if found: result[field] = found[1].strip()
    found = re.search(r'(?im)^\s*(?:Rechnungsdatum|Kaufdatum|Belegdatum|Datum)\s*:\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b', text)
    if found:
        try:
            result['since'] = (date.fromisoformat(found[1]) if '-' in found[1] else datetime.strptime(found[1], '%d.%m.%Y').date()).isoformat()
        except ValueError: pass
    return result


def _device_details(record):
    labels = [('provider', tr('Hersteller / Anbieter')), ('model', tr('Modell / Vertragsnummer')), ('serial', tr('Seriennummer / Kundennummer')), ('since', tr('Kauf / Beginn'))]
    return '\n'.join(label+': '+str(record[field]) for field, label in labels if record.get(field))


def household_payload(library, key, workflow, text='', paths=()):
    record = library.get(key); details = _device_details(record)
    if workflow == 'cancel':
        title = tr('Kündigung · ')+record['title']
        body = tr('Guten Tag,\n\nhiermit kündige ich den folgenden Vertrag zum nächstmöglichen Zeitpunkt. Bitte bestätigen Sie mir die Kündigung und das Vertragsende schriftlich.\n\n')+record['title']+'\n'+details
    elif workflow == 'support':
        title = tr('Supportanfrage · ')+record['title']
        body = tr('Guten Tag,\n\nich bitte um Unterstützung zu folgendem Gerät oder Vertrag:\n\n')+record['title']+'\n'+details+'\n\n'+(text or record.get('notes', ''))
    elif workflow == 'repair':
        title = tr('Reparatur · ')+record['title']; body = details+'\n\n'+(text or record.get('notes', ''))
    elif workflow == 'handover':
        title = tr('Übergabe · ')+record['title']; body = details+'\n\n'+(text or record.get('notes', ''))
    else: raise ValueError(tr('Unbekannter Haushaltsablauf.'))
    names = {str(library.asset(a['asset'])): a['name'] for a in record.get('attachments', [])}
    items = [dict(kind='attachment', path=str(path), title=names.get(str(path), Path(path).name)) for path in paths]
    return _payload(library, record, title, body.strip(), paths, items)


def _event(title, due, text):
    start = datetime.combine(date.fromisoformat(due), datetime.min.time()).replace(hour=9).astimezone()
    return dict(kind='event', title=title, start=start.isoformat(), end=(start+timedelta(hours=1)).isoformat(), location='', description=text)


def deadline_payload(library, key, field='remind'):
    if field not in ('remind', 'until'): raise ValueError(tr('Unbekannte Haushaltsfrist.'))
    record = library.get(key); due = record.get(field, '')
    if not due: raise ValueError(tr('Diese Frist zuerst im Haushalt eintragen.'))
    title = (tr('Kündigungsfrist · ') if field == 'remind' else tr('Garantie / Vertragsende · '))+record['title']
    marker = '[Lumen-Frist:'+key+':'+field+']'
    text = _device_details(record)+'\n\n'+record.get('notes', '')+'\n\n'+marker
    event = _event(title, due, text); event['link_key'] = 'household:'+key+':'+field
    return _payload(library, record, title, text.strip(), items=[event])


def prepare_event_update(library, values, event):
    """Find a previous deadline in the chosen account, never trust supplied remote URLs."""
    result = dict(values); link = event.get('link_key', '')
    if not link: return result
    match = re.fullmatch(r'household:([a-f0-9]{32}):(remind|until)', link)
    if not match: raise ValueError(tr('Ungültige Fristverknüpfung.'))
    marker = '[Lumen-Frist:'+match[1]+':'+match[2]+']'
    def matches(value): return marker in value.get('description', '').splitlines()
    if not matches(result): raise ValueError(tr('Dem Terminvorschlag fehlt seine Fristverknüpfung.'))
    with library.connect() as db:
        records = [json.loads(row['data']) for row in db.execute('SELECT data FROM calendar_cache WHERE account=?', (values['account'],))]
        found = [record for record in records if matches(record)]
        if len(found) > 1: raise ValueError(tr('Mehrere Termine tragen diese Frist. In Lumen Inbox zuerst den richtigen Termin auswählen.'))
        if found:
            existing = found[0]
            if existing.get('recurring') or existing.get('invited'): raise ValueError(tr('Serien oder Einladungen im ursprünglichen Kalender bearbeiten.'))
            if not all(existing.get(key) for key in ('uid', 'url', 'etag', 'ics')): raise ValueError(tr('Den Kalender zuerst aktualisieren, damit die Frist geschützt geändert werden kann.'))
            result.update({key: existing[key] for key in ('uid', 'url', 'etag', 'ics')}); return result
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='interop_event_proposals'").fetchone()
        pending = []
        if exists:
            for row in db.execute('SELECT * FROM interop_event_proposals'):
                proposal = json.loads(row['data'])
                if proposal.get('account') == values['account'] and matches(proposal): pending.append(row['id'])
        if len(pending) > 1: raise ValueError(tr('Mehrere lokale Vorschläge tragen diese Frist. In Lumen Inbox zuerst prüfen.'))
        if pending: result['proposal_id'] = pending[0]
    return result


def project_payload(library, key, workflow, text='', title='', due='', paths=()):
    record = library.get(key); questions = record.get('questions', [])
    if workflow == 'agenda':
        opened = [q['text'] for q in questions if not q.get('done')]
        if not opened: raise ValueError(tr('Dieses Projekt hat keine offenen Fragen.'))
        body = '\n'.join('- '+value for value in opened); title = tr('Agenda · ')+record['title']; items = [dict(kind='agenda', text=body)]
    elif workflow == 'lessons':
        body = text or record.get('notes', ''); title = tr('Erkenntnisse · ')+record['title']; items = []
    elif workflow == 'milestone':
        if not title.strip(): raise ValueError(tr('Bitte einen Meilenstein benennen.'))
        body = record['title']+'\n\n'+record.get('notes', ''); items = [_event(title, due, body)]
    elif workflow in ('status', 'handover'):
        title = (tr('Projektstand · ') if workflow == 'status' else tr('Projektübergabe · '))+record['title']
        body = record.get('notes', '')+'\n\n'+tr('Offene Fragen:')+'\n'+'\n'.join('- '+q['text'] for q in questions if not q.get('done'))
        body += '\n\n'+tr('Geklärt:')+'\n'+'\n'.join('- '+q['text'] for q in questions if q.get('done'))
        names = {r['target']: r.get('title', '') for r in record.get('resources', [])}
        items = [dict(kind='attachment', path=str(path), title=names.get(str(path)) or Path(path).name) for path in paths]
    else: raise ValueError(tr('Unbekannter Projektablauf.'))
    if not body.strip(): raise ValueError(tr('Zuerst einen Text für diese Übergabe ergänzen.'))
    return _payload(library, record, title, body.strip(), paths, items)


def reading_list(library, key):
    record = library.get(key); resources = record.get('resources', [])
    candidates = {r['target']: dict(path=r['target'], title=r.get('title') or Path(r['target']).name) for r in resources if r.get('kind') == 'file' and Path(r['target']).suffix.lower() in ('.pdf', '.epub', '.txt', '.md', '.html', '.htm')}
    order = [item['path'] for item in record.get('reading_list', []) if item.get('path') in candidates]
    order += [path for path in candidates if path not in order]
    return [candidates[path] for path in order]


def save_reading_list(library, key, items):
    allowed = {item['path'] for item in reading_list(library, key)}
    paths = [item['path'] for item in items]
    if len(paths) != len(set(paths)) or set(paths)-allowed: raise ValueError(tr('Die Leseliste enthält unbekanntes Projektmaterial.'))
    library.update(key, reading_list=[dict(path=item['path'], title=item['title']) for item in items])


def recent_files(library, key, job, limit=60):
    queue = [Path(r['target']) for r in library.get(key).get('resources', []) if r.get('kind') == 'file']; files = {}; visited = set(); count = 0
    while queue and count < 5000:
        job.check(); path = queue.pop(); count += 1
        if str(path) in visited: continue
        visited.add(str(path))
        try:
            if path.is_symlink(): continue
            if path.is_dir():
                with os.scandir(path) as entries:
                    for entry in entries:
                        if len(queue)+count >= 5000: break
                        if not entry.name.startswith('.') and not entry.is_symlink(): queue.append(Path(entry.path))
            elif path.is_file():
                info = path.stat(); files[str(path)] = dict(path=str(path), title=path.name, modified=info.st_mtime, size=info.st_size)
        except OSError: continue
    return sorted(files.values(), key=lambda value: (-value['modified'], value['path']))[:limit]


def repair_resource(library, key, old, new, all_projects=False):
    destination = Path(new)
    if not Path(old).is_absolute() or not destination.is_absolute() or not destination.exists(): raise ValueError(tr('Bitte eine vorhandene lokale Ersatzdatei oder einen Ordner auswählen.'))
    records = library.all() if all_projects else [library.get(key)]; changed = 0
    with library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for record in records:
            row = db.execute('SELECT data FROM records WHERE id=?', (record['id'],)).fetchone(); data = json.loads(row['data'])
            touched = False
            for item in data.get('resources', []):
                if item.get('kind') == 'file' and item.get('target') == old: item['target'] = new; touched = True
            for item in data.get('reading_list', []):
                if item.get('path') == old: item['path'] = new
            if touched:
                db.execute('UPDATE records SET data=?,updated=? WHERE id=?', (json.dumps(data), time.time(), record['id'])); changed += 1
    Registry(library.root.parent).relocate(old, new)
    return changed


def project_context(library, key):
    record = library.get(key); registry = Registry(library.root.parent)
    source = registry.register(dict(app='workbench', kind='record', id=key, title=record['title']))
    values = registry.related(source); seen = {value['url'] for value in values}
    from interop_reader import progress_for_paths
    resources = [r for r in record.get('resources', []) if r.get('kind') == 'file']
    progress = progress_for_paths([r['target'] for r in resources], library.root.parent)
    for resource in resources:
        for book in progress.get(resource['target'], []):
            ref = dict(app='reader', kind='record', id=book['id'], title=book['title'], position=dict(page=book['page']))
            url = registry.register(ref)
            if url not in seen: values.append(dict(ref, url=url)); seen.add(url)
    return values[:100]


def save_context(library, key, urls):
    if len(urls) > 8 or len(set(urls)) != len(urls): raise ValueError(tr('Bis zu acht verschiedene Inhalte für einen Arbeitskontext auswählen.'))
    registry = Registry(library.root.parent)
    for url in urls: registry.resolve(url)
    library.update(key, context=list(urls))


def spoken_status(payload, root, job):
    from tools_data import Library, synthesize
    payload = validate_payload(payload); library = Library('radio', root)
    result = synthesize(payload['text'], library, job)
    try:
        job.check()
        import hashlib
        key = library.create(payload['title'], script=payload['text'], sources=[dict(title=payload['title'], text=payload['text'], url=payload['source_url'], selected=True)], minutes=5,
                             interop_sources=[payload['source_url']], audio_hash=hashlib.sha256(payload['text'].encode()).hexdigest(), **result)
    except BaseException:
        library.asset(result['audio']).unlink(missing_ok=True); raise
    ref = dict(app='radio', kind='record', id=key, title=payload['title'])
    registry = Registry(root); registry.link(payload['source_url'], registry.register(ref), 'spoken-status')
    return ref
