"""Live AI consent for paired Server Notes; no local notebook or replica grants."""
from urllib.parse import quote
import re
from uuid import UUID
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


def account_memory(config, query):
    """Never replace an unavailable paired account with old local memories."""
    user = lumen_connect.request(config, '/bridge/me', timeout=3)
    if 'memory' not in user['capabilities']:
        raise ValueError('Server-Gedächtnis für dieses Gerät nicht freigegeben.')
    if 'memory_context_v1' not in user.get('sync_features', []):
        raise ValueError('Der Server unterstützt den aktuellen Gedächtniszugriff noch nicht.')
    result = lumen_connect.request(config, '/bridge/memories/context?q='+quote(query[:200]), timeout=3)
    if not isinstance(result, dict) or not re.fullmatch('[0-9a-f]{64}', result.get('stamp', '')):
        raise ValueError('Invalid memory context revision')
    rows = result.get('items')
    if not isinstance(rows, list) or len(rows)>6: raise ValueError('Invalid memory context')
    notes=[]
    for row in rows:
        identity=str(UUID(row['id']))
        if (type(row['revision']) is not int or row['revision']<1
                or not isinstance(row['title'],str) or len(row['title'])>200
                or not isinstance(row['text'],str) or len(row['text'])>1800):
            raise ValueError('Invalid memory context entry')
        notes.append(dict(id='server:'+identity,path='server:'+identity,remote_id=identity,
                          title=row['title'],text=row['text'],revision=row['revision'],
                          source=config['server']+'#'+identity,source_kind='server_memory',
                          origin='Lumen Server · Gedächtnis'))
    if lumen_connect.read_config()!=config: raise ValueError('Die Serververbindung wurde geändert.')
    preferences=result.get('preferences')
    if preferences is not None and (not isinstance(preferences,dict)
            or any(type(preferences.get(k)) is not bool for k in ('enabled','learn','solutions','automatic'))
            or type(preferences.get('revision')) is not int or preferences['revision']<0):
        raise ValueError('Invalid learning consent')
    return notes,dict(connection=lumen_connect.connection_scope(config),stamp=result['stamp'],preferences=preferences)


def account_memory_valid(remote):
    current=lumen_connect.read_config()
    if lumen_connect.connection_scope(current)!=remote['connection']: return False
    result=lumen_connect.request(current,'/bridge/memories/context/validate',dict(stamp=remote['stamp']),timeout=3)
    return result.get('valid') is True and lumen_connect.read_config()==current


def learning_receipt(result):
    identity=str(UUID(result['task_id']))
    if (result.get('state') not in ('queued','running','completed','skipped','failed')
            or any(type(result.get(k)) is not int or not 0<=result[k]<=3 for k in ('saved','pending'))):
        raise ValueError('Invalid learning receipt')
    return dict(task_id=identity,state=result['state'],saved=result['saved'],pending=result['pending'])


def learning(config,remote,text,event_id,context):
    user=lumen_connect.request(config,'/bridge/me',timeout=3)
    if not {'memory','tasks'}<=set(user['capabilities']) or 'memory_learning_v1' not in user.get('sync_features',[]):
        raise ValueError('Server-Lernen ist für dieses Gerät nicht verfügbar.')
    body=dict(event_id=str(UUID(event_id.removeprefix('msg_'))),text=text,
              preferences_revision=remote['preferences']['revision'])
    if context:body['previous_answer']=context
    if lumen_connect.read_config()!=config:raise ValueError('Die Serververbindung wurde geändert.')
    result=lumen_connect.request(config,'/bridge/memory-learning',body,timeout=4)
    if lumen_connect.read_config()!=config:raise ValueError('Die Serververbindung wurde geändert.')
    return learning_receipt(result)
