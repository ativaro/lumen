"""Stable data-sync scopes; identity is verified online, AI grants stay separate."""
import hashlib
import json
from uuid import UUID
import lumen_connect as connector

_VERIFIED = object()


def identity(config, user):
    return dict(server=config['server'], user_id=str(UUID(user['id'])),
                device_id=str(UUID(user['device_id'])))


def key(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def scope(config, parts, legacy):
    bound = config.get('sync_binding')
    if bound is None:
        return legacy
    if not isinstance(bound, dict) or bound.get('version') not in (1, 2):
        raise ValueError('Invalid synchronization identity; reconnect in settings.')
    stamp = key([config['server'], config.get('device_id'), config.get('token'), bound])
    if config.get(_VERIFIED) != stamp:
        current = identity(config, connector.request(config, '/bridge/me'))
        # Version 1 bindings also stored the server's workspace_id; their scope keys below still hash it.
        expected = {k: v for k, v in bound.get('identity', {}).items() if k != 'workspace_id'} if bound['version'] == 1 else bound.get('identity')
        if current != expected or current['device_id'] != config.get('device_id'):
            raise ValueError('Synchronization account changed; review the connection in settings.')
        config[_VERIFIED] = stamp
    alias = bound.get('aliases', {}).get(key(parts))
    if alias is not None:
        if not isinstance(alias, str) or len(alias) != 64 or any(c not in '0123456789abcdef' for c in alias):
            raise ValueError('Invalid synchronization scope.')
        return alias
    return key([bound['identity'], parts])


def prepare(config, aliases):
    """Called only during pairing or explicit setup, before persisting connection."""
    current = identity(config, connector.request(config, '/bridge/me'))
    if current['device_id'] != config.get('device_id'):
        raise ValueError('Device identity mismatch.')
    if config.get('sync_binding'):
        scope(config, ['verify'], '0' * 64)
        return {k:v for k,v in config.items() if isinstance(k,str)}
    return dict(config, sync_binding=dict(version=2, identity=current,
                aliases={key(parts):value for parts,value in aliases}))
