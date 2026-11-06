"""Retired Notes replica entry points; shared memory/asset helpers stay available."""
import json
import os
from pathlib import Path
from lumen_i18n import tr


def remote_text(row):
    title=' '.join(row['title'].split())
    from notes_structure import document_parts
    prefix, _old_title, gap, suffix, _found = document_parts(row['body'], title)
    return prefix+'# '+title+gap+suffix



def ensure_folder(book,path):
    parent=Path('.')
    for part in Path(path).parts:
        if part=='.':continue
        with book.directory(parent) as fd:
            try:os.mkdir(part,mode=0o700,dir_fd=fd);os.fsync(fd)
            except FileExistsError:pass
        parent=parent/part
        with book.directory(parent):pass



def retired():
    return dict(enabled=False, reason='server_owned')


def sync_config(book, expected, enabled, attachments=None):
    if enabled: raise ValueError(tr('Lumen Notes wird direkt auf dem Lumen Server bearbeitet. Ein lokaler Notizabgleich ist nicht mehr verfügbar.'))
    return retired()


def enabled(book):
    return False


def sync_info(book):
    return dict(retired(), attachments=False, scope='', server='', user='', allowed=False, reachable=False, last_sync=0)


def sync(book):
    raise ValueError(tr('Lumen Notes wird direkt auf dem Lumen Server bearbeitet. Lokale Originale bleiben erhalten.'))


def background(store):
    # Old connector copies still launch this installed helper; never reopen their replica.
    return retired()


if __name__ == '__main__':
    print(json.dumps(retired()))
