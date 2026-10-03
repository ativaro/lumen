"""Reading progress, exact source marks, conservative refresh and local page OCR."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from lumen_i18n import tr
from tools_data import Library, document_text
from interop_data import Registry, validate_payload
import reader_data


def original_path(record):
    if record.get('original_path'): return Path(record['original_path'])
    source = urlsplit(record.get('source', ''))
    if source.scheme == 'file' and not source.netloc: return Path(unquote(source.path))
    return None


def progress_for_paths(paths, root=None):
    wanted = {str(Path(path).absolute()) for path in paths}; result = {path: [] for path in wanted}
    for record in Library('reader', root).all():
        path = original_path(record)
        if path is None or str(path) not in wanted: continue
        page, pages = record.get('page', 0), record.get('pages', 0)
        result[str(path)].append(dict(id=record['id'], title=record['title'], page=page, pages=pages,
                                      progress=round(100*(page+1)/pages) if pages else 0, marks=len(record.get('notes', []))))
    return result


def marks_payload(library, key, chapter=False, registry=None):
    record = library.get(key); registry = registry or Registry(library.root.parent)
    start, end = 0, record.get('pages', 1); title = record['title']
    if chapter:
        toc = record.get('toc', []); current = record.get('page', 0)
        active = next((i for i in range(len(toc)-1, -1, -1) if toc[i][2]-1 <= current), None)
        if active is not None:
            level, heading, page = toc[active]; start = max(0, page-1); title += ' · '+heading
            end = next((max(0, row[2]-1) for row in toc[active+1:] if row[0] <= level), end)
    notes = [note for note in record.get('notes', []) if start <= note['page'] < end]
    if not notes: raise ValueError(tr('In dieser Auswahl gibt es noch keine Markierungen.'))
    source = dict(app='reader', kind='record', id=key, title=record['title'], path=str(library.asset(record['asset'])), position=dict(page=start))
    lines, items = [], []
    for note in notes:
        ref = dict(source, position=dict(page=note['page'], note=note['id']))
        url = registry.register(ref)
        lines += [tr('## Seite ')+str(note['page']+1), note.get('text', ''), note.get('note', ''), url]
        items.append(dict(kind='note', title=record['title'], text=note.get('text', ''), note=note.get('note', ''), page=note['page'], url=url))
    return validate_payload(dict(title=title+tr(' · Markierungen'), text='\n\n'.join(lines), paths=[], source=source,
                                 source_url=registry.register(source), items=items))


def marks_from_books(library,keys):
    if not 1<=len(keys)<=30:raise ValueError(tr('Zwischen einem und 30 Dokumenten auswählen.'))
    payloads=[marks_payload(library,key) for key in dict.fromkeys(keys)]
    result=dict(payloads[0]);result['title']=tr('Markierungen aus {0} Dokumenten',len(payloads))
    result['text']='\n\n'.join('# '+p['title']+'\n'+p['text'] for p in payloads)
    result['items']=[dict(kind='source',title=p['title'],text=p['text'],url=p['source_url']) for p in payloads]
    return validate_payload(result)


def send_book_marks(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QListWidget,QListWidgetItem,QDialogButtonBox
    from interop_ui import with_saved,reviewed_send
    def choose():
        dialog=QDialog(window);dialog.setWindowTitle(tr('Markierungen mehrerer Dokumente'));dialog.resize(580,420)
        layout=QVBoxLayout(dialog);listing=QListWidget();layout.addWidget(listing)
        for record in window.library.all():
            if not record.get('notes'):continue
            item=QListWidgetItem(record['title']);item.setData(Qt.UserRole,record['id']);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Unchecked);listing.addItem(item)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()!=QDialog.Accepted:return
        keys=[listing.item(i).data(Qt.UserRole) for i in range(listing.count()) if listing.item(i).checkState()==Qt.Checked]
        reviewed_send(window,marks_from_books(window.library,keys),'radio.add')
    with_saved(window,choose)


def _hash(path, job):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024*1024): job.check(); digest.update(chunk)
    job.check(); return digest.hexdigest()


def compare_original(library, key, job):
    record = library.get(key); source = original_path(record)
    if source is None or not source.is_file(): raise ValueError(tr('Die lokale Originaldatei ist nicht erreichbar.'))
    copy = library.asset(record['asset'])
    if record.get('stamp') != [copy.stat().st_size, copy.stat().st_mtime_ns]:
        raise ValueError(tr('Die Lesekopie wurde extern geändert. Als neue Datei importieren, damit Markierungen korrekt bleiben.'))
    if source.stat().st_size > reader_data.MAX_FILE: raise ValueError(tr('Lesedatei fehlt oder ist größer als 200 MiB.'))
    return dict(path=str(source), changed=_hash(source, job) != _hash(library.asset(record['asset']), job))


def _fingerprints(path, password=''):
    import pymupdf
    document = reader_data.opened(path, password)
    if document is None: raise ValueError(tr('Zum Vergleichen das Dokument zuerst entsperren.'))
    with document:
        if len(document) > 500: raise ValueError(tr('Zum sicheren Abgleich Dokumente mit höchstens 500 Seiten verwenden.'))
        values = []
        for page in document:
            # Word indices/positions and visible appearance must match before existing marks move.
            words = page.get_text('words', sort=True)
            scale = min(.2, 600/max(page.rect.width, 1), 600/max(page.rect.height, 1))
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, colorspace=pymupdf.csRGB)
            digest = hashlib.sha256(json.dumps([list(page.rect), words]).encode()); digest.update(pixmap.samples)
            values.append(digest.hexdigest())
        return dict(fingerprints=values, pages=len(document), toc=document.get_toc()[:2000], locked=False)


def refresh_original(library, key, job, password=''):
    record = library.get(key); status = compare_original(library, key, job)
    if not status['changed']: return dict(id=key, changed=False)
    source = Path(status['path'])
    if source.suffix.lower() not in ('.pdf', '.epub', '.txt', '.md'):
        raise ValueError(tr('Dieses Format als neue Lesekopie öffnen. Automatischer Abgleich unterstützt PDF, EPUB, Text und Markdown.'))
    before = [source.stat().st_size, source.stat().st_mtime_ns]
    asset = library.import_file(source, job, limit=reader_data.MAX_FILE)['asset']; path = library.asset(asset)
    try:
        if before != [source.stat().st_size, source.stat().st_mtime_ns]: raise ValueError(tr('Die Originaldatei wurde während des Imports verändert.'))
        data = json.loads(job.command([sys.executable, str(Path(__file__))], data=json.dumps(dict(old=str(library.asset(record['asset'])), new=str(path), password=password)).encode(), timeout=180, max_output=4*1024**2))
        old, new = data['old']['fingerprints'], data['new']['fingerprints']; counts, previous = Counter(new), Counter(old)
        mapping = {i: new.index(value) for i, value in enumerate(old) if counts[value] == previous[value] == 1}
        needed = {record.get('page', 0)} | {note['page'] for note in record.get('notes', [])}
        if any(page not in mapping for page in needed):
            raise ValueError(tr('Lesestand oder Markierungen lassen sich nicht eindeutig zuordnen. Die bisherige Lesekopie bleibt erhalten; das Original separat öffnen.'))
        notes = [dict(note, page=mapping[note['page']]) for note in record.get('notes', [])]
        ocr = {str(mapping[int(page)]): text for page, text in record.get('ocr_text', {}).items() if int(page) in mapping}
        job.check()
        with library.connect() as db:
            db.execute('BEGIN IMMEDIATE'); row = db.execute('SELECT data FROM records WHERE id=?', (key,)).fetchone()
            current = json.loads(row['data']) if row else {}
            if current.get('asset') != record['asset'] or current.get('notes', []) != record.get('notes', []):
                raise ValueError(tr('Die Lesekopie wurde während des Abgleichs geändert. Erneut prüfen.'))
            current.update(asset=asset, notes=notes, page=mapping[record.get('page', 0)], ocr_text=ocr,
                           stamp=[path.stat().st_size, path.stat().st_mtime_ns], original_stamp=before,
                           **{field: data['new'][field] for field in ('pages', 'toc', 'locked')})
            db.execute('UPDATE records SET data=? WHERE id=?', (json.dumps(current), key))
        try: library.asset(record['asset']).unlink(missing_ok=True)
        except OSError: pass  # A leftover old copy is preferable to losing the newly committed document.
        return dict(id=key, changed=True, pages=data['new']['pages'])
    except BaseException: path.unlink(missing_ok=True); raise


def ocr_page(library, key, page, job, password=''):
    record = library.get(key)
    rendered = reader_data.worker(job, 'page', library.asset(record['asset']), page=page, password=password, stamp=record['stamp'])
    if rendered.get('locked'): raise ValueError(tr('Die Seite zuerst entsperren.'))
    with tempfile.TemporaryDirectory(prefix='lumen-reader-ocr-') as directory:
        image = Path(directory)/'page.png'; image.write_bytes(base64.b64decode(rendered['png']))
        text = document_text(image, job)
    job.check()
    with library.connect() as db:
        db.execute('BEGIN IMMEDIATE'); row = db.execute('SELECT data FROM records WHERE id=?', (key,)).fetchone()
        current = json.loads(row['data']) if row else {}
        if current.get('asset') != record['asset']: raise ValueError(tr('Die Lesekopie wurde während der Texterkennung geändert.'))
        current.setdefault('ocr_text', {})[str(page)] = text
        db.execute('UPDATE records SET data=? WHERE id=?', (json.dumps(current), key))
    return text


def search_ocr(record, query):
    needle = query.strip().casefold()
    if not needle: return []
    result = []
    for page, text in record.get('ocr_text', {}).items():
        offset = text.casefold().find(needle)
        if offset >= 0: result.append(dict(page=int(page), text=text[max(0, offset-60):offset+180].replace('\n', ' ')))
    return result[:100]


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        print(json.dumps({key: _fingerprints(request[key], request.get('password', '')) for key in ('old', 'new')}))
    except Exception as error:
        print(str(error)[:600], file=sys.stderr); sys.exit(1)
