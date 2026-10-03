"""Track Files moves without letting an already-open project restore stale paths."""
import json
from pathlib import Path
import time
from urllib.parse import unquote,urlsplit
from interop_data import Registry
from tools_data import Library


def moves(root=None,after=0):
    registry=Registry(root)
    with registry.library.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS path_moves(seq INTEGER PRIMARY KEY AUTOINCREMENT, old TEXT NOT NULL, new TEXT NOT NULL)')
        return [dict(row) for row in db.execute('SELECT * FROM path_moves WHERE seq>? ORDER BY seq',(after,))]


def revision(root=None):
    rows=moves(root)
    return rows[-1]['seq'] if rows else 0


def mapped(value,changes):
    if not value or not isinstance(value,str):return value
    uri=urlsplit(value);is_uri=uri.scheme=='file' and not uri.netloc
    path=Path(unquote(uri.path) if is_uri else value)
    if not path.is_absolute():return value
    for change in changes:
        old=Path(change['old'])
        if path.is_relative_to(old):path=Path(change['new'])/path.relative_to(old)
    return path.as_uri() if is_uri else str(path)


def relocate(old,new,root=None):
    registry=Registry(root);moves(root)
    registry.relocate(old,new)
    with registry.library.connect() as db:
        cursor=db.execute('INSERT INTO path_moves(old,new) VALUES (?,?)',(str(old),str(new)))
        seq=cursor.lastrowid
    changes=[dict(old=str(old),new=str(new))]
    for app in ('workbench','reader','household'):
        if not (registry.library.root.parent/app/'library.sqlite').exists():continue
        library=Library(app,registry.library.root.parent)
        with library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT id,data FROM records').fetchall():
                value=json.loads(row['data']);before=json.dumps(value)
                if app=='workbench':
                    for resource in value.get('resources',[]):
                        if resource.get('kind')=='file':resource['target']=mapped(resource['target'],changes)
                    for item in value.get('reading_list',[]):item['path']=mapped(item['path'],changes)
                    value['interop_path_revision']=seq
                elif app=='household':
                    for link in value.get('linked_paths',[]):link['path']=mapped(link['path'],changes)
                else:
                    for key in ('original_path','source'):
                        if value.get(key):value[key]=mapped(value[key],changes)
                if before!=json.dumps(value):db.execute('UPDATE records SET data=?,updated=? WHERE id=?',(json.dumps(value),time.time(),row['id']))
    return seq


def update_window(window):
    from PyQt5.QtCore import Qt
    changes=moves(window.library.root.parent,getattr(window,'interop_path_revision',0))
    if not changes:return
    for index in range(window.resources.count()):
        item=window.resources.item(index);value=item.data(Qt.UserRole)
        if value.get('kind')=='file':
            value['target']=mapped(value['target'],changes)
            item.setData(Qt.UserRole,value);item.setText(value['title']+'\n'+value['target'])
    window.interop_path_revision=changes[-1]['seq']
