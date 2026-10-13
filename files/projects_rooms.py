"""Local identity links; project planning and room references keep their originals."""
import json
import time
import uuid
from lumen_i18n import tr
from file_spaces import Catalog


class ProjectRooms:
    def __init__(self, library, store):
        self.library, self.store = library, store
        with library.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS project_rooms (project TEXT PRIMARY KEY, room TEXT UNIQUE NOT NULL)')
            db.execute("CREATE TABLE IF NOT EXISTS project_flows (flow TEXT PRIMARY KEY, project TEXT NOT NULL, scope TEXT NOT NULL DEFAULT '')")

    def flows(self,project):
        with self.library.connect() as db:
            linked=dict(db.execute('SELECT flow,scope FROM project_flows WHERE project=?',(project,)).fetchall())
        return [dict(f,project_scope=linked[f['id']]) for f in self.store.workflows() if f['id'] in linked]

    def attach_flow(self,project,scope,flow):
        self.library.get(project)
        if scope:
            from projects_data import Projects
            item=Projects(self.library).get(scope)
            if item['project']!=project or item['kind']!='initiative':raise ValueError(tr('Ungültiges Vorhaben.'))
        if not any(f['id']==flow for f in self.store.workflows()):raise ValueError(tr('Ablauf nicht mehr vorhanden.'))
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT project,scope FROM project_flows WHERE flow=?',(flow,)).fetchone()
            if current and tuple(current)!=(project,scope):raise ValueError(tr('Dieser Ablauf gehört bereits zu einem anderen Vorhaben.'))
            db.execute('INSERT OR IGNORE INTO project_flows VALUES (?,?,?)',(flow,project,scope))

    def links(self):
        with self.library.connect() as db:
            return dict(db.execute('SELECT project,room FROM project_rooms').fetchall())

    def unlink(self,project):
        with self.library.connect() as db:db.execute('DELETE FROM project_rooms WHERE project=?',(project,))

    def detach_flow(self,project,flow):
        with self.library.connect() as db:db.execute('DELETE FROM project_flows WHERE project=? AND flow=?',(project,flow))

    def room(self, project):
        identity = self.links().get(project)
        return next((r for r in Catalog(self.store).rooms() if r['id'] == identity), None)

    def link(self, project, room):
        self.library.get(project)
        if not any(r['id'] == room and r.get('project') for r in Catalog(self.store).rooms()):
            raise ValueError(tr('Projekt nicht mehr vorhanden.'))
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = dict(db.execute('SELECT project,room FROM project_rooms').fetchall())
            if existing.get(project) == room: return
            if project in existing or room in existing.values():
                raise ValueError(tr('Diese Projektumgebung ist bereits zugeordnet.'))
            db.execute('INSERT INTO project_rooms VALUES (?,?)', (project, room))

    def from_room(self, room):
        """One explicit open creates planning once, even across two windows."""
        latest = next((r for r in Catalog(self.store).rooms() if r['id'] == room['id']), None)
        if latest is None: raise ValueError(tr('Projekt nicht mehr vorhanden.'))
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT project FROM project_rooms WHERE room=?', (room['id'],)).fetchone()
            if row: return row[0]
            key = uuid.uuid4().hex
            db.execute('INSERT INTO records VALUES (?,?,?,?,?)',
                       (key, latest['name'], json.dumps(dict(notes='', resources=[], questions=[])), 0, time.time()))
            db.execute('INSERT INTO project_rooms VALUES (?,?)', (key, room['id']))
            return key

    def ensure(self, project):
        current = self.room(project)
        if current: return current
        record = self.library.get(project)
        if project in self.links(): raise ValueError(tr('Die gespeicherte Projektumgebung fehlt. Bitte die Sicherung prüfen.'))
        # Deterministic IDs make an interrupted first open safe to repeat.
        identity = uuid.uuid5(uuid.NAMESPACE_URL, str(self.library.db.resolve()) + '#' + project).hex
        catalog = Catalog(self.store)
        value = next((r for r in catalog.rooms() if r['id'] == identity), None)
        if value is None:
            value = dict(id=identity, name=record['title'], project=True, sources=[], applications=[],
                         urls=[], note='', pins=[], updated=time.time(), state=dict(tabs=[],active=0,shelf=[]))
            with self.store.connect() as db:
                from file_spaces import PREFIX
                db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (PREFIX+'room/'+identity,json.dumps(value)))
        self.link(project, identity)
        return self.room(project)

    def material(self, project):
        room = self.room(project) or {}; values = []
        for source in room.get('sources', []):
            values.append(dict(kind='folder', target=source['location'], title=source['label']))
        for url in room.get('urls', []): values.append(dict(kind='url', target=url, title=url))
        for pin in room.get('pins', []):
            if pin['kind'] in ('object', 'url'):
                values.append(dict(kind='url' if pin['kind']=='url' else 'file', target=pin['url'], title=pin['title']))
        from interop_paths import revision
        return dict(title=room.get('name', ''), notes=room.get('note', ''), resources=values,
                    interop_path_revision=revision(self.library.root.parent))


def source_chain(projects, project, scope='', store=None):
    from lumen_store import Store
    values = [projects.library.get(project)]
    if scope:
        item = projects.get(scope)
        if item['project'] != project: raise ValueError(tr('Dieser Eintrag gehört zu einem anderen Projekt.'))
        if item['kind'] != 'initiative': values.append(projects.get(item['parent']))
        values.append(item)
    room = ProjectRooms(projects.library, store or Store()).material(project)
    return [room, *values]
