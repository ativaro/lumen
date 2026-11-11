"""Private durable state for Lumen tasks, changes, file actions and knowledge."""
from lumen_i18n import tr
from contextlib import contextmanager
import json
import fcntl
import os
from pathlib import Path
import sqlite3
import time
import uuid
from lumen_paths import state_path

STATES = {'draft': tr('Entwurf'), 'queued': tr('Geplant'), 'running': tr('Läuft'), 'paused': tr('Pausiert'),
          'interrupted': tr('Unterbrochen'), 'needs_input': tr('Braucht dich'), 'completed': tr('Erledigt'),
          'failed': tr('Fehlgeschlagen'), 'cancelled': tr('Abgebrochen')}

VISIBLE_TASKS = """NOT (status IN ('completed','cancelled') AND EXISTS (
    SELECT 1 FROM settings WHERE key='tasks/dismissed/' || tasks.id
    AND CAST(value AS REAL)=tasks.updated))"""


def identifier():
    return uuid.uuid4().hex


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else state_path()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'lumen.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 3:
                raise ValueError(tr('Diese Lumen-Datenbank benötigt eine neuere Version.'))
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL,
                    directory TEXT NOT NULL, roots TEXT NOT NULL, steps TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft', approved INTEGER NOT NULL DEFAULT 0,
                    session TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
                    cursor INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, task TEXT NOT NULL, kind TEXT NOT NULL,
                    detail TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS changes (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, path TEXT NOT NULL,
                    before BLOB, after_hash TEXT NOT NULL, mode INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'applied', created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, steps TEXT NOT NULL,
                    roots TEXT NOT NULL, trigger TEXT NOT NULL, interval INTEGER NOT NULL,
                    watch TEXT NOT NULL, enabled INTEGER NOT NULL, next_run REAL NOT NULL,
                    fingerprint TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL,
                    source TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS roots (path TEXT PRIMARY KEY, indexed REAL NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(root UNINDEXED, path UNINDEXED, page UNINDEXED, stamp UNINDEXED, text);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(workflows)')}
            for name, declaration in [('approved', 'INTEGER NOT NULL DEFAULT 0'), ('prompt', "TEXT NOT NULL DEFAULT ''"),('code_plan',"TEXT NOT NULL DEFAULT ''")]:
                if name not in columns: db.execute(f'ALTER TABLE workflows ADD COLUMN {name} {declaration}')
            if version < 3:
                # Version 3 renames the transfer and history keys once; the rename and the version commit together.
                db.execute("""UPDATE settings SET key=substr(key,11)
                    WHERE (key >= 'workplace/transfer/' AND key < 'workplace/transfer0'
                        OR key >= 'workplace/history/' AND key < 'workplace/history0')
                    AND NOT EXISTS (SELECT 1 FROM settings AS target WHERE target.key=substr(settings.key,11))""")
                db.execute('PRAGMA user_version=3')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def acquire(self, task):
        fd = os.open(self.directory / ('task-' + task + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd); raise
        return fd

    def recover(self):
        # The OS releases the lease on a crash, including a lost GUI or worker.
        for row in self.rows("SELECT id FROM tasks WHERE status='running' OR (status='needs_input' AND EXISTS (SELECT 1 FROM events WHERE task=tasks.id AND kind='input'))"):
            try: lease = self.acquire(row['id'])
            except BlockingIOError: continue
            try:
                with self.connect() as db:
                    changed = db.execute("UPDATE tasks SET status='interrupted',error=?,updated=? WHERE id=? AND (status='running' OR (status='needs_input' AND EXISTS (SELECT 1 FROM events WHERE task=tasks.id AND kind='input')))",
                        (tr('Ausführung wurde unterbrochen. Vor dem Fortsetzen den letzten Schritt prüfen.'), time.time(), row['id'])).rowcount
                    if changed: db.execute('INSERT INTO events (task,kind,detail,created) VALUES (?,?,?,?)',
                        (row['id'], 'interrupted', tr('Ausführungsprozess ist nicht mehr aktiv.'), time.time()))
            finally: os.close(lease)

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]

    def setting(self, key, default=None):
        rows = self.rows('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def create_task(self, title, prompt='', directory=None, roots=None, steps=None, model='', approved=False, status='draft'):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError(tr('Ein Titel mit höchstens 200 Zeichen ist erforderlich.'))
        directory = str(Path(directory or Path.home()).resolve(strict=True))
        if not Path(directory).is_dir(): raise ValueError(tr('Arbeitsordner nicht gefunden.'))
        roots = [str(Path(p).resolve(strict=True)) for p in roots or []]
        if any(not Path(p).is_dir() for p in roots): raise ValueError(tr('Freigaben müssen Ordner sein.'))
        if steps:
            from lumen_actions import validate_steps
            validate_steps(steps)
        task = identifier(); now = time.time()
        with self.connect() as db:
            db.execute('INSERT INTO tasks (id,title,prompt,directory,roots,steps,model,approved,status,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (task, title.strip(), prompt, directory, json.dumps(roots), json.dumps(steps or []), model, int(approved), status, now, now))
        return task

    def task(self, task):
        rows = self.rows('SELECT * FROM tasks WHERE id=?', (task,))
        if not rows: raise ValueError(tr('Auftrag nicht gefunden.'))
        value = rows[0]
        value['steps'] = json.loads(value['steps']); value['roots'] = json.loads(value['roots'])
        value['approved'] = bool(value['approved'])
        return value

    def tasks(self, include_dismissed=True):
        return self.rows('SELECT id,title,status,updated,error FROM tasks' +
                         ('' if include_dismissed else ' WHERE ' + VISIBLE_TASKS) + ' ORDER BY updated DESC LIMIT 200')

    def dismiss_task(self, task):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT updated FROM tasks WHERE id=? AND status IN ('completed','cancelled')", (task,)).fetchone()
            if row is None: raise ValueError(tr('Nur erledigte oder abgebrochene Aufgaben können geschlossen werden.'))
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',
                       ('tasks/dismissed/' + task, json.dumps(row['updated'])))

    def update_task(self, task, **values):
        allowed = {'status', 'approved', 'session', 'model', 'cursor', 'result', 'error', 'title', 'prompt'}
        if not values or not set(values) <= allowed: raise ValueError(tr('Ungültige Auftragsfelder.'))
        values['updated'] = time.time()
        with self.connect() as db:
            if values.get('status') in ('running','completed'):
                from code_flow_native import check_task
                check_task(db,task)
            db.execute('UPDATE tasks SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', (*values.values(), task))

    def event(self, task, kind, detail):
        with self.connect() as db:
            db.execute('INSERT INTO events (task,kind,detail,created) VALUES (?,?,?,?)', (task, kind, str(detail)[:20000], time.time()))

    def events(self, task):
        return self.rows('SELECT * FROM events WHERE task=? ORDER BY id', (task,))

    def changes(self, task=None):
        return self.rows('SELECT id,task,path,after_hash,mode,status,created FROM changes' +
                         (' WHERE task=?' if task else '') + ' ORDER BY created DESC LIMIT 200', (task,) if task else ())

    def save_memory(self, title, text, source=tr('Von mir'), memory=None):
        if not title.strip() or not text.strip() or len(text) > 20000: raise ValueError(tr('Titel und Text (max. 20.000 Zeichen) erforderlich.'))
        if self.setting('knowledge/notebook',''):
            from wissen_data import Notebook
            return Notebook(self).capture(title,text,source,memory)
        memory = memory or identifier()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?)', (memory, title[:200], text, source[:1000], time.time()))
        return memory

    def memories(self):
        if self.setting('knowledge/notebook',''):
            from wissen_data import Notebook
            book=Notebook(self);book.migrate()
            return book.scan()['notes'][:500]
        return self.rows('SELECT * FROM memories ORDER BY updated DESC LIMIT 500')

    def delete_memory(self, memory):
        if self.setting('knowledge/notebook',''):
            from wissen_data import Notebook
            book=Notebook(self);memory=book.memory_path(memory);note=book.read(memory);book.remove(memory,note['hash']);return
        with self.connect() as db: db.execute('DELETE FROM memories WHERE id=?', (memory,))

    def remove_root(self, root):
        root = str(Path(root).expanduser().resolve())
        with self.connect() as db:
            db.execute('DELETE FROM documents WHERE root=?', (root,))
            db.execute('DELETE FROM roots WHERE path=?', (root,))

    def save_file_action(self, name, steps, roots, approved=False, prompt=''):
        """Store a personal file action. It only ever starts from the file menu."""
        from lumen_actions import validate_steps
        if steps: validate_steps(steps)
        elif not prompt.strip(): raise ValueError(tr('Schritte oder ein Auftrag sind erforderlich.'))
        if not name.strip() or len(name) > 200: raise ValueError(tr('Ein gültiger Name ist erforderlich.'))
        roots = [str(Path(p).resolve(strict=True)) for p in roots]
        identity = identifier(); now = time.time()
        with self.connect() as db:
            # The table keeps its historical name and columns; file actions are its manual rows.
            db.execute('INSERT INTO workflows (id,name,steps,roots,trigger,interval,watch,enabled,next_run,fingerprint,updated,approved,prompt,code_plan) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, name, json.dumps(steps), json.dumps(roots), 'manual', 3600, '', 0, now, '', now, int(approved), prompt, ''))
        return identity

    def file_actions(self):
        rows = self.rows("SELECT * FROM workflows WHERE trigger='manual' ORDER BY name")
        for row in rows:
            row['steps'] = json.loads(row['steps']); row['roots'] = json.loads(row['roots'])
        return rows
