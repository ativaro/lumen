"""Current paired identity and grants for server-only entry points."""
from uuid import UUID
import lumen_connect


def capabilities():
    """Run outside the GUI thread. An unreachable or changed binding grants nothing."""
    try:
        config = lumen_connect.read_config()
        from server_app_session import origin
        origin(config['server'])
        device = str(UUID(config['device_id']))
        if not isinstance(config['token'], str) or not config['token']:
            return frozenset()
        me = lumen_connect.request(config, '/bridge/me', timeout=2)
        grants = me.get('capabilities')
        if (str(UUID(me.get('id'))) != me.get('id') or me.get('device_id') != device
                or not isinstance(grants, list) or not all(isinstance(value, str) for value in grants)
                or lumen_connect.connection_scope(lumen_connect.read_config()) != lumen_connect.connection_scope(config)):
            return frozenset()
        return frozenset(grants)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return frozenset()


def visible(app, grants):
    from lumen_apps import SERVER_APPS
    from server_app_session import APPS
    return app not in SERVER_APPS or APPS[SERVER_APPS[app]][1] in grants
