"""One explicitly reviewed capture into Server Notes, using the existing app session."""
import hashlib
import json
from uuid import UUID

import lumen_connect
from interop_data import Registry
from lumen_i18n import tr
from server_app_session import AppSession
from server_app_links import validate_ref

ACTION = 'wissen.import'
MAX_REPLY = 1024**2
CHOICE = {'id','title','mode','due','token'}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _profile(session, revision, job):
    job.check()
    if (not isinstance(session,AppSession) or session.binding.app!='notes'
            or type(revision) is not int or revision<0 or not session.usable
            or session.access!='read_write'):
        raise ValueError(tr('Eine aktuelle beschreibbare Lumen-Notes-Sitzung ist erforderlich.'))
    config=lumen_connect.read_config()
    private={key:config[key] for key in ('server','device_id','token','ca_file') if key in config}
    if private!=session._config:
        raise ValueError(tr('Die Serververbindung wurde geändert. Die bestehende Übernahme zuerst prüfen.'))
    me=lumen_connect.request(config,'/bridge/me',timeout=10)
    job.check()
    if (me.get('id')!=session.binding.account or me.get('device_id')!=session.binding.device
            or me.get('permissions_revision')!=revision or type(me.get('permissions_revision')) is not int
            or 'notes' not in me.get('capabilities',[]) or lumen_connect.read_config()!=config):
        raise ValueError(tr('Konto, Gerät oder Notizfreigaben wurden geändert.'))
    job.check()
    return _digest(private)


def collections(session, permissions_revision, job):
    """Writable existing collections only; selecting none uses the personal Notes area."""
    _profile(session,permissions_revision,job)
    job.check()
    rows=session.request('/api/note-collections',max_bytes=MAX_REPLY)
    _profile(session,permissions_revision,job)
    if not isinstance(rows,list) or len(rows)>1000:
        raise ValueError(tr('Die Notizsammlungen konnten nicht eindeutig geladen werden.'))
    result=[dict(id='',title=tr('Ohne Sammlung'))];seen={''}
    for row in rows:
        name=row.get('name')
        if (not isinstance(name,str) or len(name)>512 or '\0' in name
                or type(row.get('can_write')) is not bool):
            raise ValueError(tr('Ungültige Notizsammlung.'))
        if row['can_write'] and name not in seen:
            seen.add(name);result.append(dict(id=name,title=name))
    return result


def _request(registry, token, choice):
    request=registry.request(token)
    if (request['target']!='wissen' or request['action']!=ACTION
            or not isinstance(choice,dict) or set(choice)!=CHOICE or choice['token']!=token
            or choice['mode'] not in ('copy','link') or choice['due']
            or not isinstance(choice['id'],str) or len(choice['id'])>512
            or not isinstance(choice['title'],str) or not 1<=len(choice['title'])<=200
            or choice['title']!=choice['title'].strip()):
        raise ValueError(tr('Die bestätigte Notizauswahl ist ungültig.'))
    if 'note_capture' in request['choice'] and {k:v for k,v in request['choice'].items() if k!='note_capture'}!=choice:
        raise ValueError(tr('Diese Anfrage ist bereits an eine andere bestätigte Auswahl gebunden.'))
    payload=request['payload']
    if (payload.get('paths') or registry.resolve(payload.get('source_url',''))!=payload.get('source')):
        raise ValueError(tr('Lokale Dateien zuerst ausdrücklich in Lumen Drive übernehmen.'))
    if len(payload.get('references',[]))>20:raise ValueError(tr('Höchstens 20 Drive-Einträge pro Notiz auswählen.'))
    if payload.get('references') and choice['mode']!='link':
        raise ValueError(tr('Drive-Originale als Verknüpfung übernehmen.'))
    return request


def _body(payload, choice, binding, job):
    body=payload.get('text','') if choice['mode']=='copy' or payload.get('references') else ''
    title=payload['source'].get('title') or payload['title']
    def link(label,url):
        label=label.replace('\\','\\\\').replace('[','\\[').replace(']','\\]').replace('\n',' ')
        return '['+label+'](<'+url.replace('>','%3E')+'>)'
    if payload['source'].get('kind') not in ('drive_file','drive_folder'):
        body+=(('\n\n' if body else '')+tr('Quelle: ')+link(title,payload['source_url']))
    resolved=[]
    from server_app_links import drive_navigation
    references=payload.get('references',[])
    if not references and payload['source'].get('kind') in ('drive_file','drive_folder'):
        references=[payload['source']]
    for ref in references:
        if ref['locator']!=dict(server=binding.origin,account=binding.account):
            raise ValueError(tr('Die Drive-Auswahl gehört zu einem anderen Server oder Konto.'))
        navigation=drive_navigation(ref,job)
        resolved.append(dict(reference=ref,resolved=navigation['resolved']))
        body+='\n\n- '+link(ref['title'],binding.origin+navigation['route'])
    if payload.get('url'):body+='\n\n- '+link(payload['title'],payload['url'])
    if len(body)>200000:raise ValueError(tr('Die neue Notiz überschreitet 200.000 Zeichen.'))
    return body,resolved


def _save(registry, request, choice, plan):
    value=dict(choice,note_capture=plan)
    raw=json.dumps(value,allow_nan=False)
    if len(raw)>8192:raise ValueError(tr('Die bestätigte Notizauswahl ist zu groß.'))
    with registry.library.connect() as db:
        changed=db.execute('UPDATE handoffs SET choice=? WHERE id=? AND state=? AND choice=?',
            (raw,request['id'],request['state'],json.dumps(request['choice'],allow_nan=False))).rowcount
    if changed!=1:raise ValueError(tr('Die bestätigte Notizauswahl wurde gleichzeitig geändert.'))
    return registry.request(request['id'])


def _note(value, expected=None):
    if (not isinstance(value,dict) or value.get('kind')!='note' or value.get('deleted') is not False
            or value.get('can_write') is not True or type(value.get('revision')) is not int or value['revision']<1
            or not isinstance(value.get('title'),str) or not isinstance(value.get('body'),str)):
        raise ValueError(tr('Die Notiz wurde nicht eindeutig bestätigt.'))
    try:
        if str(UUID(value['id']))!=value['id']:raise ValueError
    except (ValueError,TypeError,AttributeError,KeyError):
        raise ValueError(tr('Ungültiger Notizbeleg.')) from None
    if expected and (any(value.get(k)!=expected[k] for k in ('title','body','collection'))
            or value.get('ai_allowed') is not False):
        raise ValueError(tr('Die bestätigte Notiz entspricht nicht der übernommenen Auswahl.'))
    return dict(id=value['id'],revision=value['revision'])


def capture(token, choice, session, permissions_revision, job, *, root=None, retry=False):
    """No automatic retry. A human may explicitly retry the identical operation UUID."""
    if type(retry) is not bool:raise ValueError(tr('Eine ausdrückliche Bestätigung für erneutes Prüfen ist erforderlich.'))
    registry=Registry(root);request=_request(registry,token,choice)
    if request['state'] not in ('pending','done'):
        raise ValueError(tr('Diese Notizübernahme wird bereits bearbeitet.'))
    stamp=_profile(session,permissions_revision,job)
    binding=dict(server=session.binding.origin,account=session.binding.account,device=session.binding.device,
                 permissions_revision=permissions_revision,config_stamp=stamp)
    previous=request['choice'].get('note_capture')
    if previous and previous.get('binding')!=binding:
        raise ValueError(tr('Die bestätigte Server- oder Gerätebindung hat sich geändert.'))
    if request['state']=='done':
        ref=validate_ref(registry.resolve(request['result']))
        if not previous or ref.get('app')!='note' or ref['locator']!={k:binding[k] for k in ('server','account')}:
            raise ValueError(tr('Der Notizbeleg gehört nicht zu dieser bestätigten Übernahme.'))
        job.check()
        value=session.request('/api/documents/'+ref['id'],max_bytes=MAX_REPLY);_note(value)
        _profile(session,permissions_revision,job)
        return dict(ref,title=value['title'])
    if choice['id'] not in {row['id'] for row in collections(session,permissions_revision,job)}:
        raise ValueError(tr('Die gewählte Sammlung ist nicht mehr beschreibbar.'))
    body,resolved=_body(request['payload'],choice,session.binding,job)
    document=dict(operation_id=str(UUID(token)),kind='note',title=choice['title'],body=body,
                  collection=choice['id'],ai_allowed=False,ai_override=False)
    plan=dict(version=1,operation_id=document['operation_id'],binding=binding,
              document_hash=_digest(document),references=resolved,attempted=False)
    if previous:
        if {k:v for k,v in previous.items() if k not in ('attempted','receipt')}!={k:v for k,v in plan.items() if k!='attempted'}:
            raise ValueError(tr('Die bestätigte Auswahl oder ein Drive-Original wurde verändert.'))
        if previous.get('attempted') and not previous.get('receipt') and not retry:
            raise ValueError(tr('Das Ergebnis ist unklar. Die Übernahme mit derselben Anfrage ausdrücklich erneut prüfen.'))
        plan=previous
    else:
        request=_save(registry,request,choice,plan)
    request=registry.claim(token,'wissen')
    try:
        _profile(session,permissions_revision,job)
        receipt=plan.get('receipt')
        if not receipt:
            plan=dict(plan,attempted=True);request=_save(registry,request,choice,plan)
            job.check()
            value=session.request('/api/documents',document,max_bytes=MAX_REPLY)
            receipt=_note(value,document)
            plan=dict(plan,receipt=receipt);request=_save(registry,request,choice,plan)
        _profile(session,permissions_revision,job)
        job.check()
        value=session.request('/api/documents/'+receipt['id'],max_bytes=MAX_REPLY)
        _note(value)
        if value['id']!=receipt['id']:raise ValueError(tr('Der aktuelle Notizbeleg stimmt nicht überein.'))
        _profile(session,permissions_revision,job)
        ref=validate_ref(dict(version=2,app='note',id=value['id'],title=value['title'],
                              locator={k:binding[k] for k in ('server','account')}))
        registry.finish(token,registry.register(ref))
        return ref
    except Exception:
        registry.release(token,tr('Die Notizübernahme ist nicht bestätigt. Ergebnis zuerst prüfen.'))
        raise
