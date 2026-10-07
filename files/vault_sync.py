"""Ciphertext-only native Vault transport. Never receives a password or active plaintext."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import urllib.request
from uuid import UUID, uuid4
import lumen_connect
from lumen_i18n import tr
from backup_setup import encrypted_copy

MAX_FILE=64*1024**2


class CopyJob:
    def check(self):pass


def snapshot(root):
    if not (root/'vault.kdbx').exists():return b''
    with tempfile.TemporaryDirectory(prefix='lumen-vault-ciphertext-') as tmp:
        destination=Path(tmp)/'snapshot'
        encrypted_copy(str(root)+'/.' ,destination,CopyJob())
        return (destination/'vault.kdbx').read_bytes()


def digest(data):return hashlib.sha256(data).hexdigest()


def transport(config,path,method='GET',data=None):
    request=urllib.request.Request(config['server']+'/bridge/vault'+path,method=method,data=data,headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/octet-stream'})
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=lumen_connect.tls_context(config)),lumen_connect.NoRedirect())
    with opener.open(request,timeout=30) as response:
        limit=MAX_FILE if path.endswith('/content') else 1024**2
        result=response.read(limit+1)
        if len(result)>limit:raise ValueError(tr('Serverantwort überschreitet die zulässige Größe.'))
        return result


def stage(pinned, fd, identity, data):
    # Persist only ciphertext; fixed UUID filename, exclusive private creation.
    name='sync-incoming-'+identity+'.kdbx'
    try:
        with tempfile.NamedTemporaryFile(dir=pinned,prefix='sync-transfer-') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.link(stream.name,name,dst_dir_fd=fd,follow_symlinks=False)
        os.fsync(fd)
    except FileExistsError:
        source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(source,'rb') as stream:
            item=os.fstat(stream.fileno())
            if not stat.S_ISREG(item.st_mode) or item.st_uid!=os.getuid() or item.st_nlink!=1 or item.st_mode&0o077 or stream.read(MAX_FILE+1)!=data:raise ValueError(tr('Empfangene Fassung lokal verändert; keine Datei wurde ersetzt.'))
    return name


def private_read(root, name, limit=65536):
    try: fd=os.open(root/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError:return None
    with os.fdopen(fd,'rb') as stream:
        item=os.fstat(stream.fileno())
        if not stat.S_ISREG(item.st_mode) or item.st_uid!=os.getuid() or item.st_nlink!=1 or item.st_mode&0o077:
            raise ValueError(tr('Unsichere lokale Abgleichdatei.'))
        data=stream.read(limit+1)
        if len(data)>limit:raise ValueError(tr('Ungültiger Abgleichstatus.'))
        return data


def save_auto(root, state):
    name=None
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='sync-state-',delete=False) as stream:
            name=stream.name
            stream.write(json.dumps(state).encode());stream.flush();os.fsync(stream.fileno())
        # Replace the directory entry, never follow a destination symlink.
        os.replace(name,root/'sync-auto.json')
        name=None
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if name:os.unlink(name)


def valid_state(state):
    if not isinstance(state,dict):return False
    if state.get('enabled',False) not in (True,False):return False
    if state.get('reason','disabled') not in ('disabled','ready','published','checking','incoming','conflict','uncertain','remote_changed','missing_local','connection_changed'):return False
    if not state.get('enabled'):return True
    def hash_ok(value):return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
    try:
        UUID(state['head'])
        if not all(hash_ok(state[k]) for k in ('hash','scope')):return False
        if 'pending' in state:
            pending=state['pending'];UUID(pending['id']);UUID(pending['expected'])
            if not hash_ok(pending['hash']):return False
        if 'incoming' in state:
            incoming=state['incoming'];UUID(incoming['id'])
            if not hash_ok(incoming['sha256']):return False
    except (ValueError,KeyError,TypeError,AttributeError):return False
    return True


def auto_status(state):
    return dict(enabled=state.get('enabled') is True,reason=state.get('reason','disabled'))


def automatic(root, fd, state, info, data, config, enable=False):
    head=next((v for v in info['versions'] if v['current']),None)
    def pause(reason):
        state.update(enabled=False,reason=reason);save_auto(root,state)
        return auto_status(state)
    if enable:
        if not head or head['sha256']!=info['local_hash']:
            raise ValueError(tr('Zuerst lokale Fassung veröffentlichen oder Serverfassung übernehmen, bis beide Stände übereinstimmen.'))
        state=dict(enabled=True,reason='ready',scope=info['scope'],head=head['id'],hash=head['sha256'])
        save_auto(root,state);return auto_status(state)
    pending=state.get('pending')
    if pending:
        row=next((v for v in info['versions'] if v['id']==pending['id']),None)
        if not row:return pause('uncertain')
        if row['sha256']!=pending['hash'] or row.get('parent')!=pending['expected']:
            return pause('uncertain')
        state.pop('pending')
        if row['current']:
            state.update(head=row['id'],hash=row['sha256'],reason='published')
            save_auto(root,state);return auto_status(state)
        # A retained branch blocks publishing, but incoming versions still arrive.
        state.update(reason='conflict');save_auto(root,state)
    if not head:return pause('remote_changed')
    if head['id']!=state.get('head') or head['sha256']!=state.get('hash'):
        previous=state.get('incoming',{})
        if previous.get('id')!=head['id'] or previous.get('sha256')!=head['sha256']:
            received=transport(config,'/'+str(UUID(head['id']))+'/content')
            if digest(received)!=head['sha256']:raise ValueError(tr('Die heruntergeladene Datei stimmt nicht mit der gewählten Fassung überein.'))
            stage(root,fd,str(UUID(head['id'])),received)
        state.update(incoming=dict(id=head['id'],sha256=head['sha256']),reason='incoming' if info['local_hash']==state.get('hash') else 'conflict')
        save_auto(root,state)
        return auto_status(state)
    if not data:return pause('missing_local')
    if info['local_hash']==state['hash']:return auto_status(state)
    pending=dict(id=str(uuid4()),hash=info['local_hash'],expected=state['head'])
    state.update(pending=pending,reason='checking');save_auto(root,state)
    # Persist the receipt BEFORE sending. An uncertain upload is never sent again.
    # The next poll resolves this UUID, or pauses if its outcome is still unknown.
    transport(config,'/'+pending['id']+'?expected='+pending['expected'],'POST',data)
    return auto_status(state)


def execute(request):
    root=Path(request['root']);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    lock=None
    try:
        meta=os.fstat(fd)
        if meta.st_uid!=os.getuid() or meta.st_mode&0o077:raise ValueError(tr('Ein privates Tresorverzeichnis wird benötigt.'))
        pinned=Path('/proc/self/fd')/str(fd)
        op=request['op']
        lock=os.open(pinned/'sync-auto.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        item=os.fstat(lock)
        if not stat.S_ISREG(item.st_mode) or item.st_uid!=os.getuid() or item.st_nlink!=1 or item.st_mode&0o077:
            raise ValueError(tr('Unsichere lokale Abgleichdatei.'))
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=json.loads(private_read(pinned,'sync-auto.json') or b'{}')
        if not valid_state(state):raise ValueError(tr('Ungültiger Abgleichstatus.'))
        if op=='auto-status':return auto_status(state)
        if op=='auto-disable':
            state.update(enabled=False,reason='disabled');save_auto(pinned,state);return auto_status(state)
        if op=='auto-poll' and state.get('enabled') is not True:return auto_status(state)
        try:config=lumen_connect.read_config()
        except FileNotFoundError:raise ValueError(tr('Diesen Desktop zuerst mit Lumen Server verbinden.')) from None
        scope=digest((config['server']+'\0'+config['token']+'\0'+str(root.absolute())+'\0'+str((meta.st_dev,meta.st_ino))).encode())
        if op=='auto-poll' and state.get('scope')!=scope:
            state.update(enabled=False,reason='connection_changed');save_auto(pinned,state);return auto_status(state)
        if op not in ('info','auto-poll') and request.get('scope')!=scope:raise ValueError(tr('Verbindung oder Tresor geändert. Serverabgleich erneut öffnen.'))
        user=lumen_connect.request(config,'/bridge/me')
        if 'vault_sync' not in user['capabilities']:raise ValueError(tr('Auf Lumen Server zuerst die Gerätefähigkeit „Verschlüsselten Tresor abgleichen“ freigeben.'))
        if op in ('info','auto-enable','auto-poll'):
            data=snapshot(pinned)
            versions=json.loads(transport(config,''))
            if not isinstance(versions,list) or len(versions)>200:raise ValueError(tr('Ungültige Tresorübersicht.'))
            for item in versions:
                UUID(item['id'])
                if len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']) or not 12<=item['size']<=MAX_FILE:raise ValueError(tr('Ungültige Tresorübersicht.'))
            if sum(v['current'] is True for v in versions)>1:raise ValueError(tr('Ungültige Tresorübersicht.'))
            info=dict(scope=scope,server=config['server'],user=user['name'],local_hash=digest(data) if data else '',versions=versions)
            if op!='info':return automatic(pinned,fd,state,info,data,config,op=='auto-enable')
            info['automatic']=auto_status(state) if state.get('scope')==scope else dict(enabled=False,reason='disabled')
            return info
        identity=str(UUID(request['id']))
        if op=='upload':
            data=snapshot(pinned)
            if not data or digest(data)!=request['local_hash']:raise ValueError(tr('Lokaler Tresor geändert. Vor dem Veröffentlichen aktualisieren.'))
            expected=str(UUID(request['expected'])) if request.get('expected') else ''
            return json.loads(transport(config,'/'+identity+('?expected='+expected if expected else ''),'POST',data))
        if op=='download':
            data=transport(config,'/'+identity+'/content')
            if digest(data)!=request['sha256']:raise ValueError(tr('Die heruntergeladene Datei stimmt nicht mit der gewählten Fassung überein.'))
            name=stage(pinned,fd,identity,data)
            return dict(path=str(root/name),sha256=digest(data))
        if op=='remove':return json.loads(transport(config,'/'+identity,'DELETE'))
        raise ValueError(tr('Unbekannter Tresorabgleich-Vorgang.'))
    finally:
        if lock is not None:os.close(lock)
        os.close(fd)


if __name__=='__main__':
    try:print(json.dumps(execute(json.load(sys.stdin))))
    except Exception as error:
        # HTTP errors print status only; never server response bodies, tokens or data.
        print(str(error),file=sys.stderr);sys.exit(1)
