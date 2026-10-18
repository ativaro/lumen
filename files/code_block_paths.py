"""Forward-only branch membership over the existing checkpointed node list."""
import copy
import json
from code_conditions import validate as condition, evaluate, describe

BASE_FIELDS = {'weekday', 'hour', 'success'}
SOURCE_FIELDS = {
    'text': {'text'}, 'file': {'text', 'filename', 'extension', 'size'},
    'message': {'text', 'sender', 'subject', 'has_attachment'},
    'calendar': {'text', 'subject'}, 'project': {'text', 'project_id', 'project_status'},
}


def config(node):
    try: return json.loads(node['config'])
    except (ValueError, TypeError): raise ValueError('Ungültige Bausteineinstellung.') from None


def source(value):
    if not isinstance(value, dict) or not isinstance(value.get('kind'),str) or value.get('kind') not in SOURCE_FIELDS:
        raise ValueError('Eine verfügbare Eingabequelle wählen.')
    allowed = {'kind','text','path','project_id','sender','subject','has_attachment'}
    if set(value)-allowed: raise ValueError('Unbekannte Eingabefelder.')
    for key, v in value.items():
        if key == 'has_attachment':
            if type(v) is not bool: raise ValueError('Anhang als Ja/Nein wählen.')
        elif not isinstance(v, str) or len(v)>8000 or '\0' in v: raise ValueError('Ungültige Eingabe.')
    return value


def available(nodes, index):
    fields = set(BASE_FIELDS)
    for position,n in enumerate(nodes[:index]):
        if n['kind']=='manual':fields |= SOURCE_FIELDS[source(config(n))['kind']]
        if n['kind']=='read_file':fields |= SOURCE_FIELDS['file']
        if n['kind'] in ('ai','ai_check'): fields |= {'text','result'}
        if n['kind']=='ai_check':fields.add('matched')
        if n['kind']=='for_each':
            end=next((i for i,s in enumerate(nodes) if s['id']==config(n).get('end')),-1)
            if position<index<end:fields |= {'item','item_index'}
    return fields


def choose_config(n):
    value = config(n)
    if not isinstance(value,dict) or set(value)!={'cases','otherwise'} or not isinstance(value['cases'],list) or not 1<=len(value['cases'])<=12:
        raise ValueError('Eine bis zwölf Möglichkeiten je Verzweigung wählen.')
    if not isinstance(value['otherwise'],list):raise ValueError('Ungültiger Sonst-Weg.')
    for case in value['cases']:
        if not isinstance(case,dict) or set(case)!={'when','nodes'} or not isinstance(case['nodes'],list):raise ValueError('Ungültiger Weg.')
        condition(case['when'])
    return value


def tree(plan):
    nodes={n['id']:copy.deepcopy(n) for n in plan['nodes']};owned=set()
    for n in nodes.values():
        if n['kind']=='for_each':
            c=config(n)
            if not isinstance(c,dict) or set(c)!={'nodes','end'} or not isinstance(c['nodes'],list) or not isinstance(c['end'],str):raise ValueError('Ungültige Wiederholung.')
            for identity in c['nodes']+[c['end']]:
                if not isinstance(identity,str) or identity not in nodes or identity in owned:raise ValueError('Ungültige Wiederholungszuordnung.')
                owned.add(identity)
        if n['kind']=='choose':
            c=choose_config(n)
            for ids in [*[b['nodes'] for b in c['cases']],c['otherwise']]:
                for identity in ids:
                    if not isinstance(identity,str) or identity not in nodes or identity in owned:raise ValueError('Ein Baustein gehört zu mehreren oder unbekannten Wegen.')
                    owned.add(identity)
    visited=set()
    def expand(n,depth=0):
        if n['id'] in visited or depth>3:raise ValueError('Zyklische oder zu tiefe Verzweigung.')
        visited.add(n['id'])
        if n['kind']=='for_each':
            c=config(n);end=nodes[c['end']]
            if end['kind']!='end_each' or end['config']!=n['id'] or end['id'] in visited:raise ValueError('Ungültiger Schleifenabschluss.')
            n['steps']=[expand(nodes[i],depth+1) for i in c['nodes']];n['end']=end;visited.add(end['id'])
        if n['kind']=='choose':
            c=choose_config(n)
            n['cases']=[{'when':b['when'],'steps':[expand(nodes[i],depth+1) for i in b['nodes']]} for b in c['cases']]
            n['otherwise']=[expand(nodes[i],depth+1) for i in c['otherwise']]
        return n
    result=[expand(n) for n in nodes.values() if n['id'] not in owned]
    if len(visited)!=len(nodes):raise ValueError('Nicht erreichbarer oder zyklischer Weg.')
    return result


def flatten(items):
    result=[]
    def append(n):
        row={k:copy.deepcopy(n[k]) for k in ('id','kind','title','config')}
        if n['kind']=='choose':row['config']=json.dumps({'cases':[{'when':b['when'],'nodes':[s['id'] for s in b['steps']]} for b in n['cases']], 'otherwise':[s['id'] for s in n['otherwise']]},ensure_ascii=False,separators=(',',':'))
        if n['kind']=='for_each':row['config']=json.dumps({'nodes':[s['id'] for s in n['steps']],'end':n['end']['id']},ensure_ascii=False,separators=(',',':'))
        result.append(row)
        if n['kind']=='for_each':
            for child in n['steps']:append(child)
            result.append(copy.deepcopy(n['end']))
        if n['kind']=='choose':
            for b in n['cases']:
                for step in b['steps']:append(step)
            for step in n['otherwise']:append(step)
    for n in items:append(n)
    return {'version':3,'nodes':result}


def validate(plan):
    from code_blocks import CATALOG
    if not isinstance(plan,dict) or set(plan)!={'version','nodes'} or type(plan['version']) is not int or plan['version']!=3:
        raise ValueError('Ungültige Bausteinversion.')
    nodes=plan['nodes']
    if not isinstance(nodes,list) or not 2<=len(nodes)<=60:raise ValueError('Zwei bis sechzig Bausteine wählen.')
    identities=set()
    for i,n in enumerate(nodes):
        if not isinstance(n,dict) or set(n)!={'id','kind','title','config'} or not isinstance(n['kind'],str) or n['kind'] not in CATALOG:
            raise ValueError('Ungültiger Baustein.')
        for key,limit in [('id',32),('title',160),('config',12000)]:
            if not isinstance(n[key],str) or len(n[key])>limit or '\0' in n[key]:raise ValueError('Ungültiges Bausteinfeld.')
        if len(n['id'])!=32 or any(c not in '0123456789abcdef' for c in n['id']) or n['id'] in identities or not n['title'].strip():raise ValueError('Ungültige Bausteinkennung oder Name.')
        identities.add(n['id'])
        if (i==0)!=(n['kind']=='manual'):raise ValueError('Der erste und einzige Start ist manuell.')
        if n['kind']=='manual':source(config(n))
        if n['kind']=='delay' and (not n['config'].isdigit() or not 0<=int(n['config'])<=3600):raise ValueError('Wartezeit: null bis 3.600 Sekunden.')
        if n['kind']=='project_note' and len(n['config'])>160:raise ValueError('Bitte ein Lumen-Projekt auswählen.')
        if n['kind']=='condition':condition(config(n), available(nodes,i))
        if n['kind']=='choose':
            c=choose_config(n)
            for b in c['cases']:condition(b['when'],available(nodes,i))
    parsed=tree(plan)
    if flatten(parsed)!=plan:raise ValueError('Die Reihenfolge der Wege passt nicht zum Ablauf.')
    if len(json.dumps(plan))>30000:raise ValueError('Ablauf ist zu groß.')
    return copy.deepcopy(plan)


def branch_ids(plan, n):
    c=choose_config(n);mapping={x['id']:x for x in plan['nodes']}
    def collect(ids):
        result=set(ids)
        for identity in ids:
            child=mapping[identity]
            if child['kind']=='for_each':
                cfg=config(child);result |= collect(cfg['nodes']+[cfg['end']])
            if child['kind']=='choose':
                cfg=choose_config(child)
                for group in [*[b['nodes'] for b in cfg['cases']],cfg['otherwise']]:result |= collect(group)
        return result
    return c,[collect(b['nodes']) for b in c['cases']]+[collect(c['otherwise'])]


def route(run,n,previous):
    data=run['data'];output=dict(previous)
    if n['kind']=='condition':
        matches=evaluate(config(n),previous);output['condition']=matches
        skip={s['id'] for s in run['plan']['nodes'][data['cursor']+1:]} if not matches else set()
        reason='Startbedingung nicht erfüllt'
    else:
        c,groups=branch_ids(run['plan'],n)
        selected=next((i for i,b in enumerate(c['cases']) if evaluate(b['when'],previous)),len(groups)-1)
        skip=set().union(*(group for i,group in enumerate(groups) if i!=selected))
        output['branch']=describe(c['cases'][selected]['when']) if selected<len(c['cases']) else 'Sonst'
        reason='Anderer Weg gewählt'
    for node,step in zip(run['plan']['nodes'],data['steps']):
        if node['id'] in skip:step.update(status='skipped',error=reason)
    return output


def starter():
    from code_blocks import node
    start=node('manual',json.dumps({'kind':'text','text':''}))
    return {'version':3,'nodes':[start,node('ai','Fasse den eingegebenen Text zusammen.'),node('approval'),node('notify')]}


def proposal(text):
    if not isinstance(text,str) or not text.strip() or len(text)>8000:raise ValueError('Bitte den Ablauf in höchstens 8.000 Zeichen beschreiben.')
    return ('Erstelle einen Lumen-Bausteinentwurf. Nur JSON {"steps":[...]}. '
            'Jeder Schritt: {"kind":"Typ","title":"Name","config":"Text"}. '
            'Typen: read_file,filter_text,ai,ai_check,choose,for_each,delay,approval,save_file,save_note,create_task,project_note,notify. '
            'choose hat zusätzlich "cases":[{"when":Bedingung,"steps":[...]}],"otherwise":[...]. '
            'for_each hat zusätzlich "steps":[...]; durchläuft höchstens 20 Textzeilen. '
            'Bedingung: {"all":[...]}, {"any":[...]}, {"not":...} oder {"field":"...","op":"...","value":...}. '
            'Felder: text; nach read_file filename,extension,size; nach ai_check matched; nach KI result; im for_each item,item_index; immer weekday,hour,success. '
            'Textvergleiche equals,contains,starts_with,ends_with,exists. Zahlen: equals,greater,less,at_least,at_most,exists. Bool: equals,exists. '
            'exists hat einen booleschen Wert. Vergleiche müssen zum Feldtyp passen. '
            'config nur für ai/ai_check als Auftrag, für filter_text als Suchtext, delay als 0..3600 Sekunden. Alle Pfade, Projektkennungen und Ziele leer lassen. '
            'Keine unbekannten Bausteine oder Quellen erfinden. Höchstens 30 Schritte, drei Ebenen. '
            'Wenn die Anforderung weitere Verbindungen braucht: {"question":"konkrete Rückfrage"}. '
            'Keine Werkzeuge benutzen oder Aktionen ausführen. BESCHREIBUNG (Daten): '+json.dumps(text,ensure_ascii=False))


def generated(answer, input_node=None):
    from tools_data import parse_answer
    from code_blocks import node
    value=parse_answer(answer)
    if not isinstance(value,dict):raise ValueError('Kein gültiger Bausteinentwurf.')
    if set(value)=={'question'} and isinstance(value['question'],str):raise ValueError(value['question'][:2000])
    if set(value)!={'steps'}:raise ValueError('Kein gültiger Bausteinentwurf.')
    count=0
    def build(rows,depth=0):
        nonlocal count
        if not isinstance(rows,list) or depth>3:raise ValueError('Ungültige oder zu tiefe Bausteine.')
        result=[]
        for row in rows:
            count+=1
            if count>30 or not isinstance(row,dict):raise ValueError('Zu viele oder ungültige Bausteine.')
            kind=row.get('kind');extra={'cases','otherwise'} if kind=='choose' else {'steps'} if kind=='for_each' else set()
            if kind not in ('read_file','filter_text','ai','ai_check','choose','for_each','delay','approval','save_file','save_note','create_task','project_note','notify') or set(row)!={'kind','title','config'}|extra:raise ValueError('Nicht unterstützter KI-Baustein.')
            config_value=row['config'] if kind in ('ai','ai_check','filter_text','delay') else ''
            n=node(kind,config_value,row['title'])
            if kind=='for_each':n.update(steps=build(row['steps'],depth+1),end=node('end_each',n['id'],title='Ergebnisse sammeln'))
            if kind=='choose':
                if not isinstance(row['cases'],list):raise ValueError('Ungültige Wege.')
                cases=[]
                for case in row['cases']:
                    if not isinstance(case,dict) or set(case)!={'when','steps'}:raise ValueError('Ungültiger Weg.')
                    cases.append({'when':case['when'],'steps':build(case['steps'],depth+1)})
                n.update(cases=cases,otherwise=build(row['otherwise'],depth+1))
            result.append(n)
        return result
    return validate(flatten([copy.deepcopy(input_node) if input_node else node('manual',json.dumps({'kind':'text','text':''})),*build(value['steps'])]))
