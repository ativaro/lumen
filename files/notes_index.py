"""Disposable private parse cache. Every hit requires freshly read source bytes."""
import hashlib
import json
import os
import sqlite3
import stat

VERSION = '3'  # Bump when parse(), tags or heading semantics change.


def cache_path(book):
    key = hashlib.sha256((str(book.root)+'\0'+repr(book.identity)).encode()).hexdigest()
    return book.store.directory/('notes-index-'+key+'.sqlite')


class Index:
    def __init__(self, book):
        self.db = None; self.seen = set()
        try:
            path = cache_path(book)
            fd = os.open(path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                    raise OSError('Unsafe cache file')
                os.fchmod(fd, 0o600)
            finally: os.close(fd)
            self.db = sqlite3.connect(path, timeout=.1)
            self.db.execute('PRAGMA secure_delete=ON')
            page = self.db.execute('PRAGMA page_size').fetchone()[0]
            self.db.execute('PRAGMA max_page_count='+str(256*1024**2//page))
            self.db.execute('CREATE TABLE IF NOT EXISTS notes (path TEXT PRIMARY KEY, version TEXT, hash TEXT, value TEXT)')
        except (OSError, sqlite3.Error): self.close()

    def read(self, book, path, parser):
        # Cache freshness never depends on timestamps or a prior permission decision.
        raw, modified = book._read(path)
        key = str(path); digest = hashlib.sha256(raw).hexdigest(); self.seen.add(key)
        if self.db:
            try:
                row = self.db.execute('SELECT value FROM notes WHERE path=? AND version=? AND hash=?', (key, VERSION, digest)).fetchone()
                if row:
                    checksum, payload = json.loads(row[0])
                    if hashlib.sha256(payload.encode()).hexdigest() == checksum:
                        note = json.loads(payload)
                        if isinstance(note, dict) and note.get('hash') == digest and note.get('path') == key:
                            return dict(note, modified=modified)
            except (sqlite3.Error, ValueError, TypeError, AttributeError): self.close()
        note = parser(key, raw)
        if self.db:
            try:
                payload = json.dumps(note, ensure_ascii=False)
                value = json.dumps([hashlib.sha256(payload.encode()).hexdigest(), payload], ensure_ascii=False)
                self.db.execute('INSERT OR REPLACE INTO notes VALUES (?,?,?,?)', (key, VERSION, digest, value))
            except sqlite3.Error: self.close()
        return dict(note, modified=modified)

    def prune(self):
        if self.db:
            try:
                for path, in self.db.execute('SELECT path FROM notes').fetchall():
                    if path not in self.seen: self.db.execute('DELETE FROM notes WHERE path=?', (path,))
            except sqlite3.Error: self.close()

    def close(self):
        if self.db:
            try: self.db.commit()
            except sqlite3.Error: pass
            self.db.close(); self.db = None

    def __enter__(self): return self
    def __exit__(self, *ignored): self.close()
