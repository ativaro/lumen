"""Read-only identities from pre-account sync; never create a selectable context."""

import hashlib
import json


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


def require_current_upload(legacy):
    if legacy:
        from lumen_i18n import tr
        raise ValueError(tr('Alte Übertragung pausiert: Bitte die ursprüngliche Drive-Zuordnung mit Vorschau und konkretem Ordner umstellen. Kennung und lokale Dateien bleiben erhalten.'))


def pending_drive_uploads(root):
    for entry in root.get('entries', {}).values():
        pending = entry.get('pending', {})
        if entry.get('legacy_upload_target') or pending.get('legacy_upload_target'):
            return True
        if root.get('workspace') and not root.get('account_sync_migrated') and (pending or entry.get('request_id')):
            return True
    return False


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


def drive_receipt(intent):
    return intent.get('transfer_id')
