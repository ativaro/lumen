"""Reviewed local-file children shared by server-app captures; never uploads itself."""
import hashlib
import json
from uuid import UUID,uuid5

from interop_data import Registry
from lumen_i18n import tr


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def begin(token,binding,*,target,actions,prefix,root=None):
    from interop_sources import from_paths
    from server_notes_files import _insert
    import server_file_import as imports
    registry=Registry(root);request=registry.request(token);payload=request['payload'];paths=payload.get('paths',[])
    if (request['target']!=target or request['action'] not in actions or not 1<=len(paths)<=20
            or len(set(paths))!=len(paths) or payload.get('references')
            or registry.resolve(payload.get('source_url',''))!=payload.get('source')):
        raise ValueError(tr('Höchstens 20 lokale Dateien ausdrücklich in Lumen Drive übernehmen.'))
    key=prefix+'_files'
    if request['choice']:
        plan=request['choice'].get(key)
        if not plan or plan['binding']!=binding or plan['payload_hash']!=digest(payload):
            raise ValueError(tr('Die bestätigte Dateiauswahl wurde geändert.'))
        return plan
    children=[];payloads=[]
    for index,path in enumerate(paths):
        child=from_paths([path])
        if child['items'][0]['directory']:raise ValueError(tr('Ordner zuerst in Lumen Files öffnen.'))
        child['source_url']=registry.register(child['source']);child_id=uuid5(UUID(token),prefix+'-file:'+str(index)).hex
        children.append(dict(token=child_id,payload_hash=digest(child)));payloads.append((child_id,child))
    plan=dict(binding=binding,payload_hash=digest(payload),children=children)
    with registry.library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload,choice,state FROM handoffs WHERE id=?',(token,)).fetchone()
        if current['state']!='pending' or json.loads(current['choice'])!=request['choice'] or json.loads(current['payload'])!=payload:
            raise ValueError(tr('Die Dateiauswahl wurde gleichzeitig geändert.'))
        for child_id,child in payloads:_insert(db,child_id,'files',imports.ACTION,child)
        db.execute('UPDATE handoffs SET choice=? WHERE id=?',(json.dumps({key:plan}),token))
    return plan


def confirmed(request,binding,job,*,prefix,root=None):
    """Revalidate existing import receipts and original versions without a new upload."""
    import server_file_import as imports
    payload=request['payload'];plan=request['choice'].get(prefix+'_files');paths=payload.get('paths',[])
    if (not plan or plan.get('payload_hash')!=digest(payload) or plan.get('binding')!=binding
            or len(plan.get('children',[]))!=len(paths)):
        raise ValueError(tr('Lokale Dateien zuerst ausdrücklich in Lumen Drive übernehmen.'))
    refs=[];registry=Registry(root)
    for index,child in enumerate(plan['children']):
        job.check();expected=uuid5(UUID(request['id']),prefix+'-file:'+str(index)).hex;value=registry.request(expected)
        if (child!=dict(token=expected,payload_hash=digest(value['payload'])) or value['state']!='done'
                or value['payload'].get('paths')!=[paths[index]] or value['action']!=imports.ACTION):
            raise ValueError(tr('Die bestätigte Dateikopie fehlt oder wurde verändert.'))
        refs.append(imports.apply(expected,job,root=root)['reference'])
    return refs


def receive_files(window,plan,current,*,root=None):
    """Wait for the existing Host lease/signal; cancellation never accepts a file."""
    import time
    from PySide6.QtCore import QEventLoop,QTimer
    registry=Registry(root)
    for child in plan['children']:
        current()
        if registry.request(child['token'])['state']=='done':continue
        result=[];failure=[];loop=QEventLoop();timer=QTimer();timer.setInterval(100);deadline=time.monotonic()+300
        def ready(reference,resolved):result.append(reference);loop.quit()
        def check():
            try:
                current()
                if time.monotonic()>deadline:raise ValueError(tr('Die Dateiübernahme wurde nicht abgeschlossen.'))
                if window._import_lease is None and not window._import_running and not window._import_accepting:loop.quit()
            except Exception as error:failure.append(error);loop.quit()
        window.import_reference_ready.connect(ready);timer.timeout.connect(check)
        try:
            current();window._lumen_file_import(child['token']);timer.start();loop.exec()
        finally:timer.stop();window.import_reference_ready.disconnect(ready)
        if failure:raise failure[0]
        if not result:return False
        current()
    return True
