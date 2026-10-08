"""Explicit local folders for existing project identities; no sharing or upload."""
from pathlib import Path
import time
from uuid import UUID, uuid4

from lumen_i18n import tr
from tools_data import Library


def catalog(store):
    folders = store.setting('memory/project-folders', {})
    return [dict(id=str(UUID(row['id'])), title=row['title'],
                 directory=folders.get(str(UUID(row['id'])), ''))
            for row in Library('workbench').all()]


def bindings(store):
    if not store.setting('memory/project-folders', {}):
        return {}
    # Called by the UI's context stamp too: do not stat potentially offline NAS paths here.
    return {'project:'+row['id']: row['directory'] for row in catalog(store)
            if row['directory']}


def scope(directory, folders):
    if not directory:
        return ''
    if directory.startswith('project:'):
        folder = folders.get(directory, '')
        if not folder or not Path(folder).is_dir() or str(Path(folder).resolve()) != folder:
            raise ValueError(tr('Projektordner nicht mehr zugeordnet oder erreichbar.'))
        return directory
    path = Path(directory).resolve()
    found = [key for key, folder in folders.items() if path.is_relative_to(folder)
             and Path(folder).is_dir() and str(Path(folder).resolve()) == folder]
    if len(found) > 1:
        raise ValueError(tr('Projektordner überschneiden sich. Bitte die Zuordnung prüfen.'))
    return found[0] if found else str(path)


def includes(value, directory, folders):
    if not value:
        return True
    if value.startswith('project:'):
        return value in folders and scope(directory, folders) == value
    root = Path(value)
    return root.is_absolute() and root.resolve() == root and Path(directory).resolve().is_relative_to(root)


def configure(memory, project, directory, expected, path='', revision=''):
    """CAS the folder choice; optional copy retains the original and starts unapproved."""
    project = str(UUID(project))
    with memory.book.lock('memory-state.lock'):
        choices = memory.store.setting('memory/project-folders', {})
        if choices != expected:
            raise ValueError(tr('Projektzuordnung wurde geändert. Bitte erneut öffnen.'))
        if project not in {row['id'] for row in catalog(memory.store)}:
            raise ValueError(tr('Projekt nicht mehr verfügbar.'))
        if directory:
            directory = str(Path(directory).expanduser().resolve(strict=True))
            if not Path(directory).is_dir():
                raise ValueError(tr('Bitte einen Projektordner auswählen.'))
            for key, folder in choices.items():
                if key != project and (Path(directory).is_relative_to(folder) or Path(folder).is_relative_to(directory)):
                    raise ValueError(tr('Projektordner überschneiden sich. Bitte die Zuordnung prüfen.'))
        note = None
        if path:
            if not directory:
                raise ValueError(tr('Bitte einen Projektordner auswählen.'))
            note = next((n for n in memory.scan()['notes'] if n['path'] == path), None)
            if not note or note['hash'] != revision or note['identity_conflict']:
                raise ValueError(tr('Erinnerung wurde geändert. Bitte erneut öffnen.'))
            if note['memory'].get('sync_conflict') or note['memory'].get('sync_blocked'):
                raise ValueError(tr('Zuerst den Gedächtniskonflikt lösen.'))
        choices = dict(choices)
        if directory:
            choices[project] = directory
        else:
            choices.pop(project, None)
        copied = None
        if note:
            identity = str(uuid4())
            target = 'project-'+identity+'.md'
            # No consent, remote binding or automatic-learning ownership is inherited.
            meta = dict(kind=note['memory'].get('kind', 'fact'), scope='project:'+project,
                        allowed=False, automatic=False,
                        created=time.time(), updated=time.time(),
                        copied_from=dict(id=note['id'], revision=note['hash']))
            # Persist restrictive metadata BEFORE creating a discoverable file.
            memory.save_record(dict(path=target, note_id=identity, hash=''), meta,
                               memory.store.setting('memory/records', {}))
            copied = memory.book.write(target, note['text'], '',
                                       tr('Kopie aus Lumen-Gedächtnis: {0}', note['id']), note_id=identity)
            meta['hash'] = copied['hash']
            copied = memory.save_record(copied, meta, memory.store.setting('memory/records', {}))
        memory.store.set_setting('memory/project-folders', choices)
        memory.changed(True)
        return dict(project=project, directory=directory, copied=copied)
