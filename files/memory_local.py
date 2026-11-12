"""Optional local meaning search through Lumen's Rust service `lumen-memory`.

The model never loads in the UI/API process. The service keeps it loaded between questions and ends
itself after ten minutes without one. A missing, starting or failing service returns a visible text
fallback; the service goes on filling the vector cache in small steps between questions.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
if __package__:
    from .memory_core import eligible
    from .memory_embedding import MODEL_FILES
    from .memory_index import Index
else:
    from memory_core import eligible
    from memory_embedding import MODEL_FILES
    from memory_index import Index

MAX_INPUT = 16 * 1024 * 1024


def program():
    from lumen_office import program as find
    return find('lumen-memory', 'memory-search')


def availability(home):
    home = Path(home)
    if not all((home / 'model' / name).is_file() for name in MODEL_FILES):
        return False
    try:
        program()
    except ValueError:
        return False
    return True


def channel(home):
    """The service's private socket for this model folder."""
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or Path(home) / 'run')
    key = hashlib.sha256(str(Path(home).resolve()).encode()).hexdigest()[:16]
    return runtime / 'lumen-memory' / (key + '.sock')


def start(home):
    """Starts the service on its own; a second one would find the model lock taken and leave."""
    subprocess.Popen([program(), 'serve', str(home), str(channel(home)), MODEL_FILES['model.onnx'],
                      MODEL_FILES['tokenizer.json']], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ask(home, request, timeout=3):
    """One answer from the service, starting it when none listens. TimeoutError when it takes too long."""
    path, deadline, started = channel(home), time.monotonic() + timeout, False
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(max(.05, deadline - time.monotonic()))
                connection.connect(str(path))
                connection.sendall(request)
                connection.shutdown(socket.SHUT_WR)
                data = bytearray()
                while chunk := connection.recv(1 << 16):
                    data += chunk
                    if len(data) > 2 * MAX_INPUT:
                        raise ValueError('Memory search answer too large')
            return json.loads(data)
        except (FileNotFoundError, ConnectionRefusedError):
            if not started:
                start(home)
                started = True
            if time.monotonic() >= deadline:
                raise TimeoutError('Memory search service did not start') from None
            time.sleep(.05)


def invalidate(cache):
    """Drop vectors before a permission/forget operation can be observed as complete."""
    for path in Path(cache).glob('*.sqlite3'):
        index = Index(path)
        try:
            index.prepare([], 'revoked')
        finally:
            index.close()


def retrieve(entries, query, *, boundary, home, cache, project=''):
    try:
        result = _retrieve(entries, query, boundary=boundary, home=home, cache=cache, project=project)
    except (OSError, ValueError, sqlite3.Error):
        result = {'mode': 'text', 'reason': 'unavailable', 'scores': {}}
    if Path(cache).is_dir():
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=cache, delete=False) as stream:
                json.dump({k: v for k, v in result.items() if k not in ('scores','excerpts')}, stream)
            os.replace(stream.name, Path(cache) / 'status.json')
        except OSError:
            pass  # read-only/full cache still has a functional text fallback
    return result


def _retrieve(entries, query, *, boundary, home, cache, project=''):
    home, cache = Path(home), Path(cache)
    empty = {'mode': 'text', 'reason': 'not_installed', 'scores': {}}
    if not availability(home):
        return empty
    entries = eligible(entries, boundary, project)
    if not query.strip() or not entries:
        return dict(empty, reason='no_sources')
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256((boundary + '\0' + project).encode()).hexdigest()
    path = cache / (key + '.sqlite3')
    index = Index(path)
    try:
        index.prepare(entries, boundary, project)
    finally:
        index.close()
    request = json.dumps({'path': str(path), 'query': query[:6000],
                          'entries': [dict(id=e.id, revision=e.revision, title=e.title, text=e.text,
                                           digest=Index.digest(e)) for e in entries]}).encode()
    if len(request) > MAX_INPUT:
        return dict(empty, reason='capacity')
    try:
        result = ask(home, request)
        result['scores'] = {(identity, revision): score for identity, revision, score in result['scores']}
        result['excerpts'] = {(identity, revision): text for identity, revision, text in result.get('excerpts', [])}
        return result
    except TimeoutError:
        # A loading or busy service indexes on; this question uses the text search.
        index = Index(path)
        try:
            state = index.status()
            building = state['ready'] < state['total']
            return dict(state, mode='indexing' if building else 'text',
                        reason='indexing' if building else 'unavailable', scores={})
        finally:
            index.close()
    except (OSError, ValueError, KeyError):
        return dict(empty, reason='unavailable')
