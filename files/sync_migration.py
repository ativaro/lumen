"""Read-only identities from pre-account sync; never create a selectable context."""

import hashlib
import json
from urllib.parse import quote
from uuid import uuid4


def account_identity(value):
    """Ignore the old private storage ID when verifying the same account/device."""
    return {k: v for k, v in value.items() if k != 'workspace_id'}


def memory_scope(choice, connection, account, namespace):
    """Keep pending operations/cursors at their original key after identity migration."""
    if 'workspace_id' not in choice:
        return None
    expected = hashlib.sha256(json.dumps(
        [connection, account, choice['workspace_id'], namespace]).encode()).hexdigest()
    if (choice.get('connection'), choice.get('user_id'), choice.get('scope')) != (connection, account, expected):
        return None
    return expected


def note_target(book):
    from wissen_data import digest
    key = 'knowledge/sync-workspace/' + digest((str(book.root)+'\0'+str(book.identity)).encode())
    return book.store.setting(key, '')


def note_scope_parts(book):
    return ['notes', str(book.root), list(book.identity), note_target(book)]


def pending_notes(book, state, scanned):
    """Freeze only pre-migration unsent notes at their old target; new notes are personal."""
    if state.get('account_sync_migrated'):
        return scanned
    target = note_target(book)
    pending = state.setdefault('legacy_note_targets', {})
    if target:
        known = {v['path']: k for k, v in state['notes'].items() if v.get('path')}
        for index, note in enumerate(scanned['notes']):
            identity = note['note_id'] or known.get(note['path']) or str(uuid4())
            if not state['notes'].get(identity, {}).get('revision'):
                pending[identity] = target
                if not note['note_id']:
                    scanned['notes'][index] = book.write(note['path'], note['text'], note['hash'], note_id=identity)
    state['account_sync_migrated'] = True
    return scanned


def note_request(path, state):
    identity = path.rsplit('/', 1)[-1]
    legacy = state.get('legacy_note_targets', {}).get(identity)
    return path + '?workspace=' + quote(legacy) if legacy else path


def asset_target(identity, state):
    legacy = state.get('legacy_note_targets', {}).get(identity)
    return {'legacy': legacy} if legacy else {'note': identity} if state['notes'].get(identity, {}).get('revision') else {}


def asset_path(path, target):
    if target.get('legacy'):
        return path + '?workspace=' + quote(target['legacy'])
    if target.get('note'):
        return path + '?note=' + quote(target['note'])
    return path


def drive_path(path, root):
    if root and not root.get('folder'):
        from lumen_i18n import tr
        raise ValueError(tr('Alte Drive-Bindung pausiert: Bitte einen konkreten Serverordner verbinden. Lokale Dateien und ausstehende Übertragungen bleiben erhalten.'))
    return path


def drive_legacy_address(url):
    from uuid import UUID
    UUID(url.netloc)
    parts = url.path.strip('/').split('/') if url.path.strip('/') else []
    if not parts:
        return 'root', None
    if len(parts) == 1:
        return 'folder', str(UUID(parts[0]))
    if len(parts) == 3 and parts[0] == 'file' and parts[2]:
        return 'file', str(UUID(parts[1]))
    raise ValueError('Invalid legacy Drive address')


def transfer_legacy_target(value):
    return value.get('drive', {}).get('space')


def drive_upload_target(root, intent=None):
    # An old queued request must keep its original metadata for the server receipt.
    return (intent or {}).get('legacy_upload_target')


def migrate_drive_binding(root):
    if root.get('account_sync_migrated'):
        return
    legacy = root.get('workspace')
    if legacy:
        for entry in root['entries'].values():
            if entry.get('pending'):
                entry['pending']['legacy_upload_target'] = legacy
            elif entry.get('request_id'):
                entry['legacy_upload_target'] = legacy
    root['account_sync_migrated'] = True


def drive_upload_fields(fields, legacy):
    return dict(fields, workspace=legacy) if legacy else fields


def drive_receipt(root, intent):
    from uuid import UUID, uuid5
    if intent.get('transfer_id'):
        return intent['transfer_id']
    legacy = root.get('workspace')
    return str(uuid5(UUID(root['device']), legacy + ':' + intent['request_id'])) if legacy else None
