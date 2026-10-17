"""Local flow adapters: existing timer/tasks, frozen instructions and bounded results."""
import json
import sqlite3
import time
from uuid import uuid5,NAMESPACE_URL
from code_flow import parse,prompt,encode


def configure(collection,item,approved=False):
    from code_library_execution import directory
    plan=parse(item['definition']['flow'])
    if plan.get('version')==2:raise ValueError('Bausteinabläufe werden im eigenen Ablaufeditor ausgeführt.')
    if (plan['trigger']=='schedule' and 'clock' not in plan) or plan['source_ids'] or plan['service_ids']:
        raise ValueError('Dieser Ablauf benötigt Lumen Server. Lokal sind Intervalle, Ordner, Meldungen und Aufgabenentwürfe verfügbar.')
    if 'note' in plan['outputs']:
        if not plan.get('note_root') or plan['note_root']!=collection.store.setting('knowledge/notebook',''):raise ValueError('Den aktuellen Notizordner ausdrücklich auswählen.')
        from wissen_data import Notebook
        Notebook(collection.store,root=plan['note_root'])
    root=directory(collection,item)
    if plan['trigger']=='directory':
        from pathlib import Path
        root=Path(plan['watch']).expanduser().resolve(strict=True)
        if not root.is_dir():raise ValueError('Bitte den beobachteten Ordner ausdrücklich auswählen.')
    identity=collection.store.save_workflow(item['title'],[],[str(root)],trigger=plan['trigger'],interval=plan['minutes']*60,
        watch=str(root) if plan['trigger']=='directory' else '',approved=approved,enabled=False,prompt=prompt(plan),
        workflow=item['definition'].get('workflow_id') or None,code_plan=encode(plan),collection_entry=(item['id'],item['revision']))
    return collection.get(item['id'])


def snapshot(db,task,flow,manual=False):
    if not flow['code_plan']:return
    db.execute("UPDATE code_library SET last_task=?,last_used=? WHERE kind='automation' AND NOT archived AND json_extract(definition,'$.workflow_id')=?",(task,time.time(),flow['id']))
    value={'id':flow['id'],'updated':flow['updated'],'manual':manual,'plan':parse(flow['code_plan'])}
    db.execute('INSERT INTO events(task,kind,detail,created) VALUES(?,?,?,?)',(task,'code-flow',json.dumps(value),time.time()))


def complete(db,task,result):
    event=db.execute("SELECT detail FROM events WHERE task=? AND kind='code-flow' ORDER BY id DESC LIMIT 1",(task,)).fetchone()
    if not event:return
    snapshot=json.loads(event['detail']);plan=parse(json.dumps(snapshot['plan']))
    flow=db.execute('SELECT * FROM workflows WHERE id=?',(snapshot['id'],)).fetchone()
    current=db.execute('SELECT * FROM tasks WHERE id=?',(task,)).fetchone()
    if not flow or flow['updated']!=snapshot['updated'] or not flow['approved'] or not (flow['enabled'] or snapshot['manual']):
        raise ValueError('Die Automation wurde geändert oder pausiert. Das Ergebnis wurde nicht weitergegeben.')
    if current['status']!='running':raise ValueError('Nur ein laufender Auftrag kann ein Ablauf-Ergebnis weitergeben.')
    if db.execute("SELECT 1 FROM events WHERE task=? AND kind='code-flow-done'",(task,)).fetchone():return
    prior=db.execute("SELECT value FROM settings WHERE key=?",('code-flow-result/'+flow['id'],)).fetchone()
    import hashlib
    digest=hashlib.sha256(result.encode()).hexdigest()
    changed=not prior or json.loads(prior['value'])!=digest
    db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('code-flow-result/'+flow['id'],json.dumps(digest)))
    if plan['condition']=='always' or changed:
        for index,action in enumerate(plan['outputs']):
            identity=uuid5(NAMESPACE_URL,'lumen-code-flow:'+task+':'+str(index)).hex
            if action=='task_draft':
                db.execute('''INSERT OR IGNORE INTO tasks(id,title,prompt,directory,roots,steps,status,approved,created,updated)
                  VALUES(?,?,?,?,?,?,'draft',0,?,?)''',(identity,current['title'][:200],result[:20000],current['directory'],'[]','[]',time.time(),time.time()))
            elif action=='notify':
                db.execute('INSERT INTO events(task,kind,detail,created) VALUES(?,?,?,?)',(task,'code-flow-notify',identity,time.time()))
            elif action=='note':
                db.execute('INSERT INTO events(task,kind,detail,created) VALUES(?,?,?,?)',(task,'code-flow-note',json.dumps(dict(id=identity,root=plan['note_root'])),time.time()))
            else:raise ValueError('Diese Ergebnisaktion ist lokal nicht verfügbar.')
    if plan.get('clock',{}).get('kind')=='once':db.execute('UPDATE workflows SET enabled=0 WHERE id=?',(flow['id'],))
    db.execute('INSERT INTO events(task,kind,detail,created) VALUES(?,?,?,?)',(task,'code-flow-done','',time.time()))


def deliver(store):
    deliver_notes(store)
    from lumen_notifications import publish
    rows=store.rows("SELECT e.id,e.task,e.detail,t.title,t.result FROM events e JOIN tasks t ON t.id=e.task WHERE e.kind='code-flow-notify' AND t.status='completed' LIMIT 20")
    for row in rows:
        try:
            publish('Lumen Code & Automation',row['detail'],row['title'][:300],row['result'][:2000],target='local-task:'+row['task'])
        except (ValueError,OSError,sqlite3.Error):continue
        with store.connect() as db:db.execute("UPDATE events SET kind='code-flow-notified' WHERE id=? AND kind='code-flow-notify'",(row['id'],))


def deliver_notes(store):
    from wissen_data import Notebook
    rows=store.rows("SELECT e.id,e.detail,t.title,t.result FROM events e JOIN tasks t ON t.id=e.task WHERE e.kind='code-flow-note' AND t.status='completed' LIMIT 20")
    for row in rows:
        value=json.loads(row['detail'])
        if value['root']!=store.setting('knowledge/notebook',''):continue
        try:
            book=Notebook(store,root=value['root']);path='Lumen-'+value['id']+'.md';marker='code-flow:'+value['id']
            try:
                note=book.read(path)
                if note.get('legacy')!=marker:continue
            except FileNotFoundError:
                book.write(path,'# '+row['title']+'\n\n'+row['result'],'',legacy=marker)
            with store.connect() as db:db.execute("UPDATE events SET kind='code-flow-note-saved' WHERE id=? AND kind='code-flow-note'",(row['id'],))
        except (ValueError,OSError,sqlite3.Error):continue
