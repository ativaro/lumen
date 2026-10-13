"""Read only the entry labels deliberately published by the native Vault UI."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


def _read(path, limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_nlink!=1:
            raise ValueError('Unsafe Vault catalogue file.')
        data=stream.read(limit+1)
        if len(data)>limit: raise ValueError('Vault catalogue file too large.')
        return data


def entries(query='',offset=0,*,root=None):
    if not isinstance(query,str) or len(query)>200 or type(offset) is not int or not 0<=offset<=10000:
        raise ValueError('Invalid catalogue query.')
    root=Path(root) if root is not None else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'lumen-vault-lab'
    try: data=json.loads(_read(root/'assistant-catalogue.json',8*1024**2))
    except FileNotFoundError:
        return dict(enabled=False,entries=[],requires_confirmation=True,secrets_available=False,
                    instruction='Open Lumen Vault, unlock it to refresh the visible entries.')
    if not isinstance(data,dict) or set(data)!={'version','sha256','updated','entries'} or data['version']!=1 or not re.fullmatch('[0-9a-f]{64}',str(data['sha256'])) or not isinstance(data['entries'],list) or len(data['entries'])>10000:
        raise ValueError('Invalid Vault catalogue.')
    if not isinstance(data['updated'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',data['updated']):
        raise ValueError('Invalid Vault catalogue timestamp.')
    rows=[]
    for entry in data['entries']:
        if not isinstance(entry,dict) or set(entry)!={'id','title','kind','origin'} or any(not isinstance(v,str) for v in entry.values()):
            raise ValueError('Invalid Vault catalogue entry.')
        if not re.fullmatch('[0-9a-f-]{36}',entry['id']) or len(entry['title'])>200 or entry['kind'] not in ('login','token','note','recovery','other') or len(entry['origin'])>300:
            raise ValueError('Invalid Vault catalogue entry.')
        if entry['origin']:
            url=urlsplit(entry['origin'])
            if url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None or url.path or url.query or url.fragment:
                raise ValueError('Invalid catalogue service origin.')
        if query.casefold() in (entry['title']+' '+entry['origin']).casefold():
            rows.append(dict(entry,reference='vault:'+entry['id']))
    try: stale=hashlib.sha256(_read(root/'vault.kdbx',64*1024**2)).hexdigest()!=data['sha256']
    except FileNotFoundError: stale=True
    if stale: rows=[]  # A newer encrypted version may hide previously visible entries.
    return dict(enabled=True,entries=rows[offset:offset+20],next_offset=offset+20 if len(rows)>offset+20 else None,
                updated=data['updated'],stale=stale,requires_confirmation=True,secrets_available=False)
