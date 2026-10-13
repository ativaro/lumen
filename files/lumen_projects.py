"""Desktop projects extend the existing file-room document, without copying files."""
from lumen_i18n import tr
import time
import uuid

from file_spaces import Catalog, canonical, title, virtual, scan_source
from lumen_actions import desktop_file
from lumen_history import record
from lumen_transfers import web_url


def projects(store):
    return [room for room in Catalog(store).rooms() if room.get('project')]


def save_project(store, previous, name, sources, applications, urls, note, state=None):
    if len(sources) > 24: raise ValueError(tr('Bis zu 24 Projektordner sind möglich.'))
    sources = [dict(label=title(s['label']), location=canonical(s['location'])) for s in sources]
    if any(virtual(s['location']) for s in sources) or len({s['location'] for s in sources}) != len(sources):
        raise ValueError(tr('Bitte unterschiedliche lokale Ordner oder Netzwerkordner verwenden.'))
    if len(applications) > 20 or len(urls) > 20 or len(note) > 10000:
        raise ValueError(tr('Bis zu 20 Programme, 20 Webseiten und 10.000 Zeichen Notiz sind möglich.'))
    for app in applications: desktop_file(app)
    urls = list(dict.fromkeys(web_url(url) for url in urls))
    value = dict(previous or {}, id=previous['id'] if previous else uuid.uuid4().hex,
                 project=True, name=title(name), sources=sources, applications=applications,
                 urls=urls, note=note, updated=time.time())
    value['state'] = state if state is not None else (previous or {}).get('state', {
        'tabs': [s['location'] for s in sources], 'active': 0, 'shelf': []})
    Catalog(store).put('room', value, previous)
    record(store, tr('Projekt gespeichert: ') + value['name'], 'store-setting', previous, value,
           'files/spaces/room/' + value['id'])
    return value


def recent(root):
    entries, errors, limited = [], [], False
    # ponytail: bounded live scan; a persistent index is useful above 5,000 entries.
    for entry in scan_source(root, ' ', False, 5000):
        if 'path' in entry and not entry['directory']: entries.append(entry)
        elif 'error' in entry: errors.append(entry['error'])
        elif 'limited' in entry: limited = True
    return dict(files=sorted(entries, key=lambda e: e['modified'], reverse=True)[:30],
                errors=errors[:3], limited=limited, checked=time.time())


def validate_pin(pin):
    """Small allowlist for local room references; no executable launch strings."""
    if not isinstance(pin,dict) or pin.get('kind') not in ('object','url','chat','task'):
        raise ValueError(tr('Ungültige Projekt-Verknüpfung.'))
    kind=pin['kind'];allowed={'kind','title','resume'}|{'object':{'url','app'},'url':{'url'},'chat':{'chat'},'task':{'id'}}[kind]
    if set(pin)-allowed or not isinstance(pin.get('title'),str) or not 1<=len(pin['title'])<=4096:
        raise ValueError(tr('Ungültige Projekt-Verknüpfung.'))
    if 'resume' in pin and (type(pin['resume']) is not bool or kind not in ('object','url')):raise ValueError(tr('Ungültige Projekt-Verknüpfung.'))
    if kind=='url':web_url(pin.get('url',''))
    elif kind=='object':
        from interop_data import Registry
        ref=Registry().resolve(pin.get('url',''))
        if pin.get('app')!=ref['app'] or ref['app'] not in ('files','reader','wissen'):
            raise ValueError(tr('Diese Verknüpfung gehört nicht zu Dateien oder Notes.'))
    elif kind=='chat':
        chat=pin.get('chat',{})
        if not isinstance(chat,dict) or not isinstance(chat.get('session'),str) or not chat['session'] or len(chat['session'])>256:
            raise ValueError(tr('Ungültiges Gespräch.'))
        directory=chat.get('directory','')
        from pathlib import Path
        from network import is_network_address
        if not isinstance(directory,str) or not (Path(directory).is_absolute() or is_network_address(directory)) or '\0' in chat['session']:
            raise ValueError(tr('Ungültiges Gespräch.'))
        canonical(directory)
    elif not isinstance(pin.get('id'),str) or not pin['id'] or len(pin['id'])>256:
        raise ValueError(tr('Ungültiger Auftrag.'))
    return pin
