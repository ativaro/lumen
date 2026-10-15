"""Explicitly enabled, content-addressed notebook attachments; no path following."""
import json
import os
import posixpath
import stat
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import unquote,urlsplit,quote
import lumen_connect
from wissen_data import digest
from lumen_i18n import tr

LIMIT=16*1024**2


def transfer(config,checksum,target=None,content=None):
    from sync_migration import asset_path
    path=asset_path('/bridge/notes/assets/'+checksum,{} if content is None and (target or {}).get('legacy') else target or {})
    req=urllib.request.Request(config['server']+path,data=content,headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/octet-stream'})
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=lumen_connect.tls_context(config)),lumen_connect.NoRedirect())
    with opener.open(req,timeout=20) as response:
        raw=response.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError(tr('Notizanhang zu groß.'))
    if content is not None:return json.loads(raw)
    if digest(raw)!=checksum:raise ValueError(tr('Die Anhang-Prüfsumme stimmt nicht.'))
    return raw


def read(book,path):
    path=Path(path)
    if path.is_absolute() or not path.parts or path.parts[0]!='attachments' or any(p.startswith('.') for p in path.parts):raise ValueError('Invalid attachment path')
    with book.directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Not a regular attachment')
            raw=stream.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError(tr('Notizanhang zu groß.'))
    return raw


def install(book,path,raw):
    from wissen_sync import ensure_folder
    path=Path(path);ensure_folder(book,path.parent)
    try:
        if read(book,path)!=raw:raise ValueError(tr('Ein lokaler Anhang wurde verändert. Er bleibt erhalten.'))
        return
    except FileNotFoundError:pass
    with book.directory(path.parent) as parent:
        # Write/fsync before linking without overwrite; interruption leaves no partial public file.
        name='.sync-'+os.urandom(12).hex()
        fd=os.open(name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:os.link(name,path.name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
            except FileExistsError:
                if read(book,path)!=raw:raise ValueError(tr('Ein lokaler Anhang wurde verändert. Er bleibt erhalten.'))
            os.fsync(parent)
        finally:os.unlink(name,dir_fd=parent)


def prepare(book,note,config,target,uploaded,remember):
    import re
    text=note['text'];items=[];total=0
    for match in list(re.finditer(r'!?\[[^\]\n]*\]\(([^)\n]+)\)',text)):
        link=unquote(match[1])
        if urlsplit(link).scheme or link.startswith('/'):continue
        path=posixpath.normpath(str(Path(note['path']).parent/link))
        if not path.startswith('attachments/'):continue
        try:
            raw=read(book,path)
        except FileNotFoundError:
            # A text-only client already has canonical links when attachments
            # are enabled later. Retrieve those exact bytes before publishing.
            checksum=Path(path).stem
            if not re.fullmatch('[0-9a-f]{64}',checksum) or len(Path(path).parts)!=2:raise
            raw=transfer(config,checksum,target);install(book,path,raw)
        total+=len(raw)
        if len(items)>=16 or total>64*1024**2:raise ValueError(tr('Zu viele Anhänge für eine Notiz.'))
        checksum=digest(raw);suffix=Path(path).suffix.lower()
        if len(suffix)>12 or not suffix.isascii():suffix='.bin'
        canonical='attachments/'+checksum+suffix
        install(book,canonical,raw)
        receipt=json.dumps([target,checksum],sort_keys=True)
        if receipt not in uploaded:
            present=False
            if target.get('note'):
                try:
                    transfer(config,checksum,target)
                    present=True
                except HTTPError as error:
                    if error.code != 404:raise
            if not present:transfer(config,checksum,target,raw)
            uploaded.add(receipt);remember(uploaded)
        replacement=quote(posixpath.relpath(canonical,str(Path(note['path']).parent)))
        text=text.replace('('+match[1]+')','('+replacement+')')
        item=dict(path=canonical,sha256=checksum)
        if item not in items:items.append(item)
    if text!=note['text']:note=book.write(note['path'],text,note['hash'])
    return note,items


def receive(book,items,config,target):
    import re
    total=0
    for item in items:
        path=Path(item['path']);checksum=item['sha256']
        if not re.fullmatch('[0-9a-f]{64}',checksum) or path.is_absolute() or len(path.parts)!=2 or path.parts[0]!='attachments' or path.stem!=checksum:raise ValueError('Invalid attachment manifest')
        try:
            raw=read(book,path)
            if digest(raw)!=checksum:raise ValueError(tr('Ein lokaler Anhang wurde verändert. Er bleibt erhalten.'))
        except FileNotFoundError:
            raw=transfer(config,checksum,target);install(book,path,raw)
        total+=len(raw)
        if total>64*1024**2:raise ValueError(tr('Zu viele Anhänge für eine Notiz.'))
