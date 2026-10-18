"""Opt-in text note replication; existing Notebook CAS/history own local writes."""
import re
import time
import os
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote
from lumen_i18n import tr
from wissen_data import digest
import lumen_connect


def scope_parts(book):
    from sync_migration import note_scope_parts
    return note_scope_parts(book)


def scope(book, config):
    parts = scope_parts(book)
    extra = ('\0' + parts[-1]) if parts[-1] else ''
    from sync_identity import scope as stable_scope
    return stable_scope(config, parts,
        digest((config['server']+'\0'+config['token']+'\0'+str(book.root)+'\0'+str(book.identity)+extra).encode()))


def settings(book, config):
    memory_root=(book.store.directory/'lumen-memory').resolve()
    if book.root.is_relative_to(memory_root) or memory_root.is_relative_to(book.root):
        raise ValueError(tr('Für den Notizabgleich einen persönlichen Notizordner außerhalb des Lumen-Gedächtnisses wählen.'))
    key='knowledge/server-sync/'+scope(book,config)
    return key, book.store.setting(key, {'enabled':False,'notes':{}})


def sync_info(book):
    config=lumen_connect.read_config();key,state=settings(book,config)
    try:
        user=lumen_connect.request(config,'/bridge/me');reachable=True
    except Exception:
        user=dict(name=state.get('user',''),capabilities=[]);reachable=False
    return dict(attachments=state.get('attachments',False),scope=scope(book,config),server=config['server'],user=user['name'],enabled=state['enabled'],allowed='notes' in user['capabilities'],reachable=reachable,last_sync=state.get('last_sync',0))


def sync_config(book, expected, enabled, attachments=None):
    config=lumen_connect.read_config()
    if scope(book,config)!=expected:raise ValueError(tr('Die Serververbindung hat sich geändert. Bitte erneut öffnen.'))
    info=sync_info(book) if enabled else {}
    if enabled and not info['allowed']:raise ValueError(tr('Auf dem Server zuerst die Gerätefähigkeit „Notizen synchronisieren“ freigeben.'))
    with book.lock('wissen-sync.lock'):
        key,state=settings(book,config);state['enabled']=bool(enabled)
        if attachments is not None:state['attachments']=bool(attachments)
        if info:state['user']=info['user']
        book.store.set_setting(key,state)
    # Explicit activation binds background work to this notebook inode and account.
    book.store.set_setting('knowledge/background-sync',dict(enabled=bool(enabled),
        root=str(book.root),identity=book.identity,scope=scope(book,config)))
    return {'enabled':bool(enabled)}


def enabled(book):
    try:return settings(book,lumen_connect.read_config())[1]['enabled']
    except (OSError,ValueError,KeyError):return False


def remote_text(row):
    title=' '.join(row['title'].split())
    from notes_structure import document_parts
    prefix, _old_title, gap, suffix, _found = document_parts(row['body'], title)
    return prefix+'# '+title+gap+suffix


def payload(note, revision):
    return dict(revision=revision,title=note['title'] if note else 'Deleted note',body=note['text'] if note else '',deleted=note is None,**({'path':note['path']} if note else {}),**({'assets':note['sync_assets']} if note and 'sync_assets' in note else {}))


def folder(book):
    try:
        with book.directory('Server'):pass
    except FileNotFoundError:
        try:book.create_collection('Server')
        except FileExistsError:pass


def conflict_copy(book, identity, note):
    folder(book)
    path='Server/Konflikt-'+identity+'-'+note['hash'][:16]+'.md'
    text='# '+tr('Konflikt · {0}',note['title'][:170])+'\n\n'+note['text']
    try:
        existing=book.read(path)
        if existing['text']!=text:raise ValueError(tr('Die Konfliktkopie wurde inzwischen bearbeitet. Bitte zuerst prüfen.'))
    except FileNotFoundError:
        book.write(path,text,'',source=note['source'],created=note['created'],note_id=str(uuid4()))
    return path


def ensure_folder(book,path):
    parent=Path('.')
    for part in Path(path).parts:
        if part=='.':continue
        with book.directory(parent) as fd:
            try:os.mkdir(part,mode=0o700,dir_fd=fd);os.fsync(fd)
            except FileExistsError:pass
        parent=parent/part
        with book.directory(parent):pass


def finish_move(book,key,state):
    move=state.get('pending_move')
    if not move:return
    source,target=move['source'],book.relative(move['target'])
    ensure_folder(book,target.parent)
    try:
        result=book.read(target)
        if result['note_id']!=move['id'] or result['text']!=move['text']:
            raise ValueError(tr('Eine verschobene Notiz wurde geändert. Beide Dateien bleiben erhalten.'))
    except FileNotFoundError:result=book.write(target,move['text'],'',note_id=move['id'])
    if source and source!=str(target):
        try:old=book.read(source)
        except FileNotFoundError:pass
        else:
            if old['hash']!=move['hash']:raise ValueError(tr('Eine verschobene Notiz wurde geändert. Beide Dateien bleiben erhalten.'))
            book.remove(source,old['hash'])
    state['notes'][move['id']]=dict(revision=move['revision'],path=str(target),hash=result['hash'],assets=move.get('assets',[]))
    del state['pending_move'];book.store.set_setting(key,state)


def sync(book):
    config=lumen_connect.read_config()
    state = {}
    def request(path,body=None):
        from sync_migration import note_request
        return lumen_connect.request(config,note_request(path,state) if body is not None else path,body)
    with book.lock('wissen-sync.lock'):
        from notes_move import pending
        if pending(book):raise ValueError(tr('Zuerst den offenen Verschiebevorgang fortsetzen oder zurücknehmen.'))
        key,state=settings(book,config)
        if not state['enabled']:return dict(enabled=False,changed=0,conflicts=[])
        user=request('/bridge/me')
        if 'notes' not in user['capabilities']:raise ValueError(tr('Die Notizfreigabe wurde entzogen. Lokale Notizen bleiben erhalten.'))
        finish_move(book,key,state)
        scanned=book.scan()
        if scanned['limited'] or scanned['errors']:raise ValueError(tr('Der Notizordner ist nicht vollständig lesbar. Es wurde kein Abgleich gestartet.'))
        if any(len(n['text'])>200000 or len(n['title'])>200 for n in scanned['notes']):
            raise ValueError(tr('Servernotizen sind auf 200.000 Zeichen und 200 Zeichen im Titel begrenzt.'))
        from sync_migration import pending_notes, asset_target
        scanned=pending_notes(book,state,scanned)
        book.store.set_setting(key,state)
        if state.get('attachments'):
            from wissen_sync_assets import prepare
            uploaded=set(state.get('asset_receipts',[]))
            def remember_assets(values):
                state['asset_receipts']=sorted(values);book.store.set_setting(key,state)
            for index,note in enumerate(scanned['notes']):
                value,assets=prepare(book,note,config,asset_target(note['note_id'],state),uploaded,remember_assets);value['sync_assets']=assets;scanned['notes'][index]=value
        local={};remote={};cursor=None
        # ponytail: scan metadata for at most 5000 notes; use a change feed for larger libraries.
        # Fetch bounded metadata, including tombstones. Never infer remote deletion
        # from an absent list item; concurrent inserts are seen on the next pass.
        while True:
            page=request('/bridge/notes'+('?after='+quote(cursor) if cursor else ''))
            for row in page['items']:remote[row['id']]=row
            if len(remote)>5000:raise ValueError(tr('Zu viele Servernotizen für diesen Abgleich.'))
            next_cursor=page['next']
            if not next_cursor:break
            if next_cursor==cursor:raise ValueError(tr('Ungültige Serverseite.'))
            cursor=next_cursor
        known_paths={entry['path']:identity for identity,entry in state['notes'].items() if entry['path']}
        for note in scanned['notes']:
            identity=note['note_id'] or known_paths.get(note['path']) or str(uuid4())
            if identity in local:raise ValueError(tr('Zwei Notizdateien tragen dieselbe Kennung. Bitte die Kopie zuerst prüfen.'))
            if not note['note_id']:
                assets=note.get('sync_assets');note=book.write(note['path'],note['text'],note['hash'],note_id=identity)
                if assets is not None:note['sync_assets']=assets
            local[identity]=note
        # Refuse an unreadable replacement before any server mutation.
        for identity,entry in state['notes'].items():
            if identity not in local and entry['path']:
                try:book.read(entry['path'])
                except FileNotFoundError:pass
                else:raise ValueError(tr('Der Notizordner wurde während des Abgleichs geändert. Erneut versuchen.'))
        changed=0;conflicts=[]
        for identity in sorted(set(local)|set(remote)|set(state['notes'])):
            entry=state['notes'].get(identity,dict(revision=0,path='',hash=''))
            note=local.get(identity)
            path=note['path'] if note else entry['path']
            if not note and path:
                # A symlink or unreadable replacement is not a deletion.
                try:book.read(path)
                except FileNotFoundError:pass
                else:raise ValueError(tr('Der Notizordner wurde während des Abgleichs geändert. Erneut versuchen.'))
            metadata=remote.get(identity)
            local_changed=(note['hash'] if note else '')!=entry['hash'] or bool(note and entry['path'] and path!=entry['path']) or bool(note and 'sync_assets' in note and note['sync_assets']!=entry.get('assets',[]))
            server_changed=metadata is not None and metadata['revision']!=entry['revision']
            if not local_changed and not server_changed:
                if note and entry['path']!=path:
                    entry['path']=path;state['notes'][identity]=entry;book.store.set_setting(key,state)
                continue
            if local_changed and not server_changed:
                answer=request('/bridge/notes/'+identity,payload(note,entry['revision']))
                if answer['applied']:
                    state['notes'][identity]=dict(revision=answer['note']['revision'],path=path,hash=note['hash'] if note else '',assets=answer['note'].get('note_assets',[]))
                    book.store.set_setting(key,state);changed+=1;continue
                row=answer['note']
            else:row=request('/bridge/notes/'+identity)
            if state.get('attachments') and not row['deleted']:
                from wissen_sync_assets import receive
                receive(book,row.get('note_assets',[]),config,{'note':identity})
            # A lost response may have committed our exact content already.
            same=bool(note) and (not row.get('note_path') or row['note_path']==path) and not row['deleted'] and note['title']==row['title'] and note['text'] in (row['body'],remote_text(row))
            if same:
                state['notes'][identity]=dict(revision=row['revision'],path=path,hash=note['hash'],assets=row.get('note_assets',[]))
                book.store.set_setting(key,state);continue
            if local_changed and note:
                conflicts.append(conflict_copy(book,identity,note))
            if row['deleted']:
                if note:book.remove(path,note['hash'])
                current_hash=''
            else:
                desired=str(book.relative(row['note_path'])) if row.get('note_path') else path
                if desired and desired!=path:
                    try:
                        occupant=book.read(desired)
                        if occupant['note_id']!=identity:desired=str(Path(desired).parent/(identity+'.md'))
                    except FileNotFoundError:pass
                    state['pending_move']=dict(id=identity,source=path if note else '',target=desired,
                        hash=note['hash'] if note else '',text=remote_text(row),revision=row['revision'],assets=row.get('note_assets',[]))
                    book.store.set_setting(key,state);finish_move(book,key,state);changed+=1;continue
                if not path:
                    folder(book);path='Server/'+identity+'.md'
                # A remote edit wins over a concurrent local deletion by retaining
                # the remote content as a visible note, with an explicit notice.
                if local_changed and not note and entry['revision']:conflicts.append(path)
                result=book.write(path,remote_text(row),note['hash'] if note else '',note_id=identity)
                current_hash=result['hash']
            state['notes'][identity]=dict(revision=row['revision'],path=path,hash=current_hash,assets=row.get('note_assets',[]))
            book.store.set_setting(key,state);changed+=1
        if 'note_collections_v1' in user.get('sync_features', []):
            from wissen_sync_folders import synchronize
            conflicts.extend(synchronize(book,request,key,state))
        state['last_sync']=time.time();book.store.set_setting(key,state)
        return dict(enabled=True,changed=changed,conflicts=conflicts,last_sync=state['last_sync'])


def background(store):
    from wissen_data import Notebook
    choice=store.setting('knowledge/background-sync',{})
    if not choice.get('enabled'):return dict(enabled=False)
    book=Notebook(store,choice['root'],identity=choice['identity'])
    config=lumen_connect.read_config()
    if scope(book,config)!=choice['scope']:
        raise ValueError(tr('Die Serververbindung hat sich geändert. Bitte erneut öffnen.'))
    # Opening the root verifies its inode before interpreting missing files as deletions.
    with book.directory():pass
    return sync(book)


if __name__=='__main__':
    import signal
    import sys
    from lumen_store import Store
    # Bound a pass, including waiting for an interactive sync's lock.
    signal.alarm(60)
    store=Store()
    try:
        result=background(store)
        store.set_setting('knowledge/background-status',dict(time=time.time(),ok=True,
            changed=result.get('changed',0),conflicts=len(result.get('conflicts',[]))))
        if result.get('enabled'):
            from lumen_notifications import report
            bad=bool(result.get('conflicts'))
            report('Lumen Wissen','background-sync',bad,tr('Notizabgleich braucht deine Aufmerksamkeit') if bad else tr('Notizabgleich wieder in Ordnung'),
                   tr('Öffne Lumen Notes und prüfe den Abgleich.') if bad else '',target='app:wissen')
    except Exception:
        store.set_setting('knowledge/background-status',dict(time=time.time(),ok=False))
        from lumen_notifications import report
        report('Lumen Wissen','background-sync',True,tr('Notizabgleich braucht deine Aufmerksamkeit'),
               tr('Öffne Lumen Notes und prüfe den Abgleich.'),target='app:wissen')
        print('Notizabgleich nicht abgeschlossen. Status in Lumen Notes prüfen.',file=sys.stderr)
        sys.exit(1)
