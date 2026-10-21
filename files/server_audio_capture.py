"""Explicit native selections become durable records in the current Server Audio app."""
import json
from pathlib import Path
from uuid import UUID,uuid5

import lumen_connect
from interop_data import Registry
from lumen_i18n import tr
from server_app_session import AppSession
from server_app_links import validate_ref
from server_file_capture import digest

ACTIONS=('radio.add','meetings.agenda','meetings.import')
CHOICE={'id','title','mode','due','token'}
MAX_REPLY=1024**2


def _profile(session,revision,job):
    job.check()
    if (not isinstance(session,AppSession) or session.binding.app!='audio' or not session.usable
            or session.access!='read_write'):
        raise ValueError(tr('Eine aktuelle beschreibbare Lumen-Audio-Studio-Sitzung ist erforderlich.'))
    config=lumen_connect.read_config();private={key:config[key] for key in ('server','device_id','token','ca_file') if key in config}
    if private!=session._config:raise ValueError(tr('Die Serververbindung wurde geändert.'))
    me=lumen_connect.request(config,'/bridge/me',timeout=10);job.check();actual=me.get('permissions_revision')
    if (me.get('id')!=session.binding.account or me.get('device_id')!=session.binding.device
            or type(actual) is not int or actual<0 or revision is not None and revision!=actual
            or not {'media','tasks'}<=set(me.get('capabilities',[])) or lumen_connect.read_config()!=config):
        raise ValueError(tr('Konto, Gerät oder Audiofreigaben wurden geändert.'))
    return dict(server=session.binding.origin,account=session.binding.account,device=session.binding.device,
                permissions_revision=actual,config_stamp=digest(private))


def choices(session,revision,job):
    _profile(session,revision,job)
    return []


def _save(registry,request,value):
    raw=json.dumps(value,allow_nan=False)
    if len(raw)>8192:raise ValueError(tr('Die bestätigte Audioauswahl ist zu groß.'))
    with registry.library.connect() as db:
        changed=db.execute('UPDATE handoffs SET choice=? WHERE id=? AND state=? AND choice=?',
            (raw,request['id'],request['state'],json.dumps(request['choice'],allow_nan=False))).rowcount
    if changed!=1:raise ValueError(tr('Die bestätigte Audioauswahl wurde gleichzeitig geändert.'))
    return registry.request(request['id'])


def _files(request,session,revision,job,root):
    refs=request['payload'].get('references',[])
    if request['payload'].get('paths'):
        from server_file_capture import confirmed
        refs=confirmed(request,_profile(session,revision,job),job,prefix='audio',root=root)
    if not refs:return []
    if len(refs)>20:raise ValueError(tr('Höchstens 20 Drive-Dateien auswählen.'))
    import drive_references as drive
    for ref in refs:
        drive.validate(ref)
        if ref['kind']!='drive_file' or ref['locator']!=dict(server=session.binding.origin,account=session.binding.account):
            raise ValueError(tr('Nur Drive-Dateien desselben Serverkontos übernehmen.'))
    _,rows=drive.resolve(refs,job)
    return rows


def _record(value,identity,mode):
    if (not isinstance(value,dict) or value.get('id')!=identity or value.get('mode')!=mode
            or type(value.get('revision')) is not int or value['revision']<1 or value.get('archived') is not False
            or not isinstance(value.get('title'),str) or not 1<=len(value['title'])<=200):
        raise ValueError(tr('Der Audioeintrag wurde nicht eindeutig bestätigt.'))
    return value


def _body(request,choice,session,revision,job,root):
    payload=request['payload'];rows=_files(request,session,revision,job,root)
    attachments=[dict(id=row['id'],kind='file',revision=row['version'],mode='reference') for row in rows]
    source=payload.get('source',{})
    if source.get('version')==2 and source.get('app')=='note':
        source=validate_ref(source)
        if source['locator']!=dict(server=session.binding.origin,account=session.binding.account):
            raise ValueError(tr('Die ausgewählte Notiz gehört zu einem anderen Serverkonto.'))
        value=session.request('/api/media/sources/'+source['id']+'?kind=note',max_bytes=MAX_REPLY);job.check()
        if (not isinstance(value,dict) or value.get('id')!=source['id'] or value.get('kind')!='note'
                or type(value.get('revision')) is not int or value['revision']<1 or value.get('mode')!='reference'
                or value.get('supported') is not True or value.get('readable') is not True):
            raise ValueError(tr('Die ausgewählte Notiz ist nicht aktuell für Lumen Audio Studio freigegeben.'))
        attachments.append(dict(id=source['id'],kind='note',revision=value['revision'],mode='reference'))
    if len(attachments)>20 or len({(ref['kind'],ref['id']) for ref in attachments})!=len(attachments):
        raise ValueError(tr('Höchstens 20 unterschiedliche Quellen auswählen.'))
    text=payload.get('text','')
    if not text:
        text='\n\n'.join(item['text'] for item in payload.get('items',[]) if item.get('kind')=='source' and isinstance(item.get('text'),str))
    if not text.strip() and not attachments:raise ValueError(tr('Zuerst Text oder eine Datei für Lumen Audio Studio auswählen.'))
    text+=('\n\n' if text else '')+tr('Quelle: ')+payload['source_url']
    if payload.get('url'):text+='\n'+payload['url']
    if len(text)>18000:raise ValueError(tr('Höchstens 18.000 Zeichen einschließlich Herkunft übernehmen.'))
    mode='radio' if request['action']=='radio.add' else 'meeting'
    body=dict(id=str(uuid5(UUID(request['id']),'audio:'+session.binding.account)),mode=mode,title=choice['title'],text=text,attachments=attachments)
    if request['action']=='meetings.import':
        from interop_targets import AUDIO_SUFFIXES
        if len(rows)!=1 or Path(rows[0]['name']).suffix.lower() not in AUDIO_SUFFIXES:
            raise ValueError(tr('Genau eine bestätigte Audiodatei als Aufnahme auswählen.'))
        body['recording']=rows[0]['id']
        body['attachments']=[]
    _profile(session,revision,job)
    return body


def capture(token,choice,session,revision,job,*,root=None,retry=False):
    registry=Registry(root);request=registry.request(token);payload=request['payload']
    if (request['action'] not in ACTIONS or request['target']!=request['action'].split('.')[0]
            or not isinstance(choice,dict) or set(choice)!=CHOICE or choice['token']!=token
            or choice['id'] or choice['due'] or choice['mode']!='copy'
            or not isinstance(choice['title'],str) or not 1<=len(choice['title'])<=200 or choice['title']!=choice['title'].strip()
            or registry.resolve(payload.get('source_url',''))!=payload.get('source') or type(retry) is not bool):
        raise ValueError(tr('Ungültige bestätigte Audioübernahme.'))
    if request['state'] not in ('pending','done'):raise ValueError(tr('Diese Audioübernahme wird bereits bearbeitet.'))
    binding=_profile(session,revision,job);previous=request['choice'].get('audio_capture')
    fixed={key:value for key,value in request['choice'].items() if key not in ('audio_capture','audio_files')}
    if fixed and fixed!=choice:raise ValueError(tr('Diese Anfrage ist bereits an eine andere Auswahl gebunden.'))
    if previous and previous['binding']!=binding:raise ValueError(tr('Die bestätigte Server- oder Gerätebindung wurde geändert.'))
    body=_body(request,choice,session,revision,job,root)
    plan=dict(binding=binding,payload_hash=digest(payload),body_hash=digest(body),record=body['id'],attempted=False)
    if previous:
        if {k:v for k,v in previous.items() if k not in ('attempted','receipt')}!={k:v for k,v in plan.items() if k!='attempted'}:
            raise ValueError(tr('Die bestätigte Auswahl oder Drive-Fassung wurde geändert.'))
        if previous.get('attempted') and not previous.get('receipt') and not retry:
            raise ValueError(tr('Das Ergebnis ist unklar. Dieselbe Audioübernahme ausdrücklich erneut prüfen.'))
        plan=previous
    def save(value):
        nonlocal request
        request=_save(registry,request,dict(choice,**({'audio_files':request['choice']['audio_files']} if 'audio_files' in request['choice'] else {}),audio_capture=value))
    if request['state']=='done':
        ref=validate_ref(registry.resolve(request['result']))
        if (not previous or ref['app']!='media' or ref['id']!=body['id']
                or ref['locator']!={k:binding[k] for k in ('server','account')}):raise ValueError(tr('Ungültiger Audioergebnisbeleg.'))
        value=_record(session.request('/api/media/records/'+body['id'],max_bytes=MAX_REPLY),body['id'],body['mode'])
        _profile(session,revision,job);return dict(ref,title=value['title'])
    save(plan);request=registry.claim(token,request['target'])
    try:
        if not plan.get('receipt'):
            plan=dict(plan,attempted=True);save(plan);_profile(session,revision,job)
            value=_record(session.request('/api/media/records',body,max_bytes=MAX_REPLY),body['id'],body['mode'])
            plan=dict(plan,receipt=dict(id=value['id']));save(plan)
        value=_record(session.request('/api/media/records/'+body['id'],max_bytes=MAX_REPLY),body['id'],body['mode'])
        _profile(session,revision,job)
        ref=validate_ref(dict(version=2,app='media',id=value['id'],title=value['title'],locator={k:binding[k] for k in ('server','account')}))
        registry.finish(token,registry.register(ref));return ref
    except Exception:
        registry.release(token,tr('Die Audioübernahme ist nicht bestätigt. Ergebnis zuerst prüfen.'));raise


def begin_files(token,session,revision,job,*,root=None):
    from server_file_capture import begin
    registry=Registry(root);request=registry.request(token)
    if request['action'] not in ACTIONS:raise ValueError(tr('Diese Auswahl gehört nicht zu Lumen Audio Studio.'))
    return begin(token,_profile(session,revision,job),target=request['action'].split('.')[0],actions=ACTIONS,prefix='audio',root=root)


def receive(window,token):
    from PySide6.QtWidgets import QMessageBox
    from interop_dialogs import run_job
    from interop_ui import review
    from interop_targets import ACTIONS as specs
    from server_file_capture import receive_files
    w=window;session=w.session;generation=w._generation;registry=Registry();request=registry.request(token)
    if request['action'] not in ACTIONS or request['target']!=request['action'].split('.')[0]:raise ValueError(tr('Diese Übergabe gehört nicht zu Lumen Audio Studio.'))
    if w._import_running:raise ValueError(tr('Bitte die laufende Übernahme zuerst abschließen.'))
    def current():
        if (w._disposed or w._closing or w._generation!=generation or w.session is not session
                or not session.usable or not w._pilot_current()):raise ValueError(tr('Die App-Sitzung wurde geändert.'))
    def work(title,fn):
        class Guard:
            def __init__(self,job):self.job=job
            def check(self):self.job.check();current()
        return run_job(w,title,lambda job:fn(Guard(job)))
    binding=work(tr('Lumen Audio Studio · Freigaben prüfen …'),lambda job:_profile(session,None,job))
    if binding is None:return None
    revision=binding['permissions_revision']
    if request['payload'].get('paths'):
        plan=work(tr('Lumen Audio Studio · Dateiauswahl prüfen …'),lambda job:begin_files(token,session,revision,job))
        if plan is None or not receive_files(w,plan,current):return None
        request=registry.request(token)
    w._import_running=True
    try:
        stored=request['choice'];plan=stored.get('audio_capture');retry=False
        if plan:
            choice={key:stored[key] for key in CHOICE}
            if plan.get('attempted') and not plan.get('receipt'):
                if QMessageBox.question(w,'Lumen Audio Studio',tr('Das vorherige Ergebnis ist unklar. Dieselbe Übernahme erneut prüfen?'),QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return None
                retry=True
        else:
            spec=dict(specs[request['action']],heading='Lumen Audio Studio',modes=['copy'],save_label='In Audio Studio speichern',
                reference_hint='Verknüpfungen zum Drive-Original · keine Dateien werden heruntergeladen.',
                destination_label='Eintrag',
                description=tr('Einen neuen Audio-Studio-Eintrag auf dem verbundenen Server speichern. Dateien werden als bestätigte Drive-Originale verknüpft. Vertonung und Transkription starten erst in Audio Studio.'))
            current();choice=review(w,request,spec=spec,rows=[])
            if choice is None:return None
        current();return work(tr('Lumen Audio Studio · Auswahl übernehmen …'),lambda job:capture(token,choice,session,revision,job,retry=retry))
    finally:
        w._import_running=False
        if w._import_close:w._import_close=False;w.close()
