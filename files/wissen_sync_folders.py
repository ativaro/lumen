"""Collection metadata only; notes keep their existing CAS/history sync."""
import errno
import os
from pathlib import Path
from wissen_sync import ensure_folder


def finish(book, key, state):
    pending = state.get('folder_pending')
    if not pending:
        return []
    conflicts = []
    for name in pending['names']:
        ensure_folder(book, name)
    for name in sorted(pending['remove'], key=lambda n: (n.count('/'), n), reverse=True):
        path = book.relative(name + '/note.md').parent
        try:
            with book.directory(path.parent) as fd:
                os.rmdir(path.name, dir_fd=fd)
                os.fsync(fd)
        except FileNotFoundError:
            pass
        except OSError as error:
            if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                raise
            conflicts.append(name)
    scan = book.scan()
    if scan['limited'] or scan['errors']:
        raise ValueError('Collection scan incomplete; retry the sync.')
    state['folders'] = dict(local=scan['folders'], remote=pending['names'])
    del state['folder_pending']
    book.store.set_setting(key, state)
    return conflicts


def synchronize(book, request, key, state):
    conflicts = finish(book, key, state)
    scan = book.scan()
    if scan['limited'] or scan['errors']:
        raise ValueError('Collection scan incomplete; no folders removed.')
    local = set(scan['folders'])
    previous = state.get('folders', dict(local=[], remote=[]))
    remote = set(request('/bridge/note-collections')['names'])
    additions = local - set(previous['local'])
    removals = set(previous['local']) - local
    desired = (remote - removals) | additions
    result = request('/bridge/note-collections', dict(before=sorted(remote), after=sorted(desired)))
    if not result['applied']:
        raise ValueError('Collections changed on the server; retry the sync.')
    names = result['names']
    for name in names:
        book.relative(name + '/note.md')
        if Path(name).parts[0] == 'attachments':
            raise ValueError('Invalid collection path.')
    state['folder_pending'] = dict(names=names, remove=sorted(set(previous['remote']) - set(names) - additions))
    book.store.set_setting(key, state)
    return conflicts + finish(book, key, state)
