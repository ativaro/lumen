"""Bounded, read-only inspection of the directory selected for a coding chat."""
import os
from itertools import islice
from pathlib import Path
import stat


def inspect_project(directory,command):
    root=Path(directory).resolve(strict=True)
    if not root.is_dir():raise ValueError('Der Projektordner ist nicht verfügbar.')
    try:
        command(['git','-C',str(root),'rev-parse','--is-inside-work-tree'],timeout=5,max_output=4096)
    except ValueError:
        with os.scandir(root) as scan:
            files=sorted(p.name for p in islice(scan,10000) if p.is_file(follow_symlinks=False) and not p.name.startswith('.'))[:1000]
        return {'branch':'','files':files,'diff':'','git':False}
    try:
        branch=command(['git','-C',str(root),'symbolic-ref','--short','HEAD'],timeout=5,max_output=4096).decode().strip()
    except ValueError:
        branch=command(['git','-C',str(root),'rev-parse','--short','HEAD'],timeout=5,max_output=4096).decode().strip()
    try:
        command(['git','-C',str(root),'rev-parse','--verify','HEAD'],timeout=5,max_output=4096);base=['HEAD']
    except ValueError:base=['--cached']
    raw=command(['git','-C',str(root),'ls-files','-z','--cached','--others','--exclude-standard','--','.'],timeout=5,max_output=1024*1024)
    files=list(dict.fromkeys(p.decode('utf-8',errors='replace') for p in raw.split(b'\0') if p))[:1000]
    diff=command(['git','--no-pager','-C',str(root),'diff','--no-ext-diff','--no-textconv',*base,'--','.'],timeout=5,max_output=2*1024*1024).decode('utf-8',errors='replace')
    return {'branch':branch,'files':files,'diff':diff,'git':True}


def source_text(directory,relative):
    from content_search import folder_fd
    relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.name:
        raise ValueError('Die Datei liegt außerhalb des Projektordners.')
    root=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent=handle=None
    try:
        parent=folder_fd(root,relative.parent)
        handle=os.open(relative.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        info=os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size>512*1024:
            raise ValueError('Die Datei ist kein begrenztes Textdokument.')
        data=os.read(handle,512*1024+1)
        if len(data)>512*1024 or b'\0' in data:raise ValueError('Die Datei ist kein begrenztes Textdokument.')
        return data.decode('utf-8')
    except UnicodeDecodeError:raise ValueError('Die Datei enthält keinen UTF-8-Text.') from None
    finally:
        if handle is not None:os.close(handle)
        if parent is not None:os.close(parent)
        os.close(root)
