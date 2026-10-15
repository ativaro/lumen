"""Project references never execute tasks or read the referenced contents."""
from pathlib import Path
import sys
from lumen_i18n import tr


def validate(value, root=None, check_source=True):
    if not isinstance(value, dict) or value.get('kind') not in ('file', 'folder', 'url', 'object', 'chat', 'task'):
        raise ValueError(tr('Ungültiger Projektverweis.'))
    kind = value['kind']
    fields = {'kind', 'title'} | ({'chat'} if kind == 'chat' else {'id'} if kind == 'task' else {'target'})
    if set(value) != fields or not isinstance(value['title'], str) or not 1 <= len(value['title']) <= 4096:
        raise ValueError(tr('Ungültiger Projektverweis.'))
    if 'target' in fields and not isinstance(value['target'], str):
        raise ValueError(tr('Ungültiger Projektverweis.'))
    result = dict(value)
    if kind == 'chat':
        chat = value['chat']
        if not isinstance(chat, dict) or set(chat) != {'directory', 'session'}:
            raise ValueError(tr('Ungültiger Gesprächsverweis.'))
        result['chat'] = dict(directory=directory(chat['directory']), session=session(chat['session']))
    elif kind == 'task':
        if not isinstance(value['id'], str): raise ValueError(tr('Ungültige Auftragskennung.'))
        from lumen_panel import valid_task
        result['id'] = valid_task(value['id'])
    elif kind in ('file','folder'):
        from file_spaces import canonical, virtual
        result['target'] = canonical(value['target'])
        if virtual(result['target']): raise ValueError(tr('Eine Originaldatei oder einen Ordner verknüpfen.'))
    elif kind == 'url':
        from tools_data import web_url
        result['target'] = web_url(value['target'])
    else:
        from interop_data import Registry
        if check_source: Registry(root).resolve(value['target'])
        else:
            from interop_data import base_url
            base_url(value['target'])
    return result


def directory(value):
    from file_spaces import canonical, virtual
    value = canonical(value)
    if virtual(value): raise ValueError(tr('Ungültiger Gesprächsordner.'))
    return value


def session(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        raise ValueError(tr('Ungültiges Gespräch.'))
    return value


def identity(value):
    if value['kind'] == 'chat': return ('chat', value['chat']['directory'], value['chat']['session'])
    return (value['kind'], value.get('id', value.get('target')))


def change(library, project, expected_updated, reference, remove=False):
    value = validate(reference, library.root.parent, check_source=not remove)
    record = library.get(project)
    field = 'references' if value['kind'] in ('chat', 'task') else 'resources'
    rows = record.get(field, [])
    key = identity(value)
    updated = [row for row in rows if identity(row) != key]
    if not remove: updated.append(value)
    library.update(project, expected_updated=expected_updated, **{field: updated})


def open_reference(value, store):
    from PySide6.QtCore import QProcess
    value = validate(value)
    command = [str(Path(__file__).resolve().parents[1]/'agent-app/main.py')]
    if value['kind'] == 'task':
        store.task(value['id'])
        command += ['--task', value['id']]
    elif value['kind'] == 'chat':
        chat = value['chat']
        from network import is_network_address
        if is_network_address(chat['directory']) or not Path(chat['directory']).is_dir():
            raise ValueError(tr('Der ursprüngliche Gesprächsordner ist nicht erreichbar.'))
        command += ['--directory', chat['directory'], '--session', chat['session']]
    else:
        raise ValueError(tr('Hier ein Gespräch oder einen Auftrag auswählen.'))
    started, _ = QProcess.startDetached(sys.executable, command)
    if not started: raise OSError(tr('Lumen konnte nicht geöffnet werden.'))
