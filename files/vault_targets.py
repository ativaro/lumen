"""Paired HTTPS backup destination; persisted plans contain no access tokens."""
import base64
from contextlib import contextmanager
import ssl
import tempfile
import urllib.error
import urllib.request
from uuid import UUID, uuid4

import lumen_connect as connector
from lumen_i18n import tr, worker_environment


def connection(expected=None):
    try:
        config = connector.read_config()
        device = str(UUID(config['device_id']))
        token = config['backup_token']
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError(tr('Lumen Server zuerst unter Geräte mit diesem Desktop verbinden.')) from None
    target = dict(server=config['server'], device_id=device)
    if expected is not None and target != expected:
        if not isinstance(expected, dict) or expected.get('server') != config['server']:
            raise ValueError(tr('Dieser Sicherungsplan gehört zu einer anderen Server-Verbindung.'))
        try:
            for row in connector.request(config, '/bridge/backup-targets'):
                candidate = dict(server=config['server'], device_id=str(UUID(row['device_id'])))
                if candidate == expected:
                    return dict(config, device_id=candidate['device_id'], backup_token=row['backup_token'], recovery=True), candidate
        except (OSError, ValueError, KeyError, TypeError):
            pass
        raise ValueError(tr('Wiederherstellungszugang im Server erneut freigeben.'))
    return config, target


def repository(target):
    return 'rest:' + target['server'] + '/backup/' + target['device_id'] + '/'


def available():
    try:
        config, target = connection()
        rows = [dict(label='Lumen Server · ' + target['server'], server_target=target)]
        try:
            for value in connector.request(config, '/bridge/backup-targets'):
                rows.append(dict(label=tr('Wiederherstellen')+' · '+value['name'], server_target=dict(server=config['server'], device_id=str(UUID(value['device_id'])))))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return rows
    except ValueError:
        return []


def probe(expected):
    config, target = connection(expected)
    # Only a genuine 404 means a new repo. TLS/auth/offline errors must never initialize one.
    auth = base64.b64encode((target['device_id'] + ':' + config['backup_token']).encode()).decode()
    request = urllib.request.Request(repository(target)[5:] + 'config', method='HEAD', headers={'Authorization': 'Basic ' + auth})
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=connector.tls_context(config)), connector.NoRedirect())
        with opener.open(request, timeout=15):
            existing = True
    except urllib.error.HTTPError as error:
        error.close()
        if error.code != 404:
            raise ValueError(tr('Serverzugang abgelehnt. Verbindung und Gerätefreigabe prüfen.')) from None
        existing = False
    except (OSError, ValueError):
        raise ValueError(tr('Sicherungsserver nicht erreichbar oder Zertifikat ungültig.')) from None
    return dict(path=repository(target), server_target=target, existing=existing, tested=True)


def command(plan, password, args, job, program, timeout):
    config, target = connection(plan['server_target'])
    if config.get('recovery') and (not args or args[0] not in ('cat', 'snapshots', 'ls', 'dump', 'check', 'restore')):
        raise ValueError(tr('Dieser Zugang ist nur zum Wiederherstellen freigegeben.'))
    if plan['repository'] != repository(target):
        raise ValueError(tr('Sicherungsziel stimmt nicht mit dem gekoppelten Server überein.'))
    env = {k: v for k, v in worker_environment().items() if not k.startswith('RESTIC_')}
    env.update(RESTIC_REST_USERNAME=target['device_id'], RESTIC_REST_PASSWORD=config['backup_token'])
    # Restic uses Go's trust store; export exactly the CA set used by the native connector.
    # This file contains public certificates only, never the backup key or access token.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.crt', prefix='lumen-backup-ca-') as ca:
        for cert in connector.tls_context(config).get_ca_certs(binary_form=True):
            ca.write(ssl.DER_cert_to_PEM_cert(cert))
        ca.flush()
        try:
            return job.command([program, '--quiet', '--repo', plan['repository'], '--cacert', ca.name,
                                '--password-file', '/dev/stdin', '--json', *args],
                               data=(password+'\n').encode(), timeout=timeout,
                               max_output=32*1024**2, env=env).decode('utf-8')
        except ValueError:
            # Never forward server-controlled stderr to logs/the assistant: it could echo credentials.
            raise ValueError(tr('Serversicherung fehlgeschlagen. Verbindung, Freigabe, Sicherungsschlüssel und Speicherplatz prüfen.')) from None


def report_complete(plan):
    config, _ = connection(plan['server_target'])
    if config.get('recovery'): return
    connector.request(config, '/bridge/backup-complete', {})


@contextmanager
def activity(plan, action, full=False):
    if not plan.get('server_target') or action not in ('backup', 'check', 'restore'):
        yield
        return
    config, _ = connection(plan['server_target'])
    if config.get('recovery'):
        yield
        return
    body = dict(run=str(uuid4()), operation=action, state='running', full_check=full)
    def report(state, error=''):
        try: connector.request(config, '/bridge/backup-status', dict(body, state=state, error=error))
        except Exception: pass  # A status outage must not invalidate encrypted backup data.
    report('running')
    try:
        yield
    except Exception as error:
        from tools_data import Cancelled
        report('cancelled' if isinstance(error, Cancelled) else 'failed', 'client')
        raise
    else: report('completed')
