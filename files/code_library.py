"""Durable private collection, using the existing Lumen state database."""
import json
import time
from uuid import uuid4
from code_library_contract import definition, import_template


class Collection:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS code_library (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                description TEXT NOT NULL, definition TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '',
                favorite INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0,
                revision INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL, updated REAL NOT NULL,
                last_used REAL NOT NULL DEFAULT 0, last_task TEXT NOT NULL DEFAULT '')''')
        from code_app_records import Records
        self.records=Records(self)

    @staticmethod
    def unpack(row):
        value = dict(row)
        value['definition'] = json.loads(value['definition'])
        for name in ('favorite', 'archived'):
            value[name] = bool(value[name])
        return value

    def get(self, identity):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM code_library WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise ValueError('Sammlungseintrag nicht gefunden.')
        return self.unpack(row)

    def items(self, query='', kind='', project_id=None, favorite=False, archived=False, sort='recent'):
        if kind and kind not in ('app', 'tool', 'automation', 'code'):
            raise ValueError('Unbekannte Eintragsart.')
        orders = {'recent': 'last_used DESC,updated DESC,id', 'name': 'title COLLATE NOCASE,id', 'kind': 'kind,title COLLATE NOCASE,id'}
        if sort not in orders:
            raise ValueError('Unbekannte Sortierung.')
        clauses = ['archived=?']; args = [int(archived)]
        for column, value in [('kind', kind), ('project_id', project_id)]:
            if value is not None and (column == 'project_id' or value):
                clauses.append(column + '=?'); args.append(value)
        if favorite:
            clauses.append('favorite=1')
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM code_library WHERE ' + ' AND '.join(clauses) + ' ORDER BY ' + orders[sort], args).fetchall()
        needle = query.strip().casefold()
        return [self.unpack(row) for row in rows if needle in (row['title'] + ' ' + row['description']).casefold()]

    def create(self, kind, title, description='', value=None, project_id=''):
        entry = definition(kind, title, description, value)
        if not isinstance(project_id, str) or len(project_id) > 160:
            raise ValueError('Ungültige Projektzuordnung.')
        identity = uuid4().hex; now = time.time()
        with self.store.connect() as db:
            db.execute('INSERT INTO code_library(id,kind,title,description,definition,project_id,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (identity, kind, entry['title'], entry['description'], json.dumps(entry['definition']), project_id, now, now))
        return self.get(identity)

    def update(self, identity, revision, *, adopt=(), **changes):
        if not changes or not set(changes) <= {'title', 'description', 'definition', 'project_id', 'favorite', 'archived'}:
            raise ValueError('Ungültige Sammlungsänderung.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            raw = db.execute('SELECT * FROM code_library WHERE id=?', (identity,)).fetchone()
            if raw is None:
                raise ValueError('Sammlungseintrag nicht gefunden.')
            current = self.unpack(raw)
            if current['revision'] != revision:
                raise ValueError('Eintrag inzwischen geändert. Bitte neu laden.')
            merged = {**current, **changes}
            if merged['archived'] and not current['archived']:
                active=db.execute("""SELECT 1 FROM tasks WHERE status IN ('queued','running','needs_input') AND
                    (id=? OR id IN (SELECT task FROM events WHERE (kind='code-library' AND detail=?) OR (kind='workflow' AND detail=?))) LIMIT 1""",
                    (current['last_task'],identity,current['definition'].get('workflow_id',''))).fetchone()
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_block_runs'").fetchone():
                    active=active or db.execute("SELECT 1 FROM code_block_runs WHERE entry=? AND (status IN ('running','waiting') OR (status NOT IN ('completed','cancelled') AND json_extract(data,'$.queued')=1)) LIMIT 1",(identity,)).fetchone()
                if active:raise ValueError('Bitte den laufenden Vorgang zuerst beenden. Der Eintrag bleibt in der Sammlung.')
            checked = definition(merged['kind'], merged['title'], merged['description'], merged['definition'])
            for key in ('favorite', 'archived'):
                if type(merged[key]) is not bool:
                    raise ValueError('Ungültiger Schalter: ' + key)
            if not isinstance(merged['project_id'], str) or len(merged['project_id']) > 160:
                raise ValueError('Ungültige Projektzuordnung.')
            flow_changed=(current['definition'].get('flow')!=merged['definition'].get('flow') or current['definition'].get('directory')!=merged['definition'].get('directory') or current['title']!=merged['title'])
            if (flow_changed or merged['archived']) and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_block_triggers'").fetchone():
                db.execute('UPDATE code_block_triggers SET enabled=0 WHERE entry=?',(identity,))
            if flow_changed and current['definition'].get('workflow_id'):
                db.execute('UPDATE workflows SET enabled=0,approved=0,updated=? WHERE id=?',(time.time(),current['definition']['workflow_id']))
            if merged['archived']:
                for identity_to_pause in {current['definition'].get('workflow_id'), merged['definition'].get('workflow_id')} - {None, ''}:
                    db.execute('UPDATE workflows SET enabled=0,updated=? WHERE id=?',(time.time(),identity_to_pause))
            if adopt and (current['kind']!='tool' or merged['archived']):
                raise ValueError('Nur verfügbare Werkzeuge können übernommen werden.')
            for target_id, target_revision in adopt:
                from code_flow import parse, encode
                raw_target=db.execute('SELECT * FROM code_library WHERE id=?',(target_id,)).fetchone()
                if raw_target is None:raise ValueError('Routine nicht mehr verfügbar.')
                target=self.unpack(raw_target)
                if target['kind']!='automation' or target['archived'] or target['revision']!=target_revision:
                    raise ValueError('Routine inzwischen geändert. Bitte neu laden.')
                plan=parse(target['definition'].get('flow',''))
                steps=[step for step in plan.get('steps',[]) if step.get('tool_id')==identity]
                if not steps:raise ValueError('Die Routine verwendet diese Werkzeugfassung nicht.')
                for step in steps:step.update(title=checked['title'],prompt=checked['definition'].get('prompt',''),tool_revision=revision+1)
                target['definition']['flow']=encode(plan)
                definition('automation',target['title'],target['description'],target['definition'])
                db.execute('UPDATE code_library SET definition=?,revision=revision+1,updated=? WHERE id=?',(json.dumps(target['definition']),time.time(),target_id))
                if target['definition'].get('workflow_id'):
                    db.execute('UPDATE workflows SET enabled=0,approved=0,updated=? WHERE id=?',(time.time(),target['definition']['workflow_id']))
            if current['kind']=='app' and current['definition'].get('html')!=merged['definition'].get('html'):
                self.records.remember(db,current)
            db.execute('UPDATE code_library SET title=?,description=?,definition=?,project_id=?,favorite=?,archived=?,revision=revision+1,updated=? WHERE id=?',
                       (checked['title'], checked['description'], json.dumps(checked['definition']), merged['project_id'], int(merged['favorite']), int(merged['archived']), time.time(), identity))
        return self.get(identity)

    def used(self, identity, task=None):
        with self.store.connect() as db:
            if not db.execute('SELECT 1 FROM code_library WHERE id=? AND NOT archived', (identity,)).fetchone():
                raise ValueError('Dieser Eintrag ist nicht verfügbar oder archiviert.')
            if task is None:
                db.execute('UPDATE code_library SET last_used=? WHERE id=?', (time.time(), identity))
            else:
                db.execute('UPDATE code_library SET last_used=?,last_task=? WHERE id=?', (time.time(), task, identity))

    def import_entry(self, value):
        item = import_template(value)
        return self.create(item['kind'], item['title'], item['description'], item['definition'])
