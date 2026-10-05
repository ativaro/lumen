"""Undo a reviewed local import only while its result is unchanged."""
import json
import time
from lumen_i18n import tr
from tools_data import Library

TABLES={'record':'records','project_item':'project_items','task':'tasks','draft':'drafts','event':'interop_event_proposals'}


def _same(left,right):
    def canonical(value):
        if isinstance(value,dict):
            return {key:canonical(json.loads(item) if key=='data' else item) for key,item in value.items()
                    if key!='interop_path_revision' and item not in ('',None,False,[],{})}
        if isinstance(value,list):return [canonical(item) for item in value]
        return value
    return canonical(left)==canonical(right)


def snapshot(db,kind,key):
    row=db.execute('SELECT * FROM '+TABLES[kind]+' WHERE id=?',(key,)).fetchone()
    if row is None:return None
    value=dict(row);value.pop('updated',None)
    if kind=='task':
        detail=db.execute('SELECT body FROM interop_task_details WHERE task=?',(key,)).fetchone()
        value['_body']=detail['body'] if detail else ''
    return value


def remember(db,token,ref,before,after):
    db.execute('CREATE TABLE IF NOT EXISTS interop_undo(token TEXT PRIMARY KEY, ref TEXT NOT NULL, before TEXT, after TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0)')
    db.execute('INSERT INTO interop_undo(token,ref,before,after) VALUES (?,?,?,?)',(token,json.dumps(ref),json.dumps(before),json.dumps(after)))


def undo(action,token,job,root=None,store=None):
    from interop_targets import ACTIONS,_lock
    target=ACTIONS[action]['target'];library=Library(target,root)
    with _lock(library,job),library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='interop_undo'").fetchone()
        row=db.execute('SELECT * FROM interop_undo WHERE token=?',(token,)).fetchone() if exists else None
        if not row:raise ValueError(tr('Für diese Übernahme ist kein Rückgängig-Eintrag vorhanden.'))
        ref=json.loads(row['ref']);before=json.loads(row['before']);after=json.loads(row['after'])
        if row['undone']:return ref
        job.check();kind=ref['kind']
        key=ref['id']
        if ref.get('app')=='workbench' and ref.get('position',{}).get('part','').startswith('item:'):
            kind='project_item';key=ref['position']['part'].split(':',1)[1]
        if kind=='note':
            from wissen_data import Notebook
            from lumen_store import Store
            book=Notebook(store or Store(),root=ref['locator']['root'])
            try:note=book.read(ref['id'])
            except FileNotFoundError:note=None
            if note and note['hash']!=after['hash']:raise ValueError(tr('Der übernommene Inhalt wurde inzwischen geändert. Er bleibt erhalten.'))
            if note:book.remove(ref['id'],after['hash'])
        else:
            current=snapshot(db,kind,key)
            if not _same(current,after):raise ValueError(tr('Der übernommene Inhalt wurde inzwischen geändert. Er bleibt erhalten.'))
            if before is not None and target=='workbench' and kind=='record' and db.execute("SELECT 1 FROM sqlite_master WHERE name='project_items'").fetchone():
                import hashlib
                questions=json.loads(before['data']).get('questions',[]) if before else []
                retained={hashlib.sha256((str(index)+'\0'+question.get('text','').strip()).encode()).hexdigest() for index,question in enumerate(questions)}
                imported={hashlib.sha256((str(index)+'\0'+question.get('text','').strip()).encode()).hexdigest() for index,question in enumerate(json.loads(current['data']).get('questions',[]))}-retained
                for child in db.execute('SELECT * FROM project_items WHERE project=?',(key,)).fetchall():
                    data=json.loads(child['data']); source=data.get('legacy_source')
                    if not source or source not in imported:continue
                    pristine=child['title']==data.get('legacy_text') and not any(data.get(k) for k in ('notes','resources','goal','depends')) and data.get('status')==('done' if data.get('legacy_done') else 'open')
                    if not pristine or db.execute('SELECT 1 FROM project_runs WHERE task=?',(child['id'],)).fetchone():
                        raise ValueError(tr('Die übernommene Aufgabe wurde inzwischen bearbeitet. Sie bleibt erhalten.'))
                    data['legacy_origin']=data.pop('legacy_source')
                    db.execute('UPDATE project_items SET archived=1,data=? WHERE id=?',(json.dumps(data),child['id']))
                    db.execute('DELETE FROM project_migration WHERE project=? AND source=?',(key,source))
            if before is None:
                if kind=='record':db.execute('UPDATE records SET archived=1 WHERE id=?',(ref['id'],))
                else:
                    db.execute('DELETE FROM '+TABLES[kind]+' WHERE id=?',(ref['id'],))
                    if kind=='task':db.execute('DELETE FROM interop_task_details WHERE task=?',(ref['id'],))
            else:
                values=dict(before);key=values.pop('id')
                if kind=='task':
                    detail=values.pop('_body','')
                    db.execute('INSERT INTO interop_task_details VALUES (?,?) ON CONFLICT(task) DO UPDATE SET body=excluded.body',(key,detail))
                if kind=='record':values['updated']=time.time()
                db.execute('UPDATE '+TABLES[kind]+' SET '+','.join(column+'=?' for column in values)+' WHERE id=?',(*values.values(),key))
        db.execute('UPDATE interop_undo SET undone=1 WHERE token=?',(token,))
    return ref
