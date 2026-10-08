"""Rebuildable private SQLite vector cache; authorization comes from current entries.

The caller supplies the complete authorized snapshot for one boundary/project. Call
prepare on corrections/revocations before scheduling more indexing. Revision checks
also prevent an already-running index job from restoring revoked rows.
"""
import hashlib
import os
import sqlite3
if __package__:
    from .memory_core import eligible
    from .memory_embedding import MODEL_VERSION
else:
    from memory_core import eligible
    from memory_embedding import MODEL_VERSION


class Index:
    def __init__(self, path):
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        self.db = sqlite3.connect(path, timeout=2)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA secure_delete=ON')
        # ponytail: bounded SQLite scan; replace with ANN only after measured need.
        self.db.execute('PRAGMA max_page_count=65536')  # at most 256 MiB with default 4 KiB pages
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS records (
              id TEXT PRIMARY KEY, revision TEXT NOT NULL, digest TEXT NOT NULL, complete INT NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS vectors (
              id TEXT REFERENCES records(id) ON DELETE CASCADE, position INT, vector BLOB NOT NULL,
              PRIMARY KEY(id,position));
        ''')

    @staticmethod
    def digest(entry):
        return hashlib.sha256((MODEL_VERSION + '\0' + entry.boundary + '\0' + entry.project + '\0'
                               + entry.title + '\n' + entry.text).encode()).hexdigest()

    def prepare(self, entries, boundary, project=''):
        current = eligible(entries, boundary, project)
        if len(current) > 5000 or len({e.id for e in current}) != len(current):
            raise ValueError('Memory index identity/count limit')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            wanted = {e.id: (str(e.revision), self.digest(e)) for e in current}
            for identity, revision, digest in self.db.execute('SELECT id,revision,digest FROM records').fetchall():
                if wanted.get(identity) != (revision, digest):
                    self.db.execute('DELETE FROM records WHERE id=?', (identity,))
            self.db.executemany('INSERT OR IGNORE INTO records(id,revision,digest) VALUES (?,?,?)',
                                [(e.id, str(e.revision), self.digest(e)) for e in current])
        return current

    def advance(self, entries, encoder, chunks=32):
        """Bounded work, committed per fragment; resumes after interruption."""
        remaining = chunks
        for entry in entries:
            row = self.db.execute('SELECT revision,digest,complete FROM records WHERE id=?', (entry.id,)).fetchone()
            expected = (str(entry.revision), self.digest(entry))
            if not row or row[:2] != expected or row[2]:
                continue
            start = self.db.execute('SELECT count(*) FROM vectors WHERE id=?', (entry.id,)).fetchone()[0]
            for position, vector in enumerate(encoder.encode(entry.title + '\n' + entry.text, start=start), start):
                if remaining <= 0:
                    return chunks - remaining
                with self.db:
                    self.db.execute('BEGIN IMMEDIATE')
                    if self.db.execute('SELECT revision,digest FROM records WHERE id=?', (entry.id,)).fetchone() != expected:
                        break
                    self.db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',
                                    (entry.id, position, vector.tobytes()))
                remaining -= 1
            else:
                with self.db:
                    self.db.execute('UPDATE records SET complete=1 WHERE id=? AND revision=? AND digest=?',
                                    (entry.id, *expected))
        return chunks - remaining

    def scores(self, current, query, encoder):
        """Freshly authorized ID/revision/digest match required, even for cached vectors."""
        import numpy as np
        needles = list(encoder.encode(query[:6000]))
        scores = {}
        positions = {}
        for entry in current:
            rows = self.db.execute(
                'SELECT v.vector,v.position FROM vectors v JOIN records r ON r.id=v.id '
                'WHERE r.id=? AND r.revision=? AND r.digest=? AND r.complete=1 ORDER BY v.position',
                (entry.id, str(entry.revision), self.digest(entry)))
            for blob, position in rows:
                vector = np.frombuffer(blob, dtype='<f4')
                if vector.shape != (384,) or not np.isfinite(vector).all():
                    continue
                key = (entry.id, entry.revision)
                score = max(float(vector @ needle) for needle in needles)
                if score > scores.get(key, -1):
                    scores[key], positions[key] = score, position
        return scores, positions

    def status(self):
        ready, total = self.db.execute('SELECT coalesce(sum(complete),0),count(*) FROM records').fetchone()
        return {'ready': ready, 'total': total, 'mode': 'hybrid' if ready == total else 'indexing'}

    def close(self):
        self.db.close()
