"""Local object references and reviewed, replay-safe app handoffs."""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit
from lumen_i18n import tr
from tools_data import Library

APPS = frozenset(('files','wissen','reader','inbox','meetings','household','workbench','radio','vault','sound','translate'))
KINDS = frozenset(('record','note','message','task','event','file','draft','collection'))
TOKEN = re.compile(r'[a-f0-9]{32}\Z')


def _text(value, limit=4096):
    if not isinstance(value,str) or len(value)>limit or '\0' in value:
        raise ValueError(tr('Ungültiger Übergabetext.'))
    return value


def validate_ref(ref):
    if not isinstance(ref,dict) or set(ref)-{'app','kind','id','title','path','position','locator'}:
        raise ValueError(tr('Ungültiger Lumen-Verweis.'))
    value=dict(ref)
    if value.get('app') not in APPS or value.get('kind','record') not in KINDS:
        raise ValueError(tr('Unbekannte Lumen-Anwendung.'))
    value.setdefault('kind','record')
    for key in ('id','title'):_text(value.get(key,''))
    if not value.get('id'):raise ValueError(tr('Dem Verweis fehlt eine Kennung.'))
    if value.get('path'):
        _text(value['path'])
        if not Path(value['path']).is_absolute():raise ValueError(tr('Ein absoluter Dateipfad ist erforderlich.'))
    locator=value.get('locator',{})
    if not isinstance(locator,dict) or set(locator)-{'root','account','folder','validity','uid','area'}:
        raise ValueError(tr('Ungültige Herkunftsangabe.'))
    for v in locator.values():_text(v)
    position=value.get('position',{})
    if not isinstance(position,dict) or set(position)-{'page','time','note','part','start','end','engine'}:
        raise ValueError(tr('Ungültige Fundstelle.'))
    for key,v in position.items():
        if key in ('page','time','start','end'):
            if type(v) is not int or not 0<=v<=100000000:raise ValueError(tr('Ungültige Fundstelle.'))
        else:_text(v,512)
    return json.loads(json.dumps(value))


def validate_payload(payload):
    if not isinstance(payload,dict) or set(payload)-{'title','text','paths','source','source_url','url','items'}:
        raise ValueError(tr('Ungültige Übergabe.'))
    _text(payload.get('title',''),1000);_text(payload.get('text',''),120000)
    paths=payload.get('paths',[])
    if not isinstance(paths,list) or len(paths)>100:raise ValueError(tr('Höchstens 100 Dateien gleichzeitig übergeben.'))
    for path in paths:
        _text(path)
        if not Path(path).is_absolute():raise ValueError(tr('Ein absoluter Dateipfad ist erforderlich.'))
    if payload.get('source'):validate_ref(payload['source'])
    if payload.get('source_url'):_text(payload['source_url'])
    if payload.get('url'):
        from tools_data import web_url
        web_url(payload['url'])
    items=payload.get('items',[])
    if not isinstance(items,list) or len(items)>1000 or any(not isinstance(x,dict) for x in items):raise ValueError(tr('Ungültige Übergabeauswahl.'))
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False)
    if len(encoded.encode())>512*1024:raise ValueError(tr('Übergabe zu groß. Bitte eine kleinere Auswahl treffen.'))
    return json.loads(encoded)


def _parts(url):
    p=urlsplit(_text(url))
    if p.scheme!='lumen' or p.netloc!='object' or p.fragment or not TOKEN.fullmatch(p.path.removeprefix('/')):
        raise ValueError(tr('Ungültiger Lumen-Verweis.'))
    values=parse_qs(p.query,keep_blank_values=True,strict_parsing=True)
    if set(values)-{'page','time','note','part','start','end','engine'} or any(len(v)!=1 for v in values.values()):
        raise ValueError(tr('Ungültige Fundstelle.'))
    position={k:int(v[0]) if k in ('page','time','start','end') else v[0] for k,v in values.items()}
    validate_ref(dict(app='files',id='position',position=position))
    return p.path[1:],position


def base_url(url):
    return 'lumen://object/'+_parts(url)[0]


def _identity(ref):
    # UI areas and positions describe a view, not a different underlying object.
    locator={key:value for key,value in ref.get('locator',{}).items() if key!='area' and value}
    value=dict(app=ref['app'],kind=ref.get('kind','record'),id=ref['id'],locator=locator)
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class Registry:
    def __init__(self,root=None):
        self.library=Library('interop',root)
        with self.library.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS links(source TEXT, target TEXT, relation TEXT, created REAL, UNIQUE(source,target,relation));
            CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY, target TEXT, action TEXT, payload TEXT, state TEXT, result TEXT, error TEXT, created REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS tags(object TEXT, tag TEXT, UNIQUE(object,tag));
            CREATE TABLE IF NOT EXISTS search_text(object TEXT PRIMARY KEY, text TEXT NOT NULL);
            ''')
            if 'choice' not in {row[1] for row in db.execute('PRAGMA table_info(handoffs)')}:
                db.execute("ALTER TABLE handoffs ADD COLUMN choice TEXT NOT NULL DEFAULT '{}'")

    def register(self,ref):
        ref=validate_ref(ref);position=ref.pop('position',{})
        identity=_identity(ref)
        with self.library.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id FROM objects WHERE identity=?',(identity,)).fetchone()
            if not row and ref.get('path'):
                row=db.execute("SELECT id FROM objects WHERE json_extract(data,'$.app')=? AND json_extract(data,'$.kind')=? AND json_extract(data,'$.path')=?",(ref['app'],ref['kind'],ref['path'])).fetchone()
            key=row['id'] if row else uuid.uuid4().hex
            db.execute('INSERT INTO objects VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET identity=excluded.identity,data=excluded.data,updated=excluded.updated',(key,identity,json.dumps(ref),time.time()))
        return 'lumen://object/'+key+('?' + urlencode(position) if position else '')

    def resolve(self,url):
        key,position=_parts(url)
        with self.library.connect() as db:row=db.execute('SELECT data FROM objects WHERE id=?',(key,)).fetchone()
        if row is None:raise ValueError(tr('Dieser Lumen-Verweis ist hier nicht bekannt.'))
        value=validate_ref(json.loads(row['data']))
        if position:value['position']=position
        return value

    def link(self,source,target,relation='reference'):
        self.resolve(source);self.resolve(target);_text(relation,64)
        with self.library.connect() as db:db.execute('INSERT OR IGNORE INTO links VALUES (?,?,?,?)',(source,target,relation,time.time()))

    def related(self,url):
        base=base_url(url);result=[]
        with self.library.connect() as db:
            rows=db.execute('SELECT * FROM links WHERE source=? OR source LIKE ? OR target=? OR target LIKE ? ORDER BY created DESC LIMIT 200',(base,base+'?%',base,base+'?%')).fetchall()
        for row in rows:
            outgoing=base_url(row['source'])==base
            target=row['target'] if outgoing else row['source']
            try:result.append(dict(self.resolve(target),url=target,relation=row['relation'],direction='out' if outgoing else 'in'))
            except ValueError:continue
        return result

    def set_tags(self,url,tags):
        key,_=_parts(url);self.resolve(url)
        if not isinstance(tags,list) or len(tags)>50:raise ValueError(tr('Höchstens 50 Tags verwenden.'))
        tags=list(dict.fromkeys(_text(t,80).strip().lstrip('#') for t in tags))
        with self.library.connect() as db:
            db.execute('DELETE FROM tags WHERE object=?',(key,))
            db.executemany('INSERT INTO tags VALUES (?,?)',[(key,t) for t in tags if t])

    def tags(self,url):
        key,_=_parts(url)
        with self.library.connect() as db:return [r[0] for r in db.execute('SELECT tag FROM tags WHERE object=? ORDER BY tag',(key,))]

    def index_text(self,url,text):
        key,_=_parts(url);self.resolve(url);_text(text,120000)
        with self.library.connect() as db:
            db.execute('INSERT INTO search_text VALUES (?,?) ON CONFLICT(object) DO UPDATE SET text=excluded.text',(key,text))

    def search(self,query,limit=60):
        _text(query,1000);limit=max(1,min(int(limit),200))
        with self.library.connect() as db:
            if query.startswith('#'):
                rows=db.execute('SELECT o.* FROM objects o JOIN tags t ON o.id=t.object WHERE lower(t.tag)=lower(?) ORDER BY o.updated DESC LIMIT ?',(query[1:],limit)).fetchall()
            else:
                needle='%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                rows=db.execute("SELECT o.* FROM objects o LEFT JOIN search_text t ON t.object=o.id WHERE (o.data LIKE ? ESCAPE '\\' OR t.text LIKE ? ESCAPE '\\') ORDER BY o.updated DESC LIMIT ?",(needle,needle,limit)).fetchall()
        return [dict(json.loads(r['data']),url='lumen://object/'+r['id']) for r in rows]

    def relocate(self,old,new):
        old,new=Path(old),Path(new)
        if not old.is_absolute() or not new.is_absolute():raise ValueError(tr('Ein absoluter Dateipfad ist erforderlich.'))
        with self.library.connect() as db:
            for row in db.execute('SELECT id,data FROM objects').fetchall():
                ref=json.loads(row['data']);path=ref.get('path','')
                if path and Path(path).is_relative_to(old):
                    ref['path']=str(new/Path(path).relative_to(old))
                    if ref['kind']=='file':ref['id']=ref['path']
                    if ref.get('locator',{}).get('root'):
                        book=Path(ref['locator']['root'])
                        if book.is_relative_to(old):ref['locator']['root']=str(new/book.relative_to(old))
                        if ref['kind']=='note':ref['id']=str(Path(ref['path']).relative_to(ref['locator']['root']))
                    identity=_identity(ref)
                    db.execute('UPDATE objects SET identity=?,data=?,updated=? WHERE id=?',(identity,json.dumps(ref),time.time(),row['id']))

    def enqueue(self,target,action,payload):
        if target not in APPS or not re.fullmatch(r'[a-z]+\.[a-z_-]+',action):raise ValueError(tr('Unbekanntes Übergabeziel.'))
        payload=validate_payload(payload)
        if payload.get('source_url'):self.resolve(payload['source_url'])
        key=uuid.uuid4().hex;now=time.time()
        with self.library.connect() as db:db.execute('INSERT INTO handoffs(id,target,action,payload,state,result,error,created,updated) VALUES (?,?,?,?,?,?,?,?,?)',(key,target,action,json.dumps(payload),'pending','','',now,now))
        return key

    def request(self,token):
        if not isinstance(token,str) or not TOKEN.fullmatch(token):raise ValueError(tr('Ungültige Übergabekennung.'))
        with self.library.connect() as db:row=db.execute('SELECT * FROM handoffs WHERE id=?',(token,)).fetchone()
        if row is None:raise ValueError(tr('Übergabe nicht gefunden.'))
        value=dict(row);value['payload']=validate_payload(json.loads(value['payload']));value['choice']=json.loads(value['choice']);return value

    def save_choice(self,token,choice):
        self.request(token)
        value=json.dumps(choice,allow_nan=False)
        if len(value)>8192:raise ValueError(tr('Übergabeauswahl zu groß.'))
        with self.library.connect() as db:
            db.execute("UPDATE handoffs SET choice=? WHERE id=? AND state='pending'",(value,token))

    def recover(self,target):
        if target not in APPS:raise ValueError(tr('Unbekannte Lumen-Anwendung.'))
        with self.library.connect() as db:
            return db.execute("UPDATE handoffs SET state='pending',error=?,updated=? WHERE target=? AND state='applying'",(tr('Nach unterbrochener Übernahme erneut prüfen.'),time.time(),target)).rowcount

    def claim(self,token,target):
        self.request(token)
        with self.library.connect() as db:
            result=db.execute("UPDATE handoffs SET state='applying',error='',updated=? WHERE id=? AND target=? AND state='pending'",(time.time(),token,target))
            if not result.rowcount:raise ValueError(tr('Diese Übergabe wurde bereits übernommen oder wird gerade bearbeitet.'))
        return self.request(token)

    def release(self,token,error=''):
        _text(error,4000)
        with self.library.connect() as db:db.execute("UPDATE handoffs SET state='pending',error=?,updated=? WHERE id=? AND state='applying'",(error,time.time(),token))

    def finish(self,token,result):
        request=self.request(token);self.resolve(result)
        source=request['payload'].get('source_url')
        if source:self.resolve(source)
        with self.library.connect() as db:
            changed=db.execute("UPDATE handoffs SET state='done',result=?,error='',updated=? WHERE id=? AND state='applying'",(result,time.time(),token))
            if not changed.rowcount:raise ValueError(tr('Übergabe ist nicht zur Übernahme bereit.'))
            if source:db.execute('INSERT OR IGNORE INTO links VALUES (?,?,?,?)',(source,result,'handoff',time.time()))

    def history(self,limit=100):
        with self.library.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,target,action,state,result,error,created,updated FROM handoffs ORDER BY created DESC LIMIT ?',(max(1,min(limit,200)),))]

    def mark_undone(self,token):
        with self.library.connect() as db:
            changed=db.execute("UPDATE handoffs SET state='undone',updated=? WHERE id=? AND state IN ('done','undone')",(time.time(),token))
            if not changed.rowcount:raise ValueError(tr('Diese Übernahme kann noch nicht rückgängig gemacht werden.'))
