"""Bounded, selection-first handoff payloads from the native Lumen windows.

Capture reads widgets and the current record only. It neither saves a window nor
calls a provider. MIME attachment extraction is a separate cancellable worker.
Pages are zero based and audio positions are milliseconds, as in the source apps.
"""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import Qt
from lumen_i18n import tr
from interop_parts import capture_part


MAX_TEXT = 120000
MAX_PATHS = 100
MAX_ITEMS = 1000
MAX_PAYLOAD = 512 * 1024


def source_title(source):
    title=source.get('title') or tr('Original öffnen')
    page=source.get('position',{}).get('page')
    if page is not None:title+=tr(' · Seite {0}',page+1)
    return title


def _text(widget):
    return widget.toPlainText() if hasattr(widget, 'toPlainText') else widget.text()


def _selected(widget):
    if widget is None or not hasattr(widget, 'textCursor'):
        return ''
    return widget.textCursor().selectedText().replace('\u2029', '\n')


def _focused(window, widget):
    if widget is None:return False
    focus = getattr(window, '_interop_focus', None) or window.focusWidget()
    return focus is widget or bool(focus and widget.isAncestorOf(focus))


def _item_data(widget, tree=False):
    item = widget.currentItem()
    return item.data(0, Qt.UserRole) if item and tree else item.data(Qt.UserRole) if item else None


def _url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def _file_url(value):
    parsed = urlsplit(value)
    return unquote(parsed.path) if parsed.scheme == 'file' and not parsed.netloc else ''


def _path(value, existing=True):
    if not isinstance(value, (str, Path)) or not str(value) or '\0' in str(value):
        return ''
    path = Path(value).expanduser()
    if not path.is_absolute() or (existing and not (path.is_file() or path.is_dir())):
        return ''
    return str(path.absolute())


def _asset(window, name):
    return _path(window.library.asset(name)) if name else ''


def _ref(app, key, title, kind='record', **extra):
    return dict(app=app, kind=kind, id=str(key), title=str(title), **extra)


def _payload(source, text='', paths=(), items=(), url=''):
    result = dict(title=source['title'], text=text, paths=list(dict.fromkeys(p for p in paths if p)), source=source, items=list(items))
    if _url(url):
        result['url'] = url
    return result


def _bounded(payload):
    if len(payload.get('text', '')) > MAX_TEXT or len(payload.get('items', [])) > MAX_ITEMS:
        raise ValueError(tr('Bitte einen kürzeren Auszug auswählen.'))
    if len(payload.get('paths', [])) > MAX_PATHS or len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_PAYLOAD:
        raise ValueError(tr('Bitte weniger Inhalte für die Übergabe auswählen.'))
    return payload


def from_paths(paths):
    """Capture explicit Files selections without scanning folders or reading files."""
    values = []
    for value in paths:
        path = _path(value)
        if not path:
            raise ValueError(tr('Bitte eine vorhandene lokale Datei oder einen Ordner auswählen.'))
        if path not in values:
            values.append(path)
        if len(values) > MAX_PATHS:
            raise ValueError(tr('Bitte höchstens 100 Dateien auswählen.'))
    if not values:
        raise ValueError(tr('Zuerst eine Datei auswählen.'))
    first = Path(values[0])
    source = _ref('files', str(first), first.name or str(first), 'file', path=str(first))
    items = [dict(kind='file', title=Path(path).name or path, path=path, directory=Path(path).is_dir()) for path in values]
    result = _payload(source, paths=values, items=items)
    if len(values) > 1:
        result['title'] = tr('{0} ausgewählte Dateien', len(values))
    return _bounded(result)


def _reader(window, record):
    source = _ref('reader', record['id'], record['title'], path=_asset(window, record.get('asset')))
    if _focused(window,getattr(window,'entries',None)):
        return _payload(source,paths=[source['path']])
    page = max(0, window.page_index)
    selected, words, selection = window.selection()
    if _focused(window,getattr(window,'notes',None)) or _focused(window,window.note):selected=''
    from reader_data import ENGINE
    position = dict(page=page,engine=ENGINE)
    source['position'] = position
    if selected:
        if selection:
            position.update(start=selection[0], end=selection[1])
        elif words:
            position['part'] = 'words:' + str(words[0]) + ':' + str(words[-1])
        return _payload(source, selected, items=[dict(kind='quote', text=selected, page=page, words=words, selection=selection)])
    note = next((n for n in record.get('notes', []) if n.get('id') == window.note_id), None)
    if note:
        position.update(page=note['page'], note=note['id'])
        annotation = _selected(window.note) or _text(window.note)
        text = '\n\n'.join(value for value in (note.get('text', ''), annotation) if value)
        return _payload(source, text, items=[dict(kind='note', id=note['id'], text=note.get('text', ''), note=annotation, page=note['page'])])
    text = _text(window.text)
    return _payload(source, text, paths=[source['path']], items=[dict(kind='page', page=page, pages=record.get('pages', 0))], url=record.get('url', ''))


def _wissen(window):
    if not window.book:
        raise ValueError(tr('Zuerst eine Notiz öffnen.'))
    root = str(window.book.root)
    if window.doc and not _focused(window, window.collections):
        note = window.doc
        path = _path(Path(root) / note['path'])
        source = _ref('wissen', note['path'], _text(window.title) or note['title'], 'note', path=path, locator=dict(root=root, area=window.area))
        selected = '' if _focused(window,getattr(window,'entries',None)) else _selected(window.editor)
        if selected:
            cursor = window.editor.textCursor()
            source['position'] = dict(start=cursor.selectionStart(), end=cursor.selectionEnd())
        return _payload(source, selected or window.document_text(), paths=[] if selected else [path], items=[dict(kind='note', title=source['title'], path=path, tags=list(note.get('tags', [])))])
    notes = [note for note in window.notes.values() if window.in_collection(note)]
    if not notes:
        raise ValueError(tr('Zuerst eine Notiz öffnen.'))
    title = window.collections.currentItem().text() if window.collections.currentItem() else tr('Alle Notizen')
    source = _ref('wissen', 'collection:' + window.collection, title, 'collection', locator=dict(root=root, area=window.area))
    paths = [_path(Path(root) / note['path']) for note in notes]
    items = [dict(kind='note', title=note['title'], path=path, tags=list(note.get('tags', []))) for note, path in zip(notes, paths)]
    return _payload(source, paths=paths, items=items)


def _inbox(window):
    tab = window.tabs.currentIndex()
    if tab == 3:
        task = _item_data(window.tasks, True)
        if not task:
            raise ValueError(tr('Zuerst eine Aufgabe auswählen.'))
        item = dict(kind='task', title=task['title'], text=task['title'], due=task.get('due', ''), done=bool(task.get('done')))
        return _payload(_ref('inbox', task['id'], task['title'], 'task'), task['title'], items=[item])
    if tab == 2:
        draft = _item_data(window.drafts, True)
        if not draft:
            raise ValueError(tr('Zuerst einen Entwurf auswählen.'))
        values = json.loads(draft['data'])
        items = [dict(kind='draft', title=values.get('subject', ''), to=values.get('to', ''), status=draft['status'])]
        return _payload(_ref('inbox', draft['id'], values.get('subject', '') or tr('Entwurf'), 'draft', locator=dict(account=draft['account'])), values.get('body', ''), items=items)
    if tab == 1:
        event = _item_data(window.events, True)
        if not event:
            raise ValueError(tr('Zuerst einen Termin auswählen.'))
        item = dict(kind='event', **{key: event.get(key, '') for key in ('title', 'start', 'end', 'location', 'description')})
        source = _ref('inbox', event['uid'] + '|' + event['start'], event['title'], 'event', locator=dict(account=event['account']))
        text = '\n\n'.join(str(item[key]) for key in ('title', 'start', 'end', 'location', 'description') if item[key])
        return _payload(source, text, items=[item])
    message = window.message
    if not message:
        raise ValueError(tr('Zuerst eine Nachricht auswählen.'))
    locator = {key: message[key] for key in ('account', 'folder', 'validity', 'uid')}
    identity = json.dumps(locator, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    source = _ref('inbox', hashlib.sha256(identity.encode()).hexdigest(), message['subject'] or tr('Nachricht'), 'message', locator=locator)
    if _focused(window, window.attachments) and window.attachments.currentIndex() >= 0:
        index = window.attachments.currentData()
        source['position'] = dict(part='attachment:' + str(index))
        name = window.attachments.currentText()
        payload = _payload(source, items=[dict(kind='attachment', title=name, index=index)])
        payload['title'] = name
        return payload
    text = _selected(window.reader) or _text(window.reader)
    if _selected(window.reader):
        cursor=window.reader.textCursor();source['position']=dict(start=cursor.selectionStart(),end=cursor.selectionEnd())
    items = [dict(kind='message', title=source['title'], sender=message.get('sender', ''), sent=message.get('sent', ''), thread=message.get('thread', ''))]
    return _payload(source, text, items=items)


def materialize(payload, job, root=None):
    """On a worker, copy only an explicitly selected cached MIME attachment.

    This never fetches mail, reads credentials, or changes the cached message.
    Content-addressed files are private and repeated handoffs reuse the same copy.
    """
    source = payload.get('source', {})
    part = source.get('position', {}).get('part', '')
    if source.get('app') != 'inbox' or source.get('kind') != 'message' or not part.startswith('attachment:'):
        return payload
    from email import policy
    from email.parser import BytesParser
    from inbox_data import MAX_MAIL, store
    try:
        index = int(part.split(':', 1)[1])
        locator = source['locator']
        values = tuple(locator[key] for key in ('account', 'folder', 'validity', 'uid'))
    except (ValueError, KeyError, TypeError):
        raise ValueError(tr('Anhang nicht mehr verfügbar.')) from None
    library = store(root)
    job.check()
    with library.connect() as db:
        row = db.execute('SELECT raw FROM messages WHERE account=? AND folder=? AND validity=? AND uid=?', values).fetchone()
    if not row or len(row['raw']) > MAX_MAIL:
        raise ValueError(tr('Anhang zu groß oder nicht lesbar.'))
    message = BytesParser(policy=policy.default).parsebytes(row['raw'])
    parts = list(message.iter_attachments())
    if not 0 <= index < len(parts):
        raise ValueError(tr('Anhang nicht mehr verfügbar.'))
    selected = parts[index]
    data = selected.get_payload(decode=True)
    if data is None or len(data) > MAX_MAIL:
        raise ValueError(tr('Anhang zu groß oder nicht lesbar.'))
    name = Path((selected.get_filename() or tr('Anhang')).replace('\\', '/')).name
    suffix = Path(name).suffix.lower()[:12]
    path = library.asset('handoff-' + hashlib.sha256(data).hexdigest() + suffix)
    job.check()
    created = False
    try:
        try:
            with path.open('xb') as stream:
                created = True
                os.fchmod(stream.fileno(), 0o600)
                for offset in range(0, len(data), 1024 * 1024):
                    job.check()
                    stream.write(data[offset:offset + 1024 * 1024])
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError(tr('Die lokale Übergabekopie wurde verändert.')) from None
        job.check()
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise
    result = dict(payload, paths=[str(path)], items=[dict(kind='attachment', title=name, path=str(path), index=index, size=len(data), mime=selected.get_content_type())])
    return _bounded(result)


def _selected_rows(table):
    return sorted({item.row() for item in table.selectedItems()})


def _meetings(window, record):
    from tools_data import clock_text
    source = _ref('meetings', record['id'], _text(window.title) or record['title'])
    recording = _asset(window, (record.get('recording') or {}).get('asset'))
    if recording:
        source['path'] = recording
    segments = []
    for index in range(window.transcript.rowCount()):
        stamp = window.transcript.item(index, 0).data(Qt.UserRole)
        segments.append(dict(kind='segment', text=window.transcript.item(index, 1).text(), start=stamp['start'], end=stamp['end'], index=index))
    results = []
    for index in range(window.results.rowCount()):
        kind = window.results.item(index, 0)
        segment = window.results.item(index, 2).data(Qt.UserRole)
        item = dict(kind='task' if kind.data(Qt.UserRole) == 'actions' else 'decision', text=window.results.item(index, 1).text(), segment=segment, done=kind.checkState() == Qt.Checked)
        if 0 <= segment < len(segments):
            item['time'] = segments[segment]['start']
        previous = record.get('results', [])
        if index < len(previous) and previous[index].get('due'):
            item['due'] = previous[index]['due']
        results.append(item)
    if window.tabs.currentIndex() == 2 and hasattr(window, 'agenda'):
        text = _selected(window.agenda) or _text(window.agenda)
        source['position'] = dict(part='agenda')
        return _payload(source, text, items=[dict(kind='agenda', text=text)])
    if window.tabs.currentIndex() == 0:
        selected = _selected_rows(window.transcript)
        if selected:
            parts = [segments[index] for index in selected]
            source['position'] = dict(time=parts[0]['start'], part=capture_part(window, 'segment', selected[0]))
            return _payload(source, '\n\n'.join('[' + clock_text(p['start']) + '] ' + p['text'] for p in parts), items=parts)
    else:
        text = _selected(window.summary)
        if text:
            return _payload(source, text, items=[dict(kind='summary', text=text)])
        selected = _selected_rows(window.results)
        if selected:
            parts = [results[index] for index in selected]
            source['position'] = dict(time=parts[0].get('time', 0), part=capture_part(window, 'result', selected[0]))
            return _payload(source, '\n'.join(p['text'] for p in parts), items=parts)
    summary = _text(window.summary)
    agenda = _text(window.agenda) if hasattr(window, 'agenda') else record.get('agenda', '')
    text = '\n\n'.join(p for p in (agenda, summary, '\n'.join(p['text'] for p in results), '\n\n'.join('[' + clock_text(p['start']) + '] ' + p['text'] for p in segments)) if p)
    items = ([dict(kind='agenda', text=agenda)] if agenda else []) + results + segments
    return _payload(source, text, paths=[recording], items=items)


def _attachment(window, value):
    path = _asset(window, value.get('asset'))
    return dict(kind='attachment', title=value.get('name', ''), path=path, text=value.get('text', ''))


def _household(window, record):
    source = _ref('household', record['id'], _text(window.title) or record['title'])
    selected = _selected(window.notes)
    if selected:
        return _payload(source, selected)
    attachment = _item_data(window.attachments)
    if attachment:
        item = _attachment(window, attachment)
        source['position'] = dict(part='attachment:' + attachment['asset'])
        payload = _payload(source, item['text'], paths=[item['path']], items=[item])
        payload['title'] = item['title']
        return payload
    details = dict(kind='household', title=source['title'], type=window.kind.currentData())
    details.update({key: _text(field) for key, field in window.fields.items()})
    details.update({key: field.date().toString('yyyy-MM-dd') if field.date() > field.minimumDate() else '' for key, field in window.dates.items()})
    items = [_attachment(window, window.attachments.item(i).data(Qt.UserRole)) for i in range(window.attachments.count())]
    text = '\n'.join(str(key) + ': ' + str(value) for key, value in details.items() if key != 'kind' and value) + '\n\n' + _text(window.notes)
    return _payload(source, text, paths=[item['path'] for item in items], items=[details] + items)


def _resource(value):
    target = value.get('target', '')
    return dict(kind='resource', title=value.get('title', ''), path=_path(target) if value.get('kind') == 'file' else '', url=_url(target) if value.get('kind') == 'url' else '')


def _workbench(window, record):
    if hasattr(window,'interop_payload'): return window.interop_payload()
    source = _ref('workbench', record['id'], _text(window.title) or record['title'])
    if window.tabs.currentIndex() == 1 and window.resources.currentItem():
        item = _resource(_item_data(window.resources))
        source['position'] = dict(part=capture_part(window, 'resource', window.resources.currentRow()))
        payload = _payload(source, item['title'] + '\n' + (item['path'] or item['url']), paths=[item['path']], items=[item], url=item['url'])
        payload['title'] = item['title']
        return payload
    if window.tabs.currentIndex() == 0:
        selected = _selected(window.notes)
        if selected:
            return _payload(source, selected)
        question = window.questions.currentItem()
        if question:
            item = dict(kind='question', text=question.text(), done=question.checkState() == Qt.Checked)
            source['position'] = dict(part=capture_part(window, 'question', window.questions.currentRow()))
            return _payload(source, question.text(), items=[item])
    questions = [dict(kind='question', text=window.questions.item(i).text(), done=window.questions.item(i).checkState() == Qt.Checked) for i in range(window.questions.count())]
    materials = [_resource(window.resources.item(i).data(Qt.UserRole)) for i in range(window.resources.count())]
    text = '\n\n'.join(p for p in (_text(window.notes), '\n'.join(('- [x] ' if q['done'] else '- [ ] ') + q['text'] for q in questions), '\n'.join(item['title'] + ': ' + (item['path'] or item['url']) for item in materials)) if p)
    return _payload(source, text, paths=[item['path'] for item in materials], items=questions + materials)


def _radio(window, record):
    source = _ref('radio', record['id'], _text(window.title) or record['title'])
    if window.tabs.currentIndex() == 0 and window.sources.currentItem():
        original = _item_data(window.sources)
        text = _selected(window.source_text) or _text(window.source_text)
        title = _text(window.source_title) or original.get('title', '')
        url = _url(original.get('url', ''))
        path = _path(_file_url(original.get('url', '')))
        source['position'] = dict(part=capture_part(window, 'source', window.sources.currentRow()))
        item = dict(kind='source', title=title, text=text, url=url, path=path)
        payload = _payload(source, text, paths=[] if _selected(window.source_text) else [path], items=[item], url=url)
        payload['title'] = title
        return payload
    text = _selected(window.script) or _text(window.script)
    position = max(0, int(window.player.position))
    source['position'] = dict(time=position)
    items = [dict(kind='source', title=value.get('title', ''), url=_url(value.get('url', ''))) for value in record.get('edition_sources', [])]
    selected = _selected(window.script)
    if selected:
        cursor = window.script.textCursor()
        source['position'].update(start=cursor.selectionStart(), end=cursor.selectionEnd())
    return _payload(source, text, paths=[] if selected else [_asset(window, record.get('audio'))], items=items)


def _vault(window, record):
    source = _ref('vault', record['id'], record['title'])
    selected = window.sources.currentItem()
    if selected and _focused(window, window.sources):
        path = _path(selected.text())
        return _payload(source, selected.text(), paths=[path], items=[dict(kind='file', path=path)])
    snapshot = _item_data(window.snapshots, True)
    if snapshot:
        source['position'] = dict(part='snapshot:' + snapshot)
        return _payload(source, '\n'.join(window.snapshots.currentItem().text(i) for i in range(2)), items=[dict(kind='snapshot', id=snapshot)])
    items = [dict(kind='backup_source', path=path) for path in record.get('sources', [])]
    return _payload(source, '\n'.join(record.get('sources', [])), items=items)


def _sound(window, record):
    source = _ref('sound', record['id'], record['title'])
    selected = _item_data(window.rules, True)
    rules = record.get('rules', {})
    keys = [selected] if selected in rules else list(rules)
    items = [dict(kind='audio_rule', app=key, **{field: rules[key].get(field, '') for field in ('title', 'volume', 'mute', 'sink', 'role')}) for key in keys]
    if selected in rules:
        source['position'] = dict(part=capture_part(window, 'rule', window.rules.indexOfTopLevelItem(window.rules.currentItem())))
    text = '\n'.join(str(item['title']) + ': ' + str(item['volume']) + ' % · ' + str(item['sink']) for item in items)
    return _payload(source, text, items=items)


def capture(window):
    """Capture the active object, preferring selected text or selected subobjects."""
    name = getattr(window, 'name', '')
    if name == 'wissen':
        return _bounded(_wissen(window))
    if name not in _CAPTURES:
        selected = getattr(window, 'selected_paths', None)
        if callable(selected):
            return from_paths(selected())
        raise ValueError(tr('Diese Ansicht unterstützt keine Übergabe.'))
    if name == 'inbox':
        return _bounded(_inbox(window))
    if not window.current:
        raise ValueError(tr('Zuerst einen Eintrag auswählen.'))
    record = window.library.get(window.current)
    return _bounded(_CAPTURES[name](window, record))


def _translate(window, record):
    editor = window.input if _focused(window, window.input) else window.output
    text = _selected(editor) or _text(editor) or record.get('source', '')
    paths = []
    if window.tabs.currentIndex() == 1:
        asset = record.get('pdf_result') or record.get('document_asset')
        if asset: paths = [str(window.library.asset(asset))]
    return _payload(_ref('translate', record['id'], record['title']), text=text, paths=paths)


_CAPTURES = dict(translate=_translate, reader=_reader, inbox=_inbox, meetings=_meetings, household=_household,
                 workbench=_workbench, radio=_radio, vault=_vault, sound=_sound)
