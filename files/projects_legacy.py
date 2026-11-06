"""Convert saved file rooms into collections without opening or moving their sources."""
import json
import time
import uuid
from pathlib import Path
from file_spaces import Catalog, canonical, virtual
from interop_paths import revision
from lumen_i18n import tr


def project_id(legacy_id):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'lumen:legacy-room:' + legacy_id).hex



def resolve_project_id(db, legacy_id):
    """Use the preserved project binding, including links created before this migration."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='project_rooms'").fetchone():
        bound = db.execute('SELECT project FROM project_rooms WHERE room=?', (legacy_id,)).fetchone()
        if bound: return bound[0]
    return project_id(legacy_id)


def migrate(library, store):
    """One transaction per collection; keep original settings and never overwrite edits."""
    imported = []
    for room in Catalog(store).rooms():
        if room['id'] == 'previous':
            continue  # Automatic window snapshot is not a user-created collection.
        with library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            key = resolve_project_id(db, room['id'])
            old = db.execute('SELECT data FROM records WHERE id=?', (key,)).fetchone()
            original = json.loads(old['data']) if old else {}
            if original.get('legacy_room', {}).get('id') == room['id']:continue
            if old and key == project_id(room['id']):
                raise ValueError(tr('Die Projektkennung ist bereits belegt. Originaldaten bleiben erhalten.'))
            state = room.get('state', {})
            resources, references, seen = [], [], set()
            def material(kind, target, title):
                if target and (kind, target) not in seen:
                    seen.add((kind, target))
                    resources.append(dict(kind=kind, target=target, title=title or target))
            for source in room.get('sources', []):
                if not virtual(source['location']):
                    target = canonical(source['location'])
                    material('file', target, source.get('label', ''))
            shelf = [item['location'] for item in Catalog(store).objects('room-shelf/' + room['id'])]
            for target in state.get('tabs', []) + state.get('shelf', []) + shelf + state.get('selection', []) + state.get('chat', {}).get('paths', []):
                if not virtual(target):
                    target = canonical(target)
                    material('file', target, Path(target).name)
            for url in room.get('urls', []):
                material('url', url, url)
            for pin in room.get('pins', []):
                if pin['kind'] in ('object', 'url'):
                    material(pin['kind'], pin['url'], pin['title'])
                elif pin['kind'] == 'chat':
                    references.append(dict(kind='chat', title=pin['title'], chat=dict(directory=canonical(pin['chat']['directory']), session=pin['chat']['session'])))
                elif pin['kind'] == 'task':
                    references.append(dict(kind='task', title=pin['title'], id=pin['id']))
            chat = dict(state.get('chat', {}))
            if chat.get('session'): chat['directory'] = canonical(chat['directory'])
            if chat.get('session') and not any(r['kind'] == 'chat' and r['chat'].get('session') == chat['session'] and r['chat'].get('directory') == chat.get('directory') for r in references):
                references.append(dict(kind='chat', title=tr('Gespeichertes Gespräch'), chat=dict(directory=chat.get('directory', ''), session=chat['session'])))
            for task_id in state.get('tasks', []):
                if any(r['kind'] == 'task' and r['id'] == task_id for r in references):
                    continue
                tasks = store.rows('SELECT title FROM tasks WHERE id=?', (task_id,))
                references.append(dict(kind='task', id=task_id, title=tasks[0]['title'] if tasks else tr('Gespeicherter Auftrag')))
            notes = room.get('note', '')
            draft = state.get('chat', {}).get('draft', '')
            if draft: notes += '\n\n' + tr('Übernommener Gesprächsentwurf (nicht gesendet):') + '\n' + draft
            data = dict(notes=notes, resources=resources, references=references,
                        questions=[], legacy_room=room, interop_path_revision=revision(library.root.parent))
            if old:
                merged = dict(original)
                merged['resources'] = list(original.get('resources', []))
                for item in resources:
                    if not any((v.get('kind'),v.get('target')) == (item['kind'],item['target']) for v in merged['resources']):merged['resources'].append(item)
                merged['references'] = list(original.get('references', []))
                for item in references:
                    if item not in merged['references']:merged['references'].append(item)
                merged['notes'] = original.get('notes','') + ('\n\n'+notes if notes else '')
                merged['legacy_room'] = room
                db.execute('UPDATE records SET data=?,updated=? WHERE id=?',(json.dumps(merged),time.time(),key))
            else:
                db.execute('INSERT INTO records VALUES(?,?,?,?,?)', (key, room['name'], json.dumps(data), 0, time.time()))
            imported.append(key)
    return imported
