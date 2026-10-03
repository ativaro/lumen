"""Undo a reviewed local import only while its result is unchanged."""
import json
import time
from lumen_i18n import tr
from tools_data import Library

TABLES={'record':'records','task':'tasks','draft':'drafts','event':'interop_event_proposals'}


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
        if kind=='note':
            from wissen_data import Notebook
            from lumen_store import Store
            book=Notebook(store or Store(),root=ref['locator']['root'])
            try:note=book.read(ref['id'])
            except FileNotFoundError:note=None
            if note and note['hash']!=after['hash']:raise ValueError(tr('Der übernommene Inhalt wurde inzwischen geändert. Er bleibt erhalten.'))
            if note:book.remove(ref['id'],after['hash'])
        else:
            current=snapshot(db,kind,ref['id'])
            if not _same(current,after):raise ValueError(tr('Der übernommene Inhalt wurde inzwischen geändert. Er bleibt erhalten.'))
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
