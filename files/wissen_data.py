"""Lumen Notes' notebook through the desktop service: the notebook core (file format, revisions,
locks, history, drafts, scans, the import of old memories) is `native/service/src/notebook.rs`;
this module carries its requests (`notes.*`, native/service/README.md) and keeps no format logic.
Refusals arrive as the exceptions the earlier Python core raised (ValueError, OSError and its
subclasses, UnicodeError). Picture work stays here, in a worker process: PIL makes the PNG of an
imported picture and the previews, the service reads and writes the files."""
from lumen_i18n import tr, language
from contextlib import contextmanager
import base64
import fcntl
import gzip
import io
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import lumen_service
from tools_data import Library

MAX_NOTE = 1024 * 1024
MAX_RESULT = 256 * 1024 ** 2
# The answers of a scan and of a context carry note texts: up to 128 MiB, escaped as JSON.
MAX_ANSWER = 2 * MAX_RESULT
# Answered by the service; the others run their Python modules in a worker process, as before.
SERVICE = {'activate', 'scan', 'read', 'write', 'create', 'create_collection', 'remove', 'versions', 'restore', 'capture', 'context'}


def _texts():
    return dict(language=language(), catalogue=str(Path(__file__).with_name('translations') / 'en'))


def _place(root):
    return str(Path(root).expanduser().absolute()) if root else None


def _ask(op, payload=b'', **values):
    answer = lumen_service.ask({'op': 'notes.' + op, 'texts': _texts(), **values}, timeout=60, limit=MAX_ANSWER, payload=payload)
    lumen_service.refused(answer)
    return answer


def parse(path, raw):
    return _ask('parse', path=str(path), raw=base64.b64encode(raw).decode())


def excerpt(text, query, limit=3000):
    return _ask('excerpt', text=text, query=query, limit=limit)['text']


class Notebook:
    def __init__(self, store, root=None, create=False, identity=None):
        self.store = store
        answer = _ask('open', store=str(store.directory), root=_place(root), create=create, identity=identity)
        self.root = Path(answer['root'])
        self.identity = answer['identity']
        self.history = Library('wissen-history', store.directory)

    def _ask(self, op, payload=b'', **values):
        return _ask(op, payload, store=str(self.store.directory), root=str(self.root), identity=self.identity, **values)

    @contextmanager
    def lock(self, name='wissen.lock'):
        """The lock files the service takes too: wissen.lock for every write, others for longer steps."""
        fd = os.open(self.store.directory / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def relative(self, path):
        self._ask('relative', path=str(path))
        return Path(path)

    def stat(self, path, folder=False):
        """`(st_dev, st_ino)` of a folder below the root, or of an entry without following a link;
        None when the entry does not exist."""
        value = self._ask('stat', path=str(path), folder=folder)['stat']
        return tuple(value) if value else None

    def raw(self, path):
        return base64.b64decode(self._ask('raw', path=str(path))['raw'])

    def read(self, path):
        return self._ask('read', path=str(path))

    def image(self, path):
        return base64.b64decode(self._ask('image', path=str(path))['raw'])

    def context(self, paths, query):
        return self._ask('context', paths=list(paths), query=query)['notes']

    def scan(self, known=None, migrate=False):
        values = {} if known is None else dict(known={p: [v[0], repr(v[1])] for p, v in known.items()})
        return self._ask('scan', migrate=migrate, **values)

    def write(self, path, text, expected, source=None, legacy=None, created=None, note_id=None):
        return self._ask('write', path=str(path), text=text, expected=expected, source=source, legacy=legacy, created=created, note_id=note_id)

    def replace(self, path, before, after):
        """One note's bytes replaced after checking `before`; the earlier bytes go to the history."""
        self._ask('replace', path=str(path), before=base64.b64encode(before).decode(), after=base64.b64encode(after).decode())

    def create(self, title, text='', source='', legacy='', folder='.', note_id=''):
        return self._ask('create', title=title, text=text, source=source, legacy=legacy, folder=str(folder), note_id=note_id)

    def create_collection(self, name):
        return self._ask('create_collection', name=name)['name']

    def rename_collection(self, source, target):
        from notes_move import plan, execute
        return execute(self, plan(self, source, target))['path']

    def remove(self, path, expected):
        return self._ask('remove', path=str(path), expected=expected)['key']

    def versions(self, path=None):
        return self._ask('versions', path=path)['versions']

    def restore(self, key, expected):
        return self._ask('restore', key=key, expected=expected)

    def capture(self, title, text, source='', memory=None):
        return self._ask('capture', title=title, text=text, source=source, memory=memory)['path']

    def memory_path(self, memory):
        return self._ask('memory_path', memory=memory)['path']

    def migrate(self):
        return self._ask('migrate')['changed']

    def add_image(self, path):
        from PIL import Image, ImageOps
        source = Path(path)
        if source.stat().st_size > 20 * 1024 ** 2: raise ValueError(tr('Bild größer als 20 MiB.'))
        with Image.open(source) as image:
            if image.width * image.height > 36_000_000: raise ValueError(tr('Bild größer als 36 Megapixel.'))
            image = ImageOps.exif_transpose(image); image.thumbnail((2400, 2400)); image = image.convert('RGBA')
            output = io.BytesIO(); image.save(output, format='PNG')
        png = output.getvalue()
        return self._ask('attach', payload=png, size=len(png))['path']

    def preview(self, path, text):
        from PIL import Image, ImageOps
        images = {}; total = 0
        for target in re.findall(r'!\[[^\]\n]*\]\(([^)\n]+)\)', text)[:16]:
            target = unquote(target)
            if urlsplit(target).scheme or target.startswith('/'): continue
            relative = os.path.normpath(str(Path(path).parent / target))
            try:
                raw = self.image(relative)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > 36_000_000: continue
                    image = ImageOps.exif_transpose(image); image.thumbnail((1600, 1600)); output = io.BytesIO(); image.convert('RGBA').save(output, format='PNG')
                    encoded = base64.b64encode(output.getvalue()).decode(); total += len(encoded)
                    if total > 16 * 1024 ** 2: break
                    images[relative] = encoded
            except (OSError, ValueError): continue
        return images


def activate(store, root=None):
    return _ask('activate', store=str(store.directory), root=_place(root))['root']


def draft(store, root, path, text=None, expected=''):
    return _ask('draft', store=str(store.directory), root=str(root), path=path, text=text, expected=expected)['draft']


def clear_draft(store, root, path):
    _ask('clear_draft', store=str(store.directory), root=str(root), path=path)


def worker(job, store, action, root=None, **values):
    if action in SERVICE:
        job.check()
        if action == 'activate': return activate(store, root)
        book = Notebook(store, root, identity=values.pop('identity', None))
        if action == 'scan': return book.scan(values.get('known'), migrate=True)
        return getattr(book, action)(**values)
    request = dict(store=str(store.directory), root=root, action=action, _compressed=True, **values)
    output = job.command([sys.executable, str(Path(__file__))], data=json.dumps(request).encode(), timeout=60, max_output=40 * 1024 ** 2)
    with gzip.GzipFile(fileobj=io.BytesIO(output)) as stream: result = stream.read(MAX_RESULT + 1)
    if len(result) > MAX_RESULT: raise ValueError(tr('Verarbeitungsergebnis zu groß.'))
    return json.loads(result)


def main():
    from lumen_store import Store
    request = json.load(sys.stdin); compressed = request.pop('_compressed', False); store = Store(request.pop('store')); action = request.pop('action'); root = request.pop('root')
    if action in ('save_memory', 'memories', 'delete_memory'): result = getattr(store, action)(**request)
    else:
        book = Notebook(store, root, identity=request.pop('identity', None))
        if action.startswith('move_'):
            import notes_move
            result = {'move_plan': notes_move.plan, 'move_apply': notes_move.execute, 'move_resume': notes_move.execute, 'move_undo': notes_move.undo}[action](book, **request)
        elif action in ('daily', 'from_template'):
            import notes_capture
            result = getattr(notes_capture, action)(book, **request)
        elif action in ('plan_tags', 'apply_tags'):
            import note_tag_actions
            result = getattr(note_tag_actions, 'plan' if action == 'plan_tags' else 'apply')(book, **request)
        elif action in ('sync_info', 'sync_config', 'sync'):
            import wissen_sync
            result = getattr(wissen_sync, action)(book, **request)
            if action == 'sync': result['scan'] = book.scan()
        elif action in ('rename_collection', 'add_image', 'preview'): result = getattr(book, action)(**request)
        else: raise ValueError(tr('Unbekannte Notizaktion.'))
    if compressed:
        with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', compresslevel=1) as stream:
            # ASCII escapes keep the entire transport buffer from widening for one emoji.
            for chunk in json.JSONEncoder(ensure_ascii=True).iterencode(result): stream.write(chunk.encode())
    else: print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception as error: print(str(error), file=sys.stderr); sys.exit(1)
