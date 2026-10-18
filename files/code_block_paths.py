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
    if not isinstance(value, dict) or value.get('kind') not in SOURCE_FIELDS:
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
    for n in nodes[:index]:
        if n['kind']=='manual':fields |= SOURCE_FIELDS[source(config(n))['kind']]
        if n['kind']=='read_file':fields |= SOURCE_FIELDS['file']
        if n['kind'] in ('ai','ai_check'): fields |= {'text','result'}
        if n['kind']=='ai_check':fields.add('matched')
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
        result.append(row)
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
