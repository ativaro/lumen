"""The views' binding to Lumen's memory in the desktop service (native/service/src/recall.rs, learning.rs).

The memory (its notebook, records, shares, project folders, stamp, context, learning and proposals) lives in
lumen-service; this module carries its `memory.*` requests (native/service/README.md) and keeps no memory
logic. Refusals arrive as the exceptions the earlier Python code raised (ValueError, OSError, UnicodeError).
"""
from lumen_i18n import tr
import os
from uuid import UUID

import lumen_service

# The kinds' names in the window's language (the service checks the kinds).
KINDS = {'preference': tr('Vorliebe'), 'fact': tr('Fakt'), 'decision': tr('Entscheidung'), 'solution': tr('Lösungsweg')}


def _ask(op, store, timeout=30, **values):
    answer = lumen_service.ask({'op': 'memory.' + op, 'store': str(store.directory) if store else '', 'env': dict(os.environ),
                                'texts': lumen_service.texts(), **values}, timeout=timeout)
    lumen_service.refused(answer)
    return answer['result']


def options(store):
    return _ask('options', store)


def stamp(store):
    return _ask('stamp', store)['stamp']


def server_stamp(store):
    """The stamp of the paired server's mirror of shared memories (`lumen_connect.memory_stamp` before)."""
    return _ask('stamp', store)['server']


def root(store):
    return store.directory / 'lumen-memory'


def model():
    """The meaning search's model: `version`, `files` (path → SHA-256) and the installation folder `home`."""
    return _ask('model', None)


def search_home():
    from pathlib import Path
    return Path(model()['home'])


def verify(home):
    """The mode a search on an empty index answers with the installed model (`hybrid` when it works)."""
    return _ask('verify', None, timeout=90, home=str(home))


def retrieval_status(store):
    return _ask('status', store)


def changed(store, invalidate=False):
    """The memory's revision counts up (with `invalidate` also the privacy revision, and the index forgets its
    rows); for callers that hold memory-state.lock themselves."""
    _ask('changed', store, invalidate=invalidate)


def worker(job, store, action, **values):
    job.check()
    return _ask(action, store, **values)


class Memory:
    def __init__(self, store):
        from wissen_data import Notebook
        self.store = store
        opened = _ask('open', store)
        self.namespace = UUID(opened['namespace'])
        self.book = Notebook(store, opened['root'], identity=opened['identity'])

    def _ask(self, op, **values):
        return _ask(op, self.store, **values)

    def identity(self, path):
        return self._ask('identity', path=path)

    def record(self, note):
        return self._ask('record', note=note)

    def shared(self, book, path):
        """Whether a note of the user's notebook `book` is shared with Lumen."""
        return self._ask('shared', path=path, root=str(book.root), identity=book.identity)

    def configure(self, enabled, learn, expected=None, solutions=None, automatic=None):
        return self._ask('configure', enabled=enabled, learn=learn, expected=expected, solutions=solutions, automatic=automatic)

    def scan(self):
        return self._ask('scan')

    def migrate(self, dry_run=True):
        return self._ask('migrate', dry_run=dry_run)

    def eligible(self, directory, query='', limit=100):
        return self._ask('eligible', directory=directory, query=query, limit=limit)

    def remember(self, title, text='', source=None, kind='fact', scope='', automatic=False, evidence='', path='', expected='', verification=''):
        return self._ask('remember', title=title, text=text, source=source, kind=kind, scope=scope, automatic=automatic,
                         evidence=evidence, path=path, expected=expected, verification=verification)

    def write(self, path, text, expected):
        return self._ask('write', path=path, text=text, expected=expected)

    def restore(self, key, expected):
        return self._ask('restore', key=key, expected=expected)

    def forget(self, path, expected):
        return self._ask('forget', path=path, expected=expected)

    def share(self, path, allow, directory=False):
        return self._ask('share', path=path, allow=allow, directory=directory)

    def allow(self, path, expected, allowed):
        return self._ask('allow', path=path, expected=expected, allowed=allowed)

    def prepare(self, query, directory):
        return self._ask('prepare', query=query, directory=directory)

    def valid_prepared(self, prepared):
        return self._ask('valid_prepared', prepared=prepared)

    def learn_account(self, text, prepared, event_id, context=None):
        return self._ask('learn_account', text=text, prepared=prepared, event_id=event_id, context=context)

    def account_learning_status(self, remote, task_id):
        return self._ask('account_learning_status', remote=remote, task_id=task_id)

    def apply(self, items, user_text, directory, source, candidates, revision, context=None, prepared_stamp=None):
        return self._ask('apply', items=items, user_text=user_text, directory=directory, source=source,
                         candidates=candidates, revision=revision, context=context, prepared_stamp=prepared_stamp)

    def propose(self, title, text, kind, directory, path='', expected='', operation='remember'):
        return self._ask('propose', title=title, text=text, kind=kind, directory=directory, path=path,
                         expected=expected, operation=operation)

    def proposals(self):
        return self._ask('proposals')

    def review(self, identity, accept):
        return self._ask('review', identity=identity, accept=accept)

    def project_info(self):
        return self._ask('project_info')

    def project_configure(self, **values):
        return self._ask('project_configure', **values)

    # The replication (memory_sync.py) changes the records under its own memory-state.lock.
    def changed(self, invalidate=False):
        changed(self.store, invalidate)

    def save_record(self, note, meta, records):
        return self._ask('save_record', note=note, meta=meta, records=records)
