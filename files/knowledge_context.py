"""Opt-in, live server consent for the currently paired notebook; no offline grant cache."""
from urllib.parse import quote
import lumen_connect
from wissen_data import Notebook
from wissen_sync import settings, scope


def active(store):
    if not store.setting('knowledge/notebook', ''): return None
    book = Notebook(store)
    try: config = lumen_connect.read_config()
    except FileNotFoundError: return None
    _, state = settings(book, config)
    if not state.get('enabled') or not state.get('server_context'):
        return None
    return book, config, scope(book, config)


def fetch(memory, query):
    bound = active(memory.store)
    if not bound or not query.strip(): return [], None
    book, config, identity = bound
    user = lumen_connect.request(config, '/bridge/me', timeout=3)
    if not {'notes', 'memory'} <= set(user['capabilities']) or 'knowledge_context_v1' not in user.get('sync_features', []):
        return [], None
    suffix = ''
    rows = lumen_connect.request(config, '/bridge/knowledge-context' + suffix + ('&' if suffix else '?') + 'q=' + quote(query[:200]), timeout=3)
    if not isinstance(rows, list) or len(rows) > 4: raise ValueError('Invalid knowledge context')
    notes = []
    for row in rows:
        if memory.share_decision(book, row['path']) is False: continue
        if len(row['text']) > 1800: raise ValueError('Invalid knowledge context size')
        notes.append(dict(id='server-note:'+row['id'], path='server-note:'+row['id'], remote_id=row['id'],
                          title=row['title'], text=row['text'], revision=row['revision'],
                          source=config['server']+'#'+row['id'], source_kind='server_note'))
    return notes, (config, identity, suffix)


def valid(store, bound, notes):
    if not bound or not notes: return not notes
    current = active(store)
    config, identity, suffix = bound
    if not current or current[2] != identity: return False
    refs = [dict(id=n['remote_id'], revision=n['revision']) for n in notes]
    result = lumen_connect.request(config, '/bridge/knowledge-context/validate' + suffix, dict(notes=refs), timeout=3)
    return result.get('valid') is True
