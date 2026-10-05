"""Private records and bounded local media jobs for the standalone tools."""
from lumen_i18n import tr
import json
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit
from html.parser import HTMLParser


class Cancelled(Exception):
    pass


class Library:
    def __init__(self, name, root=None):
        self.root = Path(root or os.environ.get('LUMEN_TOOLS_DATA') or
                         Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'lumen-tools') / name
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.assets = self.root / 'assets'; self.assets.mkdir(exist_ok=True, mode=0o700)
        self.db = self.root / 'library.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL)')
        self.db.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10); db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def all(self, archived=False, query=''):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM records WHERE archived=? ORDER BY updated DESC', (int(archived),)).fetchall()
        records = [dict(id=r['id'], title=r['title'], **json.loads(r['data'])) for r in rows]
        return [r for r in records if query.casefold() in json.dumps(r, ensure_ascii=False).casefold()]

    def get(self, key):
        with self.connect() as db: row = db.execute('SELECT * FROM records WHERE id=?', (key,)).fetchone()
        if row is None: raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        return dict(id=row['id'], title=row['title'], _archived=bool(row['archived']), **json.loads(row['data']))

    def create(self, title, **data):
        title = title.strip()
        if not title: raise ValueError(tr('Bitte einen Namen angeben.'))
        if self.root.name=='workbench':
            from interop_paths import revision
            data.setdefault('interop_path_revision',revision(self.root.parent))
        key = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO records VALUES (?,?,?,?,?)', (key, title, json.dumps(data), 0, time.time()))
        return key

    def update(self, key, expected_updated=None, **changes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM records WHERE id=?', (key,)).fetchone()
            if row is None: raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
            if expected_updated is not None and (str(row['updated']) != expected_updated or row['archived']):
                raise ValueError('Project changed or archived. Read it again before editing.')
            title = changes.pop('title', row['title']).strip()
            if not title: raise ValueError(tr('Bitte einen Namen angeben.'))
            data = json.loads(row['data']); data.update(changes)
            db.execute('UPDATE records SET title=?, data=?, updated=? WHERE id=?', (title, json.dumps(data), time.time(), key))

    def archive(self, key, value=True):
        with self.connect() as db: db.execute('UPDATE records SET archived=? WHERE id=?', (int(value), key))

    def asset(self, name):
        if Path(name).name != name or not name: raise ValueError(tr('Ungültige lokale Datei.'))
        return self.assets / name

    def import_file(self, path, job, limit=2*1024**3):
        path = Path(path).expanduser()
        if not path.is_file(): raise ValueError(tr('Bitte eine reguläre Datei auswählen.'))
        if path.stat().st_size > limit: raise ValueError(tr('Datei zu groß (maximal {0} MB).' , limit//1024**2))
        name = uuid.uuid4().hex + path.suffix.lower()[:12]
        target = self.asset(name)
        try:
            with path.open('rb') as src, target.open('xb') as dst:
                total = 0
                while chunk := src.read(1024*1024):
                    job.check(); total += len(chunk)
                    if total > limit: raise ValueError(tr('Datei überschreitet das Importlimit.'))
                    dst.write(chunk)
                dst.flush(); os.fsync(dst.fileno())
            target.chmod(0o600)
            return dict(name=path.name, asset=name)
        except BaseException:
            target.unlink(missing_ok=True); raise


def clock_text(milliseconds):
    s = max(0, int(milliseconds)//1000)
    return f'{s//3600:02d}:{s//60%60:02d}:{s%60:02d}'


def validate_segments(value):
    result = []; previous = 0
    if not isinstance(value, list) or len(value) > 40000: raise ValueError(tr('Ungültiges Transkript.'))
    for item in value:
        start, end = item['offsets']['from'], item['offsets']['to']
        text = item['text']
        if not isinstance(start, int) or not isinstance(end, int) or start < previous or end < start or end > 8*3600000 or not isinstance(text, str):
            raise ValueError(tr('Ungültige Zeitmarken im Transkript.'))
        previous = start
        if text.strip(): result.append(dict(start=start, end=end, text=text.strip()))
    if not result: raise ValueError(tr('Keine Sprache erkannt. Aufnahme und Sprache prüfen.'))
    return result


def media_duration(path, job):
    data = json.loads(job.command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)]))
    duration = float(data['format']['duration'])
    if not 0 < duration <= 8*3600: raise ValueError(tr('Aufnahmen dürfen höchstens acht Stunden lang sein.'))
    return round(duration*1000)


def transcribe(path, settings, job):
    from lumen_setup import executable
    from lumen_speech import transcription_arguments
    model = settings.value('speechModel', '')
    binary = executable('whisper-cli')
    if not binary or not model or not Path(model).is_file():
        raise ValueError(tr('Die lokale Spracherkennung fehlt. Über Einrichtung das Diktat installieren.'))
    with tempfile.TemporaryDirectory(prefix='lumen-meeting-') as tmp:
        wav, output = Path(tmp)/'audio.wav', Path(tmp)/'transcript'
        job.progress.emit(tr('Audio wird für die lokale Erkennung vorbereitet …'))
        job.command(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(wav)], timeout=1800)
        args = transcription_arguments(settings, wav, output, model)
        # Whisper's -nt suppresses segment timestamps in inference, not just logs.
        args.remove('-nt'); args.remove('-otxt'); args += ['-oj']
        job.progress.emit(tr('Sprache wird lokal erkannt … Bei langen Aufnahmen kann das dauern.'))
        job.command([binary] + args, timeout=8*3600)
        return validate_segments(json.loads(output.with_suffix('.json').read_text())['transcription'])


def document_text(path, job):
    path = Path(path); suffix = path.suffix.lower()
    if suffix == '.pdf':
        text = job.command(['pdftotext', '-enc', 'UTF-8', str(path), '-'], timeout=90).decode(errors='replace')
        pages=text.split('\f'); pages=pages[:-1] if pages[-1]=='' else pages
        if any(len(page.strip())<20 for page in pages):
            value=json.loads(job.command([sys.executable,str(Path(__file__)),'ocr',str(path)],data=text.encode(),timeout=3600))
            text=value['text']
            if value['partial']: raise ValueError(tr('Scan zu lang; bitte in Dokumente mit höchstens 80 Seiten teilen.'))
    elif suffix in {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'}:
        text=json.loads(job.command([sys.executable,str(Path(__file__)),'ocr',str(path)],timeout=120))['text']
    elif suffix in {'.txt', '.md', '.csv'}:
        if path.stat().st_size > 2*1024**2: raise ValueError(tr('Textdatei zu groß (maximal 2 MB).'))
        text = path.read_text(encoding='utf-8-sig', errors='replace')
    else:
        raise ValueError(tr('Textimport unterstützt PDF, TXT, Markdown und Bilder mit Texterkennung.'))
    job.check()
    if len(text) > 120000: raise ValueError(tr('Mehr als 120.000 Zeichen; bitte einen kürzeren Auszug importieren.'))
    if not text.strip(): raise ValueError(tr('Kein lesbarer Text gefunden.'))
    return text.strip()


def web_url(value):
    value = value.strip(); url = urlsplit(value)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
        raise ValueError(tr('Bitte eine HTTP(S)-Adresse ohne Zugangsdaten angeben.'))
    return value


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.hidden = 0; self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'): self.hidden += 1
        if tag in ('p', 'div', 'article', 'section', 'h1', 'h2', 'li', 'br'): self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'): self.hidden = max(0, self.hidden-1)
        if tag in ('p', 'div', 'article', 'section', 'li'): self.parts.append('\n')

    def handle_data(self, text):
        if not self.hidden: self.parts.append(text)

    def text(self):
        return '\n'.join(line.strip() for line in ''.join(self.parts).splitlines() if line.strip())


def fetch_article(address, job):
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, target):
            web_url(target)
            return super().redirect_request(request, fp, code, msg, headers, target)
    address = web_url(address)
    with build_opener(Redirect()).open(Request(address, headers={'User-Agent':'Lumen-Radio/1.0', 'Accept':'text/html,text/plain'}), timeout=20) as response:
        mime = response.headers.get_content_type()
        if mime not in ('text/html', 'text/plain'): raise ValueError(tr('Keine Artikelseite. Dokument stattdessen als Datei importieren.'))
        raw = response.read(2*1024**2+1); job.check()
        if len(raw) > 2*1024**2: raise ValueError(tr('Seite zu groß. Bitte relevanten Text einfügen.'))
        text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        if mime == 'text/html':
            parser = ArticleParser(); parser.feed(text); text = parser.text()
        if not text.strip() or len(text) > 120000: raise ValueError(tr('Kein geeigneter Artikeltext. Bitte einen Auszug einfügen.'))
        return dict(title=urlsplit(address).hostname, url=response.geturl(), text=text.strip(), selected=True)


def selected_sources(sources):
    chosen = [s for s in sources if s.get('selected', True)]
    if not chosen: raise ValueError(tr('Bitte mindestens eine Quelle auswählen.'))
    if sum(len(s['text']) for s in chosen) > 70000:
        raise ValueError(tr('Die gewählten Quellen enthalten mehr als 70.000 Zeichen. Bitte weniger Quellen wählen oder kürzen.'))
    return chosen


def parse_answer(answer):
    value = answer.strip()
    if value.startswith('```'):
        value = value.split('\n', 1)[1].rsplit('```', 1)[0]
    data = json.loads(value)
    if not isinstance(data, dict): raise ValueError(tr('Die KI-Antwort hat kein gültiges Format.'))
    return data


def meeting_result(answer, count):
    data = parse_answer(answer)
    if not isinstance(data.get('summary'), str): raise ValueError(tr('Zusammenfassung fehlt.'))
    for name in ('decisions', 'actions'):
        if not isinstance(data.get(name), list) or len(data[name]) > 200: raise ValueError(tr('Ungültige Ergebnisliste.'))
        for row in data[name]:
            if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not isinstance(row.get('segment'), int) or not 0 <= row['segment'] < count:
                raise ValueError(tr('Ergebnis ohne gültige Transkriptstelle; bitte erneut erzeugen.'))
    return data


def synthesize(text, library, job):
    from lumen_tts import available, command, prepare_text
    import wave
    if not available(): raise ValueError(tr('Die lokale Stimme fehlt. Über Einrichtung den Sprachdialog installieren.'))
    if not text.strip() or len(text) > 24000: raise ValueError(tr('Das Hörskript muss 1 bis 24.000 Zeichen enthalten.'))
    name = uuid.uuid4().hex + '.wav'; path = library.asset(name)
    try:
        job.command(command(path), data=(prepare_text(text)+'\n').encode(), timeout=1800)
        with wave.open(str(path)) as audio: duration = round(audio.getnframes()/audio.getframerate()*1000)
        if duration <= 0: raise ValueError(tr('Keine Audiodaten erzeugt.'))
        path.chmod(0o600); return dict(audio=name, duration=duration)
    except BaseException:
        path.unlink(missing_ok=True)
        path.with_name(path.name+'.partial').unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    # Run existing OCR in a child group so cancelling also stops its decoders.
    if len(sys.argv)!=3 or sys.argv[1]!='ocr': raise SystemExit(tr('Nur interne Texterkennung.'))
    from lumen_ocr import image_text, visual_content
    source=Path(sys.argv[2])
    if source.suffix.lower()=='.pdf':
        content,partial,_=visual_content(source,text=sys.stdin.read(),ocr=True)
    else: content,partial=image_text(source),False
    print(json.dumps(dict(text=content,partial=partial)))
