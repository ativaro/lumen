"""Desktop projects extend the existing file-room document, without copying files."""
import time
import uuid

from file_spaces import Catalog, canonical, title, virtual, scan_source
from lumen_actions import desktop_file
from lumen_history import record
from lumen_transfers import web_url


def projects(store):
    return [room for room in Catalog(store).rooms() if room.get('project')]


def save_project(store, previous, name, sources, applications, urls, note, state=None):
    if not 1 <= len(sources) <= 24: raise ValueError('Bitte 1 bis 24 Projektordner angeben.')
    sources = [dict(label=title(s['label']), location=canonical(s['location'])) for s in sources]
    if any(virtual(s['location']) for s in sources) or len({s['location'] for s in sources}) != len(sources):
        raise ValueError('Bitte unterschiedliche lokale Ordner oder Netzwerkordner verwenden.')
    if len(applications) > 20 or len(urls) > 20 or len(note) > 10000:
        raise ValueError('Bis zu 20 Programme, 20 Webseiten und 10.000 Zeichen Notiz sind möglich.')
    for app in applications: desktop_file(app)
    urls = list(dict.fromkeys(web_url(url) for url in urls))
    value = dict(previous or {}, id=previous['id'] if previous else uuid.uuid4().hex,
                 project=True, name=title(name), sources=sources, applications=applications,
                 urls=urls, note=note, updated=time.time())
    value['state'] = state if state is not None else (previous or {}).get('state', {
        'tabs': [s['location'] for s in sources], 'active': 0, 'shelf': []})
    Catalog(store).put('room', value, previous)
    record(store, 'Projekt gespeichert: ' + value['name'], 'store-setting', previous, value,
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
