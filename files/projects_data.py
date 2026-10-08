"""Project children and execution history in the existing workbench database."""
import hashlib
import json
import time
import uuid
from lumen_i18n import tr

KINDS = {'manual': 'Manuell', 'research': 'Recherche', 'analysis': 'Analyse', 'automation': 'Automation'}
STATES = {'open': 'Offen', 'running': 'Läuft', 'done': 'Erledigt', 'failed': 'Fehlgeschlagen', 'cancelled': 'Abgebrochen', 'paused': 'Pausiert'}


class Projects:
    def __init__(self, library):
        self.library = library
        with library.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS project_items (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, parent TEXT NOT NULL,
                    kind TEXT NOT NULL, title TEXT NOT NULL, data TEXT NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS project_children ON project_items(project,parent);
                CREATE TABLE IF NOT EXISTS project_runs (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, started REAL NOT NULL,
                    finished REAL, status TEXT NOT NULL, data TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS project_running ON project_runs(task) WHERE status='running';
                CREATE TABLE IF NOT EXISTS project_migration (project TEXT NOT NULL, source TEXT NOT NULL,
                    PRIMARY KEY(project,source));
            ''')

    @staticmethod
    def writable(db, project):
        row=db.execute('SELECT data FROM records WHERE id=?',(project,)).fetchone()
        data=json.loads(row['data']) if row else {}
        if data.get('server_bound') and data.get('server_role')=='reader':raise ValueError(tr('Dieses Serverprojekt ist nur lesbar.'))

    @staticmethod
    def unpack(row):
        if row is None: raise ValueError(tr('Dieser Eintrag ist nicht mehr vorhanden.'))
        value = dict(row); data = json.loads(value.pop('data')); return dict(data, **value)

    def get(self, key):
        with self.library.connect() as db:
            return self.unpack(db.execute('SELECT * FROM project_items WHERE id=?', (key,)).fetchone())

    def items(self, project, parent=None, archived=False):
        with self.library.connect() as db:
            rows = db.execute('SELECT * FROM project_items WHERE project=? AND archived=? ORDER BY created,id', (project, int(archived))).fetchall()
        return [self.unpack(r) for r in rows if parent is None or r['parent'] == parent]

    def add(self, project, parent, title, kind='manual', **data):
        title = title.strip()
        if not title: raise ValueError(tr('Bitte einen Namen angeben.'))
        key = uuid.uuid4().hex; now = time.time()
        value = dict(notes='', resources=[], goal='', depends=[], status='open', enabled=False, interval=86400, next_run=0)
        value.update(data)
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.writable(db,project)
            record = db.execute('SELECT archived FROM records WHERE id=?', (project,)).fetchone()
            if record is None or record['archived']: raise ValueError('Project unavailable or archived.')
            if kind != 'initiative':
                owner = self.unpack(db.execute('SELECT * FROM project_items WHERE id=?', (parent,)).fetchone())
                if owner['project'] != project or owner['kind'] != 'initiative' or owner['archived']:
                    raise ValueError(tr('Eine Aufgabe gehört zu einem aktiven Vorhaben.'))
                if kind not in KINDS: raise ValueError(tr('Ungültige Aufgabenart.'))
            elif parent: raise ValueError(tr('Ein Vorhaben gehört direkt zum Projekt.'))
            db.execute('INSERT INTO project_items VALUES (?,?,?,?,?,?,?,?,0)', (key, project, parent, kind, title, json.dumps(value), now, now))
        return key

    def update(self, key, expected_updated=None, **changes):
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self.unpack(db.execute('SELECT * FROM project_items WHERE id=?', (key,)).fetchone())
            self.writable(db,current['project'])
            if expected_updated is not None:
                self.check_edit(db, current, expected_updated)
            if 'depends' in changes:
                graph = {r['id']: self.unpack(r) for r in db.execute('SELECT * FROM project_items WHERE project=?', (current['project'],))}
                graph[key]['depends'] = list(dict.fromkeys(changes['depends']))
                def visit(node, path):
                    if node in path: raise ValueError(tr('Aufgaben dürfen sich nicht gegenseitig blockieren.'))
                    value = graph.get(node)
                    if not value or value['kind'] == 'initiative' or (value['archived'] and node!=key):
                        raise ValueError(tr('Eine Abhängigkeit ist nicht mehr verfügbar.'))
                    for dependency in value.get('depends', []): visit(dependency, path | {node})
                visit(key, set())
            title = str(changes.pop('title', current['title'])).strip()
            if not title: raise ValueError(tr('Bitte einen Namen angeben.'))
            archived = int(changes.pop('archived', current['archived']))
            data = {k:v for k,v in current.items() if k not in ('id','project','parent','kind','title','created','updated','archived')}
            if 'interval' in changes:
                interval=int(changes['interval'])
                if not 3600<=interval<=365*86400:raise ValueError(tr('Ungültiges Zeitintervall.'))
                if data.get('enabled') and interval!=data.get('interval'):changes['next_run']=time.time()+interval
            data.update(changes)
            db.execute('UPDATE project_items SET title=?,data=?,updated=?,archived=? WHERE id=?', (title,json.dumps(data),time.time(),archived,key))

    def migrate(self, project):
        """Also imports newly handed-off questions; original records remain intact."""
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM records WHERE id=?',(project,)).fetchone()
            if not row:return
            record=json.loads(row[0])
            owner = db.execute("SELECT id FROM project_items WHERE project=? AND kind='initiative' AND parent='' AND archived=0 ORDER BY created LIMIT 1", (project,)).fetchone()
            current_sources=set()
            for index, question in enumerate(record.get('questions', [])):
                text = question.get('text', '').strip()
                if not text: continue
                source = hashlib.sha256((str(index)+'\0'+text).encode()).hexdigest()
                current_sources.add(source)
                if db.execute('SELECT 1 FROM project_migration WHERE project=? AND source=?', (project,source)).fetchone(): continue
                now = time.time()
                if not owner:
                    owner = (uuid.uuid4().hex,)
                    db.execute('INSERT INTO project_items VALUES (?,?,?,?,?,?,?,?,0)', (owner[0],project,'','initiative',tr('Übernommene Aufgaben'),'{}',now,now))
                value = dict(notes='',resources=[],goal='',depends=[],status='done' if question.get('done') else 'open',legacy_question=index,legacy_source=source,legacy_text=text,legacy_done=bool(question.get('done')))
                db.execute('INSERT INTO project_items VALUES (?,?,?,?,?,?,?,?,0)', (uuid.uuid4().hex,project,owner[0],'manual',text,json.dumps(value),now,now))
                db.execute('INSERT INTO project_migration VALUES (?,?)', (project,source))
            # Undoing a handoff removes its untouched derived task as well. Edited
            # tasks remain as user work even when their original question is gone.
            for row in db.execute('SELECT * FROM project_items WHERE project=? AND archived=0',(project,)).fetchall():
                data=json.loads(row['data'])
                if not data.get('legacy_source') or data['legacy_source'] in current_sources:continue
                pristine=row['title']==data.get('legacy_text') and not any(data.get(k) for k in ('notes','resources','goal','depends')) and data.get('status')==('done' if data.get('legacy_done') else 'open')
                archive=pristine and not db.execute('SELECT 1 FROM project_runs WHERE task=?',(row['id'],)).fetchone()
                data['legacy_origin']=data.pop('legacy_source')
                db.execute('UPDATE project_items SET archived=?,data=? WHERE id=?',(int(bool(archive)),json.dumps(data),row['id']))
                db.execute('DELETE FROM project_migration WHERE project=? AND source=?',(project,data['legacy_origin']))

    def runs(self, task):
        with self.library.connect() as db:
            return [self.unpack(r) for r in db.execute('SELECT * FROM project_runs WHERE task=? ORDER BY started DESC', (task,))]

    def update_run(self, run, **changes):
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data FROM project_runs WHERE id=? AND status='running'",(run,)).fetchone()
            if row:
                data=json.loads(row[0]); data.update(changes)
                db.execute('UPDATE project_runs SET data=? WHERE id=?',(json.dumps(data),run))

    @staticmethod
    def check_edit(db, item, expected_updated):
        project = db.execute('SELECT archived FROM records WHERE id=?', (item['project'],)).fetchone()
        parent = db.execute('SELECT archived FROM project_items WHERE id=?', (item['parent'],)).fetchone()
        if (str(item['updated']) != expected_updated or item['archived'] or not project or project[0]
                or (item['kind'] != 'initiative' and (not parent or parent[0]))):
            raise ValueError('Project entry changed or archived. Read it again before editing or starting.')
        if db.execute("SELECT 1 FROM project_runs WHERE task=? AND status='running'", (item['id'],)).fetchone():
            raise ValueError('Task is running. Wait for its result before editing or starting again.')

    def begin_run(self, task, snapshot, scheduled=False, expected_updated=None):
        key = uuid.uuid4().hex; now = time.time()
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = self.unpack(db.execute('SELECT * FROM project_items WHERE id=?', (task,)).fetchone())
            if item['kind'] not in ('research', 'analysis', 'automation') and expected_updated is not None:
                raise ValueError('Only research, analysis and automation tasks can run.')
            if expected_updated is not None: self.check_edit(db, item, expected_updated)
            if scheduled and (item['kind']!='automation' or not item.get('enabled') or item.get('next_run',0)>now):
                raise ValueError(tr('Dieser Zeitplan ist nicht mehr fällig.'))
            project = db.execute('SELECT archived,data FROM records WHERE id=?', (item['project'],)).fetchone()
            if project and json.loads(project['data']).get('server_bound'):
                raise ValueError(tr('Dieses Projekt wird auf Lumen Server ausgeführt. Dort den Auftrag starten.'))
            owner = db.execute('SELECT archived FROM project_items WHERE id=?', (item['parent'],)).fetchone()
            if item['archived'] or not project or project[0] or not owner or owner[0]: raise ValueError(tr('Archivierte Aufgaben werden nicht ausgeführt.'))
            for dep in item.get('depends', []):
                prerequisite = self.unpack(db.execute('SELECT * FROM project_items WHERE id=?', (dep,)).fetchone())
                if prerequisite.get('status') != 'done': raise ValueError(tr('Zuerst die vorausgesetzten Aufgaben abschließen.'))
            if db.execute("SELECT 1 FROM project_runs WHERE task=? AND status='running'", (task,)).fetchone():
                raise ValueError(tr('Diese Aufgabe läuft bereits.'))
            db.execute('INSERT INTO project_runs VALUES (?,?,?,NULL,?,?)', (key,task,now,'running',json.dumps(dict(snapshot=snapshot,result='',error=''))))
            data = json.loads(db.execute('SELECT data FROM project_items WHERE id=?',(task,)).fetchone()[0]); data['status']='running'
            if item['kind']=='automation': data['next_run']=now+int(item.get('interval',86400))
            db.execute('UPDATE project_items SET data=?,updated=? WHERE id=?',(json.dumps(data),now,task))
        return key

    def finish_run(self, run, status, result='', error=''):
        if status not in ('done','failed','cancelled','paused'): raise ValueError('Invalid run status')
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM project_runs WHERE id=?',(run,)).fetchone()
            value = self.unpack(row)
            if value['status'] != 'running': return
            data = json.loads(row['data']); data.update(result=result,error=error)
            now=time.time(); db.execute('UPDATE project_runs SET data=?,status=?,finished=? WHERE id=?',(json.dumps(data),status,now,run))
            row = db.execute('SELECT data FROM project_items WHERE id=?',(value['task'],)).fetchone()
            task=json.loads(row[0]); task.update(status=status,last_run=now)
            # Errors pause recurring execution until the user reviews the task.
            if status != 'done': task['enabled']=False
            db.execute('UPDATE project_items SET data=?,updated=? WHERE id=?',(json.dumps(task),now,value['task']))

    def source_chain(self, key):
        task = self.get(key); project = self.library.get(task['project'])
        return [project, self.get(task['parent']), task]
