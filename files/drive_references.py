"""Original Drive references are bound to a server and user, never a device token."""
from urllib.parse import urlsplit
from uuid import UUID
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile
import fcntl
import stat
import signal

import drive_sync as sync
import lumen_connect
from lumen_i18n import tr

KINDS = ('drive_file', 'drive_folder')
MAX_COPY = 128 * 1024**2
READ_TIMEOUT = 35  # Leave cleanup time before the native dispatcher's 45-second hard limit.
TEXT_SUFFIXES = ('.txt','.md','.csv','.json','.log','.py','.js','.ts','.yaml','.yml','.toml','.xml','.html','.htm','.css')


def readable(row):
    suffix=Path(row['name']).suffix.lower()
    return suffix in TEXT_SUFFIXES and row.get('size',MAX_COPY)<=2*1024**2 or suffix in ('.pdf','.png','.jpg','.jpeg','.webp','.tif','.tiff') and row.get('size',MAX_COPY)<=MAX_COPY


class ContextLimit(ValueError):pass


def server_sources(references, job=None):
    """Ask the bound server about explicitly selected originals; never parse/copy."""
    refs = [validate(ref) for ref in references]
    if len(refs) > 20:
        raise ContextLimit(tr('Bitte höchstens 20 Drive-Einträge auswählen.'))
    config, rows = resolve(refs, job)
    capabilities = []
    for ref, row in zip(refs, rows):
        if job: job.check()
        if ref['kind'] != 'drive_file':
            capabilities.append(None)
            continue
        source = dict(kind='file', id=row['id'], revision=row['version'], mode='reference')
        value = lumen_connect.request(config, '/bridge/context/capability', source)
        if (not isinstance(value, dict) or any(value.get(key) != item for key,item in source.items())
                or type(value.get('revision')) is not int or type(value.get('supported')) is not bool
                or not isinstance(value.get('reason'), str) or len(value['reason']) > 4096):
            raise ValueError(tr('Der Server hat die gewählte Quelle nicht eindeutig bestätigt.'))
        capabilities.append(value)
    if sync.scope(lumen_connect.read_config()) != sync.scope(config):
        raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
    return config, rows, capabilities


def task_attachments(references, intent='open', context_bytes=0):
    config,rows,capabilities=server_sources(references)
    attachments=[]
    for ref,row,source in zip(references,rows,capabilities):
        if source and source['supported']:
            attachments.append(dict(kind='file',id=row['id'],revision=row['version'],mode='reference'))
        elif intent!='open':
            raise ContextLimit(source['reason'] if source and source['reason'] else tr('Diese Auswahl ist nur als Metadaten verfügbar.'))
    # Extracted characters and the combined source budget remain authoritative on the server.
    if context_bytes>60000:
        raise ContextLimit(tr('Die Auswahlbeschreibung überschreitet 60 KB. Bitte weniger Einträge auswählen.'))
    return config,attachments


def validate(ref):
    if not isinstance(ref,dict) or ref.get('app') != 'files' or ref.get('kind') not in KINDS or set(ref) != {'app', 'kind', 'id', 'title', 'locator'}:
        raise ValueError(tr('Ungültiger Drive-Verweis.'))
    locator = ref['locator']
    if not isinstance(locator, dict) or set(locator) != {'server', 'account'}:
        raise ValueError(tr('Ungültige Drive-Herkunft.'))
    if any(not isinstance(value,str) or len(value)>4096 or any(ord(c)<32 for c in value) for value in locator.values()):
        raise ValueError(tr('Ungültige Drive-Herkunft.'))
    server = urlsplit(locator['server'])
    if server.scheme != 'https' or not server.hostname or server.username or server.password or server.path or server.query or server.fragment:
        raise ValueError(tr('Ungültige Drive-Herkunft.'))
    try:
        valid=str(UUID(locator['account'])) == locator['account'] and str(UUID(ref['id'])) == ref['id']
    except (ValueError,TypeError,AttributeError):valid=False
    if not valid:
        raise ValueError(tr('Ungültige Drive-Kennung.'))
    if not isinstance(ref['title'], str) or not ref['title'] or len(ref['title']) > 4096 or '\0' in ref['title']:
        raise ValueError(tr('Ungültiger Drive-Name.'))
    return dict(ref, locator=dict(locator))


def capture(browser, paths):
    config = browser.config
    if not config or sync.scope(lumen_connect.read_config()) != sync.scope(config):
        raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
    account = str(UUID(browser.profile['id']))
    result = []
    for path in dict.fromkeys(paths):
        kind, row = browser.entries[path]
        result.append(validate(dict(app='files', kind='drive_' + kind,
            id=row['family'] if kind == 'file' else row['id'], title=row['name'],
            locator=dict(server=config['server'], account=account))))
    if not result:
        raise ValueError(tr('Zuerst eine Datei auswählen.'))
    return result


def resolve(references, job=None):
    refs = [validate(ref) for ref in references]
    if not refs:
        raise ValueError(tr('Zuerst eine Datei auswählen.'))
    config = lumen_connect.read_config()
    if any(ref['locator']['server'] != config['server'] for ref in refs):
        raise ValueError(tr('Dieser Drive-Verweis gehört zu einer anderen Serververbindung.'))
    if job: job.check()
    me = lumen_connect.request(config, '/bridge/me')
    if job: job.check()
    if any(ref['locator']['account'] != me['id'] for ref in refs):
        raise ValueError(tr('Dieser Drive-Verweis gehört zu einem anderen Konto.'))
    cache = sync.inventory(config, job=job)
    rows = []
    for ref in refs:
        if job: job.check()
        row = cache['files' if ref['kind'] == 'drive_file' else 'folders'].get(ref['id'])
        if not row or row['trashed']:
            raise ValueError(tr('Drive-Eintrag nicht mehr verfügbar oder nicht freigegeben.'))
        rows.append(row)
    if sync.scope(lumen_connect.read_config()) != sync.scope(config):
        raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
    return config, rows


def links(references, root=None):
    from interop_data import Registry
    registry = Registry(root)
    return [dict(kind='object', title=ref['title'], target=registry.register(ref)) for ref in references]


@contextmanager
def _copy_directory():
    cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'lumen-drive-handoffs'
    cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    if cache.is_symlink() or cache.stat().st_uid!=os.getuid() or cache.stat().st_mode&0o077:
        raise ValueError(tr('Der private Drive-Zwischenspeicher ist nicht sicher verfügbar.'))
    fd=os.open(cache/'copy.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError(tr('Ungültiger Drive-Zwischenspeicher.'))
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError(tr('Eine andere Drive-Übergabe läuft. Bitte danach erneut versuchen.')) from None
        # Holding the lock proves these private directories were left by an interrupted handoff.
        for path in cache.glob('copy-*'):
            if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
        with tempfile.TemporaryDirectory(prefix='copy-',dir=cache) as temp:yield temp
    finally:os.close(fd)


@contextmanager
def materialized(references, job):
    """A bounded private copy lives only for the explicitly invoked consumer."""
    import drive_local as local
    import drive_transport as transport
    from core import valid_name
    config, rows=resolve(references,job)
    if any(ref['kind']!='drive_file' for ref in references):
        raise ValueError(tr('Hier eine einzelne unterstützte Datei auswählen; Ordner werden nur verknüpft.'))
    if any(type(row['size']) is not int or row['size']<0 for row in rows) or sum(row['size'] for row in rows)>MAX_COPY:
        raise ValueError(tr('Die ausgewählte lokale Kopie darf höchstens 128 MiB groß sein.'))
    with _copy_directory() as temp:
        paths=[]
        for row in rows:
            job.check();folder=Path(temp)/str(UUID(row['id']));folder.mkdir(mode=0o700)
            info=folder.stat();root=dict(path=str(folder),identity=[info.st_dev,info.st_ino])
            name=valid_name(row['name'])
            staged=transport.download(config,root,row,lambda *_:job.check())
            local.install(root,name,staged,None)
            paths.append(str(folder/name))
        current, fresh=resolve(references,job)
        if sync.scope(current)!=sync.scope(config) or any((old['id'],old['revision'],old['sha256'])!=(new['id'],new['revision'],new['sha256']) for old,new in zip(rows,fresh)):
            raise ValueError(tr('Die Drive-Datei wurde während des Ladens geändert. Bitte erneut öffnen.'))
        job.check()
        yield paths


def read_reference(url, root=None):
    from tools_ui import Job
    job=Job(lambda _:None)
    def expired(*_):
        job.cancelled.set()
        raise ValueError(tr('Drive-Lesen hat zu lange gedauert. Bitte eine kleinere Datei auswählen oder später erneut versuchen.'))
    previous=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,READ_TIMEOUT)
    try:return _read_reference(url,root,job)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def _read_reference(url,root,job):
    from interop_data import Registry
    from tools_data import document_text
    registry=Registry(root);ref=validate(registry.resolve(url))
    config,rows=resolve([ref],job);row=rows[0]
    if ref['kind']=='drive_folder':
        cache=sync.inventory(config);children=[]
        parent_row=cache['folders'].get(ref['id'])
        if not parent_row or parent_row['trashed']:
            raise ValueError(tr('Drive-Eintrag nicht mehr verfügbar oder nicht freigegeben.'))
        if sync.scope(lumen_connect.read_config())!=sync.scope(config):
            raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
        for kind,records,parent in (('drive_file',cache['files'].values(),'folder_id'),('drive_folder',cache['folders'].values(),'parent_id')):
            for child in records:
                if not child['trashed'] and child[parent]==ref['id']:
                    original=dict(ref,kind=kind,id=child['family'] if kind=='drive_file' else child['id'],title=child['name'])
                    children.append(dict(name=child['name'],kind=kind,ref=registry.register(original)))
        import json
        if len(json.dumps(children).encode())>512*1024:raise ValueError(tr('Dieser Ordner enthält zu viele Einträge. Bitte einen Unterordner auswählen.'))
        if sync.scope(lumen_connect.read_config())!=sync.scope(config):
            raise ValueError(tr('Serververbindung geändert. Drive neu öffnen.'))
        return dict(source=ref,children=children)
    if not readable(row):raise ValueError(tr('Dieser Dateityp oder diese Dateigröße kann nicht als Lumen-Text gelesen werden.'))
    with materialized([ref],job) as paths:
        path=Path(paths[0])
        text=path.read_text(encoding='utf-8-sig') if path.suffix.lower() in TEXT_SUFFIXES else document_text(path,job)
        if len(text)>120000:raise ValueError(tr('Mehr als 120.000 Zeichen; bitte eine kleinere Datei auswählen.'))
        current,fresh=resolve([ref],job)
        if sync.scope(current)!=sync.scope(config) or any(row[key]!=fresh[0][key] for key in ('id','revision','sha256')):
            raise ValueError(tr('Die Drive-Datei wurde während des Ladens geändert. Bitte erneut öffnen.'))
        return dict(source=ref,text=text,content_is_untrusted=True)
