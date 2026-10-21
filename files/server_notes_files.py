"""Durable local-file handoffs through reviewed Drive copies and one Server note."""
import json
from pathlib import Path
import time
from uuid import UUID,uuid5

import drive_references as drive
import lumen_connect
from interop_data import Registry,validate_payload
from interop_sources import from_paths
from lumen_i18n import tr
import server_file_import as imports
import server_note_capture as notes
from server_app_links import identity,validate_ref


def _bound(session,revision,job):
    stamp=notes._profile(session,revision,job)
    config=lumen_connect.read_config();me=lumen_connect.request(config,'/bridge/me',timeout=10);job.check()
    if (me.get('id')!=session.binding.account or me.get('device_id')!=session.binding.device
            or me.get('permissions_revision')!=revision or type(me.get('permissions_revision')) is not int
            or not isinstance(me.get('capabilities'),list) or not {'notes','drive'}<=set(me['capabilities'])
            or lumen_connect.read_config()!=config):
        raise ValueError(tr('Für diese bestätigte Dateikopie die Gerätefreigabe für Lumen Drive erlauben.'))
    job.check()
    return dict(server=session.binding.origin,account=session.binding.account,device=session.binding.device,
                permissions_revision=revision,config_stamp=stamp)


def _parent(registry,token):
    request=registry.request(token);payload=request['payload'];paths=payload.get('paths',[])
    if (request['target']!='wissen' or request['action']!='wissen.import' or request['state'] not in ('pending','done')
            or not 1<=len(paths)<=20 or len(set(paths))!=len(paths) or payload.get('references')
            or registry.resolve(payload.get('source_url',''))!=payload.get('source')):
        raise ValueError(tr('Eine Auswahl mit höchstens 20 lokalen Dateien ist erforderlich. Ordner in Lumen Files öffnen.'))
    return request


def _key(token,label):return uuid5(UUID(token),label).hex


def _children(registry,request,plan):
    if (type(plan.get('version')) is not int or plan['version']!=1
            or plan.get('payload_hash')!=notes._digest(request['payload'])
            or plan.get('note_token')!=_key(request['id'],'note')
            or not isinstance(plan.get('children'),list)
            or len(plan['children'])!=len(request['payload']['paths'])):
        raise ValueError(tr('Die gespeicherte Dateiauswahl wurde verändert.'))
    result=[]
    for index,child in enumerate(plan['children']):
        if set(child)!={'token','payload_hash'} or child['token']!=_key(request['id'],'file:'+str(index)):
            raise ValueError(tr('Ungültiger Dateiübernahmebeleg.'))
        value=registry.request(child['token'])
        if (value['target']!='files' or value['action']!=imports.ACTION
                or notes._digest(value['payload'])!=child['payload_hash']
                or value['payload'].get('paths')!=[request['payload']['paths'][index]]):
            raise ValueError(tr('Die bestätigte Dateiherkunft wurde verändert.'))
        result.append(value)
    return result


def _insert(db,key,target,action,payload):
    row=db.execute('SELECT target,action,payload FROM handoffs WHERE id=?',(key,)).fetchone()
    if row:
        if (row['target'],row['action'],json.loads(row['payload']))!=(target,action,payload):
            raise ValueError(tr('Die bestehende Übergabekennung gehört zu einem anderen Inhalt.'))
        return
    now=time.time()
    db.execute("INSERT INTO handoffs(id,target,action,payload,state,result,error,created,updated) VALUES (?,?,?,?,'pending','','',?,?)",
               (key,target,action,json.dumps(payload),now,now))


def begin(token,session,revision,job,*,root=None):
    """Only local intent is persisted; this does not approve or upload a file."""
    registry=Registry(root);request=_parent(registry,token);binding=_bound(session,revision,job)
    if request['choice']:
        if set(request['choice'])!={'note_files'} or request['choice']['note_files'].get('binding')!=binding:
            raise ValueError(tr('Server, Konto, Gerät oder bestätigte Auswahl wurden geändert.'))
        plan=request['choice']['note_files'];_children(registry,request,plan);return plan
    if request['state']!='pending':raise ValueError(tr('Für diese Übergabe fehlt ein bestätigter Dateibeleg.'))
    children=[];payloads=[]
    for index,path in enumerate(request['payload']['paths']):
        job.check();payload=from_paths([path])
        if payload['items'][0]['directory']:raise ValueError(tr('Ordner zuerst in Lumen Files öffnen und die gewünschten Dateien auswählen.'))
        payload['source_url']=registry.register(payload['source'])
        key=_key(token,'file:'+str(index));children.append(dict(token=key,payload_hash=notes._digest(payload)))
        payloads.append((key,payload))
    plan=dict(version=1,binding=binding,payload_hash=notes._digest(request['payload']),
              children=children,note_token=_key(token,'note'),note_payload_hash=None)
    raw=json.dumps(dict(note_files=plan),allow_nan=False)
    if len(raw)>8192:raise ValueError(tr('Die Dateiauswahl ist zu groß.'))
    _bound(session,revision,job)
    with registry.library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT choice,state,payload FROM handoffs WHERE id=?',(token,)).fetchone()
        if (json.loads(current['choice'])!=request['choice'] or current['state']!='pending'
                or json.loads(current['payload'])!=request['payload']):
            raise ValueError(tr('Die Dateiauswahl wurde gleichzeitig geändert.'))
        for key,payload in payloads:_insert(db,key,'files',imports.ACTION,payload)
        db.execute('UPDATE handoffs SET choice=? WHERE id=?',(raw,token))
    return plan


def note_request(token,session,revision,job,*,root=None):
    """All file receipts precede the derived note; completed copies never reupload."""
    registry=Registry(root);request=_parent(registry,token);plan=begin(token,session,revision,job,root=root)
    children=_children(registry,request,plan)
    with registry.library.connect() as db:existing=db.execute('SELECT id FROM handoffs WHERE id=?',(plan['note_token'],)).fetchone()
    if existing:
        note=registry.request(plan['note_token'])
        if (note['target']!='wissen' or note['action']!='wissen.import'
                or note['payload'].get('source_url')!=request['payload']['source_url']
                or note['payload'].get('source')!=request['payload']['source']
                or notes._digest(note['payload'])!=plan.get('note_payload_hash')):
            raise ValueError(tr('Der gespeicherte Notizbeleg passt nicht zur Dateiübernahme.'))
        return note
    references=[];text_refs=[]
    for child in children:
        job.check()
        if child['state']!='done':raise ValueError(tr('Zuerst jede gewünschte Drivekopie bestätigen oder die Übergabe abbrechen.'))
        # Existing completed-import validation checks hash, size, folder and account.
        result=imports.apply(child['id'],job,root=root);ref=result['reference'];references.append(ref)
        if not request['payload'].get('text','').strip() and Path(child['payload']['paths'][0]).suffix.lower() in ('.txt','.md'):
            receipt=child['choice'].get('drive_import_receipt',{})
            if type(receipt.get('size')) is not int or not 0<=receipt['size']<=512000:
                raise ValueError(tr('Für eine bearbeitbare Textnotiz höchstens 120.000 Zeichen auswählen. Die bestätigte Drivekopie bleibt erhalten.'))
            text_refs.append(ref)
    text=request['payload'].get('text','')
    if text_refs:
        with drive.materialized(text_refs,job) as paths:
            texts=[Path(path).read_text(encoding='utf-8-sig') for path in paths]
            text='\n\n'.join(texts)
    if len(text)>120000:raise ValueError(tr('Für eine bearbeitbare Notiz höchstens 120.000 Zeichen auswählen. Die bestätigten Drivekopien bleiben erhalten.'))
    payload=validate_payload(dict(title=request['payload']['title'],text=text,paths=[],references=references,
        source=request['payload']['source'],source_url=request['payload']['source_url'],
        **({'url':request['payload']['url']} if request['payload'].get('url') else {})))
    _bound(session,revision,job)
    with registry.library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT choice,state,payload FROM handoffs WHERE id=?',(token,)).fetchone()
        if (json.loads(current['choice'])!=dict(note_files=plan) or current['state']!='pending'
                or json.loads(current['payload'])!=request['payload']):raise ValueError(tr('Die Dateiübernahme wurde gleichzeitig geändert.'))
        _insert(db,plan['note_token'],'wissen','wissen.import',payload)
        db.execute('UPDATE handoffs SET choice=? WHERE id=?',
                   (json.dumps(dict(note_files=dict(plan,note_payload_hash=notes._digest(payload)))),token))
    return registry.request(plan['note_token'])


def complete(token,reference,session,revision,job,*,root=None):
    registry=Registry(root);request=_parent(registry,token);plan=begin(token,session,revision,job,root=root)
    child=registry.request(plan['note_token']);ref=validate_ref(reference)
    if (child['state']!='done' or notes._digest(child['payload'])!=plan.get('note_payload_hash')
            or identity(registry.resolve(child['result']))!=identity(ref)
            or ref['locator']!={k:plan['binding'][k] for k in ('server','account')}):
        raise ValueError(tr('Die Notiz wurde nicht eindeutig bestätigt.'))
    result=registry.register(ref);_bound(session,revision,job)
    # Publishing the parent receipt is one local transaction; no half-claimed parent.
    with registry.library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT choice,state,payload,result FROM handoffs WHERE id=?',(token,)).fetchone()
        if (json.loads(current['choice'])!=dict(note_files=plan) or json.loads(current['payload'])!=request['payload']
                or current['state'] not in ('pending','done') or current['state']=='done' and current['result']!=result):
            raise ValueError(tr('Der Dateiübernahmebeleg wurde gleichzeitig geändert.'))
        db.execute("UPDATE handoffs SET state='done',result=?,error='',updated=? WHERE id=?",(result,time.time(),token))
        db.execute('INSERT OR IGNORE INTO links VALUES (?,?,?,?)',(request['payload']['source_url'],result,'handoff',time.time()))
    return ref
