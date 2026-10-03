"""Concrete mail, meeting and listening workflows with bounded provenance."""
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid
import zipfile

from lumen_i18n import tr
from tools_data import clock_text, Library
from interop_data import Registry, validate_payload


def _message_ref(message):
    locator = {key: str(message[key]) for key in ('account', 'folder', 'validity', 'uid')}
    identity = hashlib.sha256(json.dumps(locator, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return dict(app='inbox', kind='message', id=identity, title=message['subject'] or tr('Nachricht'), locator=locator)


def _payload(library, ref, text='', paths=(), items=(), title=None):
    registry = Registry(library.root.parent)
    return validate_payload(dict(title=title or ref['title'], source=ref, source_url=registry.register(ref), text=text, paths=list(paths), items=list(items)))


def _thread_rows(library, message, raw=False):
    if not message or not message.get('thread'):
        raise ValueError(tr('Zuerst eine Nachricht mit Unterhaltung auswählen.'))
    fields = 'account,folder,validity,uid,subject,sender,sent,body' + (',raw' if raw else '')
    with library.connect() as db:
        size = db.execute('SELECT count(*),sum(length(raw)),sum(length(body)) FROM messages WHERE account=? AND thread=?', (message['account'], message['thread'])).fetchone()
        if size[0] > 100 or (size[1] or 0) > 128 * 1024**2 or (not raw and (size[2] or 0) > 100000):
            raise ValueError(tr('Unterhaltung zu groß. Bitte einzelne Nachrichten übernehmen.'))
        rows = [dict(row) for row in db.execute('SELECT ' + fields + ' FROM messages WHERE account=? AND thread=?', (message['account'], message['thread']))]
    def stamp(row):
        try: return parsedate_to_datetime(row['sent']).timestamp()
        except (ValueError, TypeError, OverflowError): return 0
    if not rows:
        raise ValueError(tr('Die Unterhaltung ist lokal nicht mehr vorhanden.'))
    return sorted(rows, key=lambda row: (stamp(row), row['uid']))


def mail_thread(library, message):
    """The selected account/thread only; each message keeps a distinct deep link."""
    rows = _thread_rows(library, message)
    registry = Registry(library.root.parent)
    parts, items = [], []
    for row in rows:
        url = registry.register(_message_ref(row))
        parts.append('## ' + row['subject'] + '\n\n' + row['sender'] + ' · ' + row['sent'] + '\n\n' + row['body'] + '\n\n' + tr('Nachricht in Lumen Inbox: ') + url)
        items.append(dict(kind='message', title=row['subject'], sender=row['sender'], sent=row['sent'], url=url))
    return _payload(library, _message_ref(message), '\n\n---\n\n'.join(parts), items=items)


def archive_thread(library, message, job):
    """Private ZIP with original MIME messages, including their attachments."""
    job.check()
    rows = _thread_rows(library, message, raw=True)
    registry = Registry(library.root.parent)
    destination = library.asset('conversation-' + uuid.uuid4().hex + '.zip')
    try:
        with destination.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                manifest = []
                for index, row in enumerate(rows):
                    job.check()
                    name = f'{index + 1:03d}.eml'
                    archive.writestr(name, row['raw'])
                    manifest.append(dict(file=name, subject=row['subject'], sender=row['sender'], sent=row['sent'], source=registry.register(_message_ref(row))))
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        job.check()
        source = dict(app='files', kind='file', id=str(destination), path=str(destination), title=message['subject'] or tr('Mail-Unterhaltung'))
        payload = _payload(library, source, tr('Vollständige Unterhaltung mit {0} lokalen Nachrichten und eingebetteten Anhängen.', len(rows)), paths=[str(destination)])
        registry.link(registry.register(_message_ref(message)), payload['source_url'], 'conversation_archive')
        return payload
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def compare_attachment(payload, existing, job, root=None):
    from interop_sources import materialize
    payload = materialize(payload, job, root)
    if len(payload.get('paths', [])) != 1:
        raise ValueError(tr('Genau einen Mailanhang auswählen.'))
    selected, existing = Path(payload['paths'][0]), Path(existing)
    if not existing.is_file() or existing.stat().st_size > 128 * 1024**2:
        raise ValueError(tr('Eine vorhandene Datei bis 128 MiB auswählen.'))
    def digest(path):
        value = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                job.check()
                value.update(chunk)
        return value.hexdigest()
    return dict(identical=digest(selected) == digest(existing), incoming_size=selected.stat().st_size, existing_size=existing.stat().st_size, existing=str(existing))


def save_attachment_with_source(payload, destination, job, root=None):
    from interop_sources import materialize
    payload = materialize(payload, job, root)
    if len(payload.get('paths', [])) != 1:
        raise ValueError(tr('Genau einen Mailanhang auswählen.'))
    destination = Path(destination)
    created = False
    try:
        with Path(payload['paths'][0]).open('rb') as source, destination.open('xb') as output:
            created = True
            os.fchmod(output.fileno(), 0o600)
            while chunk := source.read(1024 * 1024):
                job.check()
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        job.check()
        registry = Registry(root)
        target = registry.register(dict(app='files', kind='file', id=str(destination.absolute()), path=str(destination.absolute()), title=destination.name))
        origin = payload.get('source_url') or registry.register(payload['source'])
        registry.link(origin, target, 'mail_attachment')
        return str(destination)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def _meeting_ref(record, index=None, result=False):
    ref = dict(app='meetings', kind='record', id=record['id'], title=record['title'])
    if index is not None:
        segment = record['results'][index]['segment'] if result else index
        from interop_parts import make_part
        kind = 'result' if result else 'segment'
        ref['position'] = dict(time=record['segments'][segment]['start'], part=make_part(kind,index,record['results' if result else 'segments'][index]))
    return ref


def meeting_result_payload(library, key, index):
    record = library.get(key)
    if not 0 <= index < len(record.get('results', [])):
        raise ValueError(tr('Zuerst ein Meeting-Ergebnis auswählen.'))
    result = record['results'][index]
    item = dict(kind='task' if result['kind'] == 'actions' else 'decision', text=result['text'], done=bool(result.get('done')), due=result.get('due', ''), time=record['segments'][result['segment']]['start'])
    return _payload(library, _meeting_ref(record, index, True), result['text'], items=[item], title=result['text'][:300])


def meeting_protocol(library, key, *, results=None, transcript=True):
    record = library.get(key)
    registry = Registry(library.root.parent)
    lines = [record.get('summary', '')] if results is None else []
    if results is None and record.get('agenda'):
        lines += [tr('## Agenda'), record['agenda']]
    indices = range(len(record.get('results', []))) if results is None else results
    items = []
    for index in indices:
        payload = meeting_result_payload(library, key, index)
        item = payload['items'][0]
        prefix = ('- [x] ' if item['done'] else '- [ ] ') if item['kind'] == 'task' else tr('- Entscheidung: ')
        lines.append(prefix + item['text'] + (' · ' + item['due'] if item['due'] else '') + '\n' + payload['source_url'])
        items.append(item)
    if transcript:
        lines.append(tr('## Transkript'))
        for index, segment in enumerate(record.get('segments', [])):
            url = registry.register(_meeting_ref(record, index))
            lines.append('[' + clock_text(segment['start']) + '](' + url + ') ' + segment['text'])
    return _payload(library, _meeting_ref(record), '\n\n'.join(line for line in lines if line), items=items)


def link_meeting_document(library, key, segment, document, page):
    record = library.get(key)
    if not 0 <= segment < len(record.get('segments', [])):
        raise ValueError(tr('Zuerst eine Transkriptstelle auswählen.'))
    reader = Library('reader', library.root.parent)
    book = reader.get(document)
    if not 0 <= page < book.get('pages', 1):
        raise ValueError(tr('Die gewählte Buchseite ist nicht vorhanden.'))
    registry = Registry(library.root.parent)
    origin = registry.register(_meeting_ref(record, segment))
    target = registry.register(dict(app='reader', kind='record', id=document, title=book['title'], path=str(reader.asset(book['asset'])), position=dict(page=page)))
    registry.link(origin, target, 'mentioned_document')
    links = record.get('document_links', [])
    value = dict(segment=segment, source=origin, target=target)
    if value not in links:
        library.update(key, document_links=links + [value])
    return target


def link_meeting_event(library, key, account, uid, start):
    import inbox_data
    inbox = inbox_data.store(library.root.parent)
    with inbox.connect() as db:
        rows = db.execute('SELECT data FROM calendar_cache WHERE account=?', (account,))
        event = next((value for row in rows if (value := json.loads(row['data'])).get('uid') == uid and value.get('start') == start), None)
    if not event:
        raise ValueError(tr('Der Kalendertermin ist lokal nicht mehr vorhanden.'))
    registry = Registry(library.root.parent)
    record = library.get(key)
    source = registry.register(_meeting_ref(record))
    target = registry.register(dict(app='inbox', kind='event', id=uid + '|' + start, title=event['title'], locator=dict(account=account)))
    registry.link(source, target, 'calendar_event')
    library.update(key, calendar_event=target)
    return target


def support_payload(library, key, attachment_indices, description):
    record = library.get(key)
    attachments = record.get('attachments', [])
    if any(type(index) is not int or not 0 <= index < len(attachments) for index in attachment_indices):
        raise ValueError(tr('Ein ausgewählter Beleg ist nicht mehr vorhanden.'))
    items = [dict(kind='attachment', title=attachments[index]['name'], path=str(library.asset(attachments[index]['asset']))) for index in dict.fromkeys(attachment_indices)]
    text = '\n'.join(record.get(key, '') for key in ('title', 'provider', 'model', 'serial') if record.get(key)) + '\n\n' + description
    return _payload(library, dict(app='household', kind='record', id=key, title=record['title']), text, paths=[item['path'] for item in items], items=items, title=tr('Support: ') + record['title'])


def radio_bundle(library, key):
    record = library.get(key)
    sources = [dict(kind='source', title=item.get('title', ''), url=item.get('url', '')) for item in record.get('edition_sources', [])]
    text = record.get('script', '') + tr('\n\n## Quellen\n\n') + '\n'.join('- ' + item['title'] + ': ' + item['url'] for item in sources)
    paths = [str(library.asset(record['audio']))] if record.get('audio') else []
    return _payload(library, dict(app='radio', kind='record', id=key, title=record['title']), text, paths=paths, items=sources)


def radio_note(library, key, position, text):
    record = library.get(key)
    if type(position) is not int or not 0 <= position <= record.get('duration', 0):
        raise ValueError(tr('Ungültige Hörposition.'))
    if not text.strip():
        raise ValueError(tr('Bitte eine Hörnotiz eingeben.'))
    ref = dict(app='radio', kind='record', id=key, title=record['title'], position=dict(time=position))
    from interop_radio_audio import audio_source
    selected = audio_source(record, position)
    sources = [dict(kind='source', title=item.get('title', ''), url=item.get('url', '')) for item in ([selected] if selected else record.get('edition_sources', []))]
    return _payload(library, ref, text, items=sources, title=record['title'] + ' · ' + clock_text(position))


def radio_script_source(record, cursor, script):
    """Resolve exact generated script paragraphs; never guess audio timing."""
    if hashlib.sha256(script.encode()).hexdigest() != record.get('edition_script_hash'):
        return None
    return next((item for item in record.get('edition_sections', []) if item['start'] <= cursor < item['end']), None)


def knowledge_note(registry, url):
    """Read just the selected note, without following symlinks or loading a store."""
    from content_search import folder_fd
    from wissen_data import MAX_NOTE, parse
    ref = registry.resolve(url)
    relative = Path(ref['id'])
    root = Path(ref.get('locator', {}).get('root', ''))
    if (ref['app'] != 'wissen' or ref['kind'] != 'note' or not root.is_absolute()
            or relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.md'
            or any(part.startswith('.') for part in relative.parts)):
        raise ValueError(tr('Dieser Verweis zeigt nicht auf eine lokale Wissensnotiz.'))
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = folder_fd(root_fd, relative.parent)
        try:
            fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError(tr('Keine reguläre Notizdatei.'))
                raw = stream.read(MAX_NOTE + 1)
                if len(raw) > MAX_NOTE: raise ValueError(tr('Notiz größer als 1 MiB.'))
        finally: os.close(parent)
    finally: os.close(root_fd)
    return dict(parse(str(relative), raw), url=url)


def install_communications_menu(window):
    from interop_communication_ui import install
    install(window)
