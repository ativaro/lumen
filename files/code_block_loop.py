"""Bounded per-line loops using the same durable checkpoints and effect identities."""
import copy
import hashlib
import json


def enter(run,n,previous):
    from code_block_paths import config
    cfg=config(n);items=[s for s in previous.get('text','').splitlines() if s.strip()]
    if len(items)>20 or any(len(s)>8000 for s in items):raise ValueError('Bis zu zwanzig Textzeilen mit je 8.000 Zeichen durchlaufen.')
    cursor=run['data']['cursor'];end=next(i for i,node in enumerate(run['plan']['nodes']) if node['id']==cfg['end'])
    state={'index':0,'items':items,'input':dict(previous),'history':[],'start':cursor,'end':end}
    run['data'].setdefault('loops',{})[n['id']]=state
    if not items:
        for step in run['data']['steps'][cursor+1:end]:step.update(status='skipped',error='Keine Elemente')
        return dict(previous,items_count=0)
    return item_input(state,n['id'])


def item_input(state,identity):
    base=state['input'];index=state['index']
    return {**base,'text':state['items'][index],'item':state['items'][index],'item_index':index+1,
            'iteration_key':base.get('iteration_key','')+'/'+identity+':'+str(index)}


def leave(run,n,previous):
    identity=n['config'];state=run['data']['loops'][identity];data=run['data'];steps=data['steps']
    if not state['items']:return dict(state['input'],text='',items_count=0)
    state['history'].append({'index':state['index']+1,'text':previous.get('text',''),
        'steps':[{'id':node['id'],'status':step['status'],'attempts':step['attempts'],'effect':step['output'].get('effect'),'error':step['error']} for node,step in zip(run['plan']['nodes'][state['start']+1:state['end']],steps[state['start']+1:state['end']])]})
    joined='\n'.join(row['text'] for row in state['history'])
    if len(joined)>120000:raise ValueError('Die gesammelten Ergebnisse sind größer als 120.000 Zeichen.')
    state['index']+=1
    if state['index']<len(state['items']):
        for step in steps[state['start']+1:state['end']]:
            step.clear();step.update(status='pending',attempts=0,input={},output={},error='')
        steps[state['start']]['output']=item_input(state,identity)
        return {'_next_cursor':state['start']+1}
    return {**state['input'],'text':joined,'result':joined,'items_count':len(state['items'])}


def effect_key(run,n,previous):
    iteration=previous.get('iteration_key','')
    return n['id']+('-'+hashlib.sha256(iteration.encode()).hexdigest()[:16] if iteration else '')
