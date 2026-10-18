"""Three local triggers over the existing checkpointed block runner, disabled by default."""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from code_clock import validate as clock_validate, starts


def validate(value, source):
    if not isinstance(value,dict) or value.get('kind') not in ('clock','directory','project'):
        raise ValueError('Einen verfügbaren Auslöser wählen.')
    kind=value['kind'];keys={'kind','clock'} if kind=='clock' else {'kind','path'} if kind=='directory' else {'kind'}
    if set(value)!=keys:raise ValueError('Ungültige Auslöserfelder.')
    if kind=='clock':
        clock_validate(value['clock'])
        if value['clock']['kind']=='manual':raise ValueError('Für einen Zeitplan eine Wiederholung wählen.')
    if kind=='directory':
        path=value['path']
        if source!='file' or not isinstance(path,str) or not Path(path).is_absolute() or '..' in Path(path).parts or '\0' in path or len(path)>3000:
            raise ValueError('Einen absoluten beobachteten Ordner wählen.')
    if kind=='project' and source!='project':raise ValueError('Für Projektänderungen ein Lumen-Projekt auswählen.')
    return value


def project_choices(store):
    from tools_data import Library
    from lumen_projects import projects
    return {**{p['id']:p['name'] for p in projects(store)},
            **{'workbench:'+p['id']:p['title'] for p in Library('workbench').all()}}


def project_snapshot(identity,store):
    if identity.startswith('workbench:'):
        from tools_data import Library
        from projects_data import Projects
        library=Library('workbench');record=library.get(identity[10:])
        if record['_archived']:raise ValueError('Das ausgewählte Lumen-Projekt wurde archiviert.')
        items=Projects(library).items(record['id'])
        if len(items)>1000:raise ValueError('Für diesen Ablauf ein Projekt mit höchstens 1.000 Einträgen wählen.')
        # Linked document contents are not implicitly opened or sent to a model.
        data={'title':record['title'],'notes':record.get('notes',''),'resources':record.get('resources',[]),
              'items':[{k:p.get(k) for k in ('id','parent','title','kind','status','notes','goal','resources')} for p in items]}
    else:
        from lumen_projects import projects
        record=next((p for p in projects(store) if p['id']==identity),None)
        if record is None:raise ValueError('Das ausgewählte Lumen-Projekt ist nicht mehr verfügbar.')
        data={'title':record['name'],'notes':record.get('note','')}
    text=json.dumps(data,ensure_ascii=False,sort_keys=True)
    if len(text)>60000:raise ValueError('Die Projektübersicht ist größer als 60.000 Zeichen.')
    return {'text':text,'project_id':identity,'project_status':record.get('status',''),
            'revision':hashlib.sha256(text.encode()).hexdigest()}


def scan(path):
    from code_blocks_run import directory_fd
    result={}
    with directory_fd(path) as fd:
        info=os.fstat(fd);root=[info.st_dev,info.st_ino]
        with os.scandir(fd) as entries:
            for index,e in enumerate(entries):
                if index>=10000:raise ValueError('Bis zu 10.000 Einträge im beobachteten Ordner.')
                s=e.stat(follow_symlinks=False)
                if e.name.startswith('.') or not stat.S_ISREG(s.st_mode):continue
                if s.st_size<=20*1024**2:result[e.name]=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]
    return root,result


def file_event(source,path):
    trigger=validate(source['trigger'],source['kind']);path=Path(path)
    if trigger['kind']!='directory' or path.parent!=Path(trigger['path']):raise ValueError('Eine Datei direkt aus dem gewählten Ordner auswählen.')
    root,files=scan(trigger['path'])
    if path.name not in files:raise ValueError('Eine reguläre Datei bis 20 MiB auswählen.')
    return dict(path=str(path),stamp=files[path.name],root=root)


class Triggers:
    def __init__(self,collection):
        self.collection=collection;self.store=collection.store
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS code_block_triggers (
              entry TEXT PRIMARY KEY, signature TEXT NOT NULL, enabled INTEGER NOT NULL,
              state TEXT NOT NULL, next_run REAL NOT NULL, error TEXT NOT NULL, checked REAL NOT NULL)''')

    def get(self,entry,db=None):
        if db is None:
            with self.store.connect() as con:return self.get(entry,con)
        row=db.execute('SELECT * FROM code_block_triggers WHERE entry=?',(entry,)).fetchone()
        return dict(row) if row else None

    def activate(self,entry,now=None):
        from code_blocks import parse,permissions
        from code_blocks_run import digest
        from code_block_paths import config
        now=time.time() if now is None else now
        item=self.collection.get(entry);plan=parse(item['definition']['flow']);permissions(plan)
        source=config(plan['nodes'][0]);trigger=validate(source.get('trigger'),source['kind'])
        if item['archived']:raise ValueError('Archivierte Abläufe nicht aktivieren.')
        if trigger['kind']=='project' and any(n['kind']=='project_note' and n['config']==source.get('project_id') for n in plan['nodes']):
            raise ValueError('Das auslösende Projekt nicht selbst verändern; ein anderes Ziel wählen.')
        state={};due=0
        if trigger['kind']=='directory':
            if any(n['kind']=='save_file' and Path(n['config'])==Path(trigger['path']) for n in plan['nodes']):
                raise ValueError('Ergebnisse in einem anderen Ordner speichern, damit sie nicht erneut auslösen.')
            root,files=scan(trigger['path']);state=dict(root=root,accepted=files,observed=files)
        elif trigger['kind']=='project':state['revision']=project_snapshot(source.get('project_id',''),self.store)['revision']
        else:
            dates=starts(trigger['clock'],now)
            if not dates:raise ValueError('Eine zukünftige Startzeit wählen.')
            due=dates[0]
        if any(n['kind']=='save_note' for n in plan['nodes']):
            state['notes_root']=self.store.setting('knowledge/notebook','')
            if not state['notes_root']:raise ValueError('Zuerst einen Notizordner in Lumen Notes wählen.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT revision,archived FROM code_library WHERE id=?',(entry,)).fetchone()
            if not current or current['revision']!=item['revision'] or current['archived']:raise ValueError('Ablauf inzwischen geändert.')
            db.execute('INSERT OR REPLACE INTO code_block_triggers VALUES(?,?,?,?,?,?,?)',
                       (entry,digest(plan),1,json.dumps(state),due,'',now))

    def pause(self,entry):
        with self.store.connect() as db:db.execute('UPDATE code_block_triggers SET enabled=0 WHERE entry=?',(entry,))

    def poll(self,now=None):
        from code_blocks import parse
        from code_block_paths import config
        from code_blocks_run import Runs,digest
        now=time.time() if now is None else now;runs=Runs(self.collection);created=[]
        with self.store.connect() as db:
            entries=[r['entry'] for r in db.execute('SELECT entry FROM code_block_triggers WHERE enabled=1 ORDER BY checked LIMIT 20')]
        for entry in entries:
            try:
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE');row=self.get(entry,db)
                    if not row or not row['enabled']:continue
                    item=db.execute('SELECT archived,definition FROM code_library WHERE id=?',(entry,)).fetchone()
                    if not item or item['archived']:raise ValueError('Ablauf nicht mehr verfügbar.')
                    plan=parse(json.loads(item['definition'])['flow'])
                    if digest(plan)!=row['signature']:raise ValueError('Ablauf geändert. Erneut prüfen und aktivieren.')
                    state=json.loads(row['state']);source=config(plan['nodes'][0]);trigger=validate(source['trigger'],source['kind'])
                    if db.execute("SELECT 1 FROM code_block_runs WHERE entry=? AND status IN ('running','paused','waiting','error') LIMIT 1",(entry,)).fetchone():
                        db.execute('UPDATE code_block_triggers SET checked=? WHERE entry=?',(now,entry));continue
                    event=None;due=row['next_run']
                    if trigger['kind']=='clock' and now>=due:
                        event={'scheduled_at':due}
                        dates=starts(trigger['clock'],now);due=dates[0] if dates else 253402300799
                    elif trigger['kind']=='directory':
                        root,files=scan(trigger['path'])
                        if root!=state['root']:raise ValueError('Der beobachtete Ordner wurde ersetzt. Erneut auswählen.')
                        state['accepted']={k:v for k,v in state['accepted'].items() if k in files}
                        for name,stamp in sorted(files.items()):
                            if stamp!=state['accepted'].get(name) and stamp==state['observed'].get(name):
                                event=dict(path=str(Path(trigger['path'])/name),stamp=stamp,root=root);state['accepted'][name]=stamp;break
                        state['observed']=files
                    elif trigger['kind']=='project':
                        snapshot=project_snapshot(source['project_id'],self.store)
                        if snapshot['revision']!=state['revision']:event={'project':snapshot};state['revision']=snapshot['revision']
                    if event is not None:
                        event.update(background=True,notes_root=state.get('notes_root',''))
                        created.append(runs.create(entry,False,event=event,db=db)['id'])
                    db.execute('UPDATE code_block_triggers SET state=?,next_run=?,checked=?,error=? WHERE entry=?',
                               (json.dumps(state),due,now,'',entry))
            except (ValueError,OSError,KeyError) as error:
                with self.store.connect() as db:db.execute('UPDATE code_block_triggers SET enabled=0,error=?,checked=? WHERE entry=?',(str(error)[:2000],now,entry))
        return created
