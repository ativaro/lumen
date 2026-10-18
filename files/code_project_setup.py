"""Explicit project setup; Git receives argv and only a private empty destination."""
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit


def validate(value):
    kind=value['source']
    if kind not in ('folder','new','repo'):raise ValueError('Eine Projektquelle wählen.')
    raw=value['directory'].strip()
    if not raw:raise ValueError('Bitte einen Projektordner wählen.')
    path=Path(raw).expanduser()
    if not path.is_absolute():raise ValueError('Bitte einen absoluten Projektordner wählen.')
    if kind!='folder' and (path.exists() or path.is_symlink()):raise ValueError('Der Zielordner existiert bereits und wird nicht verändert.')
    path=path.resolve(strict=kind=='folder')
    if kind=='folder':
        if not path.is_dir():raise ValueError('Der Projektordner ist nicht verfügbar.')
    elif path.exists() or path.is_symlink():raise ValueError('Der Zielordner existiert bereits und wird nicht verändert.')
    elif not path.parent.is_dir():raise ValueError('Der übergeordnete Zielordner fehlt.')
    url=value.get('url','').strip();branch=value.get('branch','').strip()
    if kind=='repo':
        parts=urlsplit(url)
        https=parts.scheme=='https' and parts.hostname and not parts.username and not parts.password and parts.path not in ('','/') and not parts.query and not parts.fragment
        ssh=re.fullmatch(r'[a-zA-Z0-9_.-]+@[a-zA-Z0-9.-]+:[a-zA-Z0-9_./-]+',url)
        if len(url)>2048 or any(c.isspace() for c in url) or not (https or ssh):raise ValueError('Eine HTTPS- oder Git-SSH-Adresse ohne eingebettete Zugangsdaten wählen.')
        if branch and (not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_./-]{0,199}',branch) or '..' in branch or '@{' in branch):raise ValueError('Ungültiger Branchname.')
    return dict(source=kind,directory=str(path),url=url if kind=='repo' else '',branch=branch if kind=='repo' else '')


def prepare(value,job):
    value=validate(value);path=Path(value['directory'])
    if value['source']=='folder':return str(path)
    temporary=Path(tempfile.mkdtemp(prefix='.lumen-project-',dir=path.parent))
    try:
        if value['source']=='repo':
            args=['git','-c','core.hooksPath=/dev/null','-c','protocol.file.allow=never','-c','protocol.ext.allow=never','clone','--no-recurse-submodules']
            if value['branch']:args+=['--branch',value['branch']]
            args+=['--',value['url'],str(temporary)]
            environment=dict(os.environ,GIT_TERMINAL_PROMPT='0');job.command(args,timeout=300,max_output=65536,env=environment)
        job.check();validate(value)
        from drive_local import move
        info=path.parent.stat()
        move({'path':str(path.parent),'identity':[info.st_dev,info.st_ino],'native_names':True},temporary.name,path.name)
        return str(path)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
