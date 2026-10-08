"""Optional, isolated local search worker. One model process per installation.

Indexing never loads a model in the UI/API process. Missing/busy/failed workers
return a visible text fallback; a bounded background pass fills the vector cache.
"""
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import time
if __package__:
    from .memory_core import Entry, eligible
    from .memory_index import Index
else:
    from memory_core import Entry, eligible
    from memory_index import Index

RAM_MIB = 500
MODEL_BYTES = 127535388
MAX_INPUT = 16 * 1024 * 1024


def availability(home):
    home = Path(home)
    return all((home / file).is_file() for file in ('env/bin/python', 'model/model.onnx', 'model/tokenizer.json'))


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
    payload = json.dumps({'entries': [asdict(e) for e in entries], 'query': query[:6000]}).encode()
    if len(payload) > MAX_INPUT:
        return dict(empty, reason='capacity')
    command = [str(home / 'env/bin/python'), str(Path(__file__).resolve()), str(home), str(path)]
    try:
        run = subprocess.run(command, input=payload, capture_output=True, timeout=3,
                             env=dict(os.environ, TOKENIZERS_PARALLELISM='false', OPENBLAS_NUM_THREADS='1'))
        if run.returncode:
            return dict(empty, reason='unavailable')
        result = json.loads(run.stdout)
        if result.pop('fill', False):
            fill(command, payload)
        result['scores'] = {(identity, revision): score for identity, revision, score in result['scores']}
        result['excerpts'] = {(identity, revision): text for identity, revision, text in result.get('excerpts',[])}
        return result
    except subprocess.TimeoutExpired:
        # Slow CPUs must still advance the index after the foreground budget expires.
        fill(command, payload)
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


def fill(command, payload):
    process = subprocess.Popen(command + ['fill'], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True,
                               env=dict(os.environ, TOKENIZERS_PARALLELISM='false', OPENBLAS_NUM_THREADS='1'))
    try:
        process.stdin.write(payload)
        process.stdin.close()
    except BrokenPipeError:
        pass  # another query already started the single model worker


def worker():
    from memory_embedding import Encoder
    request = json.loads(sys.stdin.buffer.read(MAX_INPUT + 1))
    home, path = Path(sys.argv[1]), Path(sys.argv[2])
    descriptor = os.open(home / 'model.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({'mode': 'text', 'reason': 'busy', 'scores': []}))
        os.close(descriptor)
        return
    index = Index(path)
    try:
        entries = [Entry(**row) for row in request['entries']]
        encoder = Encoder(home / 'model')
        fill = len(sys.argv) > 3
        deadline = time.monotonic() + 20
        while True:
            processed = index.advance(entries, encoder, chunks=128 if fill else 32)
            state = index.status()
            if not fill or not processed or state['ready'] == state['total'] or time.monotonic() >= deadline:
                break
        scores, positions = ({}, {}) if fill else index.scores(entries, request['query'], encoder)
        by_id = {(entry.id, entry.revision): entry for entry in entries}
        excerpts = []
        for key in sorted(scores, key=lambda key: (-scores[key],key))[:12]:
            if scores[key] >= .35:
                entry = by_id[key]
                excerpts.append([*key, encoder.excerpt(entry.title+'\n'+entry.text,positions[key])])
        print(json.dumps(dict(state, reason='', fill=not fill and state['mode'] == 'indexing',
                              scores=[[identity, revision, value] for (identity, revision), value in scores.items()],
                              excerpts=excerpts)))
    finally:
        index.close()
        # Keep the model lock until process exit, after native model/library teardown.
        # Releasing it here permits a second model while the first still occupies RAM.


if __name__ == '__main__':
    worker()
