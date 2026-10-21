"""Reviewed native transfers into the current Server Projects session."""
import hashlib
import json
from uuid import UUID,uuid5
from urllib.error import HTTPError
import lumen_connect
from interop_data import Registry
from lumen_i18n import tr
from server_app_session import AppSession
from server_app_links import validate_ref

ACTIONS=('workbench.add','workbench.question')
CHOICE={'id','title','mode','due','token'}
MAX_REPLY=1024**2


def _digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _profile(session,revision,job):
    job.check()
    if not isinstance(session,AppSession) or session.binding.app!='projects' or not session.usable or session.access!='read_write':
        raise ValueError(tr('Eine aktuelle beschreibbare Lumen-Projekte-Sitzung ist erforderlich.'))
    config=lumen_connect.read_config();private={key:config[key] for key in ('server','device_id','token','ca_file') if key in config}
    if private!=session._config:raise ValueError(tr('Die Serververbindung wurde geändert.'))
    me=lumen_connect.request(config,'/bridge/me',timeout=10);job.check()
    actual=me.get('permissions_revision')
    if (me.get('id')!=session.binding.account or me.get('device_id')!=session.binding.device
            or type(actual) is not int or actual<0 or revision is not None and actual!=revision
            or 'projects' not in me.get('capabilities',[]) or lumen_connect.read_config()!=config):
        raise ValueError(tr('Konto, Gerät oder Projektfreigaben wurden geändert.'))
    return dict(server=session.binding.origin,account=session.binding.account,device=session.binding.device,
                permissions_revision=actual,config_stamp=_digest(private))


def _project(row):
    if (not isinstance(row,dict) or not isinstance(row.get('title'),str) or not isinstance(row.get('notes'),str)
            or row.get('archived') is not False or row.get('role') not in ('manager','editor')
            or type(row.get('revision')) is not int or row['revision']<1 or str(UUID(row['id']))!=row['id']):
        raise ValueError(tr('Das Projekt ist nicht mehr beschreibbar.'))
    return row


def projects(session,revision,job):
    _profile(session,revision,job);rows=[];offset=0
    while True:
        page=session.request('/api/project-collections?offset='+str(offset),max_bytes=MAX_REPLY);job.check()
        if not isinstance(page,dict) or not isinstance(page.get('items'),list):raise ValueError(tr('Ungültige Projektliste.'))
        for row in page['items']:
            if row.get('archived') is False and row.get('role') in ('manager','editor'):
                row=_project(row);rows.append(dict(id=row['id'],title=row['title']))
        following=page.get('next_offset')
        if following is None:break
        if type(following) is not int or not offset<following<=5000:raise ValueError(tr('Ungültige Projektliste.'))
        offset=following
    _profile(session,revision,job)
    return rows


def _save(registry,request,value):
    raw=json.dumps(value,allow_nan=False)
    if len(raw)>8192:raise ValueError(tr('Die bestätigte Projektauswahl ist zu groß.'))
    with registry.library.connect() as db:
        changed=db.execute('UPDATE handoffs SET choice=? WHERE id=? AND state=? AND choice=?',
            (raw,request['id'],request['state'],json.dumps(request['choice'],allow_nan=False))).rowcount
    if changed!=1:raise ValueError(tr('Die bestätigte Projektauswahl wurde gleichzeitig geändert.'))
    return registry.request(request['id'])


def _files(request,session,revision,job,root):
    payload=request['payload'];refs=payload.get('references',[])
    if payload.get('paths'):
        plan=request['choice'].get('project_files')
        if (not plan or plan.get('payload_hash')!=_digest(payload) or plan.get('binding')!=_profile(session,revision,job)
                or len(plan.get('children',[]))!=len(payload['paths'])):
            raise ValueError(tr('Lokale Dateien zuerst ausdrücklich in Lumen Drive übernehmen.'))
        import server_file_import as imports
        refs=[]
        for index,child in enumerate(plan['children']):
            expected=uuid5(UUID(request['id']),'project-file:'+str(index)).hex
            value=Registry(root).request(expected)
            if (child!=dict(token=expected,payload_hash=_digest(value['payload'])) or value['state']!='done'
                    or value['payload'].get('paths')!=[payload['paths'][index]] or value['action']!=imports.ACTION):
                raise ValueError(tr('Die bestätigte Dateikopie fehlt oder wurde verändert.'))
            refs.append(imports.apply(expected,job,root=root)['reference'])
    if len(refs)>20:raise ValueError(tr('Höchstens 20 bestätigte Drive-Dateien auswählen.'))
    if not refs:return []
    import drive_references as drive
    for ref in refs:
        if ref['locator']!=dict(server=session.binding.origin,account=session.binding.account) or ref['kind']!='drive_file':
            raise ValueError(tr('Nur Drive-Dateien desselben Serverkontos übernehmen.'))
    _,rows=drive.resolve(refs,job)
    return [dict(id=row['id'],kind='file',revision=row['version']) for row in rows]


def capture(token,choice,session,revision,job,*,root=None,retry=False):
    registry=Registry(root);request=registry.request(token);payload=request['payload']
    if (request['target']!='workbench' or request['action'] not in ACTIONS or not isinstance(choice,dict)
            or set(choice)!=CHOICE or choice['token']!=token or choice['due'] or choice['mode'] not in ('copy','link')
            or not isinstance(choice['title'],str) or not 1<=len(choice['title'])<=200
            or registry.resolve(payload.get('source_url',''))!=payload.get('source') or type(retry) is not bool):
        raise ValueError(tr('Ungültige bestätigte Projektübernahme.'))
    if request['state'] not in ('pending','done'):raise ValueError(tr('Diese Projektübernahme wird bereits bearbeitet.'))
    binding=_profile(session,revision,job);previous=request['choice'].get('project_capture')
    fixed={key:value for key,value in request['choice'].items() if key not in ('project_capture','project_files')}
    if fixed and fixed!=choice:raise ValueError(tr('Diese Anfrage ist bereits an eine andere Auswahl gebunden.'))
    if previous and previous['binding']!=binding:raise ValueError(tr('Die bestätigte Server- oder Gerätebindung wurde geändert.'))
    identity=previous['project'] if previous else str(UUID(choice['id'] or token))
    if request['state']=='done':
        ref=validate_ref(registry.resolve(request['result']))
        if ref['app']!='projects' or ref['id']!=identity or ref['locator']!={k:binding[k] for k in ('server','account')}:raise ValueError(tr('Ungültiger Projektbeleg.'))
        session.request('/api/project-collections/'+identity,max_bytes=MAX_REPLY);_profile(session,revision,job);return ref
    files=_files(request,session,revision,job,root)
    if choice['mode']=='link' and not files:raise ValueError(tr('Text als eigenständigen Projektinhalt übernehmen.'))
    text=payload.get('text','')
    if request['action']=='workbench.question' and not text.strip():raise ValueError(tr('Bitte einen Fragetext auswählen.'))
    if len(text)>12000:raise ValueError(tr('Höchstens 12.000 Zeichen als Projektinhalt übernehmen.'))
    if previous and previous.get('attempted') and not previous.get('receipt') and not retry:
        raise ValueError(tr('Das Ergebnis ist unklar. Dieselbe Übernahme ausdrücklich erneut prüfen.'))
    if previous and previous['payload_hash']!=_digest(payload):raise ValueError(tr('Die bestätigte Quelle wurde verändert.'))
    plan=previous or dict(binding=binding,project=identity,payload_hash=_digest(payload),attempted=False)
    request=_save(registry,request,dict(choice,**({'project_files':request['choice']['project_files']} if 'project_files' in request['choice'] else {}),project_capture=plan))
    request=registry.claim(token,'workbench')
    try:
        try:row=_project(session.request('/api/project-collections/'+identity,max_bytes=MAX_REPLY)['project'])
        except HTTPError as error:
            if choice['id'] or error.code!=404:raise
            row=_project(session.request('/api/project-collections',dict(id=identity,title=choice['title'],notes=''),max_bytes=MAX_REPLY))
        question=text+'\n\nQuelle der Auswahl: '+payload['source_url']
        if request['action']=='workbench.question' and len(question)>12000:raise ValueError(tr('Die Projektfrage überschreitet 12.000 Zeichen.'))
        body=(dict(request_id=str(UUID(token)),revision=row['revision'],question=question,project_chat=True,sources=[]) if request['action']=='workbench.question'
              else dict(operation_id=str(UUID(token)),revision=row['revision'],title=choice['title'],text=text,source_url=payload['source_url'],files=files))
        # Replays must use the original CAS and original confirmed reference versions.
        if plan.get('body_hash'):
            body['revision']=plan['revision']
            if _digest(body)!=plan['body_hash']:raise ValueError(tr('Die bestätigte Projektauswahl oder Drive-Fassung wurde geändert.'))
        else:plan=dict(plan,revision=row['revision'],body_hash=_digest(body))
        request=_save(registry,request,dict(request['choice'],project_capture=plan))
        if not plan.get('receipt'):
            plan=dict(plan,attempted=True);request=_save(registry,request,dict(request['choice'],project_capture=plan));_profile(session,revision,job)
            path='/api/project-collections/'+identity+('/questions' if request['action']=='workbench.question' else '/capture')
            result=session.request(path,body,max_bytes=MAX_REPLY)
            if request['action']=='workbench.question':
                task=result.get('task',{})
                if task.get('project_context',{}).get('id')!=identity or task.get('prompt')!=body['question'].strip() or str(UUID(task['id']))!=task['id']:raise ValueError(tr('Ungültiger Projektgesprächsbeleg.'))
                receipt=dict(task=task['id'])
            else:
                row=_project(result.get('project'))
                if row['id']!=identity or result.get('operation_id')!=str(UUID(token)):raise ValueError(tr('Ungültiger Projektbeleg.'))
                receipt=dict(project=identity)
            plan=dict(plan,receipt=receipt);request=_save(registry,request,dict(request['choice'],project_capture=plan))
        _profile(session,revision,job)
        ref=validate_ref(dict(version=2,app='projects',id=identity,title=row['title'],locator={k:binding[k] for k in ('server','account')}))
        registry.finish(token,registry.register(ref));return ref
    except Exception as error:
        registry.release(token,tr('Die Projektübernahme ist nicht bestätigt. Ergebnis zuerst prüfen.'));raise


def begin_files(token,session,revision,job,*,root=None):
    """Persist intent only; each child still uses the existing reviewed Drive import."""
    from interop_sources import from_paths
    from server_notes_files import _insert
    import server_file_import as imports
    registry=Registry(root);request=registry.request(token);payload=request['payload'];paths=payload.get('paths',[])
    if (request['target']!='workbench' or request['action']!='workbench.add' or not 1<=len(paths)<=20
            or len(set(paths))!=len(paths) or payload.get('references')
            or registry.resolve(payload.get('source_url',''))!=payload.get('source')):
        raise ValueError(tr('Höchstens 20 lokale Dateien ausdrücklich in Lumen Drive übernehmen.'))
    binding=_profile(session,revision,job)
    if request['choice']:
        plan=request['choice'].get('project_files')
        if not plan or plan['binding']!=binding or plan['payload_hash']!=_digest(payload):raise ValueError(tr('Die bestätigte Dateiauswahl wurde geändert.'))
        return plan
    children=[];payloads=[]
    for index,path in enumerate(paths):
        child=from_paths([path]);job.check()
        if child['items'][0]['directory']:raise ValueError(tr('Ordner zuerst in Lumen Files öffnen.'))
        child['source_url']=registry.register(child['source']);key=uuid5(UUID(token),'project-file:'+str(index)).hex
        children.append(dict(token=key,payload_hash=_digest(child)));payloads.append((key,child))
    plan=dict(binding=binding,payload_hash=_digest(payload),children=children)
    with registry.library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT payload,choice,state FROM handoffs WHERE id=?',(token,)).fetchone()
        if current['state']!='pending' or json.loads(current['choice'])!=request['choice'] or json.loads(current['payload'])!=payload:raise ValueError(tr('Die Dateiauswahl wurde gleichzeitig geändert.'))
        for key,child in payloads:_insert(db,key,'files',imports.ACTION,child)
        db.execute('UPDATE handoffs SET choice=? WHERE id=?',(json.dumps(dict(project_files=plan)),token))
    return plan


def receive(window,token):
    """Native Projects Requests calls this; no renderer bridge or automatic acceptance."""
    from PySide6.QtCore import QEventLoop,QTimer
    from PySide6.QtWidgets import QMessageBox
    from interop_dialogs import run_job
    from interop_ui import review
    from interop_targets import ACTIONS as specs
    import time
    w=window;session=w.session;generation=w._generation
    registry=Registry();request=registry.request(token)
    if request['target']!='workbench' or request['action'] not in ACTIONS:raise ValueError(tr('Diese Übergabe gehört nicht zu Lumen Projekte.'))
    if w._import_running:raise ValueError(tr('Bitte die laufende Übernahme zuerst abschließen.'))
    def current():
        if (w._disposed or w._closing or w._generation!=generation or w.session is not session
                or not session.usable or not w._pilot_current()):raise ValueError(tr('Die App-Sitzung wurde geändert.'))
    def work(title,fn):
        class Guard:
            def __init__(self,job):self.job=job
            def check(self):self.job.check();current()
        return run_job(w,title,lambda job:fn(Guard(job)))
    prepared=work(tr('Lumen Projekte · Ziele laden …'),lambda job:(_profile(session,None,job),projects(session,None,job)))
    if prepared is None:return None
    binding,rows=prepared;revision=binding['permissions_revision']
    if request['payload'].get('paths'):
        plan=work(tr('Lumen Projekte · Dateiauswahl prüfen …'),lambda job:begin_files(token,session,revision,job))
        if plan is None:return None
        for child in plan['children']:
            if registry.request(child['token'])['state']=='done':continue
            result=[];failure=[];loop=QEventLoop();timer=QTimer();timer.setInterval(100);deadline=time.monotonic()+300
            def ready(reference,resolved):result.append(reference);loop.quit()
            def check():
                try:
                    current()
                    if time.monotonic()>deadline:raise ValueError(tr('Die Dateiübernahme wurde nicht abgeschlossen.'))
                    if w._import_lease is None and not w._import_running and not w._import_accepting:loop.quit()
                except Exception as error:failure.append(error);loop.quit()
            window.import_reference_ready.connect(ready);timer.timeout.connect(check)
            try:
                current();w._lumen_file_import(child['token']);timer.start();loop.exec()
            finally:timer.stop();window.import_reference_ready.disconnect(ready)
            if failure:raise failure[0]
            if not result:return None
        request=registry.request(token)
    w._import_running=True
    try:
        stored=request['choice'];plan=stored.get('project_capture');retry=False
        if plan:
            choice={key:stored[key] for key in CHOICE}
            if plan.get('attempted') and not plan.get('receipt'):
                if QMessageBox.question(w,'Lumen Projekte',tr('Das vorherige Ergebnis ist unklar. Dieselbe Übernahme erneut prüfen?'),QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return None
                retry=True
        else:
            spec=dict(specs[request['action']],heading='Lumen Projekte',modes=['link'] if request['payload'].get('references') or request['payload'].get('paths') else ['copy'],
                      description=tr('Die bestätigte Auswahl auf dem verbundenen Server speichern. Originale bleiben unverändert.'),
                      save_label='Frage senden' if request['action']=='workbench.question' else 'Übernehmen')
            current();choice=review(w,request,spec=spec,rows=rows)
            if choice is None:return None
        current()
        return work(tr('Lumen Projekte · Auswahl übernehmen …'),lambda job:capture(token,choice,session,revision,job,retry=retry))
    finally:
        w._import_running=False
        if w._import_close:w._import_close=False;w.close()
