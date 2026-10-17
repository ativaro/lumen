"""Durable manual block runs with revision fences and replay-safe direct actions."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from uuid import uuid4
from code_blocks import parse, encode, permissions


def digest(plan):return hashlib.sha256(encode(plan).encode()).hexdigest()


@contextmanager
def directory_fd(path):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('Bitte einen absoluten Pfad ohne .. wählen.')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        yield fd
    finally:os.close(fd)


def read_file(path,job):
    from tools_data import document_text
    path=Path(path)
    with directory_fd(path.parent) as folder:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=folder)
        with os.fdopen(fd,'rb') as source:
            info=os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>20*1024**2:raise ValueError('Nur reguläre Dateien bis 20 MiB lesen.')
            # Decode a bounded private snapshot; later source changes cannot redirect the decoder.
            with tempfile.TemporaryDirectory(prefix='lumen-block-read-') as temporary:
                snapshot=Path(temporary)/('source'+path.suffix.lower());total=0
                with snapshot.open('xb') as output:
                    while chunk:=source.read(1024*1024):
                        job.check();total+=len(chunk)
                        if total>20*1024**2:raise ValueError('Datei ist größer als 20 MiB.')
                        output.write(chunk)
                text=document_text(snapshot,job)
    return dict(text=text,source=str(path),filename=path.name)


def write_file(folder,name,text):
    raw=text.encode()
    with directory_fd(folder) as fd:
        try:
            existing=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        except FileNotFoundError:existing=None
        if existing is not None:
            with os.fdopen(existing,'rb') as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode) or source.read(len(raw)+1)!=raw:
                    raise ValueError('Am Ergebnisziel liegt bereits eine andere Datei. Sie bleibt erhalten.')
            return str(Path(folder)/name)
        temporary='.lumen-'+uuid4().hex
        try:
            output=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=fd)
            with os.fdopen(output,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.link(temporary,name,src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
            os.fsync(fd)
        finally:os.unlink(temporary,dir_fd=fd)
    return str(Path(folder)/name)


class Runs:
    def __init__(self,collection):
        self.collection=collection;self.store=collection.store
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS code_block_runs (
              id TEXT PRIMARY KEY,entry TEXT NOT NULL,plan TEXT NOT NULL,signature TEXT NOT NULL,
              testing INTEGER NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL)''')

    def get(self,identity,db=None):
        if db is None:
            with self.store.connect() as connection:return self.get(identity,connection)
        row=db.execute('SELECT * FROM code_block_runs WHERE id=?',(identity,)).fetchone()
        if row is None:raise ValueError('Durchlauf nicht gefunden.')
        result=dict(row);result['plan']=parse(result['plan']);result['data']=json.loads(result['data'])
        return result

    def latest(self,entry):
        with self.store.connect() as db:
            row=db.execute('SELECT id FROM code_block_runs WHERE entry=? ORDER BY updated DESC LIMIT 1',(entry,)).fetchone()
        return self.get(row['id']) if row else None

    def fence(self,run,db):
        row=db.execute('SELECT archived,definition FROM code_library WHERE id=?',(run['entry'],)).fetchone()
        if row is None or row['archived'] or digest(parse(json.loads(row['definition']).get('flow',''))) != run['signature']:
            raise ValueError('Ablauf geändert oder archiviert. Diesen Durchlauf nicht weiter ausführen; neuen Durchlauf starten.')

    def save(self,db,run):
        db.execute('UPDATE code_block_runs SET status=?,data=?,updated=? WHERE id=?',
                   (run['status'],json.dumps(run['data'],ensure_ascii=False),time.time(),run['id']))

    def create(self,entry,testing=True):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item=db.execute('SELECT * FROM code_library WHERE id=?',(entry,)).fetchone()
            if item is None or item['archived']:raise ValueError('Automation nicht verfügbar.')
            plan=parse(json.loads(item['definition'])['flow']);permissions(plan)
            identity=uuid4().hex
            notes_root=self.store.setting('knowledge/notebook','') if any(n['kind']=='save_note' for n in plan['nodes']) else ''
            if not testing and any(n['kind']=='save_note' for n in plan['nodes']) and not notes_root:raise ValueError('Lumen Notes zuerst öffnen und einen Notizordner wählen.')
            data=dict(notes_root=notes_root,cursor=0,steps=[dict(status='pending',attempts=0,input={},output={},error='') for _ in plan['nodes']])
            db.execute('INSERT INTO code_block_runs VALUES(?,?,?,?,?,?,?,?)',
                       (identity,entry,encode(plan),digest(plan),int(testing),'paused',json.dumps(data),time.time()))
        return self.get(identity)

    @contextmanager
    def lease(self,identity):
        fd=self.store.acquire('block-'+identity)
        try:yield
        finally:os.close(fd)

    def resume(self,identity):
        # Caller holds the process lease throughout execution, including model waits.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');run=self.get(identity,db);self.fence(run,db)
            if run['status'] in ('completed','cancelled'):raise ValueError('Dieser Durchlauf ist bereits beendet.')
            if run['status']=='waiting':raise ValueError('Bitte zuerst das Ergebnis bestätigen oder ablehnen.')
            cursor=run['data']['cursor'];step=run['data']['steps'][cursor]
            if step['status']=='running':step.update(status='pending',error='Nach Unterbrechung erneut begonnen.')
            run['status']='running';self.save(db,run)
        return self.get(identity)

    def control(self,identity,action):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');run=self.get(identity,db)
            if run['status'] in ('completed','cancelled'):return run
            if action=='approve':
                self.fence(run,db)
                if run['status']!='waiting':raise ValueError('Keine Bestätigung offen.')
                step=run['data']['steps'][run['data']['cursor']]
                step.update(status='completed',output={**step['input'],'approval':'Bestätigt'})
                run['data']['cursor']+=1;run['status']='completed' if run['data']['cursor']==len(run['plan']['nodes']) else 'paused'
            elif action in ('cancel','pause'):
                run['status']='cancelled' if action=='cancel' else 'paused'
                step=run['data']['steps'][run['data']['cursor']]
                if step['status'] in ('running','waiting'):step['status']=run['status']
            else:raise ValueError('Unbekannte Steuerung.')
            self.save(db,run)
        return self.get(identity)

    def advance(self,identity,job):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');run=self.get(identity,db);self.fence(run,db)
            if run['status']!='running':return None
            data=run['data'];cursor=data['cursor']
            if cursor==len(data['steps']):run['status']='completed';self.save(db,run);return None
            n=run['plan']['nodes'][cursor];step=data['steps'][cursor]
            if step['status']=='running':raise ValueError('Dieser Baustein läuft bereits.')
            previous=next((s['output'] for s in reversed(data['steps'][:cursor]) if s['status']=='completed'),{})
            step.update(status='running',attempts=step['attempts']+1,input=previous,output={},error='',ticket=uuid4().hex)
            token=step['ticket'];self.save(db,run)
        kind=n['kind']
        if kind=='ai':return dict(prompt=json.dumps(dict(instruction=n['config'],input=previous,format={'text':'Ergebnistext'}),ensure_ascii=False),attempt=token)
        if kind=='approval':
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE');run=self.get(identity,db);self.fence(run,db)
                if run['status']=='running':
                    run['status']='waiting';run['data']['steps'][cursor]['status']='waiting';self.save(db,run)
            return None
        try:
            if kind=='read_file':output=read_file(n['config'],job)
            else:
                # Fence, direct effect and checkpoint share the entry's write lock.
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE');run=self.get(identity,db);self.fence(run,db)
                    if run['status']!='running':return None
                    job.check();output=self.effect(run,n,previous,job)
                    self.finish(db,run,output,token);return None
            self.finish_external(identity,output,token)
        except Exception as error:self.fail(identity,str(error),token)
        return None

    def finish(self,db,run,output,attempt):
        step=run['data']['steps'][run['data']['cursor']]
        if run['status']!='running' or step['status']!='running' or step.get('ticket')!=attempt:return
        step.update(status='completed',output=output,error='');run['data']['cursor']+=1
        while run['data']['cursor']<len(run['data']['steps']) and run['data']['steps'][run['data']['cursor']]['status']=='skipped':run['data']['cursor']+=1
        if run['data']['cursor']==len(run['plan']['nodes']):run['status']='completed'
        self.save(db,run)

    def finish_external(self,identity,output,attempt):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');run=self.get(identity,db);self.fence(run,db)
            if run['data']['cursor']<len(run['data']['steps']):self.finish(db,run,output,attempt)

    def ai_done(self,identity,answer,attempt):
        from tools_data import parse_answer
        try:
            value=parse_answer(answer)
            if set(value)!={'text'} or not isinstance(value['text'],str) or not value['text'].strip() or len(value['text'])>120000:
                raise ValueError('Die KI-Antwort muss einen Ergebnistext bis 120.000 Zeichen enthalten.')
            run=self.get(identity);previous=run['data']['steps'][run['data']['cursor']]['input']
            self.finish_external(identity,{**previous,'text':value['text']},attempt)
        except Exception as error:self.fail(identity,str(error),attempt)

    def fail(self,identity,error,attempt=None):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');run=self.get(identity,db)
            if run['status'] not in ('running',):return
            step=run['data']['steps'][run['data']['cursor']]
            if attempt is not None and step.get('ticket')!=attempt:return
            step.update(status='error',error=error[:2000]);run['status']='error';self.save(db,run)

    def effect(self,run,n,previous,job):
        kind=n['kind'];token=run['id']+n['id'];text=previous.get('text','');output=dict(previous)
        if kind=='manual':return dict(text='',start='Manuell')
        if kind=='if_pdf':
            pdf=previous.get('filename','').lower().endswith('.pdf');output['branch']='Dann' if pdf else 'Sonst'
            if not pdf:
                cursor=run['data']['cursor']+1
                while cursor<len(run['plan']['nodes']) and run['plan']['nodes'][cursor]['kind']!='notify':
                    run['data']['steps'][cursor].update(status='skipped',error='Sonst-Pfad');cursor+=1
            return output
        if kind in ('save_file','save_note','create_task') and not text.strip():raise ValueError('Kein Ergebnis zum Speichern vorhanden.')
        title=n['config'].strip() or n['title']
        if run['testing'] and kind in ('save_file','save_note','create_task','notify'):
            folder=self.store.directory/'block-tests'/run['id'];folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            output['effect']=dict(test=True,path=write_file(folder,n['id']+'.json',json.dumps(dict(kind=kind,title=title,text=text),ensure_ascii=False)))
        elif kind=='save_file':output['effect']=dict(path=write_file(n['config'],'Lumen-'+run['id']+'-'+n['id'][:8]+'.md',text))
        elif kind in ('save_note','create_task'):
            if kind=='save_note' and self.store.setting('knowledge/notebook','')!=run['data']['notes_root']:
                raise ValueError('Der Notizordner wurde geändert. Neues Ziel in einem neuen Durchlauf freigeben.')
            from interop_data import Registry
            from interop_targets import apply
            url=Registry().register(dict(app='files',kind='record',id=token,title='Automation: '+n['title']))
            payload=dict(title=title[:300],text=text,paths=[],source_url=url)
            output['effect']=apply('wissen.import' if kind=='save_note' else 'inbox.task',payload,dict(token=token,mode='copy',title=title[:300]),job,store=self.store)
        elif kind=='notify':
            from lumen_notifications import publish
            output['effect']=dict(notification=publish('Lumen Code & Automation',token,n['title'],text[:2000]))
        return output
