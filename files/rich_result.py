"""Bounded, declarative assistant UI data. No executable content or intent filters."""
import json
import math
import uuid
from studio_results import present as present_files

KIND = 'lumen.view.v1'
TOOL = 'lumen_present_view'
# The instruction that offers native views is the service's (native/service/src/turn.rs).

STR = {'type':'string','maxLength':200}
SCHEMA = {'type':'object','additionalProperties':False,'required':['title','blocks'],'properties':{
    'title': STR, 'submit_label': STR,
    'blocks': {'type':'array','maxItems':12,'items':{'type':'object','additionalProperties':False,
        'required':['id','type','label'],'properties':{
        'id':{'type':'string','minLength':1,'maxLength':64},
        'type':{'type':'string','enum':['table','slider','select','toggle','chart','progress','files']},
        'label':STR,
        'columns':{'type':'array','maxItems':8,'items':STR},
        'rows':{'type':'array','maxItems':100,'items':{'type':'array','maxItems':8,'items':{}}},
        'options':{'type':'array','maxItems':24,'items':STR},
        'value':{}, 'min':{'type':'integer'},'max':{'type':'integer'},'step':{'type':'integer'},
        'unit':{'type':'string','maxLength':24},
        'items':{'type':'array','maxItems':24,'items':{'type':'object','required':['label','value'],
            'additionalProperties':False,'properties':{'label':STR,'value':{}}}},
        'paths':{'type':'array','maxItems':24,'items':{'type':'string','maxLength':4096}}
    }}}}}


def text(value, limit=200):
    if not isinstance(value,str) or len(value)>limit or '\0' in value: raise ValueError('Invalid view text.')
    return value


def number(value):
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e12:
        raise ValueError('Invalid numeric value.')
    return value


def validate(payload, check_files=False):
    if not isinstance(payload,dict) or payload.get('kind')!=KIND: raise ValueError('Invalid view.')
    identity=text(payload.get('id'),128)
    if not identity: raise ValueError('Missing view identity.')
    title=text(payload.get('title')); submit=text(payload.get('submit_label',''))
    blocks=payload.get('blocks')
    if not isinstance(blocks,list) or len(blocks)>12: raise ValueError('Too many blocks.')
    clean=[]; ids=set(); cells=0
    for block in blocks:
        if not isinstance(block,dict): raise ValueError('Invalid block.')
        key=text(block.get('id'),64); kind=block.get('type'); label=text(block.get('label'))
        if not key or key in ids: raise ValueError('Each block needs a unique id.')
        ids.add(key); item=dict(id=key,type=kind,label=label)
        if kind=='table':
            columns=block.get('columns'); rows=block.get('rows')
            if not isinstance(columns,list) or not 1<=len(columns)<=8: raise ValueError('Use 1–8 columns.')
            if not isinstance(rows,list) or len(rows)>100: raise ValueError('Use at most100 rows.')
            cells+=len(columns)*len(rows)
            if cells>1200:raise ValueError('Use at most1200 table cells per view.')
            item['columns']=[text(c) for c in columns]; item['rows']=[]
            for row in rows:
                if not isinstance(row,list) or len(row)!=len(columns): raise ValueError('Row width differs from columns.')
                item['rows'].append([text(v,2000) if isinstance(v,str) else number(v) for v in row])
        elif kind=='slider':
            low=number(block.get('min',0)); high=number(block.get('max',100)); step=number(block.get('step',1)); value=number(block.get('value',low))
            if any(type(v) is not int for v in (low,high,step,value)) or not low<high or step<=0 or step>high-low or not low<=value<=high:
                raise ValueError('Slider requires bounded integer min/max/step/value.')
            item.update(min=low,max=high,step=step,value=value,unit=text(block.get('unit',''),24))
        elif kind=='select':
            options=block.get('options'); value=block.get('value')
            if not isinstance(options,list) or not 1<=len(options)<=24: raise ValueError('Use 1–24 choices.')
            options=[text(v) for v in options]
            if len(set(options))!=len(options) or value not in options: raise ValueError('Invalid choice.')
            item.update(options=options,value=value)
        elif kind=='toggle':
            if type(block.get('value')) is not bool: raise ValueError('Toggle value must be boolean.')
            item['value']=block['value']
        elif kind=='chart':
            points=block.get('items')
            if not isinstance(points,list) or not 1<=len(points)<=24: raise ValueError('Use 1–24 chart items.')
            item['items']=[]; item['unit']=text(block.get('unit',''),24)
            for point in points:
                if not isinstance(point,dict): raise ValueError('Invalid chart item.')
                value=number(point.get('value'))
                if value<0: raise ValueError('Bar values must be nonnegative.')
                item['items'].append(dict(label=text(point.get('label')),value=value))
        elif kind=='progress':
            value=number(block.get('value'))
            if not 0<=value<=100: raise ValueError('Progress must be 0–100.')
            item['value']=value
        elif kind=='files':
            paths=block.get('paths')
            if not isinstance(paths,list) or len(paths)>24: raise ValueError('Use at most24 files.')
            if check_files: paths=present_files(paths)['paths']
            else:
                from studio_results import validate as validate_files
                paths=validate_files(dict(kind='lumen.presentation.v1',id=identity,title='',paths=paths))['paths']
            item['paths']=paths
        else: raise ValueError('Unknown component type.')
        clean.append(item)
    result=dict(kind=KIND,id=identity,title=title,submit_label=submit,blocks=clean)
    if len(json.dumps(result,ensure_ascii=False))>400000:raise ValueError('View is too large; reduce table data.')
    return result


def present(args):
    return validate(dict(args,kind=KIND,id=uuid.uuid4().hex),check_files=True)


def _located_result(messages, include_files=False):
    for index in range(len(messages)-1, -1, -1):
        message = messages[index]
        if message.get('info',{}).get('role')!='assistant': continue
        for part_index in range(len(message.get('parts', []))-1, -1, -1):
            part = message['parts'][part_index]
            tool=part.get('tool',''); state=part.get('state',{})
            if part.get('type')!='tool' or not isinstance(tool,str): continue
            files = include_files and (tool=='lumen_present_files' or tool.endswith('_lumen_present_files'))
            if not files and tool!=TOOL and not tool.endswith('_'+TOOL): continue
            output=state.get('output')
            if state.get('status')!='completed' or not isinstance(output,str) or len(output)>1800000: continue
            try:
                value=json.loads(output)
                if files:
                    from studio_results import validate as validate_files
                    value=validate_files(value)
                    value=dict(kind=KIND,id=value['id'],title=value['title'],blocks=[
                        dict(id='files'+str(i),type='files',label='',paths=value['paths'][i:i+24])
                        for i in range(0,len(value['paths']),24)])
                return index, part_index, validate(value)
            except (ValueError,TypeError):continue
    return None


def from_messages(messages, include_files=False):
    result = _located_result(messages, include_files)
    return result[2] if result else None


def display_messages(messages, include_files=False):
    """Anchor the current interactive result between the text parts that produced it."""
    location = _located_result(messages, include_files)
    rows = []
    for index, message in enumerate(messages):
        info = message.get('info', {})
        if location is None or index != location[0]:
            rows.append(dict(info=info, parts=message.get('parts', [])))
            continue
        cut = location[1]; parts = message['parts']; key = str(info.get('id', index))
        if parts[:cut]: rows.append(dict(info=info, parts=parts[:cut]))
        rows.append(dict(info=dict(info, id=key+':view:'+str(cut)), parts=[], presentation=True))
        if parts[cut+1:]:
            rows.append(dict(info=dict(info, id=key+':after:'+str(cut)), parts=parts[cut+1:]))
    return rows
