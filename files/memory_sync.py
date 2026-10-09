"""Personal memory replication with durable retries and explicit conflicts."""
import hashlib
import json
import time
from uuid import UUID, uuid4
from urllib.error import HTTPError

import lumen_connect as connector
from lumen_i18n import tr
from lumen_memory import Memory
from wissen_sync import remote_text


def binding(store, config, user):
    connection=connector.connection_scope(config)
    account=str(UUID(user['id']));workspace=str(UUID(user['workspace_id']))
    scope=hashlib.sha256(json.dumps([connection,account,workspace,str(Memory(store).namespace)]).encode()).hexdigest()
    return dict(connection=connection,scope=scope,user_id=account,workspace_id=workspace)


def key(choice):return 'memory/server-sync/'+choice['scope']


def info(store):
    choice=store.setting('memory/sync-choice',{})
    result=dict(enabled=bool(choice.get('enabled')),allowed=False,reachable=False,server='',user='',connection='',conflicts=0,last_sync=0)
    if choice.get('scope'):
        state=store.setting(key(choice),{})
        result.update(conflicts=len(state.get('conflicts',{})),last_sync=state.get('last_sync',0))
    try:
        config=connector.read_config();result.update(server=config['server'],connection=connector.connection_scope(config))
        result['enabled']=result['enabled'] and choice.get('connection')==result['connection']
        user=connector.request(config,'/bridge/me')
        result.update(reachable=True,user=user.get('name',''),allowed='memory_sync' in user.get('capabilities',[]) and 'memory_sync_v1' in user.get('sync_features',[]))
    except (OSError,ValueError,KeyError):pass
    return result


def configure(store, enabled, expected):
    memory=Memory(store)
    if not enabled:
        with memory.book.lock('memory-sync.lock'):
            choice=store.setting('memory/sync-choice',{});choice['enabled']=False
            store.set_setting('memory/sync-choice',choice)
        return dict(enabled=False)
    config=connector.read_config()
    if connector.connection_scope(config)!=expected:raise ValueError(tr('Die Serververbindung wurde geändert.'))
    user=connector.request(config,'/bridge/me')
    if 'memory_sync' not in user.get('capabilities',[]) or 'memory_sync_v1' not in user.get('sync_features',[]):
        raise ValueError(tr('Auf dem Server zuerst „Persönliches Gedächtnis synchronisieren“ freigeben.'))
    choice=binding(store,config,user)
    memory.migrate(False)
    with memory.book.lock('memory-sync.lock'):
        if connector.connection_scope(connector.read_config())!=choice['connection']:
            raise ValueError(tr('Die Serververbindung wurde geändert.'))
        store.set_setting('memory/sync-choice',dict(choice,enabled=True))
        with memory.book.lock('memory-state.lock'):
            records=store.setting('memory/records',{})
            for meta in records.values():
                if (meta.get('sync_user'),meta.get('sync_workspace'),meta.get('sync_server'))==(choice['user_id'],choice['workspace_id'],config['server']):
                    meta['sync_connection']=choice['connection']
                    meta['sync_blocked']=False
            store.set_setting('memory/records',records);memory.changed(True)
    return dict(enabled=True)


def row(value, identity=None):
    """Validate remote data before it can become a local file or permission flag."""
    if not isinstance(value,dict):raise ValueError('Invalid memory response')
    ident=str(UUID(value['id']))
    if identity and ident!=identity:raise ValueError('Unexpected memory identity')
    if type(value.get('revision')) is not int or value['revision']<1:raise ValueError('Invalid memory revision')
    if type(value.get('deleted')) is not bool or type(value.get('confirmed')) is not bool:raise ValueError('Invalid memory state')
    for name,limit in (('title',200),('body',20000)):
        if not isinstance(value.get(name),str) or len(value[name])>limit:raise ValueError('Invalid memory text')
    meta=value.get('memory_meta',{})
    if not isinstance(meta,dict) or meta.get('kind','fact') not in ('fact','preference','decision','solution'):raise ValueError('Invalid memory metadata')
    if meta.get('scope','global')!='global':raise ValueError('Project memory needs an explicit project mapping')
    for name,limit in (('source',2000),('evidence',500)):
        if not isinstance(meta.get(name,''),str) or len(meta.get(name,''))>limit:raise ValueError('Invalid memory provenance')
    return value


def payload(note, revision, categories=False):
    if note and (len(note['text'])>16000 or len(note['title'])>200):
        raise ValueError(tr('Für den Serverabgleich die Erinnerung auf 16.000 Zeichen und den Titel auf 200 Zeichen kürzen. Die lokale Fassung bleibt erhalten.'))
    meta=note.get('memory',{}) if note else {}
    if meta.get('scope'):
        raise ValueError(tr('Projektwissen benötigt einen eigenen Projektabgleich.'))
    return dict(revision=revision,title=note['title'] if note else 'Forgotten memory',
                body=note['text'] if note else '',deleted=note is None,
                metadata=dict(kind=meta.get('kind','fact'),source=note.get('source','') if note else '',
                              evidence=meta.get('evidence',''),automatic=bool(meta.get('automatic')),
                              verification=meta.get('verification',''),scope='global',
                              **({'correction':bool(meta.get('correction'))} if categories else {})))


def mark(memory, identity, **values):
    records=memory.store.setting('memory/records',{})
    for meta in records.values():
        if meta.get('id')==identity:meta.update(values)
    memory.store.set_setting('memory/records',records);memory.changed(True)


def synchronize(store):
    memory=Memory(store)
    with memory.book.lock('memory-sync.lock'):
        choice=store.setting('memory/sync-choice',{})
        if not choice.get('enabled'):return dict(enabled=False,changed=0,conflicts=0)
        config=connector.read_config()
        def block_remote():
            with memory.book.lock('memory-state.lock'):
                records=store.setting('memory/records',{})
                for meta in records.values():
                    if meta.get('sync_remote') and meta.get('sync_connection')==choice['connection']:meta['sync_blocked']=True
                store.set_setting('memory/records',records);memory.changed(True)
        def request(path,body=None):
            if connector.connection_scope(connector.read_config())!=choice['connection']:
                raise ValueError(tr('Die Serververbindung wurde geändert.'))
            try:result=connector.request(config,path,body)
            except HTTPError as error:
                if error.code in (401,403):block_remote()
                if error.code==409 and path.startswith('/bridge/memories?'):
                    block_remote()
                    raise ValueError(tr('Der Serverstand wurde zurückgesetzt. In den Abgleicheinstellungen „Vollständig vergleichen“ wählen.')) from None
                raise
            if connector.connection_scope(connector.read_config())!=choice['connection']:
                raise ValueError(tr('Die Serververbindung wurde geändert.'))
            return result
        user=request('/bridge/me')
        if binding(store,config,user)!= {k:choice[k] for k in ('connection','scope','user_id','workspace_id')}:
            raise ValueError(tr('Die Serververbindung wurde geändert.'))
        if 'memory_sync' not in user.get('capabilities',[]) or 'memory_sync_v1' not in user.get('sync_features',[]):
            block_remote()
            raise ValueError(tr('Der Gedächtnisabgleich ist auf dem Server nicht freigegeben.'))
        memory.migrate(False)
        state=store.setting(key(choice),dict(refs={},pending={},conflicts={},cursor=0))
        def save():
            with memory.book.lock('memory-state.lock'):
                forgotten=store.setting('memory/tombstones',{})
                state['pending']={i:p for i,p in state['pending'].items() if i not in forgotten or p['body']['deleted']}
                for name in ('conflicts','accept_remote'):
                    state[name]={i:p for i,p in state.get(name,{}).items() if i not in forgotten}
                store.set_setting(key(choice),state)
        def local():
            scanned=memory.scan()
            if scanned['limited'] or scanned['errors'] or any(n['identity_conflict'] for n in scanned['notes']):
                raise ValueError(tr('Das Gedächtnis ist unvollständig lesbar oder enthält doppelte Kennungen.'))
            return {n['id']:n for n in scanned['notes'] if not n['memory'].get('scope') and
                    n['memory'].get('sync_connection',choice['connection'])==choice['connection']}
        changed=0
        notes=local()

        def conflict(identity,remote):
            state['conflicts'][identity]=remote;save()
            with memory.book.lock('memory-state.lock'):mark(memory,identity,sync_conflict=True)

        def receive(remote):
            nonlocal changed
            identity=remote['id'];note=notes.get(identity);base=state['refs'].get(identity,{})
            forgotten=identity in store.setting('memory/tombstones',{})
            if remote['deleted']:
                if note and not forgotten:memory.forget(note['path'],note['hash'])
                else:
                    with memory.book.lock('memory-state.lock'):
                        deleted=store.setting('memory/tombstones',{})
                        deleted.setdefault(identity,dict(revision='',forgotten=time.time()))
                        store.set_setting('memory/tombstones',deleted);memory.changed(True)
                state['refs'][identity]=dict(revision=remote['revision'],hash='',path='')
                notes.pop(identity,None)
                state['conflicts'].pop(identity,None);save();changed+=1;return
            if forgotten:
                # A known tombstone wins; retain only the remote revision needed to delete it.
                state['refs'][identity]=dict(revision=remote['revision'],hash='forgotten-remote',path='')
                save();return
            if remote['revision']<=base.get('revision',0) and 'full_scan' not in state:return
            same=bool(note and note['text']==remote_text(remote) and note['title']==remote['title'] and
                      note['memory'].get('kind','fact')==remote.get('memory_meta',{}).get('kind','fact') and
                      bool(note['memory'].get('correction'))==bool(remote.get('memory_meta',{}).get('correction')))
            accepted=bool(note and state.get('accept_remote',{}).get(identity)==dict(hash=note['hash'],revision=remote['revision']))
            if note and not same and not accepted and (note['hash']!=base.get('hash') or identity in state['conflicts'] or remote['revision']<=base.get('revision',0)):
                conflict(identity,remote);return
            if same:
                state['refs'][identity]=dict(revision=remote['revision'],hash=note['hash'],path=note['path'])
                if identity in state['conflicts'] or note['memory'].get('sync_blocked'):
                    with memory.book.lock('memory-state.lock'):mark(memory,identity,sync_conflict=False,sync_blocked=False)
                state['conflicts'].pop(identity,None);state.get('accept_remote',{}).pop(identity,None);save();return
            path=note['path'] if note else 'Server-'+identity+'.md'
            with memory.book.lock('memory-state.lock'):
                if identity in store.setting('memory/tombstones',{}):
                    raise ValueError(tr('Erinnerung während des Abgleichs geändert. Erneut versuchen.'))
                if note and memory.book.read(path)['hash']!=note['hash']:
                    raise ValueError(tr('Erinnerung während des Abgleichs geändert. Erneut versuchen.'))
                records=store.setting('memory/records',{})
                meta=dict(remote.get('memory_meta',{}),id=identity,scope='',allowed=False,automatic=False,
                          verification='',sync_connection=choice['connection'],sync_remote=True,sync_conflict=False,
                          sync_user=choice['user_id'],sync_workspace=choice['workspace_id'],sync_server=config['server'],
                          updated=time.time())
                # Authorization is durable before the new file can be observed after a crash.
                records[path]=meta;store.set_setting('memory/records',records)
                note=memory.book.write(path,remote_text(remote),note['hash'] if note else '',
                    source=meta.get('source','') or config['server'],note_id=identity)
                notes[identity]=memory.save_record(note,dict(meta,hash=note['hash']),records);memory.changed(True)
            state['refs'][identity]=dict(revision=remote['revision'],hash=note['hash'],path=path)
            state['conflicts'].pop(identity,None);state.get('accept_remote',{}).pop(identity,None);save();changed+=1

        def deliver(identity):
            nonlocal changed
            save() # A concurrent native Forget invalidates unsent text, including after another receipt.
            if identity not in state['pending']:return
            pending=state['pending'][identity]
            answer=request('/bridge/memories/'+identity,pending['body'])
            remote=row(answer.get('memory'),identity)
            if type(answer.get('applied')) is not bool or type(answer.get('revision')) is not int:
                raise ValueError('Invalid memory receipt')
            if answer['applied']:
                state['refs'][identity]=dict(revision=answer['revision'],hash=pending['hash'],path=pending['path'])
                with memory.book.lock('memory-state.lock'):
                    mark(memory,identity,sync_connection=choice['connection'],sync_conflict=False,
                         sync_user=choice['user_id'],sync_workspace=choice['workspace_id'],sync_server=config['server'])
                state['conflicts'].pop(identity,None);changed+=1
            else:conflict(identity,remote)
            state['pending'].pop(identity,None);save()
            if remote['deleted'] or (answer['applied'] and remote['revision']!=answer['revision']):receive(remote)

        for identity in list(state['pending']):deliver(identity)
        cursor=state['cursor'];seen=0
        while True:
            page=request('/bridge/memories?after='+str(cursor))
            if (page.get('protocol')!=1 or page.get('user_id')!=choice['user_id'] or
                page.get('workspace_id')!=choice['workspace_id'] or not isinstance(page.get('items'),list) or len(page['items'])>100 or
                type(page.get('cursor')) is not int or page['cursor']<cursor or type(page.get('more')) is not bool):
                raise ValueError('Invalid memory sync page')
            seen+=len(page['items'])
            if seen>5000:raise ValueError('Memory sync capacity reached')
            for item in page['items']:
                remote=row(item)
                if 'full_scan' in state:state['full_scan'][remote['id']]=True
                receive(remote)
            if page['more'] and page['cursor']==cursor:raise ValueError('Memory sync cursor did not advance')
            cursor=page['cursor'];state['cursor']=cursor;save()
            if not page['more']:break
        if 'full_scan' in state:
            for identity,base in state['refs'].items():
                if identity not in state['full_scan']:
                    base.update(revision=0,hash='missing-after-restore')
            state.pop('full_scan');save()
        notes=local();tombstones=store.setting('memory/tombstones',{})
        for identity in sorted(set(notes)|(set(tombstones)&set(state['refs']))):
            if identity in state['conflicts']:continue
            note=notes.get(identity);base=state['refs'].get(identity,{})
            checksum=note['hash'] if note else ''
            if checksum==base.get('hash'):continue
            change=payload(note,base.get('revision',0),'memory_categories_v1' in user.get('sync_features',[]));change['operation_id']=str(uuid4())
            state['pending'][identity]=dict(body=change,hash=checksum,path=note['path'] if note else base.get('path',''))
            save();deliver(identity)
        state['last_sync']=time.time();save()
        return dict(enabled=True,changed=changed,conflicts=len(state['conflicts']),last_sync=state['last_sync'])


def rescan(store):
    """Explicit recovery after a server restore; keep local copies, receipts and tombstones."""
    memory=Memory(store)
    with memory.book.lock('memory-sync.lock'),memory.book.lock('memory-state.lock'):
        choice=store.setting('memory/sync-choice',{})
        if not choice.get('enabled') or connector.connection_scope(connector.read_config())!=choice.get('connection'):
            raise ValueError(tr('Die Serververbindung wurde geändert.'))
        state=store.setting(key(choice),dict(refs={},pending={},conflicts={},cursor=0))
        state.update(cursor=0,full_scan={});store.set_setting(key(choice),state)
    return dict(pending=True)


def conflicts(store, identity=None):
    choice=store.setting('memory/sync-choice',{})
    if not choice.get('scope'):return []
    if connector.connection_scope(connector.read_config())!=choice['connection']:return []
    state=store.setting(key(choice),{});notes={n['id']:n for n in Memory(store).scan()['notes']}
    entries=state.get('conflicts',{})
    if identity:
        if identity not in entries:raise ValueError(tr('Der Konflikt wurde inzwischen geändert. Bitte erneut öffnen.'))
        return dict(id=identity,remote=entries[identity],local=notes.get(identity))
    return [dict(id=identity,title=value['title']) for identity,value in entries.items()]


def resolve(store, identity, use_server, expected_revision, expected_hash):
    memory=Memory(store)
    with memory.book.lock('memory-sync.lock'),memory.book.lock('memory-state.lock'):
        choice=store.setting('memory/sync-choice',{})
        if connector.connection_scope(connector.read_config())!=choice.get('connection'):
            raise ValueError(tr('Die Serververbindung wurde geändert.'))
        state=store.setting(key(choice),{})
        if identity in state.get('pending',{}):raise ValueError(tr('Eine Änderung wartet noch auf Bestätigung. Zuerst erneut abgleichen.'))
        remote=state.get('conflicts',{}).get(identity)
        note=next((n for n in memory.scan()['notes'] if n['id']==identity),None)
        checksum=note['hash'] if note else ''
        if not remote or remote['revision']!=expected_revision or checksum!=expected_hash:
            raise ValueError(tr('Der Konflikt wurde inzwischen geändert. Bitte erneut öffnen.'))
        if use_server:
            if not note:raise ValueError(tr('Diese Erinnerung wurde vergessen. Bei Bedarf ausdrücklich einen neuen Eintrag anlegen.'))
            state.setdefault('accept_remote',{})[identity]=dict(hash=checksum,revision=expected_revision)
            state['cursor']=0
        else:
            change=payload(note,expected_revision);change['operation_id']=str(uuid4())
            state['pending'][identity]=dict(body=change,hash=checksum,path=note['path'] if note else '')
        store.set_setting(key(choice),state)
    return dict(pending=True)


def worker(job,store,action,**values):
    import sys
    from pathlib import Path
    request=dict(store=str(store.directory),action=action,**values)
    return json.loads(job.command([sys.executable,str(Path(__file__))],data=json.dumps(request).encode(),timeout=65,max_output=8*1024**2))


if __name__=='__main__':
    import signal
    import sys
    from lumen_store import Store
    signal.alarm(60)
    request=json.loads(sys.stdin.read() or '{}')
    store=Store(request.pop('store',None));action=request.pop('action','synchronize')
    try:
        if action not in ('info','configure','synchronize','conflicts','resolve','rescan'):raise ValueError('Invalid memory sync action')
        result=globals()[action](store,**request)
        if action=='synchronize':store.set_setting('memory/sync-status',dict(ok=True,time=time.time(),**result))
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        store.set_setting('memory/sync-status',dict(ok=False,time=time.time()))
        print(str(error),file=sys.stderr);sys.exit(1)
