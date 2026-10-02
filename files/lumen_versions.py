"""Opt-in, content-addressed file history, sampled independently of the UI."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from lumen_store import Store
from lumen_offline import digest, replace_file, scan

KEY = 'versions/config'
DEFAULT = {'roots': [], 'interval': 30, 'copies': 20, 'days': 90, 'bytes': 5 * 1024**3}


class Versions:
    def __init__(self, store=None):
        self.store = store or Store(); self.objects = self.store.directory / 'versions' / 'objects'
        self.objects.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS file_versions (
                id INTEGER PRIMARY KEY, root TEXT NOT NULL, path TEXT NOT NULL,
                hash TEXT, size INTEGER NOT NULL, created REAL NOT NULL, mode INTEGER NOT NULL DEFAULT 384);
                CREATE INDEX IF NOT EXISTS file_versions_path ON file_versions(path, id);
                CREATE TABLE IF NOT EXISTS version_heads (root TEXT NOT NULL, path TEXT NOT NULL, hash TEXT,
                    PRIMARY KEY(root,path));''')

    def config(self):
        return dict(DEFAULT, **self.store.setting(KEY, {}))

    def configure(self, roots, interval=30, copies=20, days=90, size_gib=5):
        if not 10 <= interval <= 3600 or not 2 <= copies <= 1000 or not 1 <= days <= 3650 or not 1 <= size_gib <= 1000:
            raise ValueError('Ungültige Aufbewahrungseinstellung.')
        clean = []
        for value in roots:
            path = Path(value).expanduser().absolute()
            if not path.is_dir() or path.is_symlink() or self.store.directory.resolve().is_relative_to(path.resolve()) or path.resolve().is_relative_to(self.store.directory.resolve()):
                raise ValueError('Bitte einen vorhandenen Ordner außerhalb des Lumen-Datenspeichers wählen.')
            if any(path.is_relative_to(Path(r)) or Path(r).is_relative_to(path) for r in clean):
                raise ValueError('Überlappende Ordner bitte nur einmal hinzufügen.')
            clean.append(str(path))
        self.store.set_setting(KEY, dict(roots=clean, interval=interval, copies=copies, days=days, bytes=size_gib * 1024**3))

    def capture(self, root):
        root = Path(root); contents = scan(root)
        heads = {r['path']: r['hash'] for r in self.store.rows('SELECT path,hash FROM version_heads WHERE root=?', (str(root),))}
        for relative, checksum in contents.items():
            path = root / relative
            if heads.get(str(path)) == checksum: continue
            blob = self.objects / checksum
            if not blob.exists():
                size = path.stat().st_size
                if size > self.config()['bytes']: raise ValueError('Datei überschreitet die Speichergrenze: ' + str(path))
                if shutil.disk_usage(self.objects).free < size + 64 * 1024**2: raise ValueError('Nicht genug freier Speicher für die nächste Version.')
                with tempfile.NamedTemporaryFile(dir=self.objects, delete=False) as out:
                    staged = Path(out.name)
                    try:
                        with path.open('rb') as src: shutil.copyfileobj(src, out, 1024 * 1024)
                        out.flush(); os.fsync(out.fileno())
                        if digest(staged) != checksum: raise ValueError('Datei während Sicherung verändert: ' + str(path))
                        os.replace(staged, blob)
                    finally: staged.unlink(missing_ok=True)
            self.add(str(root), str(path), checksum, blob.stat().st_size)
        for path, checksum in heads.items():
            if Path(path).relative_to(root).as_posix() not in contents and checksum is not None:
                self.add(str(root), path, None, 0)

    def add(self, root, path, checksum, size):
        with self.store.connect() as db:
            db.execute('INSERT INTO file_versions(root,path,hash,size,created,mode) VALUES(?,?,?,?,?,?)', (root,path,checksum,size,time.time(), (Path(path).stat().st_mode & 0o777) if checksum else 0o600))
            db.execute('INSERT OR REPLACE INTO version_heads VALUES(?,?,?)', (root,path,checksum))

    def history(self, path=None):
        return self.store.rows('SELECT * FROM file_versions' + (' WHERE path=?' if path else '') + ' ORDER BY id DESC LIMIT 1000', (str(path),) if path else ())

    def prune(self):
        config = self.config()
        with self.store.connect() as db:
            db.execute('DELETE FROM file_versions WHERE created<?', (time.time() - config['days'] * 86400,))
            db.execute('DELETE FROM file_versions WHERE id IN (SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY path ORDER BY id DESC) n FROM file_versions) WHERE n>?)', (config['copies'],))
        self.gc()
        # ponytail: whole oldest versions are evicted when the explicit storage budget is full.
        while sum(p.stat().st_size for p in self.objects.iterdir()) > config['bytes']:
            oldest = self.store.rows('SELECT hash FROM file_versions WHERE hash IS NOT NULL ORDER BY id LIMIT 1')
            if not oldest: break
            with self.store.connect() as db: db.execute('DELETE FROM file_versions WHERE hash=?', (oldest[0]['hash'],))
            self.gc()
        # If retention removed the head, a subsequent sample must create a new version.
        with self.store.connect() as db:
            db.execute('DELETE FROM version_heads WHERE hash IS NOT NULL AND hash NOT IN (SELECT hash FROM file_versions WHERE hash IS NOT NULL)')

    def gc(self):
        used = {r['hash'] for r in self.store.rows('SELECT DISTINCT hash FROM file_versions WHERE hash IS NOT NULL')}
        for path in self.objects.iterdir():
            if path.name not in used: path.unlink()

    def restore(self, identity, expected):
        row = self.store.rows('SELECT * FROM file_versions WHERE id=?', (identity,))
        if not row or not row[0]['hash']: raise ValueError('Bitte eine gespeicherte Dateifassung wählen.')
        row = row[0]; path = Path(row['path'])
        from lumen_offline import safe_path
        safe_path(Path(row['root']), str(path.relative_to(row['root'])))
        current = digest(path)
        if current != expected: raise ValueError('Die aktuelle Datei wurde inzwischen verändert. Vergleich neu öffnen.')
        if current is not None:
            blob = self.objects / current
            if not blob.exists(): shutil.copy2(path, blob)
            if digest(blob) != current: raise ValueError('Datei während Sicherung verändert.')
            self.add(row['root'], str(path), current, blob.stat().st_size)
        replace_file(self.objects / row['hash'], path, row['hash'], expected, None)
        path.chmod(row['mode'])
        self.add(row['root'], str(path), row['hash'], row['size'])
        return str(path)


def start(store):
    return subprocess.Popen([sys.executable, str(Path(__file__)), '--watch'], env=dict(os.environ, LUMEN_DATA=str(store.directory)),
                            start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def watch():
    versions = Versions()
    try: lease = versions.store.acquire('versions-watch')
    except BlockingIOError: return
    try:
        while Path(__file__).is_file() and versions.config()['roots']:
            for root in versions.config()['roots']:
                try:
                    result = subprocess.run([sys.executable, str(Path(__file__)), '--capture', root], capture_output=True, text=True, timeout=300)
                    status = 'Aktuell' if result.returncode == 0 else result.stdout[-1000:] or 'Sicherung fehlgeschlagen'
                except subprocess.TimeoutExpired: status = 'Ordner antwortet nicht · später erneut versuchen'
                versions.store.set_setting('versions/status/' + root, dict(status=status, time=time.time()))
            time.sleep(versions.config()['interval'])
    finally: os.close(lease)


if __name__ == '__main__':
    if sys.argv[1:] == ['--watch']: watch()
    else:
        versions = Versions()
        try:
            lease = versions.store.acquire('versions-data')
            try:
                if sys.argv[1] == '--capture': versions.capture(sys.argv[2]); versions.prune(); print(json.dumps({'ok': True}))
                elif sys.argv[1] == '--restore': print(json.dumps({'path': versions.restore(int(sys.argv[2]), json.loads(sys.argv[3]))}))
                elif sys.argv[1] == '--compare':
                    import difflib
                    row = versions.store.rows('SELECT * FROM file_versions WHERE id=?', (int(sys.argv[2]),))[0]
                    target = Path(row['path']); checksum = digest(target)
                    old = b''
                    if row['hash']:
                        with (versions.objects / row['hash']).open('rb') as f: old = f.read(200000)
                    current = b''
                    if checksum is not None:
                        with target.open('rb') as f: current = f.read(200000)
                    preview = ''
                    if row['hash'] and len(sys.argv) > 3:
                        preview = str(Path(sys.argv[3]) / target.name); shutil.copyfile(versions.objects / row['hash'], preview)
                    if b'\0' in old + current:
                        detail = 'Binäre Datei · Vorschau der gespeicherten Fassung verwenden. Aktuelle Größe: ' + str(target.stat().st_size if checksum else 0) + ' Bytes'
                    else: detail = ''.join(difflib.unified_diff(old.decode(errors='replace').splitlines(True), current.decode(errors='replace').splitlines(True), 'Gespeicherte Fassung', 'Aktuelle Datei')) or 'Inhalte identisch.'
                    print(json.dumps({'expected': checksum, 'detail': detail[:50000], 'preview': preview}))
            finally: os.close(lease)
        except Exception as error: print(json.dumps({'error': str(error)})); sys.exit(1)
