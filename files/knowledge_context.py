"""Live AI consent for paired Server Notes; no local notebook or replica grants."""
from urllib.parse import quote
import lumen_connect


def active(store):
    try: return lumen_connect.read_config()
    except FileNotFoundError: return None


def fetch(memory, query):
    bound = active(memory.store)
    if not bound or not query.strip(): return [], None
    config = bound
    user = lumen_connect.request(config, '/bridge/me', timeout=3)
    if not {'notes', 'memory'} <= set(user['capabilities']) or 'knowledge_context_v1' not in user.get('sync_features', []):
        return [], None
    rows = lumen_connect.request(config, '/bridge/knowledge-context?q=' + quote(query[:200]), timeout=3)
    if not isinstance(rows, list) or len(rows) > 4: raise ValueError('Invalid knowledge context')
    notes = []
    for row in rows:
        if len(row['text']) > 1800: raise ValueError('Invalid knowledge context size')
        notes.append(dict(id='server-note:'+row['id'], path='server-note:'+row['id'], remote_id=row['id'],
                          title=row['title'], text=row['text'], revision=row['revision'],
                          source=config['server']+'#'+row['id'], source_kind='server_note'))
    return notes, config


def valid(store, bound, notes):
    if not bound or not notes: return not notes
    current = active(store)
    config = bound
    if current != config: return False
    refs = [dict(id=n['remote_id'], revision=n['revision']) for n in notes]
    result = lumen_connect.request(config, '/bridge/knowledge-context/validate', dict(notes=refs), timeout=3)
    return result.get('valid') is True
