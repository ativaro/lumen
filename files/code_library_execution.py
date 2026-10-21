"""Collection actions reuse Lumen's task engine and workflow approvals."""
import os
from pathlib import Path
import stat
import tempfile
from code_library_contract import app_document


def directory(collection, item):
    selected = item['definition'].get('directory', '')
    if selected:
        path = Path(selected).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError('Der ausgewählte Projektordner ist nicht verfügbar.')
        return path
    path = collection.store.directory / 'code-work' / item['id']
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def prepare_run(collection, identity, user_input=''):
    from code_flow_native import unavailable
    unavailable()


def generated_html(collection, identity):
    item = collection.get(identity)
    if item['kind'] != 'app' or not item['last_task']:
        raise ValueError('Noch kein App-Auftrag vorhanden.')
    task = collection.store.task(item['last_task'])
    if task['status'] != 'completed':
        raise ValueError('Die App-Erstellung ist noch nicht erfolgreich abgeschlossen.')
    expected = Path(task['directory']).resolve()
    if expected.parent != (collection.store.directory/'code-work'/item['id']).resolve():
        raise ValueError('Der App-Auftrag gehört nicht zum erwarteten Ordner.')
    handle = os.open(expected / 'index.html', os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 262144:
            raise ValueError('Die App-Datei fehlt oder ist zu groß.')
        with os.fdopen(handle, 'rb', closefd=False) as stream:
            source = stream.read(262145)
        if len(source) > 262144:
            raise ValueError('Die App-Datei ist zu groß.')
        return source.decode('utf-8')
    finally:
        os.close(handle)


def preview_file(collection, identity):
    item = collection.get(identity)
    if item['archived'] or item['kind'] != 'app':
        raise ValueError('Diese App ist nicht verfügbar.')
    source = item['definition'].get('html', '')
    if not source.strip():
        raise ValueError('Bitte zuerst App-Inhalt hinterlegen oder den abgeschlossenen Auftrag übernehmen.')
    root = collection.store.directory / 'code-previews'
    root.mkdir(mode=0o700, exist_ok=True)
    target = root / (item['id'] + '.html')
    fd, temporary = tempfile.mkstemp(dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(app_document(source))
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    collection.used(identity)
    return target
