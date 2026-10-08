"""Portable Markdown notebooks. Local drafts/history are private recovery data."""
from lumen_i18n import tr
from contextlib import contextmanager
import base64
import fcntl
import hashlib
import json
import io
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid
from urllib.parse import unquote,urlsplit
from content_search import folder_fd,STOP_WORDS
from tools_data import Library

MAX_NOTE=1024*1024
META=re.compile(r'^<!-- lumen: (\{[^\n]*\}) -->\n?')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    return value if type(value) in (int,float) and 0<value<253402214400 else 0


def timestamp_text(note):
    from datetime import datetime
    created=timestamp(note.get('created')) or timestamp(note.get('memory',{}).get('created'))
    modified=timestamp(note.get('modified')) or timestamp(note.get('memory',{}).get('updated'))
    def display(value):return datetime.fromtimestamp(value).strftime('%d.%m.%Y %H:%M') if value else ''
    first,last=display(created),display(modified)
    parts=[tr('Erstellt: {0}',first)] if first else []
    if last and last!=first:parts.append(tr('Geändert: {0}',last))
    return ' · '.join(parts)


def parse(path,raw):
    text=raw.decode('utf-8-sig');meta={};match=META.match(text)
    if match:
        try:
            candidate=json.loads(match[1])
            if isinstance(candidate,dict):meta=candidate;text=text[match.end():]
        except ValueError:pass
    try: note_id=str(uuid.UUID(str(meta.get('note_id',''))))
    except ValueError: note_id=''
    heading=re.search(r'^# (.+)$',text,re.M)
    title=heading[1].strip() if heading else Path(path).stem
    plain=re.sub(r'```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`','',text)
    tags=sorted(set(re.findall(r'(?<![\w/#])#([^\W\d][\w/-]*)',plain)))[:100]
    links=re.findall(r'\[\[([^\]\n]+)\]\]',plain)+re.findall(r'(?<!!)\[[^\]\n]*\]\(([^)\n]+)\)',plain)
    return dict(id=path,path=path,note_id=note_id,title=title[:300],text=text,source=str(meta.get('source',''))[:2000],legacy=str(meta.get('legacy',''))[:200],created=timestamp(meta.get('created')),tags=tags,links=links,hash=digest(raw),raw_size=len(raw))


def encode(text,source='',legacy='',created=0,note_id=''):
    meta=dict(source=source,legacy=legacy)
    if note_id:meta['note_id']=str(uuid.UUID(note_id))
    if timestamp(created):meta['created']=created
    prefix='<!-- lumen: '+json.dumps(meta,ensure_ascii=False)+' -->\n' if source or legacy or timestamp(created) or note_id else ''
    raw=(prefix+text).encode()
    if len(raw)>MAX_NOTE:raise ValueError(tr('Notiz größer als 1 MiB. Bitte aufteilen.'))
    return raw


def resolve_link(origin,target,notes):
    target=unquote(target.split('|',1)[0].split('#',1)[0].strip())
    if not target:return origin
    if urlsplit(target).scheme or target.startswith(('/', '\\')):return None
    if not target.lower().endswith('.md'):target+='.md'
    local=os.path.normpath(str(Path(origin).parent/target))
    if local=='..' or local.startswith('../'):return None
    for candidate in (local,os.path.normpath(target)):
        if candidate in notes:return candidate
    matches=[p for p,n in notes.items() if Path(p).stem.casefold()==Path(target).stem.casefold() or n['title'].casefold()==target[:-3].casefold()]
    return matches[0] if len(matches)==1 else None


def search(notes,query,limit=60):
    terms=[w for w in re.findall(r'\w+',query.casefold()) if w not in STOP_WORDS and len(w)>1][:12]
    ranked=[]
    for note in notes:
        hay=(note['title']+' '+note['text']+' '+note['source']).casefold()
        score=sum((4 if t in note['title'].casefold() else 1) for t in terms if t in hay)
        if not terms or score:ranked.append((score,note))
    return [n for _,n in sorted(ranked,key=lambda p:(-p[0],p[1]['title'].casefold()))[:limit]]


def excerpt(text,query,limit=3000):
    terms=[w for w in re.findall(r'\w+',query.casefold()) if w not in STOP_WORDS and len(w)>1][:12]
    positions=[text.casefold().find(t) for t in terms if t in text.casefold()]
    start=max(0,min(positions)-limit//4) if positions else 0
    return ('…\n' if start else '')+text[start:start+limit]+('\n…' if start+limit<len(text) else '')


def directory_identity(fd):
    """Filesystem identity survives a remount; st_dev is only a runtime number."""
    st=os.fstat(fd)
    fsid=getattr(os.fstatvfs(fd),'f_fsid',0)
    return ['fsid:'+str(fsid),st.st_ino] if fsid else [st.st_dev,st.st_ino]


def root_identity(root):
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:return directory_identity(fd)
    finally:os.close(fd)


class Notebook:
    def __init__(self,store,root=None,create=False,identity=None):
        self.store=store
        chosen=root or store.setting('knowledge/notebook','')
        if not chosen:raise ValueError(tr('Lumen Wissen zuerst öffnen und einen Notizordner wählen.'))
        self.root=Path(chosen).expanduser()
        if create:self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root=self.root.resolve(strict=True)
        self.identity=identity or (store.setting('knowledge/identity') if str(self.root)==store.setting('knowledge/notebook') else None) or root_identity(self.root)
        self.history=Library('wissen-history',store.directory)

    def context(self,paths,query):
        if not 1<=len(paths)<=8:raise ValueError(tr('Eine bis acht Quellen auswählen.'))
        return [dict(note,text=excerpt(note['text'],query)) for note in (self.read(p) for p in dict.fromkeys(paths))]

    @contextmanager
    def directory(self,relative='.'):
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            st=os.fstat(fd)
            actual=directory_identity(fd) if isinstance(self.identity[0],str) else [st.st_dev,st.st_ino]
            if actual!=self.identity:raise ValueError(tr('Der Notizordner wurde ersetzt oder getrennt. Erneut auswählen.'))
            part=Path(relative)
            if part.is_absolute() or '..' in part.parts:raise ValueError(tr('Pfad außerhalb des Notizordners.'))
            child=folder_fd(fd,part)
            try:yield child
            finally:os.close(child)
        finally:os.close(fd)

    @contextmanager
    def lock(self,name='wissen.lock'):
        fd=os.open(self.store.directory/name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:os.close(fd)

    def relative(self,path):
        path=Path(path)
        if path.is_absolute() or '..' in path.parts or not path.parts or any(p.startswith('.') for p in path.parts) or path.suffix.lower()!='.md':raise ValueError(tr('Bitte eine Markdown-Notiz innerhalb des gewählten Ordners wählen.'))
        return path

    def _read(self,path):
        path=self.relative(path)
        with self.directory(path.parent) as parent:
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError(tr('Keine reguläre Notizdatei.'))
                with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(MAX_NOTE+1)
                if len(raw)>MAX_NOTE:raise ValueError(tr('Notiz größer als 1 MiB.'))
                return raw,os.fstat(fd).st_mtime
            finally:os.close(fd)

    def raw(self,path):return self._read(path)[0]

    def read(self,path):
        raw,modified=self._read(path)
        return dict(parse(str(path),raw),modified=modified)

    def image(self,path):
        path=Path(path)
        if path.is_absolute() or '..' in path.parts or any(p.startswith('.') for p in path.parts) or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.gif'):raise ValueError(tr('Kein lokales Notizbild.'))
        with self.directory(path.parent) as parent:
            fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            with os.fdopen(fd,'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError(tr('Kein reguläres Bild.'))
                raw=stream.read(16*1024**2+1)
        if len(raw)>16*1024**2:raise ValueError(tr('Bild größer als 16 MiB.'))
        return raw

    def add_image(self,path):
        from PIL import Image,ImageOps
        source=Path(path)
        if source.stat().st_size>20*1024**2:raise ValueError(tr('Bild größer als 20 MiB.'))
        with Image.open(source) as image:
            if image.width*image.height>36_000_000:raise ValueError(tr('Bild größer als 36 Megapixel.'))
            image=ImageOps.exif_transpose(image);image.thumbnail((2400,2400));image=image.convert('RGBA')
            with self.directory() as root:
                try:os.mkdir('attachments',0o700,dir_fd=root)
                except FileExistsError:pass
            name=uuid.uuid4().hex+'.png'
            with self.directory('attachments') as parent:
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=parent)
                with os.fdopen(fd,'wb') as stream:image.save(stream,format='PNG');stream.flush();os.fsync(stream.fileno())
            return 'attachments/'+name

    def preview(self,path,text):
        from PIL import Image,ImageOps
        images={};total=0
        for target in re.findall(r'!\[[^\]\n]*\]\(([^)\n]+)\)',text)[:16]:
            target=unquote(target)
            if urlsplit(target).scheme or target.startswith('/'):continue
            relative=os.path.normpath(str(Path(path).parent/target))
            try:
                raw=self.image(relative)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width*image.height>36_000_000:continue
                    image=ImageOps.exif_transpose(image);image.thumbnail((1600,1600));output=io.BytesIO();image.convert('RGBA').save(output,format='PNG')
                    encoded=base64.b64encode(output.getvalue()).decode();total+=len(encoded)
                    if total>16*1024**2:break
                    images[relative]=encoded
            except (OSError,ValueError):continue
        return images

    def scan(self):
        notes=[];folders=[];queue=[Path('.')];count=size=errors=0
        while queue and count<10000 and size<32*1024**2 and len(notes)<5000:
            relative=queue.pop()
            with self.directory(relative) as parent:
                for entry in os.scandir(parent):
                    count+=1
                    if count>10000 or size>=32*1024**2 or len(notes)>=5000:break
                    if entry.name.startswith('.') or entry.is_symlink():continue
                    path=relative/entry.name
                    if entry.is_dir(follow_symlinks=False):
                        queue.append(path)
                        if path.parts[0]!='attachments':folders.append(str(path))
                    elif entry.name.lower().endswith('.md') and entry.is_file(follow_symlinks=False):
                        try:
                            note=self.read(path);notes.append(note);size+=note['raw_size']
                        except (OSError,ValueError,UnicodeError):errors+=1
        return dict(notes=notes,folders=sorted(folders),errors=errors,limited=bool(queue) or count>=10000 or size>=32*1024**2 or len(notes)>=5000,root=str(self.root),identity=self.identity)

    def backup(self,path,raw):
        asset=uuid.uuid4().hex+'.md';target=self.history.asset(asset)
        with target.open('xb') as stream:target.chmod(0o600);stream.write(raw)
        return self.history.create(Path(path).name,root=str(self.root),path=str(path),asset=asset,created=time.time())

    def write(self,path,text,expected,source=None,legacy=None,created=None,note_id=None):
        path=self.relative(path)
        with self.lock():
            try:before,modified=self._read(path)
            except FileNotFoundError:before=None;modified=0
            if (digest(before) if before is not None else '')!=expected:raise ValueError(tr('CONFLICT: Die Datei wurde außerhalb dieses Fensters geändert. Entwurf bleibt erhalten.'))
            old=parse(str(path),before) if before is not None else {}
            if before is None:created_at=time.time() if created is None else created
            else:created_at=old.get('created',0) or timestamp(created)
            raw=encode(text,old.get('source','') if source is None else source,old.get('legacy','') if legacy is None else legacy,created_at,old.get('note_id','') if note_id is None else note_id)
            if before==raw:return dict(parse(str(path),raw),modified=modified)
            if before is not None:self.backup(path,before)
            with self.directory(path.parent) as parent:
                temporary='.lumen-'+uuid.uuid4().hex
                fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=parent)
                try:
                    with os.fdopen(fd,'wb') as stream:
                        stream.write(raw);stream.flush();os.fsync(stream.fileno());modified=os.fstat(stream.fileno()).st_mtime
                    try:latest=self.raw(path)
                    except FileNotFoundError:latest=None
                    if latest!=before:raise ValueError(tr('CONFLICT: Die Datei wurde während des Speicherns geändert.'))
                    os.replace(temporary,path.name,src_dir_fd=parent,dst_dir_fd=parent);os.fsync(parent)
                finally:
                    try:os.unlink(temporary,dir_fd=parent)
                    except FileNotFoundError:pass
            return dict(parse(str(path),raw),modified=modified)

    def rename_collection(self,source,target):
        source,target=Path(source),Path(target)
        for value in (source,target):
            if value.is_absolute() or not value.parts or '..' in value.parts or any(p.startswith('.') for p in value.parts):raise ValueError(tr('Ungültiger Sammlungsname.'))
        if target.is_relative_to(source):raise ValueError(tr('Eine Sammlung kann nicht in sich selbst verschoben werden.'))
        from drive_local import move
        with self.lock():
            with self.directory(source):pass
            with self.directory() as fd:
                st=os.fstat(fd)
                move(dict(path=str(self.root),identity=[st.st_dev,st.st_ino]),str(source),str(target))
        return str(target)

    def create_collection(self,name):
        name=name.strip()
        if not name or name.startswith('.') or re.search(r'[/\\\x00-\x1f\x7f]',name) or len(name.encode())>200 or name=='attachments':
            raise ValueError(tr('Bitte einen Sammlungsnamen ohne Schrägstriche eingeben (nicht versteckt oder „attachments“).'))
        with self.lock(),self.directory() as parent:
            os.mkdir(name,mode=0o700,dir_fd=parent);os.fsync(parent)
        return name

    def create(self,title,text='',source='',legacy='',folder='.',note_id=''):
        title=' '.join(title.split()).strip()[:200]
        if not title:raise ValueError(tr('Bitte einen Titel eingeben.'))
        stem=re.sub(r'[^\w .-]','-',title).strip('. ')[:100] or 'Notiz'
        path=str(Path(folder)/(stem+'-'+uuid.uuid4().hex[:8]+'.md'))
        return self.write(path,'# '+title+'\n\n'+text,'',source,legacy,note_id=note_id)

    def remove(self,path,expected):
        with self.lock():
            raw=self.raw(path)
            if digest(raw)!=expected:raise ValueError(tr('CONFLICT: Die Notiz wurde geändert. Neu laden, bevor sie entfernt wird.'))
            key=self.backup(path,raw);path=self.relative(path)
            with self.directory(path.parent) as parent:os.unlink(path.name,dir_fd=parent)
            return key

    def versions(self,path=None):
        return [r for r in self.history.all() if r['root']==str(self.root) and (path is None or r['path']==path)]

    def restore(self,key,expected):
        row=self.history.get(key)
        if row['root']!=str(self.root):raise ValueError(tr('Die Sicherung gehört zu einem anderen Ordner.'))
        note=parse(row['path'],self.history.asset(row['asset']).read_bytes())
        return self.write(row['path'],note['text'],expected,note['source'],note['legacy'],created=note['created'],note_id=note.get('note_id') or None)

    def capture(self,title,text,source='',memory=None):
        if not memory:return self.create(title,text,source)['path']
        memory=self.memory_path(memory)
        note=self.read(memory)
        return self.write(memory,'# '+title.strip()+'\n\n'+text,note['hash'],source)['path']

    def memory_path(self,memory):
        if memory.endswith('.md'):return memory
        imported=self.store.setting('knowledge/imports',{}).get(memory,{})
        if imported.get('root')!=str(self.root):raise ValueError(tr('Die alte Erinnerung zuerst in Lumen Wissen öffnen.'))
        return imported['path']

    def migrate(self):
        with self.lock('wissen-import.lock'):return self.import_legacy()

    def import_legacy(self):
        imported=self.store.setting('knowledge/imports',{});changed=0
        existing=None
        for row in self.store.rows('SELECT * FROM memories ORDER BY updated'):
            version=digest(json.dumps(row,sort_keys=True).encode());old=imported.get(row['id'],{})
            if old.get('version')==version:continue
            # Never overwrite a Markdown edit with a late legacy-window update.
            token=row['id']+'@'+version
            if existing is None:existing={n['legacy']:n for n in self.scan()['notes'] if n['legacy']}
            note=existing.get(token) or self.create(row['title'],row['text'],row['source'],token)
            imported[row['id']]=dict(version=version,path=note['path'],root=str(self.root));self.store.set_setting('knowledge/imports',imported);changed+=1
        return changed


def activate(store,root=None):
    chosen=root or store.setting('knowledge/notebook','') or str(store.directory/'wissen')
    identity=None
    if root:
        identity=root_identity(Path(root).expanduser().resolve(strict=True))
    book=Notebook(store,chosen,create=not root and not store.setting('knowledge/notebook',''),identity=identity)
    book.migrate();store.set_setting('knowledge/notebook',str(book.root));store.set_setting('knowledge/identity',book.identity);return str(book.root)


def draft(store,root,path,text=None,expected=''):
    directory=store.directory/'wissen-drafts';directory.mkdir(mode=0o700,exist_ok=True)
    name=digest((str(root)+'\0'+path).encode());target=directory/(name+'.json')
    if text is None:return json.loads(target.read_text()) if target.exists() else None
    data=dict(root=str(root),path=path,text=text,expected=expected)
    temporary=directory/(name+'.tmp');fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(data,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,target);return data


def clear_draft(store,root,path):
    (store.directory/'wissen-drafts'/(digest((str(root)+'\0'+path).encode())+'.json')).unlink(missing_ok=True)


def worker(job,store,action,root=None,**values):
    request=dict(store=str(store.directory),root=root,action=action,**values)
    return json.loads(job.command([sys.executable,str(Path(__file__))],data=json.dumps(request).encode(),timeout=60,max_output=40*1024**2))


def main():
    from lumen_store import Store
    request=json.load(sys.stdin);store=Store(request.pop('store'));action=request.pop('action');root=request.pop('root')
    if action=='activate':result=activate(store,root)
    elif action in ('save_memory','memories','delete_memory'):result=getattr(store,action)(**request)
    else:
        book=Notebook(store,root,identity=request.pop('identity',None))
        if action=='scan':book.migrate();result=book.scan()
        elif action in ('sync_info','sync_config','sync'):
            import wissen_sync
            result=getattr(wissen_sync,action)(book,**request)
            if action=='sync':result['scan']=book.scan()
        elif action in ('read','write','create','create_collection','rename_collection','remove','versions','restore','capture','add_image','preview','context'):result=getattr(book,action)(**request)
        else:raise ValueError(tr('Unbekannte Notizaktion.'))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
