"""Inactive native adapter: one reviewed file copy into an existing Drive folder.

Only call prepare after review acceptance. Persisted Registry choice is the intent;
apply/retry uses its same request ID. No UI action or automatic upload is installed.
Local source/provenance stays native and is never part of the upload wire metadata.
"""
from pathlib import Path
from uuid import UUID
import json

import drive_references as drive
import drive_transport as transport
from drive_transfers import checksum
from drive_local import relative
from transfer_copy import root as source_root
from interop_data import Registry, validate_ref
from interop_sources import from_paths
from lumen_i18n import tr

ACTION = 'files.drive_import'
RECEIPT_FIELDS = ('id','family','version','revision','sha256','size','name','folder_id')


def _request(registry, token):
    value = registry.request(token)
    if value['target'] != 'files' or value['action'] != ACTION:
        raise ValueError(tr('Diese Übergabe ist keine bestätigte Drive-Übernahme.'))
    payload = value['payload']
    if (len(payload.get('paths', [])) != 1 or payload.get('references') or payload.get('text')
            or registry.resolve(payload.get('source_url', '')) != payload.get('source')):
        raise ValueError(tr('Genau eine lokale Datei mit bekanntem Rückweg auswählen.'))
    return value


def _same_connection(config):
    if drive.sync.scope(drive.lumen_connect.read_config()) != drive.sync.scope(config):
        raise ValueError(tr('Serververbindung geändert. Die bestehende Übernahme zuerst prüfen.'))


def _save_choice(registry, token, saved, choice, state):
    value = json.dumps(choice, allow_nan=False)
    if len(value) > 8192:
        raise ValueError(tr('Übergabeauswahl zu groß.'))
    # Bind intent and confirmed receipt atomically within the existing handoff store.
    with registry.library.connect() as db:
        changed = db.execute('UPDATE handoffs SET choice=? WHERE id=? AND state=? AND choice=?',
                             (value,token,state,json.dumps(saved,allow_nan=False))).rowcount
    if changed != 1:
        raise ValueError(tr('Die bestätigte Auswahl wurde gleichzeitig geändert. Bitte erneut prüfen.'))


def _destination(ref, device=None, revision=None):
    ref = drive.validate(ref)
    if ref['kind'] != 'drive_folder':
        raise ValueError(tr('Einen vorhandenen Drive-Zielordner auswählen.'))
    config, rows = drive.resolve([ref])
    row = rows[0]
    profile = drive.lumen_connect.request(config, '/bridge/me')
    current = str(UUID(profile['device_id']))
    if (profile['id'] != ref['locator']['account'] or device is not None and current != device
            or row.get('can_write') is not True or row.get('name') != ref['title']
            or type(row.get('revision')) is not int or row['revision'] < 1
            or revision is not None and row['revision'] != revision):
        raise ValueError(tr('Konto, Gerät oder bestätigter Zielordner wurde geändert oder entzogen.'))
    _same_connection(config)
    return config, current, row['revision']


def prepare(token, choice, destination, job, *, root=None):
    """Reuse the accepted id/title/mode/due/token review choice, without uploading."""
    if choice is None:
        return None
    registry = Registry(root)
    request = _request(registry, token)
    destination = drive.validate(destination)
    if (not isinstance(choice, dict) or set(choice) != {'id','title','mode','due','token'}
            or choice['mode'] != 'copy' or choice['token'] != token
            or choice['id'] != destination['id'] or choice['due']):
        raise ValueError(tr('Die Dateiübernahme muss als eigenständige Kopie bestätigt werden.'))
    if not isinstance(choice['title'],str) or not 1 <= len(choice['title']) <= 200:
        raise ValueError(tr('Einen einzelnen Dateinamen bestätigen.'))
    name = str(relative(choice['title']))
    if not name or Path(name).name != name or name == '.':
        raise ValueError(tr('Einen einzelnen Dateinamen bestätigen.'))
    saved = request['choice']
    if 'drive_import' in saved:
        if ({k:v for k,v in saved.items() if k not in ('drive_import','drive_import_receipt')} != choice
                or saved['drive_import']['destination'] != destination):
            raise ValueError(tr('Diese Anfrage ist bereits an eine andere Auswahl gebunden.'))
        return saved['drive_import']
    if request['state'] != 'pending':
        raise ValueError(tr('Diese Übergabe wird bereits bearbeitet.'))
    job.check()
    payload = request['payload']
    captured = from_paths(payload['paths'])
    if captured['source'] != payload['source'] or captured['items'][0]['directory']:
        raise ValueError(tr('Die bestätigte lokale Quelldatei wurde geändert.'))
    config, device, revision = _destination(destination)
    path = Path(payload['paths'][0])
    origin = source_root(path.parent, native_names=True)
    digest, stamp = checksum(origin, path.name, lambda *_:job.check())
    _same_connection(config)
    job.check()
    plan = dict(version=1, request_id=str(UUID(token)), destination=destination,
                device_id=device, destination_revision=revision, name=name,
                root=origin, path=path.name, sha256=digest, stamp=stamp)
    _save_choice(registry, token, saved, dict(choice, drive_import=plan), 'pending')
    return plan


def _source(plan, request, job):
    expected = Path(request['payload']['paths'][0])
    if (type(plan.get('version')) is not int or plan['version'] != 1 or plan['request_id'] != str(UUID(request['id']))
            or Path(plan['root']['path']) / plan['path'] != expected
            or plan['path'] != expected.name or plan['name'] != request['choice']['title']
            or plan['destination']['id'] != request['choice']['id']):
        raise ValueError(tr('Die gespeicherte Übernahme passt nicht zur bestätigten Auswahl.'))
    digest, stamp = checksum(plan['root'], plan['path'], lambda *_:job.check())
    if digest != plan['sha256'] or stamp != plan['stamp']:
        raise ValueError(tr('Quelldatei wurde verändert. Die bestehende Übernahme zuerst prüfen.'))


def _result(request, ref, row):
    if any(type(row.get(key)) is not int or row[key] < 1 for key in ('version','revision')):
        raise ValueError(tr('Ungültiger Drive-Versionsbeleg.'))
    return dict(action='upload', request_id=str(UUID(request['id'])), reference=drive.validate(ref),
                resolved=dict(id=str(UUID(row['id'])), version=row['version'], revision=row['revision']),
                source=validate_ref(request['payload']['source']), return_to=request['payload']['source_url'])


def _receipt(row, plan):
    if (any(type(row.get(key)) is not int or row[key] < 1 for key in ('version','revision'))
            or type(row.get('size')) is not int or row['size'] != plan['stamp'][2]
            or row.get('sha256') != plan['sha256'] or row.get('name') != plan['name']
            or row.get('folder_id') != plan['destination']['id']
            or row.get('trashed') is not False or row.get('current') is not True):
        raise ValueError(tr('Die Drive-Fassung entspricht nicht mehr der bestätigten Übernahme.'))
    return {key:row[key] for key in RECEIPT_FIELDS}


def apply(token, job, *, root=None):
    """An uncertain response leaves the same durable intent pending for explicit retry."""
    registry = Registry(root)
    request = _request(registry, token)
    plan = request['choice'].get('drive_import')
    if not plan:
        raise ValueError(tr('Die lokale Dateiübernahme zuerst ausdrücklich bestätigen.'))
    job.check()
    if request['state'] == 'done':
        ref = registry.resolve(request['result'])
        config, rows = drive.resolve([ref], job)
        if (_receipt(rows[0], plan) != request['choice'].get('drive_import_receipt')
                or ref['kind'] != 'drive_file' or ref['id'] != rows[0]['family']
                or ref['locator'] != plan['destination']['locator'] or ref['title'] != plan['name']):
            raise ValueError(tr('Die Drive-Fassung wurde seit der bestätigten Übernahme geändert.'))
        _same_connection(config)
        return _result(request, ref, rows[0])
    request = registry.claim(token, 'files')
    try:
        plan = request['choice']['drive_import']
        _source(plan, request, job)
        config, _, _ = _destination(plan['destination'], plan['device_id'], plan['destination_revision'])
        def progress(*_):
            job.check()
            _same_connection(config)
        acknowledgement = []
        def remember(value):
            if not isinstance(value,str) or str(UUID(value)) != value:
                raise ValueError(tr('Ungültiger Drive-Übertragungsbeleg.'))
            acknowledgement.append(value)
            progress()
        progress()
        row = transport.upload(config, plan['root'], plan['path'], plan['destination']['id'],
                               plan['request_id'], plan['sha256'], filename=plan['name'], progress=progress, remember=remember)
        progress()
        _destination(plan['destination'], plan['device_id'], plan['destination_revision'])
        _source(plan, request, job)
        if acknowledgement != [row.get('id')]:
            raise ValueError(tr('Der Server hat die bestätigte Dateiübernahme nicht eindeutig bestätigt.'))
        receipt = _receipt(row, plan)
        if request['choice'].get('drive_import_receipt',receipt) != receipt:
            raise ValueError(tr('Die Drive-Fassung wurde seit der bestätigten Übernahme geändert.'))
        ref = drive.validate(dict(app='files', kind='drive_file', id=row['family'], title=row['name'],
                                  locator=dict(plan['destination']['locator'])))
        _, fresh = drive.resolve([ref], job)
        if _receipt(fresh[0], plan) != receipt:
            raise ValueError(tr('Die Drive-Fassung wurde inzwischen geändert oder entzogen.'))
        progress()
        result = _result(request, ref, row)
        _save_choice(registry, token, request['choice'], dict(request['choice'], drive_import_receipt=receipt), 'applying')
        registry.finish(token, registry.register(ref))
        return result
    except Exception:
        registry.release(token, tr('Übernahme nicht bestätigt. Mit derselben Anfrage erneut prüfen.'))
        raise
