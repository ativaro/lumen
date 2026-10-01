"""Private durable state for Lumen tasks, changes, workflows and knowledge."""
from contextlib import contextmanager
import json
import fcntl
import os
from pathlib import Path
import sqlite3
import time
import uuid

STATES = {'draft': 'Entwurf', 'queued': 'Geplant', 'running': 'Läuft', 'paused': 'Pausiert',
          'interrupted': 'Unterbrochen', 'needs_input': 'Braucht dich', 'completed': 'Erledigt',
          'failed': 'Fehlgeschlagen', 'cancelled': 'Abgebrochen'}

VISIBLE_TASKS = """NOT (status='completed' AND EXISTS (
    SELECT 1 FROM settings WHERE key='tasks/dismissed/' || tasks.id
    AND CAST(value AS REAL)=tasks.updated))"""


def state_path():
    return Path(os.environ.get('LUMEN_DATA', str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'lumen')))


def identifier():
    return uuid.uuid4().hex


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else state_path()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'lumen.sqlite3'
        with self.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()[0] > 2:
                raise ValueError('Diese Lumen-Datenbank benötigt eine neuere Version.')
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
            for name, declaration in [('approved', 'INTEGER NOT NULL DEFAULT 0'), ('prompt', "TEXT NOT NULL DEFAULT ''")]:
                if name not in columns: db.execute(f'ALTER TABLE workflows ADD COLUMN {name} {declaration}')
            db.execute('PRAGMA user_version=2')
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
                        ('Ausführung wurde unterbrochen. Vor dem Fortsetzen den letzten Schritt prüfen.', time.time(), row['id'])).rowcount
                    if changed: db.execute('INSERT INTO events (task,kind,detail,created) VALUES (?,?,?,?)',
                        (row['id'], 'interrupted', 'Ausführungsprozess ist nicht mehr aktiv.', time.time()))
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
            raise ValueError('Ein Titel mit höchstens 200 Zeichen ist erforderlich.')
        directory = str(Path(directory or Path.home()).resolve(strict=True))
        if not Path(directory).is_dir(): raise ValueError('Arbeitsordner nicht gefunden.')
        roots = [str(Path(p).resolve(strict=True)) for p in roots or []]
        if any(not Path(p).is_dir() for p in roots): raise ValueError('Freigaben müssen Ordner sein.')
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
        if not rows: raise ValueError('Auftrag nicht gefunden.')
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
            row = db.execute("SELECT updated FROM tasks WHERE id=? AND status='completed'", (task,)).fetchone()
            if row is None: raise ValueError('Nur erledigte Aufgaben können geschlossen werden.')
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',
                       ('tasks/dismissed/' + task, json.dumps(row['updated'])))

    def update_task(self, task, **values):
        allowed = {'status', 'approved', 'session', 'model', 'cursor', 'result', 'error', 'title', 'prompt'}
        if not values or not set(values) <= allowed: raise ValueError('Ungültige Auftragsfelder.')
        values['updated'] = time.time()
        with self.connect() as db:
            db.execute('UPDATE tasks SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', (*values.values(), task))

    def event(self, task, kind, detail):
        with self.connect() as db:
            db.execute('INSERT INTO events (task,kind,detail,created) VALUES (?,?,?,?)', (task, kind, str(detail)[:20000], time.time()))

    def events(self, task):
        return self.rows('SELECT * FROM events WHERE task=? ORDER BY id', (task,))

    def changes(self, task=None):
        return self.rows('SELECT id,task,path,after_hash,mode,status,created FROM changes' +
                         (' WHERE task=?' if task else '') + ' ORDER BY created DESC LIMIT 200', (task,) if task else ())

    def save_memory(self, title, text, source='Von mir', memory=None):
        if not title.strip() or not text.strip() or len(text) > 20000: raise ValueError('Titel und Text (max. 20.000 Zeichen) erforderlich.')
        memory = memory or identifier()
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?)', (memory, title[:200], text, source[:1000], time.time()))
        return memory

    def memories(self):
        return self.rows('SELECT * FROM memories ORDER BY updated DESC LIMIT 500')

    def delete_memory(self, memory):
        with self.connect() as db: db.execute('DELETE FROM memories WHERE id=?', (memory,))

    def remove_root(self, root):
        root = str(Path(root).expanduser().resolve())
        with self.connect() as db:
            db.execute('DELETE FROM documents WHERE root=?', (root,))
            db.execute('DELETE FROM roots WHERE path=?', (root,))

    def save_workflow(self, name, steps, roots, trigger='manual', interval=3600, watch='', enabled=False, now=None, workflow=None, approved=False, prompt=''):
        from lumen_actions import validate_steps
        if steps: validate_steps(steps)
        elif not prompt.strip(): raise ValueError('Schritte oder ein Auftrag sind erforderlich.')
        if enabled and not approved: raise PermissionError('Den Ablauf zuerst ausdrücklich freigeben.')
        if not name.strip() or len(name) > 200: raise ValueError('Ein gültiger Name ist erforderlich.')
        if trigger not in ('manual', 'interval', 'directory'): raise ValueError('Unbekannter Auslöser.')
        if not 60 <= int(interval) <= 31536000: raise ValueError('Intervall: 60 Sekunden bis ein Jahr.')
        roots = [str(Path(p).resolve(strict=True)) for p in roots]
        if trigger == 'directory':
            watch = str(Path(watch).resolve(strict=True))
            if not Path(watch).is_dir() or not any(Path(watch).is_relative_to(Path(p)) for p in roots):
                raise ValueError('Beobachteter Ordner muss freigegeben sein.')
        workflow = workflow or identifier(); now = time.time() if now is None else now
        fingerprint = directory_fingerprint(watch) if watch else ''
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO workflows (id,name,steps,roots,trigger,interval,watch,enabled,next_run,fingerprint,updated,approved,prompt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (workflow, name, json.dumps(steps), json.dumps(roots), trigger, int(interval), watch, int(enabled), now + int(interval), fingerprint, now, int(approved), prompt))
        return workflow

    def workflows(self):
        rows = self.rows('SELECT * FROM workflows ORDER BY name')
        for row in rows:
            row['steps'] = json.loads(row['steps']); row['roots'] = json.loads(row['roots'])
        return rows

    def set_workflow_enabled(self, workflow, enabled):
        with self.connect() as db:
            if enabled and not db.execute('SELECT approved FROM workflows WHERE id=?', (workflow,)).fetchone()[0]:
                raise PermissionError('Den Ablauf zuerst freigeben.')
            db.execute('UPDATE workflows SET enabled=?, next_run=?+interval WHERE id=?', (int(enabled), time.time(), workflow))

    def enqueue_due(self, now=None):
        now = time.time() if now is None else now
        queued = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for flow in db.execute("SELECT * FROM workflows WHERE enabled=1 AND approved=1 AND trigger!='manual' AND next_run<=?", (now,)).fetchall():
                fingerprint = flow['fingerprint']
                if flow['trigger'] == 'directory':
                    try: fingerprint = directory_fingerprint(flow['watch'])
                    except OSError:
                        db.execute('UPDATE workflows SET enabled=0 WHERE id=?', (flow['id'],)); continue
                db.execute('UPDATE workflows SET next_run=?,fingerprint=? WHERE id=?', (now + flow['interval'], fingerprint, flow['id']))
                if flow['trigger'] == 'directory' and fingerprint == flow['fingerprint']: continue
                pending = db.execute("SELECT 1 FROM tasks JOIN events ON events.task=tasks.id WHERE events.kind='workflow' AND events.detail=? AND tasks.status IN ('queued','running','needs_input','paused','interrupted') LIMIT 1", (flow['id'],)).fetchone()
                if pending: continue
                task = identifier(); roots = json.loads(flow['roots'])
                db.execute('INSERT INTO tasks (id,title,prompt,directory,roots,steps,status,approved,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (task, flow['name'], flow['prompt'], roots[0] if roots else str(Path.home()), flow['roots'], flow['steps'], 'queued', 1, now, now))
                db.execute('INSERT INTO events (task,kind,detail,created) VALUES (?,?,?,?)', (task, 'workflow', flow['id'], now))
                queued.append(task)
        return queued


def directory_fingerprint(directory):
    import hashlib
    root = Path(directory)
    if root.is_symlink() or root.resolve() != root: raise OSError('Beobachteter Ordner wurde ersetzt.')
    # ponytail: watch immediate children only, add explicit recursive subscriptions if needed.
    entries = []
    with os.scandir(root) as scan:
        for entry in scan:
            if entry.name.startswith('.') or entry.is_symlink(): continue
            info = entry.stat(follow_symlinks=False)
            entries.append((entry.name, info.st_size, info.st_mtime_ns))
            if len(entries) > 10000: raise OSError('Zu viele Einträge im beobachteten Ordner.')
    return hashlib.sha256(json.dumps(sorted(entries)).encode()).hexdigest()
